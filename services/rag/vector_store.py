"""SQLite-backed vector store for BGE-M3 RAG chunks."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np

from services.rag.embeddings import get_embedding_dim, get_embedding_model_name

ROOT = Path(__file__).parent.parent.parent
VECTOR_DB_PATH = ROOT / "data" / "rag_vectors.db"


def _get_conn() -> sqlite3.Connection:
    VECTOR_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(VECTOR_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_vector_store():
    """Create or migrate tables."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS rag_chunks (
            chunk_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL DEFAULT '',
            ticker TEXT DEFAULT '',
            industry TEXT DEFAULT '',
            content TEXT NOT NULL,
            metadata_json TEXT DEFAULT '{}',
            vector_json TEXT DEFAULT '[]',
            generated_at TEXT NOT NULL DEFAULT '',
            ttl_hours INTEGER DEFAULT 168
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_source ON rag_chunks(source_type);
        CREATE INDEX IF NOT EXISTS idx_chunks_ticker ON rag_chunks(ticker);
        CREATE INDEX IF NOT EXISTS idx_chunks_industry ON rag_chunks(industry);
    """)
    _ensure_column(conn, "rag_chunks", "vector_blob", "BLOB")
    _ensure_column(conn, "rag_chunks", "vector_dim", "INTEGER DEFAULT 0")
    _ensure_column(conn, "rag_chunks", "vector_model", "TEXT DEFAULT ''")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_model ON rag_chunks(vector_model, vector_dim)"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rag_retrieval_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_text TEXT NOT NULL,
            mode TEXT NOT NULL,
            hit_count INTEGER DEFAULT 0,
            top_scores TEXT DEFAULT '[]',
            queries_used TEXT DEFAULT '[]',
            source_types TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()


def _serialize_vector_json(vec: np.ndarray) -> str:
    return json.dumps(np.asarray(vec, dtype=np.float32).tolist())


def _vector_to_blob(vec: np.ndarray) -> bytes:
    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    return arr.tobytes()


def _deserialize_vector(row: sqlite3.Row, expected_dim: int) -> np.ndarray:
    blob = row["vector_blob"] if "vector_blob" in row.keys() else None
    if blob:
        vec = np.frombuffer(blob, dtype=np.float32)
        if vec.shape[0] == expected_dim:
            return vec.copy()

    json_str = row["vector_json"] if "vector_json" in row.keys() else ""
    try:
        data = json.loads(json_str or "[]")
    except (json.JSONDecodeError, TypeError):
        return np.zeros(expected_dim, dtype=np.float32)

    if not data:
        return np.zeros(expected_dim, dtype=np.float32)

    # Backward compatibility with old sparse TF-IDF vectors. These are only
    # used if a caller explicitly searches with that same dimension.
    if isinstance(data[0], (list, tuple)):
        vec = np.zeros(expected_dim, dtype=np.float32)
        for idx, val in data:
            if 0 <= int(idx) < expected_dim:
                vec[int(idx)] = float(val)
        return vec

    vec = np.asarray(data, dtype=np.float32)
    if vec.shape[0] != expected_dim:
        return np.zeros(expected_dim, dtype=np.float32)
    return vec


def upsert_chunk(
    chunk_id: str,
    content: str,
    vector: np.ndarray,
    source_type: str = "",
    ticker: str = "",
    industry: str = "",
    metadata: dict | None = None,
    ttl_hours: int = 168,
    generated_at: str = "",
    vector_model: str | None = None,
) -> None:
    """Insert or update a chunk and its BGE-M3 vector."""
    init_vector_store()
    from datetime import datetime

    if not generated_at:
        generated_at = datetime.now().isoformat()

    arr = np.asarray(vector, dtype=np.float32).reshape(-1)
    model_name = vector_model or get_embedding_model_name()
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO rag_chunks
           (chunk_id, source_type, ticker, industry, content, metadata_json,
            vector_json, vector_blob, vector_dim, vector_model, generated_at, ttl_hours)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            chunk_id,
            source_type,
            ticker,
            industry,
            content,
            metadata_json,
            _serialize_vector_json(arr),
            _vector_to_blob(arr),
            int(arr.shape[0]),
            model_name,
            generated_at,
            ttl_hours,
        ),
    )
    conn.commit()
    conn.close()


def search(
    query_vector: np.ndarray,
    top_k: int = 5,
    source_types: list[str] | None = None,
    ticker: str | None = None,
    industry: str | None = None,
    min_score: float = 0.05,
    vector_model: str | None = None,
) -> list[dict]:
    """Search chunks by cosine similarity with metadata filtering."""
    from services.rag.embeddings import cosine_similarity

    init_vector_store()
    model_name = vector_model or get_embedding_model_name()
    expected_dim = len(query_vector)

    where_clauses = ["vector_model = ?", "vector_dim = ?"]
    params: list[object] = [model_name, expected_dim]

    if source_types:
        placeholders = ",".join("?" * len(source_types))
        where_clauses.append(f"source_type IN ({placeholders})")
        params.extend(source_types)
    if ticker:
        where_clauses.append("ticker = ?")
        params.append(ticker)
    if industry:
        where_clauses.append("industry = ?")
        params.append(industry)

    conn = _get_conn()
    rows = conn.execute(
        f"""SELECT chunk_id, source_type, ticker, industry, content, metadata_json,
                   generated_at, vector_json, vector_blob
            FROM rag_chunks
            WHERE {' AND '.join(where_clauses)}""",
        params,
    ).fetchall()
    conn.close()

    if not rows:
        return []

    vectors = [_deserialize_vector(row, expected_dim) for row in rows]
    doc_matrix = np.vstack(vectors).astype(np.float32)
    scores = cosine_similarity(query_vector, doc_matrix)
    ranked_indices = np.argsort(scores)[::-1]

    results = []
    for idx in ranked_indices:
        score = float(scores[idx])
        if score < min_score:
            continue
        chunk = dict(rows[idx])
        chunk["score"] = round(score, 4)
        chunk.pop("vector_json", None)
        chunk.pop("vector_blob", None)
        results.append(chunk)
        if len(results) >= top_k:
            break
    return results


def get_chunk(chunk_id: str) -> dict | None:
    init_vector_store()
    conn = _get_conn()
    row = conn.execute(
        """SELECT chunk_id, source_type, ticker, industry, content, metadata_json,
                  generated_at, ttl_hours, vector_dim, vector_model
           FROM rag_chunks WHERE chunk_id = ?""",
        (chunk_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def chunk_is_current(chunk_id: str, model_name: str | None = None, dim: int | None = None) -> bool:
    """Return True when an existing chunk uses the active embedding model."""
    model_name = model_name or get_embedding_model_name()
    dim = dim or get_embedding_dim()
    row = get_chunk(chunk_id)
    return bool(row and row.get("vector_model") == model_name and row.get("vector_dim") == dim)


def has_current_chunks(
    source_type: str,
    ticker: str | None = None,
    model_name: str | None = None,
    dim: int | None = None,
) -> bool:
    init_vector_store()
    model_name = model_name or get_embedding_model_name()
    dim = dim or get_embedding_dim()
    where = ["source_type = ?", "vector_model = ?", "vector_dim = ?"]
    params: list[object] = [source_type, model_name, dim]
    if ticker:
        where.append("ticker = ?")
        params.append(ticker)
    conn = _get_conn()
    row = conn.execute(
        f"SELECT COUNT(*) as cnt FROM rag_chunks WHERE {' AND '.join(where)}",
        params,
    ).fetchone()
    conn.close()
    return bool(row and row["cnt"] > 0)


def delete_chunk(chunk_id: str) -> bool:
    conn = _get_conn()
    cur = conn.execute("DELETE FROM rag_chunks WHERE chunk_id = ?", (chunk_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def is_expired(source_type: str, ticker: str | None = None) -> bool:
    """Check if chunks of a source type are missing, stale, or on old embeddings."""
    from datetime import datetime

    init_vector_store()
    where = ["source_type = ?", "vector_model = ?", "vector_dim = ?"]
    params: list[object] = [source_type, get_embedding_model_name(), get_embedding_dim()]
    if ticker:
        where.append("ticker = ?")
        params.append(ticker)

    conn = _get_conn()
    rows = conn.execute(
        f"SELECT generated_at, ttl_hours FROM rag_chunks WHERE {' AND '.join(where)}",
        params,
    ).fetchall()
    conn.close()

    if not rows:
        return True

    now = datetime.now()
    for row in rows:
        if row["ttl_hours"] < 0:
            return False
        try:
            created = datetime.fromisoformat(row["generated_at"])
        except (ValueError, TypeError):
            continue
        if (now - created).total_seconds() / 3600 <= row["ttl_hours"]:
            return False
    return True


def delete_expired_chunks() -> int:
    """Remove chunks whose TTL has expired. Returns count removed."""
    from datetime import datetime

    conn = _get_conn()
    rows = conn.execute(
        "SELECT chunk_id, generated_at, ttl_hours FROM rag_chunks WHERE ttl_hours >= 0"
    ).fetchall()

    expired_ids = []
    now = datetime.now()
    for row in rows:
        try:
            created = datetime.fromisoformat(row["generated_at"])
        except (ValueError, TypeError):
            continue
        if (now - created).total_seconds() / 3600 > row["ttl_hours"]:
            expired_ids.append((row["chunk_id"],))

    if expired_ids:
        conn.executemany("DELETE FROM rag_chunks WHERE chunk_id = ?", expired_ids)
    conn.commit()
    conn.close()
    return len(expired_ids)


def clear_all_chunks() -> int:
    """Delete all indexed chunks and retrieval logs. Used for full rebuilds."""
    init_vector_store()
    conn = _get_conn()
    chunk_count = conn.execute("SELECT COUNT(*) as cnt FROM rag_chunks").fetchone()["cnt"]
    conn.execute("DELETE FROM rag_chunks")
    conn.execute("DELETE FROM rag_retrieval_log")
    conn.commit()
    conn.close()
    return int(chunk_count)


def count_chunks(source_type: str | None = None, current_only: bool = False) -> int:
    init_vector_store()
    conn = _get_conn()
    where = []
    params: list[object] = []
    if source_type:
        where.append("source_type = ?")
        params.append(source_type)
    if current_only:
        where.extend(["vector_model = ?", "vector_dim = ?"])
        params.extend([get_embedding_model_name(), get_embedding_dim()])
    sql = "SELECT COUNT(*) as cnt FROM rag_chunks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def get_all_chunk_ids(source_type: str | None = None) -> list[str]:
    init_vector_store()
    conn = _get_conn()
    if source_type:
        rows = conn.execute(
            "SELECT chunk_id FROM rag_chunks WHERE source_type = ?", (source_type,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT chunk_id FROM rag_chunks").fetchall()
    conn.close()
    return [r["chunk_id"] for r in rows]
