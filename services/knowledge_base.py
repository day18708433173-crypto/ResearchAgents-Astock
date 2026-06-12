"""结构化知识库 —— 为辩论提供分层验证数据，消除 LLM 编造外部数据的动机"""
import json
from pathlib import Path
from datetime import datetime
from services.market_data import get_valuation
from services.financial_data import get_income_statement, get_balance_sheet, get_cash_flow

CACHE_DIR = Path(__file__).parent.parent / "data" / "kb_cache"
CACHE_TTL_HOURS = 24


def build_knowledge_base(ts_code: str) -> str:
    """构建完整的结构化知识库文本，24h 缓存。"""
    code = ts_code.split(".")[0]
    today = datetime.now().strftime("%Y%m%d")

    # 检查缓存
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{code}_{today}.json"
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            age = (datetime.now() - datetime.fromisoformat(cached["cached_at"])).total_seconds() / 3600
            if age < CACHE_TTL_HOURS:
                return cached["content"]
        except Exception:
            pass

    # 构建
    kb = _build_raw(code)
    try:
        cache_file.write_text(json.dumps(
            {"content": kb, "cached_at": datetime.now().isoformat()},
            ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return kb


def _build_raw(code: str) -> str:
    """实际构建知识库内容"""
    sections = []

    info = _get_company_info(code)
    if info:
        sections.append(f"## 公司档案\n{info}")

    fin = _get_financial_summary(code)
    if fin:
        sections.append(f"## 财务报表（最近8季）\n{fin}")

    val = _get_valuation_snapshot(code)
    if val:
        sections.append(f"## 估值快照\n{val}")

    own = _get_ownership_snapshot(code)
    if own:
        sections.append(f"## 资金筹码\n{own}")

    return "\n\n".join(sections)


def _get_company_info(code: str) -> str:
    """L1: 公司基本信息"""
    lines = []
    try:
        info = _eastmoney_stock_info(code)
        if info:
            parts = []
            if info.get("name"): parts.append(info["name"])
            if info.get("industry"): parts.append(f"行业：{info['industry']}")
            if info.get("list_date"): parts.append(f"上市日期：{info['list_date']}")
            lines.append(" | ".join(parts))
    except Exception:
        pass
    try:
        f10 = _mootdx_f10(code)
        if f10:
            lines.append(f10[:500])
    except Exception:
        pass
    return "\n".join(lines) if lines else ""


def _get_financial_summary(code: str) -> str:
    """L2: 8季财报摘要表"""
    try:
        lrb = get_income_statement(code)
        fzb = get_balance_sheet(code)
        llb = get_cash_flow(code)
    except Exception:
        return ""

    if not lrb:
        return ""

    # 取最近 8 季，时间正序
    recent = list(reversed(lrb[:8]))
    periods = [r["report_date"] for r in recent]

    # 构建 Markdown 表格
    header = "| 报告期 | " + " | ".join(periods) + " |"
    sep = "|------|" + "|".join(["------" for _ in periods]) + "|"

    rows = []
    for label, key in [("营收(亿)", "营业收入"), ("净利润(亿)", "净利润"),
                       ("营业成本(亿)", "营业成本"), ("销售费用(亿)", "销售费用"),
                       ("管理费用(亿)", "管理费用"), ("财务费用(亿)", "财务费用"),
                       ("营业利润(亿)", "营业利润")]:
        vals = []
        for r in recent:
            v = r.get(key)
            vals.append(f"{v/1e8:.1f}" if v else "-")
        rows.append(f"| {label} | " + " | ".join(vals) + " |")

    # 资产负债表关键项
    if fzb:
        fzb_recent = list(reversed(fzb[:8]))
        fzb_map = {r["report_date"]: r for r in fzb_recent}
        for label, key in [("总资产(亿)", "总资产"), ("总负债(亿)", "总负债")]:
            vals = []
            for p in periods:
                entry = fzb_map.get(p, {})
                v = entry.get(key)
                vals.append(f"{v/1e8:.1f}" if v else "-")
            rows.append(f"| {label} | " + " | ".join(vals) + " |")

    # 现金流量表关键项
    if llb:
        llb_recent = list(reversed(llb[:8]))
        llb_map = {r["report_date"]: r for r in llb_recent}
        for label, key in [("经营CF(亿)", "经营活动现金流净额")]:
            vals = []
            for p in periods:
                entry = llb_map.get(p, {})
                v = entry.get(key)
                vals.append(f"{v/1e8:.1f}" if v else "-")
            rows.append(f"| {label} | " + " | ".join(vals) + " |")

    return header + "\n" + sep + "\n" + "\n".join(rows)


def _get_valuation_snapshot(code: str) -> str:
    """L3: 估值摘要"""
    try:
        v = get_valuation(code)
        if not v:
            return ""
        return f"PE(TTM) {v.get('pe_ttm', '-')} | PE(静) {v.get('pe_static', '-')} | PB {v.get('pb', '-')} | 总市值 {v.get('mcap_yi', '-')}亿 | 流通市值 {v.get('float_mcap_yi', '-')}亿 | 换手率 {v.get('turnover_pct', '-')}%"
    except Exception:
        return ""


def _get_ownership_snapshot(code: str) -> str:
    """L4: 资金筹码摘要"""
    parts = []
    try:
        from services.advanced_data import get_latest_margin, get_latest_holder
        m = get_latest_margin(code)
        if m and m.get("rzye_yi"):
            parts.append(f"融资余额 {m['rzye_yi']}亿")
        h = get_latest_holder(code)
        if h and h.get("holder_num"):
            parts.append(f"股东户数 {h['holder_num']} | 变化 {h.get('change_ratio', '-')}%")
    except Exception:
        pass
    return " | ".join(parts) if parts else ""


def _eastmoney_stock_info(code: str) -> dict:
    """东财个股基本信息"""
    import requests
    market = 1 if code.startswith("6") else 0
    try:
        r = requests.get("https://push2.eastmoney.com/api/qt/stock/get", params={
            "fltt": "2", "invt": "2",
            "fields": "f57,f58,f127,f189",
            "secid": f"{market}.{code}",
        }, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        d = r.json().get("data", {})
        return {
            "name": d.get("f58", ""),
            "industry": d.get("f127", ""),
            "list_date": str(d.get("f189", ""))[:10] if d.get("f189") else "",
        }
    except Exception:
        return {}


def _mootdx_f10(code: str) -> str:
    """mootdx F10 公司概况"""
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market="std")
        text = client.F10(symbol=code, name="公司概况")
        # 截取前500字符
        return text[:500] if text else ""
    except Exception:
        return ""
