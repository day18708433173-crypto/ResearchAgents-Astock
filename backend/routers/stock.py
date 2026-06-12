"""路由：健康检查 / RAG 状态 / 股票搜索"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException, Query

from services.akshare_client import search_stocks as _search_stocks
from backend.schemas import StockSearchResponse

router = APIRouter()


@router.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@router.get("/api/rag/stats")
async def rag_stats():
    """RAG status and recent retrieval metrics."""
    try:
        from services.rag.embeddings import get_embedding_dim, get_embedding_model_name, is_fitted
        from services.rag.knowledge_index import is_rag_ready
        from services.rag.retriever import get_retrieval_stats
        from services.rag.vector_store import count_chunks

        source_types = [
            "concept_definition",
            "industry_benchmark",
            "company_profile",
            "financial_report",
            "announcement",
        ]
        counts = {
            source: count_chunks(source, current_only=True)
            for source in source_types
        }
        return {
            "ready": is_rag_ready(),
            "embedding_model": get_embedding_model_name(),
            "embedding_dim": get_embedding_dim(),
            "embedding_runtime_ready": is_fitted(),
            "current_chunks": count_chunks(current_only=True),
            "all_chunks": count_chunks(),
            "counts": counts,
            "recent_retrievals": get_retrieval_stats(20),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/stock/search", response_model=List[StockSearchResponse])
async def stock_search(q: str = Query(..., min_length=2)):
    """股票搜索：支持代码精确匹配和名称模糊搜索"""
    try:
        results = _search_stocks(q)
        return [StockSearchResponse(
            ts_code=r.get("ts_code", ""),
            name=r.get("name", ""),
            code=r.get("code", ""),
            price=r.get("price", 0.0),
            industry=r.get("industry", ""),
        ) for r in results[:10]]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
