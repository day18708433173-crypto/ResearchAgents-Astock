"""统一行情+估值客户端 — 腾讯财经(估值) + mootdx(K线)"""
import urllib.request
from datetime import datetime, timedelta


def _parse_tencent_quote(code: str) -> dict | None:
    """腾讯财经实时行情 — PE/PB/市值/换手率/涨跌停价"""
    if code.startswith(("6", "9")):
        prefixed = f"sh{code}"
    elif code.startswith("8"):
        prefixed = f"bj{code}"
    else:
        prefixed = f"sz{code}"

    url = f"https://qt.gtimg.cn/q={prefixed}"
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
        if len(vals) < 53:
            continue
        return {
            "name": vals[1],
            "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "open": float(vals[5]) if vals[5] else 0,
            "change_amt": float(vals[31]) if vals[31] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "amount_wan": float(vals[37]) if vals[37] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm": float(vals[39]) if vals[39] else 0,
            "amplitude_pct": float(vals[43]) if vals[43] else 0,
            "float_mcap_yi": float(vals[44]) if vals[44] else 0,
            "mcap_yi": float(vals[45]) if vals[45] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
            "limit_up": float(vals[47]) if vals[47] else 0,
            "limit_down": float(vals[48]) if vals[48] else 0,
            "vol_ratio": float(vals[49]) if vals[49] else 0,
            "pe_static": float(vals[52]) if vals[52] else 0,
        }
    return None


def get_valuation(code: str) -> dict:
    """获取个股估值数据。
    返回: {pe_ttm, pe_static, pb, mcap_yi, float_mcap_yi, turnover_pct,
           price, change_pct, limit_up, limit_down, vol_ratio, name}
    失败返回空 dict。
    """
    q = _parse_tencent_quote(code)
    if q is None:
        return {}
    return {
        "name": q.get("name", ""),
        "price": q.get("price", 0),
        "pe_ttm": q.get("pe_ttm", 0),
        "pe_static": q.get("pe_static", 0),
        "pb": q.get("pb", 0),
        "mcap_yi": q.get("mcap_yi", 0),
        "float_mcap_yi": q.get("float_mcap_yi", 0),
        "turnover_pct": q.get("turnover_pct", 0),
        "change_pct": q.get("change_pct", 0),
        "limit_up": q.get("limit_up", 0),
        "limit_down": q.get("limit_down", 0),
        "vol_ratio": q.get("vol_ratio", 0),
    }


# 历史估值分位窗口（交易日）
_PCT_WINDOW_1Y = 250
_PCT_WINDOW_3Y = 750
_PCT_WINDOW_5Y = 1250
_PCT_MIN_SAMPLES = 60


def _percentile_rank(current: float, history: list[float]) -> float | None:
    """计算当前值在历史序列中的百分位（0-100）。"""
    valid = [v for v in history if v is not None and v == v and 0 < v < 500]
    if len(valid) < _PCT_MIN_SAMPLES or current is None or current != current or current <= 0:
        return None
    below = sum(1 for v in valid if v < current)
    equal = sum(1 for v in valid if v == current)
    return round((below + 0.5 * equal) / len(valid) * 100, 1)


def _window_percentiles(
    series: list[float],
    windows: dict[str, int],
    current: float | None = None,
) -> dict[str, float | None]:
    """按交易日窗口计算当前值的历史分位。current 可覆盖序列末位（用于与腾讯实时估值对齐）。"""
    if not series:
        return {k: None for k in windows}
    cur = current if current is not None else series[-1]
    result: dict[str, float | None] = {}
    for key, days in windows.items():
        window = series[-days:] if len(series) >= days else series
        result[key] = _percentile_rank(cur, window[:-1] if len(window) > 1 else window)
    return result


def _resolve_pb_column(df) -> str | None:
    """按列名匹配 PB，避免固定列索引因表结构变更取错。"""
    for col in df.columns:
        col_str = str(col).strip()
        if col_str in ("PB", "市净率") or "PB" in col_str or "市净率" in col_str:
            return col
    if len(df.columns) > 9:
        return df.columns[9]
    return None


def _resolve_close_column(df) -> str | None:
    """按列名匹配收盘价，用于估值交叉验证时对齐价格时点。"""
    for col in df.columns:
        if "收盘" in str(col).strip():
            return col
    if len(df.columns) > 1:
        return df.columns[1]
    return None


