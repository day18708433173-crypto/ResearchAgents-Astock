"""Multi-mode retrieval pipeline.

Constructs queries for different retrieval modes and runs searches
against the vector store, with result fusion and relevance filtering.
Includes retrieval quality monitoring via SQLite log table.
"""

import sqlite3
import json
import re
from datetime import datetime
from pathlib import Path
from services.rag.embeddings import encode_single
from services.rag.vector_store import search

ROOT = Path(__file__).parent.parent.parent
LOG_DB = ROOT / "data" / "rag_vectors.db"


def _log_retrieval(query: str, mode: str, hit_count: int, top_scores: list[float],
                   queries_used: list[str], source_types: list[str] | None = None):
    """Log a retrieval operation for quality monitoring."""
    try:
        conn = sqlite3.connect(str(LOG_DB))
        conn.execute("PRAGMA journal_mode=WAL")
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
            )
        """)
        conn.execute(
            """INSERT INTO rag_retrieval_log
               (query_text, mode, hit_count, top_scores, queries_used, source_types)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                query,
                mode,
                hit_count,
                json.dumps(top_scores[:5]),
                json.dumps(queries_used),
                json.dumps(source_types or []),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # Logging is non-critical


def get_retrieval_stats(limit: int = 50) -> list[dict]:
    """Get recent retrieval statistics for debugging.

    Returns:
        List of recent log entries with query, mode, hit_count, top_scores.
    """
    try:
        conn = sqlite3.connect(str(LOG_DB))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM rag_retrieval_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []

# ── Risk dimensions for blind-spot scanning (used in query construction) ──

RISK_DIMENSIONS = [
    "估值风险", "财务质量", "行业竞争", "政策监管",
    "大股东质押", "应收账款质量", "商誉减值", "现金流健康度",
    "原材料成本", "客户集中度", "关联交易", "对外担保",
    "技术迭代", "市场份额", "管理层稳定性", "法律合规",
]

# ── Query construction ──


def build_queries_for_mode(
    mode: str,
    ticker: str = "",
    data_card: dict | None = None,
    debate_text: str = "",
    claim: str = "",
) -> list[str]:
    """Construct retrieval queries based on the retrieval mode and context.

    Args:
        mode: One of 'pre_debate', 'claim_verification', 'literacy', 'history'
        ticker: Stock ticker code (e.g., "600519.SH")
        data_card: The data card dict (for pre_debate enrichment)
        debate_text: Full debate transcript (for claim verification)
        claim: A specific claim or question text

    Returns:
        List of query strings to use for retrieval
    """
    code = ticker.split(".")[0] if "." in ticker else ticker
    queries = []

    if mode == "pre_debate":
        # Retrieve context to enrich the debate prompt
        queries = [
            f"{code} 公司主营业务 商业模式 行业地位 竞争优势",
            f"{code} 财务质量 盈利能力 现金流 ROE 毛利率 负债率",
            f"{code} 所属行业 行业平均估值 PE PB ROE",
            f"{code} 近期公告 业绩预告 重大合同 股东变动",
        ]

    elif mode == "claim_verification":
        # Verify a specific claim by searching for supporting/contradicting info
        queries = [claim]

    elif mode == "literacy":
        # Find concept definitions for financial literacy Q&A
        queries = [f"金融概念：{claim}"]

    elif mode == "history":
        # Find similar past debates
        queries = [f"{code} 辩论 多空"]

    elif mode == "industry":
        # Industry-specific queries
        industry_name = ""
        if data_card and "rag_context" in data_card:
            industry_name = data_card["rag_context"].get("industry", "")
        queries = [f"{industry_name} 行业平均PE PB ROE 增长率"]

    else:
        # Generic fallback
        queries = [claim or ticker]

    return queries


# ── Retrieval ──


def retrieve(
    queries: list[str],
    mode: str = "pre_debate",
    ticker: str = "",
    top_k: int = 5,
    source_types: list[str] | None = None,
    industry: str | None = None,
    min_score: float = 0.02,
) -> dict:
    """Multi-query retrieval with result deduplication and score-based ranking.

    Args:
        queries: List of query strings
        mode: Retrieval mode (for logging)
        ticker: Filter by stock ticker
        top_k: Max results per query (before dedup)
        source_types: Filter by source type(s)
        industry: Filter by industry name
        min_score: Minimum cosine similarity threshold

    Returns:
        dict with keys:
            chunks: list of dicts (chunk_id, content, source_type, score, ...)
            queries_used: list of query strings that produced results
            hit_count: total number of unique chunks found
    """
    fused: dict[str, dict] = {}
    queries_used = []

    for query in queries:
        if not query.strip():
            continue

        try:
            query_vec = encode_single(query)
        except Exception:
            continue

        results = search(
            query_vec,
            top_k=top_k,
            source_types=source_types,
            ticker=ticker,
            industry=industry,
            min_score=min_score,
        )

        if results:
            queries_used.append(query)

        for rank, r in enumerate(results, start=1):
            cid = r.get("chunk_id", "")
            if not cid:
                continue
            semantic_score = float(r.get("score", 0))
            rrf_score = 1.0 / (60 + rank)
            fused_score = semantic_score + rrf_score
            if cid not in fused:
                item = dict(r)
                item["_semantic_score"] = semantic_score
                item["_rrf_score"] = rrf_score
                item["_fused_score"] = fused_score
                item["_matched_queries"] = [query]
                fused[cid] = item
            else:
                item = fused[cid]
                item["_semantic_score"] = max(item["_semantic_score"], semantic_score)
                item["_rrf_score"] += rrf_score
                item["_fused_score"] = item["_semantic_score"] + item["_rrf_score"]
                item["_matched_queries"].append(query)

    all_results = list(fused.values())
    all_results.sort(key=lambda r: r.get("_fused_score", 0), reverse=True)
    for r in all_results:
        r["semantic_score"] = round(float(r.pop("_semantic_score", 0)), 4)
        r["rrf_score"] = round(float(r.pop("_rrf_score", 0)), 4)
        r["score"] = round(float(r.pop("_fused_score", r.get("score", 0))), 4)
        r["matched_queries"] = r.pop("_matched_queries", [])

    # Log retrieval for quality monitoring
    top_scores = [r.get("score", 0) for r in all_results[:5]]
    _log_retrieval(
        query=queries[0] if queries else "",
        mode=mode,
        hit_count=len(all_results),
        top_scores=top_scores,
        queries_used=queries_used,
        source_types=source_types,
    )

    return {
        "chunks": all_results,
        "queries_used": queries_used,
        "hit_count": len(all_results),
    }


