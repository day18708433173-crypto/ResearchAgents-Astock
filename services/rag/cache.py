"""TTL-based content cache backed by SQLite.

Used for caching fetched knowledge source content, such as company profiles,
industry benchmarks, and announcements.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent.parent
CACHE_DB_PATH = ROOT / "data" / "rag_cache.db"

# Default TTLs in hours
TTL_EMBEDDING = 720    # 30 days for vectors (stable once computed)
TTL_COMPANY = 168      # 7 days for company profiles
TTL_INDUSTRY = 168     # 7 days for industry benchmarks
TTL_ANNOUNCEMENT = 6   # 6 hours for announcements
TTL_CONCEPT = -1       # indefinite for concept definitions


def _get_conn() -> sqlite3.Connection:
    CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_cache_table():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS content_cache (
            cache_key TEXT PRIMARY KEY,
            data_blob BLOB NOT NULL,
            content_type TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            ttl_hours INTEGER DEFAULT 168
        )
    """)
    conn.commit()
    conn.close()


def get_cached(cache_key: str) -> bytes | None:
    """Get cached data by key. Returns None if expired or missing."""
    ensure_cache_table()
    conn = _get_conn()
    row = conn.execute(
        "SELECT data_blob, created_at, ttl_hours FROM content_cache WHERE cache_key = ?",
        (cache_key,),
    ).fetchone()
    conn.close()

    if not row:
        return None

    # Check TTL
    if row["ttl_hours"] >= 0:  # -1 = indefinite
        created = datetime.fromisoformat(row["created_at"])
        age_hours = (datetime.now() - created).total_seconds() / 3600
        if age_hours > row["ttl_hours"]:
            return None

    return row["data_blob"]


def set_cache(cache_key: str, data: bytes, content_type: str = "", ttl_hours: int = TTL_EMBEDDING):
    """Store data in cache."""
    ensure_cache_table()
    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO content_cache (cache_key, data_blob, content_type, created_at, ttl_hours)
           VALUES (?, ?, ?, ?, ?)""",
        (cache_key, data, content_type, datetime.now().isoformat(), ttl_hours),
    )
    conn.commit()
    conn.close()


def set_cached_json(cache_key: str, data: dict, content_type: str = "", ttl_hours: int = TTL_EMBEDDING):
    """Store JSON-serializable dict in cache."""
    set_cache(cache_key, json.dumps(data, ensure_ascii=False).encode("utf-8"), content_type, ttl_hours)


def get_cached_json(cache_key: str) -> dict | None:
    """Get cached JSON dict. Returns None if expired or missing."""
    blob = get_cached(cache_key)
    if blob is None:
        return None
    try:
        return json.loads(blob.decode("utf-8"))
    except Exception:
        return None


def get_cached_text(cache_key: str) -> str | None:
    """Get cached text. Returns None if expired or missing."""
    blob = get_cached(cache_key)
    if blob is None:
        return None
    try:
        return blob.decode("utf-8")
    except Exception:
        return None


def set_cached_text(cache_key: str, text: str, content_type: str = "", ttl_hours: int = TTL_COMPANY):
    """Store text in cache."""
    set_cache(cache_key, text.encode("utf-8"), content_type, ttl_hours)


def purge_expired() -> int:
    """Remove all expired cache entries. Returns count removed."""
    ensure_cache_table()
    conn = _get_conn()
    now = datetime.now()
    rows = conn.execute("SELECT cache_key, created_at, ttl_hours FROM content_cache").fetchall()
    expired_keys = []
    for row in rows:
        if row["ttl_hours"] < 0:
            continue
        created = datetime.fromisoformat(row["created_at"])
        age_hours = (now - created).total_seconds() / 3600
        if age_hours > row["ttl_hours"]:
            expired_keys.append((row["cache_key"],))
    if expired_keys:
        conn.executemany("DELETE FROM content_cache WHERE cache_key = ?", expired_keys)
    conn.commit()
    conn.close()
    return len(expired_keys)
