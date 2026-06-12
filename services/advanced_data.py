"""高级数据客户端 — 一致预期 + 资金流向 + 融资融券 + 股东户数"""
import re
import requests
import pandas as pd
from io import StringIO
from datetime import datetime


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# ═══════════════════════════════════════════════
# 东财数据中心统一查询
# ═══════════════════════════════════════════════

_DC_BASE = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def _eastmoney_datacenter(report_name: str, columns: str = "ALL",
                          filter_str: str = "", page_size: int = 50,
                          sort_columns: str = "", sort_types: str = "-1") -> list[dict]:
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageSize": page_size,
        "sortColumns": sort_columns, "sortTypes": sort_types,
    }
    headers = {"User-Agent": UA}
    try:
        r = requests.get(_DC_BASE, params=params, headers=headers, timeout=15)
        d = r.json()
        return (d.get("result") or {}).get("data") or []
    except Exception:
        return []


# ═══════════════════════════════════════════════
# 同花顺一致预期 EPS
# ═══════════════════════════════════════════════

def _parse_forecast_year(year_str: str) -> int | None:
    """从表格年度列解析四位年份。"""
    m = re.search(r"(20\d{2})", str(year_str))
    return int(m.group(1)) if m else None


def _parse_int_cell(value) -> int:
    """解析表格中的整数单元格（pandas 常将 46 读成 46.0）。"""
    if value is None:
        return 0
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


def get_consensus_eps(code: str) -> dict:
    """同花顺机构一致预期EPS。
    返回: {eps_current, eps_next, analyst_count, eps_min, eps_max}
    失败返回空 dict。
    """
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.encoding = "gbk"
        dfs = pd.read_html(StringIO(r.text))
        if not dfs:
            return {}
        current_year = datetime.now().year
        for df in dfs:
            if df.shape[1] >= 4:
                cols = [str(c).strip() for c in df.columns]
                if any("预测" in c or "年度" in c or "机构" in c for c in cols):
                    by_year: dict[int, dict] = {}
                    for row in df.values.tolist():
                        year = _parse_forecast_year(row[0])
                        if year is None or year < current_year:
                            continue
                        try:
                            analyst_count = _parse_int_cell(row[1]) if len(row) > 1 else 0
                            mean_eps = float(row[3]) if len(row) > 3 else 0
                            min_eps = float(row[2]) if len(row) > 2 else 0
                            max_eps = float(row[4]) if len(row) > 4 else 0
                        except (TypeError, ValueError):
                            continue
                        if mean_eps == 0:
                            continue
                        by_year[year] = {
                            "mean": mean_eps,
                            "min": min_eps,
                            "max": max_eps,
                            "analyst_count": analyst_count,
                        }
                    future_years = sorted(by_year)
                    if not future_years:
                        continue
                    cur_year = current_year if current_year in by_year else future_years[0]
                    cur = by_year[cur_year]
                    result = {
                        "eps_current": cur["mean"],
                        "eps_min": cur["min"],
                        "eps_max": cur["max"],
                        "analyst_count": cur["analyst_count"],
                    }
                    next_candidates = [y for y in future_years if y > cur_year]
                    if next_candidates:
                        nxt = by_year[next_candidates[0]]
                        result["eps_next"] = nxt["mean"]
                    return result
        return {}
    except Exception:
        return {}


# ═══════════════════════════════════════════════
# 东财资金流向 (日级120日)
# ═══════════════════════════════════════════════

def get_fund_flow_120d(code: str) -> list[dict]:
    """个股资金流（日级，最近120个交易日）。
    返回: [{date, main_net, large_net, mid_net, small_net, super_net}]
    单位: 元
    """
    market_code = 1 if code.startswith("6") else 0
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": f"{market_code}.{code}",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "lmt": "120",
    }
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        d = r.json()
        rows = []
        for line in (d.get("data") or {}).get("klines") or []:
            parts = line.split(",")
            if len(parts) >= 7:
                rows.append({
                    "date": parts[0],
                    "main_net": float(parts[1]),
                    "small_net": float(parts[2]),
                    "mid_net": float(parts[3]),
                    "large_net": float(parts[4]),
                    "super_net": float(parts[5]),
                })
        return rows
    except Exception:
        return []