def refresh_percentile_current(
    pct: dict,
    current_pe: float | None = None,
    current_pb: float | None = None,
) -> dict:
    """用腾讯实时 PE/PB 重算历史分位，使分位与数据卡估值层口径一致。"""
    if not pct:
        return pct
    windows = {"1y": _PCT_WINDOW_1Y, "3y": _PCT_WINDOW_3Y, "5y": _PCT_WINDOW_5Y}
    out = dict(pct)
    pe_series = pct.get("pe_series") or []
    pb_series = pct.get("pb_series") or []
    if current_pe and current_pe > 0 and pe_series:
        out["pe_ttm"] = current_pe
        out["pe_ttm_pct"] = _window_percentiles(pe_series, windows, current=current_pe)
    if current_pb and current_pb > 0 and pb_series:
        out["pb"] = current_pb
        out["pb_pct"] = _window_percentiles(pb_series, windows, current=current_pb)
    return out


def get_valuation_percentiles(code: str) -> dict:
    """获取 PE(TTM)、PB 的历史估值分位（东财日频，约 2018 年至今）。

    返回:
        pe_ttm, pb: 当前值
        pe_ttm_pct, pb_pct: {"1y": float|None, "3y": float|None, "5y": float|None}
        history_trading_days: 可用历史交易日数
        source: 数据来源说明
    失败返回空 dict。
    """
    try:
        import akshare as ak
        import pandas as pd

        df = ak.stock_value_em(symbol=code)
    except Exception:
        return {}

    if df is None or len(df) == 0 or "PE(TTM)" not in df.columns:
        return {}

    pe_series = pd.to_numeric(df["PE(TTM)"], errors="coerce").tolist()
    pb_col = _resolve_pb_column(df)
    pb_series = (
        pd.to_numeric(df[pb_col], errors="coerce").tolist()
        if pb_col is not None
        else []
    )
    close_col = _resolve_close_column(df)
    close_series = (
        pd.to_numeric(df[close_col], errors="coerce").tolist()
        if close_col is not None
        else []
    )

    windows = {"1y": _PCT_WINDOW_1Y, "3y": _PCT_WINDOW_3Y, "5y": _PCT_WINDOW_5Y}

    return {
        "pe_ttm": pe_series[-1] if pe_series else None,
        "pb": pb_series[-1] if pb_series else None,
        "close": close_series[-1] if close_series else None,
        "pe_ttm_pct": _window_percentiles(pe_series, windows),
        "pb_pct": _window_percentiles(pb_series, windows),
        "pe_series": pe_series,
        "pb_series": pb_series,
        "history_trading_days": len(df),
        "source": "东方财富历史估值(stock_value_em)",
    }


def get_price_history(code: str, days: int = 30) -> list[dict]:
    """获取日K线历史 — mootdx TCP。
    返回: [{trade_date, open, high, low, close, vol}]
    """
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market="std")
        market = 1 if code.startswith("6") else 0
        end = datetime.now()
        start = end - timedelta(days=days + 5)
        df = client.bars(symbol=code, market=market, frequency=9,
                         start=start.strftime("%Y-%m-%d"),
                         end=end.strftime("%Y-%m-%d"))
        if df is None or len(df) == 0:
            return []
        return [
            {"trade_date": str(row.get("trade_date", row.get("date", ""))).replace("-", "")[:8],
             "open": float(row.get("open", 0)),
             "high": float(row.get("high", 0)),
             "low": float(row.get("low", 0)),
             "close": float(row.get("close", 0)),
             "vol": float(row.get("vol", row.get("volume", 0)))}
            for _, row in df.tail(days).iterrows()
        ]
    except Exception:
        return []


def get_realtime_price(code: str) -> float:
    """获取实时价格"""
    q = _parse_tencent_quote(code)
    return q.get("price", 0) if q else 0


def get_realtime_prices_batch(codes: list[str]) -> dict[str, float]:
    """批量获取实时价格 — 一次 HTTP 请求查询多只股票。

    腾讯财经 API 支持逗号分隔多代码，如 q=sh600519,sz000001。
    将 N 次串行 HTTP 请求合并为 1 次。
    """
    if not codes:
        return {}
    prefixed = []
    for code in codes:
        if code.startswith(("6", "9")):
            prefixed.append(f"sh{code}")
        elif code.startswith("8"):
            prefixed.append(f"bj{code}")
        else:
            prefixed.append(f"sz{code}")

    url = f"https://qt.gtimg.cn/q={','.join(prefixed)}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = resp.read().decode("gbk")
    except Exception:
        return {}

    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        vals = line.split('"')[1].split("~")
        if len(vals) < 4:
            continue
        # 腾讯返回变量名为 v_sh600519，不能从 symbol 剥离前缀；代码在 vals[2]
        raw_code = vals[2].strip()
        if not raw_code:
            continue
        try:
            price = float(vals[3]) if vals[3] else 0
        except (ValueError, IndexError):
            price = 0
        result[raw_code] = price

    return result
