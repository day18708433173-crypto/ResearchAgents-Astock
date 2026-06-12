"""AKShare 市场数据客户端 —— 免费无限制，用于股票搜索和行情"""
import os
import json
from pathlib import Path
from datetime import datetime, timedelta

# akshare 直连东方财富，不走代理
for _key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_key, None)

import akshare as ak

_CACHE_DIR = Path(__file__).parent.parent / "data"
_CACHE_FILE = _CACHE_DIR / "stock_list_ak.json"
_CACHE_TTL_HOURS = 24

_stock_cache: list[dict] | None = None


def _load_all_stocks() -> list[dict]:
    global _stock_cache
    if _stock_cache is not None:
        return _stock_cache

    if _CACHE_FILE.exists():
        mtime = datetime.fromtimestamp(_CACHE_FILE.stat().st_mtime)
        age = (datetime.now() - mtime).total_seconds() / 3600
        if age < _CACHE_TTL_HOURS:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                _stock_cache = json.load(f)
            return _stock_cache

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # akshare: 获取全部A股代码和名称
    df = ak.stock_info_a_code_name()
    _stock_cache = [
        {"ts_code": f"{row['code']}.{'SH' if row['code'].startswith('6') else 'SZ'}",
         "name": row["name"],
         "code": row["code"]}
        for _, row in df.iterrows()
    ]
    with open(_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(_stock_cache, f, ensure_ascii=False)
    return _stock_cache


def search_stocks(query: str, limit: int = 10) -> list[dict]:
    """模糊搜索A股 —— 支持代码和名称，akshare源无频率限制"""
    all_stocks = _load_all_stocks()
    q = query.strip().upper()
    results = []
    for s in all_stocks:
        code = s.get("code", "")
        ts = s.get("ts_code", "")
        if q in code or q in ts or q in s["name"]:
            results.append(s)
        if len(results) >= limit:
            break
    results.sort(key=lambda x: (0 if q in x.get("code", "") else 1, x["code"]))
    results = results[:limit]

    # 批量获取实时价格（增强搜索结果）
    if results:
        try:
            from services.market_data import get_realtime_prices_batch
            codes = [r["code"] for r in results]
            prices = get_realtime_prices_batch(codes)
            for r in results:
                r["price"] = prices.get(r["code"], 0.0)
        except Exception:
            pass

    return results


def get_daily_price(code: str, days: int = 30) -> list[dict]:
    """获取日线行情 —— akshare无频率限制"""
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
        if df is None or len(df) == 0:
            return []
        return [
            {"trade_date": row["日期"].replace("-", ""),
             "open": float(row["开盘"]), "high": float(row["最高"]),
             "low": float(row["最低"]), "close": float(row["收盘"]),
             "vol": float(row["成交量"])}
            for _, row in df.tail(days).iterrows()
        ]
    except Exception:
        return []


def get_spot_price(code: str) -> float:
    """获取实时价格"""
    try:
        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"] == code]
        if len(row) > 0:
            return float(row.iloc[0]["最新价"])
    except Exception:
        pass
    return 0.0
