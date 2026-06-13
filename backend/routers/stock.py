"""路由：健康检查 / RAG 状态 / 股票搜索 / 市场脉冲"""

import logging
import urllib.request
from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException, Query

from services.akshare_client import search_stocks as _search_stocks
from backend.schemas import IndexPulse, MarketPulseResponse, StockSearchResponse

router = APIRouter()
logger = logging.getLogger(__name__)


def _parse_index_quote(prefix: str, code: str) -> dict | None:
    """腾讯指数行情：prefix 为 sh 或 sz。"""
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = resp.read().decode("gbk")
    except Exception:
        return None

    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        vals = line.split('"')[1].split("~")
        if len(vals) < 33:
            continue
        try:
            return {
                "price": float(vals[3]) if vals[3] else None,
                "change_pct": float(vals[32]) if vals[32] else None,
            }
        except ValueError:
            return None
    return None


def _fetch_market_pulse() -> MarketPulseResponse:
    now = datetime.now().isoformat()
    sh_quote = _parse_index_quote("sh", "000001")
    sz_quote = _parse_index_quote("sz", "399001")

    north_flow_yi = None
    limit_up_count = None
    note_parts: list[str] = []

    try:
        import akshare as ak
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        def _fetch_north_flow():
            df = ak.stock_hsgt_fund_flow_summary_em()
            if df is not None and len(df) >= 2:
                north_rows = df.iloc[[0, 2]] if len(df) >= 3 else df.iloc[:2]
                for col_idx in (6, 5):
                    total = north_rows.iloc[:, col_idx].fillna(0).sum()
                    if total != 0:
                        return round(float(total), 2)
                return 0.0

            hist = ak.stock_hsgt_hist_em(symbol="北向资金")
            if hist is not None and len(hist) > 0:
                flow_series = hist.iloc[:, 5].dropna()
                if len(flow_series) > 0:
                    return round(float(flow_series.iloc[-1]), 2)
            return None

        def _fetch_limit_up():
            today = datetime.now().strftime("%Y%m%d")
            zt_df = ak.stock_zt_pool_em(date=today)
            return int(len(zt_df)) if zt_df is not None else None

        with ThreadPoolExecutor(max_workers=2) as pool:
            north_future = pool.submit(_fetch_north_flow)
            zt_future = pool.submit(_fetch_limit_up)
            try:
                north_flow_yi = north_future.result(timeout=8)
            except FuturesTimeout:
                note_parts.append("北向资金请求超时")
            except Exception as exc:
                logger.warning("North flow fetch failed: %s", exc)
                note_parts.append("北向资金暂不可用")
            try:
                limit_up_count = zt_future.result(timeout=8)
            except FuturesTimeout:
                note_parts.append("涨停家数请求超时")
            except Exception as exc:
                logger.warning("Limit-up pool fetch failed: %s", exc)
                note_parts.append("涨停家数暂不可用")
    except ImportError:
        note_parts.append("AkShare 未安装，部分指标不可用")

    available = any([
        sh_quote and sh_quote.get("change_pct") is not None,
        sz_quote and sz_quote.get("change_pct") is not None,
        north_flow_yi is not None,
        limit_up_count is not None,
    ])

    return MarketPulseResponse(
        sh_index=IndexPulse(
            name="上证指数",
            code="000001",
            change_pct=sh_quote.get("change_pct") if sh_quote else None,
            price=sh_quote.get("price") if sh_quote else None,
        ),
        sz_index=IndexPulse(
            name="深证成指",
            code="399001",
            change_pct=sz_quote.get("change_pct") if sz_quote else None,
            price=sz_quote.get("price") if sz_quote else None,
        ),
        north_flow_yi=north_flow_yi,
        limit_up_count=limit_up_count,
        updated_at=now,
        available=available,
        note="；".join(note_parts),
    )


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


@router.get("/api/market/pulse", response_model=MarketPulseResponse)
async def market_pulse():
    """今日 A 股脉冲：指数涨跌幅、北向资金、涨停家数。"""
    return _fetch_market_pulse()


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