def get_recent_fund_flow(code: str, days: int = 5) -> dict:
    """近N日资金流汇总。
    返回: {main_net_5d(万元), flow_signal("流入"/"流出"/"平衡")}
    """
    flows = get_fund_flow_120d(code)
    if not flows:
        return {}
    recent = flows[:min(days, len(flows))]
    total = sum(r["main_net"] for r in recent)
    if total > 10000000:
        signal = "流入"
    elif total < -10000000:
        signal = "流出"
    else:
        signal = "平衡"
    dates = [r["date"] for r in recent if r.get("date")]
    return {
        "main_net_5d_wan": round(total / 10000, 0),
        "flow_signal": signal,
        "as_of": max(dates) if dates else None,
    }


# ═══════════════════════════════════════════════
# 东财融资融券
# ═══════════════════════════════════════════════

def get_margin_trading(code: str, page_size: int = 10) -> list[dict]:
    """融资融券明细（日级）。
    返回: [{date, rzye(融资余额), rzmre(融资买入), rzche(融资偿还),
           rqye(融券余额), rqmcl(融券卖出量), rqchl(融券偿还量), rzrqye(合计)}]
    """
    data = _eastmoney_datacenter(
        "RPTA_WEB_RZRQ_GGMX",
        filter_str=f'(SCODE="{code}")',
        page_size=page_size,
        sort_columns="DATE", sort_types="-1",
    )
    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("DATE", ""))[:10],
            "rzye": row.get("RZYE", 0),
            "rzmre": row.get("RZMRE", 0),
            "rzche": row.get("RZCHE", 0),
            "rqye": row.get("RQYE", 0),
            "rqmcl": row.get("RQMCL", 0),
            "rqchl": row.get("RQCHL", 0),
            "rzrqye": row.get("RZRQYE", 0),
        })
    return rows


def get_latest_margin(code: str) -> dict:
    """最新融资融券数据。
    返回: {rzye_yi(融资余额亿), rqye_yi(融券余额亿), rzrqye_yi(合计亿),
           margin_signal(做多/做空/平衡)}
    """
    data = get_margin_trading(code, page_size=1)
    if not data:
        return {}
    d = data[0]
    rzye_yi = (d.get("rzye", 0) or 0) / 1e8
    rqye_yi = (d.get("rqye", 0) or 0) / 1e8
    if rzye_yi > rqye_yi * 10:
        signal = "做多"
    elif rqye_yi > rzye_yi * 0.1:
        signal = "做空"
    else:
        signal = "平衡"
    return {
        "date": d.get("date"),
        "rzye_yi": round(rzye_yi, 2),
        "rqye_yi": round(rqye_yi, 2),
        "rzrqye_yi": round((d.get("rzrqye", 0) or 0) / 1e8, 2),
        "margin_signal": signal,
    }


# ═══════════════════════════════════════════════
# 东财股东户数变化
# ═══════════════════════════════════════════════

def get_holder_change(code: str, page_size: int = 10) -> list[dict]:
    """股东户数变化（季度级）。
    返回: [{date, holder_num, change_num, change_ratio, avg_shares}]
    """
    data = _eastmoney_datacenter(
        "RPT_HOLDERNUMLATEST",
        filter_str=f'(SECURITY_CODE="{code}")',
        page_size=page_size,
        sort_columns="END_DATE", sort_types="-1",
    )
    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("END_DATE", ""))[:10],
            "holder_num": row.get("HOLDER_NUM", 0),
            "change_num": row.get("HOLDER_NUM_CHANGE", 0),
            "change_ratio": row.get("HOLDER_NUM_RATIO", 0),
            "avg_shares": row.get("AVG_HOLD_NUM", 0),
            "total_a_shares": row.get("TOTAL_A_SHARES", 0),
            "total_market_cap": row.get("TOTAL_MARKET_CAP", 0),
        })
    return rows


def get_latest_holder(code: str) -> dict:
    """最新股东户数。
    返回: {holder_num, change_ratio, avg_shares, concentration_signal}
    """
    data = get_holder_change(code, page_size=2)
    if not data:
        return {}
    d = data[0]
    ratio = d.get("change_ratio", 0) or 0
    if ratio < -5:
        signal = "集中"
    elif ratio > 5:
        signal = "分散"
    else:
        signal = "稳定"
    return {
        "end_date": d.get("date"),
        "holder_num": d.get("holder_num", 0),
        "change_ratio": ratio,
        "avg_shares": d.get("avg_shares", 0),
        "total_a_shares": d.get("total_a_shares", 0),
        "total_market_cap": d.get("total_market_cap", 0),
        "concentration_signal": signal,
    }