def retrieve_by_ticker(
    ticker: str,
    query: str = "",
    top_k: int = 5,
    source_types: list[str] | None = None,
) -> list[dict]:
    """Convenience: retrieve chunks for a specific ticker.

    If query is empty, uses the ticker code as the query.
    """
    if not query:
        query = ticker
    result = retrieve(
        [query],
        mode="pre_debate",
        ticker=ticker,
        top_k=top_k,
        source_types=source_types,
    )
    return result["chunks"]


def retrieve_concepts(query: str, top_k: int = 3) -> list[dict]:
    """Convenience: retrieve financial concept definitions."""
    expanded_queries = _expand_concept_query(query)
    result = retrieve(
        expanded_queries,
        mode="literacy",
        source_types=["concept_definition"],
        top_k=max(12, top_k * 4),
        min_score=0.0,
    )
    return _rerank_concepts(query, result["chunks"])[:top_k]


CONCEPT_ALIASES: dict[str, list[str]] = {
    "PE": ["PE", "市盈率", "本益比", "price earnings", "市盈"],
    "PB": ["PB", "市净率", "股价净值比", "破净"],
    "ROE": ["ROE", "净资产收益率", "净资产回报率"],
    "ROIC": ["ROIC", "投入资本回报率", "投入资本收益率"],
    "毛利率": ["毛利率", "gross margin"],
    "资产负债率": ["资产负债率", "负债率", "杠杆率"],
    "经营现金流": ["经营现金流", "经营现金流净额", "经营活动现金流", "利润现金含量"],
    "PEG": ["PEG", "市盈率相对盈利增长比率"],
    "流动比率": ["流动比率", "速动比率", "短期偿债"],
    "自由现金流": ["自由现金流", "FCF", "free cash flow"],
    "换手率": ["换手率", "成交活跃度"],
    "扣非净利润": ["扣非净利润", "扣非", "非经常性损益"],
    "一致预期": ["一致预期", "一致预期EPS", "EPS预测", "分析师预期"],
    "融资融券": ["融资融券", "两融", "融资余额", "融券余额"],
    "股东户数": ["股东户数", "股东人数", "筹码集中", "户均持股"],
    "三费占比": ["三费占比", "销售费用", "管理费用", "财务费用", "期间费用"],
    "商誉": ["商誉", "商誉减值", "并购商誉"],
    "杜邦分析": ["杜邦分析", "杜邦拆解", "ROE拆解"],
}


def _normalize_for_match(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", (text or "").lower(), flags=re.UNICODE)


def _expand_concept_query(query: str) -> list[str]:
    q_norm = _normalize_for_match(query)
    queries = [query]
    for canonical, aliases in CONCEPT_ALIASES.items():
        alias_norms = [_normalize_for_match(a) for a in aliases + [canonical]]
        if any(a and (a in q_norm or q_norm in a) for a in alias_norms):
            expanded = " ".join(dict.fromkeys([canonical, *aliases]))
            queries.append(expanded)
            break
    return queries


def _concept_term(chunk: dict) -> str:
    try:
        meta = json.loads(chunk.get("metadata_json", "{}"))
        term = str(meta.get("term", "")).strip()
        if term:
            return term
    except Exception:
        pass
    first_line = str(chunk.get("content", "")).splitlines()[0] if chunk.get("content") else ""
    return first_line.replace("金融概念：", "").strip()


def _concept_lexical_boost(query: str, chunk: dict) -> float:
    q_norm = _normalize_for_match(query)
    if not q_norm:
        return 0.0

    term = _concept_term(chunk)
    term_norm = _normalize_for_match(term)
    content_norm = _normalize_for_match(chunk.get("content", "")[:300])

    boost = 0.0
    if q_norm == term_norm:
        boost = max(boost, 0.6)
    elif q_norm and (q_norm in term_norm or term_norm in q_norm):
        boost = max(boost, 0.45)
    elif q_norm in content_norm:
        boost = max(boost, 0.12)

    for canonical, aliases in CONCEPT_ALIASES.items():
        canonical_norm = _normalize_for_match(canonical)
        alias_norms = [_normalize_for_match(a) for a in aliases]
        query_hits = any(a and (a in q_norm or q_norm in a) for a in alias_norms)
        term_hits = canonical_norm in term_norm or any(a and a in term_norm for a in alias_norms)
        if query_hits and term_hits:
            boost = max(boost, 0.8)
            break

    return boost


def _rerank_concepts(query: str, chunks: list[dict]) -> list[dict]:
    reranked = []
    for chunk in chunks:
        item = dict(chunk)
        lexical_boost = _concept_lexical_boost(query, item)
        item["lexical_boost"] = round(lexical_boost, 4)
        item["score"] = round(float(item.get("score", 0)) + lexical_boost, 4)
        reranked.append(item)
    reranked.sort(key=lambda c: c.get("score", 0), reverse=True)
    return reranked
