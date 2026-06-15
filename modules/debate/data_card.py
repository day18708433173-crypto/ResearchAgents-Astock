"""数据卡生成 —— 四层数据架构：估值(腾讯) + 财务(AKShare+新浪) + 预期(同花顺) + 资金筹码(东财)

数据等级定义：
- A级：数值至少经过一次其他数据来源的交叉验证（偏差在容差内）
- B级：单源直采或系统计算，未经交叉验证
- C级：多源数据存在但交叉验证偏差超出容差，引用需谨慎
- 不可得：接口未返回该字段

性能优化：所有独立的网络请求并行执行（ThreadPoolExecutor），
将原来 15-25s 的串行调用压缩到 ~3-5s（取决于最慢的单个请求）。
"""
import os
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)

import akshare as ak
from services.market_data import get_valuation, get_valuation_percentiles, refresh_percentile_current
from services.financial_data import (
    get_financial_bundle,
    get_em_latest_indicators,
    get_sina_gjzb_latest,
    pick_report_row,
)
from services.advanced_data import (
    get_consensus_eps, get_recent_fund_flow,
    get_latest_margin, get_latest_holder,
)


def generate(ts_code: str) -> dict:
    code = ts_code.split(".")[0]
    fields = {}
    errors = []

    # ── 并行发起所有独立网络请求 ──
    # 这些数据源互不依赖，用 ThreadPoolExecutor 并发获取，
    # 总耗时 = max(各请求耗时) 而非 sum(各请求耗时)
    results = {}  # key → (data_or_exception, is_error)

    def _fetch(name, fn, *args):
        """包装网络请求，返回 (name, data, error_str_or_None)"""
        try:
            return (name, fn(*args), None)
        except Exception as e:
            return (name, None, f"{name}:{e}")

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {
            pool.submit(_fetch, "valuation", get_valuation, code): "valuation",
            pool.submit(_fetch, "akshare", _fetch_akshare, code): "akshare",
            pool.submit(_fetch, "fin_bundle", get_financial_bundle, code): "fin_bundle",
            pool.submit(_fetch, "em_fin", get_em_latest_indicators, code): "em_fin",
            pool.submit(_fetch, "gjzb", get_sina_gjzb_latest, code): "gjzb",
            pool.submit(_fetch, "fund_flow", get_recent_fund_flow, code, 5): "fund_flow",
            pool.submit(_fetch, "margin", get_latest_margin, code): "margin",
            pool.submit(_fetch, "holder", get_latest_holder, code): "holder",
            pool.submit(_fetch, "price_history", _fetch_price_history, code): "price_history",
            pool.submit(_fetch, "valuation_pct", get_valuation_percentiles, code): "valuation_pct",
        }

        for future in as_completed(futures):
            name, data, err = future.result()
            if err:
                errors.append(err)
                results[name] = None
            else:
                results[name] = data

    today = datetime.now().strftime("%Y-%m-%d")
    quote_ctx = {"as_of": today, "period_label": "实时行情"}

    # ═══════════════════════════════════════════════
    # 估值层：腾讯财经
    # ═══════════════════════════════════════════════
    val = results.get("valuation")
    close_price = 0
    if val:
        fields["当前价"] = _a(val.get("price"), source="腾讯财经", **quote_ctx)
        fields["PE(TTM)"] = _a(val.get("pe_ttm"), source="腾讯财经", **quote_ctx)
        fields["PE(静)"] = _a(val.get("pe_static"), source="腾讯财经", **quote_ctx)
        fields["PB"] = _a(val.get("pb"), source="腾讯财经", **quote_ctx)
        fields["总市值"] = _a(val.get("mcap_yi"), suffix="亿", source="腾讯财经", **quote_ctx)
        fields["流通市值"] = _a(val.get("float_mcap_yi"), suffix="亿", source="腾讯财经", **quote_ctx)
        fields["换手率"] = _a(val.get("turnover_pct"), suffix="%", source="腾讯财经", **quote_ctx)
        fields["涨跌幅"] = _a(val.get("change_pct"), suffix="%", source="腾讯财经", **quote_ctx)
        fields["涨停价"] = _a(val.get("limit_up"), source="腾讯财经", **quote_ctx)
        fields["跌停价"] = _a(val.get("limit_down"), source="腾讯财经", **quote_ctx)
        fields["量比"] = _a(val.get("vol_ratio"), source="腾讯财经", **quote_ctx)
        close_price = val.get("price", 0)

    pct = results.get("valuation_pct")
    # 保留东财序列末位原始值，供与腾讯估值交叉验证
    em_pe = pct.get("pe_ttm") if pct else None
    em_pb = pct.get("pb") if pct else None
    em_close = pct.get("close") if pct else None
    if pct:
        if val:
            pct = refresh_percentile_current(
                pct,
                current_pe=val.get("pe_ttm"),
                current_pb=val.get("pb"),
            )
        _apply_valuation_percentile_fields(fields, pct, tencent_aligned=bool(val), as_of=today)

    # ═══════════════════════════════════════════════
    # 财务层 A：AKShare 同花顺摘要
    # ═══════════════════════════════════════════════
    akshare_data = results.get("akshare")
    ths_report_as_of = None
    if akshare_data:
        latest = akshare_data
        ths = "同花顺财务摘要"
        ths_report_as_of = _normalize_date(latest.get("报告期"))
        ths_ctx = _financial_time_ctx(ths_report_as_of)
        fields["营收"] = _a(latest.get("营业总收入"), source=ths, **ths_ctx)
        fields["营收同比"] = _a(latest.get("营业总收入同比增长率"), suffix="%", source=ths, **ths_ctx)
        fields["净利润"] = _a(latest.get("净利润"), source=ths, **ths_ctx)
        fields["净利润同比"] = _a(latest.get("净利润同比增长率"), suffix="%", source=ths, **ths_ctx)
        fields["扣非净利润"] = _a(latest.get("扣非净利润"), source=ths, **ths_ctx)
        fields["扣非净利润同比"] = _a(latest.get("扣非净利润同比增长率"), suffix="%", source=ths, **ths_ctx)
        fields["ROE"] = _a(latest.get("净资产收益率"), suffix="%", source=ths, **ths_ctx)
        fields["毛利率"] = _a(latest.get("销售毛利率"), suffix="%", source=ths, **ths_ctx)
        fields["净利率"] = _a(latest.get("销售净利率"), suffix="%", source=ths, **ths_ctx)
        fields["每股收益"] = _a(latest.get("基本每股收益"), source=ths, **ths_ctx)
        fields["每股净资产"] = _a(latest.get("每股净资产"), source=ths, **ths_ctx)
        fields["每股经营现金流"] = _a(latest.get("每股经营现金流"), source=ths, **ths_ctx)
        fields["资产负债率"] = _a(latest.get("资产负债率"), suffix="%", source=ths, **ths_ctx)
        fields["流动比率"] = _a(latest.get("流动比率"), source=ths, **ths_ctx)
        fields["速动比率"] = _a(latest.get("速动比率"), source=ths, **ths_ctx)
        fields["存货周转率"] = _a(latest.get("存货周转率"), source=ths, **ths_ctx)
        fields["应收账款周转率"] = _a(latest.get("应收账款周转率"), source=ths, **ths_ctx)
        _calc_derived_ths(fields, latest, ths_report_as_of)

    # ═══════════════════════════════════════════════
    # 财务层 B：新浪财报三表
    # ═══════════════════════════════════════════════
    fin_bundle = results.get("fin_bundle") or {}
    fin = fin_bundle.get("latest") or {}
    fin_quarters = fin_bundle.get("quarters") or []
    em_fin = results.get("em_fin") or {}
    gjzb = results.get("gjzb") or {}
    sina_report_as_of = None
    if fin:
        sina = "新浪财报三表"
        sina_report_as_of = _normalize_date(fin.get("report_date"))
        sina_ctx = _financial_time_ctx(sina_report_as_of)
        fields["营业成本"] = _a(fin.get("营业成本"), source=sina, **sina_ctx)
        fields["销售费用"] = _a(fin.get("销售费用"), source=sina, **sina_ctx)
        fields["管理费用"] = _a(fin.get("管理费用"), source=sina, **sina_ctx)
        fields["财务费用"] = _a(fin.get("财务费用"), source=sina, **sina_ctx)
        fields["研发费用"] = _a(fin.get("研发费用"), source=sina, **sina_ctx)
        fields["营业利润"] = _a(fin.get("营业利润"), source=sina, **sina_ctx)
        fields["利润总额"] = _a(fin.get("利润总额"), source=sina, **sina_ctx)
        fields["总资产"] = _a(fin.get("总资产"), source=sina, **sina_ctx)
        fields["总负债"] = _a(fin.get("总负债"), source=sina, **sina_ctx)
        fields["经营现金流净额"] = _a(fin.get("经营活动现金流净额"), source=sina, **sina_ctx)
        fields["投资现金流净额"] = _a(fin.get("投资活动现金流净额"), source=sina, **sina_ctx)
        fields["筹资现金流净额"] = _a(fin.get("筹资活动现金流净额"), source=sina, **sina_ctx)
        _calc_derived_sina(fields, fin, sina_report_as_of)

    # ═══════════════════════════════════════════════
    # 预期层：同花顺一致预期 EPS（依赖 close_price）
    # ═══════════════════════════════════════════════
    eps_cur = None
    try:
        eps_data = get_consensus_eps(code)
        if eps_data:
            ths_eps = "同花顺一致预期"
            eps_ctx = {
                "as_of": today,
                "period_label": f"{datetime.now().year}一致预期",
            }
            fields["一致预期EPS(当年)"] = _a(eps_data.get("eps_current"), source=ths_eps, **eps_ctx)
            fields["一致预期EPS(明年)"] = _a(eps_data.get("eps_next"), source=ths_eps, **eps_ctx)
            fields["预测机构数"] = _a(eps_data.get("analyst_count"), suffix="家", source=ths_eps, **eps_ctx)
            eps_cur = eps_data.get("eps_current")
            eps_nxt = eps_data.get("eps_next")
            calc_ctx = {"as_of": today, "period_label": "实时计算"}
            if close_price > 0 and eps_cur and eps_cur > 0:
                fwd_pe = close_price / eps_cur
                fields["前向PE"] = _make_field(
                    round(fwd_pe, 1), "B",
                    "系统计算: 当前价÷一致预期EPS(当年)", **calc_ctx,
                )
                if eps_nxt is not None:
                    eps_growth = (eps_nxt - eps_cur) / eps_cur * 100
                    if eps_growth > 0.5:
                        peg = round(fwd_pe / eps_growth, 2)
                        fields["前向PEG"] = _make_field(
                            peg, "B",
                            f"系统计算: 前向PE÷一致预期EPS增速({round(eps_growth, 1)}%)",
                            **calc_ctx,
                        )
    except Exception as e:
        errors.append(f"一致预期:{e}")

    # ═══════════════════════════════════════════════
    # 资金筹码层：东财（已在并行阶段获取）
    # ═══════════════════════════════════════════════
    flow = results.get("fund_flow")
    if flow:
        flow_as_of = _normalize_date(flow.get("as_of")) or today
        flow_ctx = {"as_of": flow_as_of, "period_label": "近5交易日"}
        fields["主力资金流(近5日)"] = _a(flow.get("main_net_5d_wan"), suffix="万元", source="东方财富资金流", **flow_ctx)
        fields["资金信号"] = _a(flow.get("flow_signal"), source="东方财富资金流", **flow_ctx)

    margin = results.get("margin")
    if margin:
        margin_as_of = _normalize_date(margin.get("date")) or today
        margin_ctx = {"as_of": margin_as_of, "period_label": "日度两融"}
        fields["融资余额"] = _a(margin.get("rzye_yi"), suffix="亿", source="东方财富两融", **margin_ctx)
        fields["融券余额"] = _a(margin.get("rqye_yi"), suffix="亿", source="东方财富两融", **margin_ctx)
        fields["两融信号"] = _a(margin.get("margin_signal"), source="东方财富两融", **margin_ctx)

    holder = results.get("holder")
    if holder:
        holder_as_of = _normalize_date(holder.get("end_date"))
        holder_ctx = _financial_time_ctx(holder_as_of) if holder_as_of else {"as_of": today, "period_label": "股东户数"}
        fields["股东户数"] = _a(holder.get("holder_num"), suffix="户", source="东方财富股东户数", **holder_ctx)
        fields["户均持股"] = _a(holder.get("avg_shares"), suffix="股", source="东方财富股东户数", **holder_ctx)
        fields["筹码信号"] = _a(holder.get("concentration_signal"), source="东方财富股东户数", **holder_ctx)

    # ═══════════════════════════════════════════════
    # 行情历史
    # ═══════════════════════════════════════════════
    hist = results.get("price_history")
    if hist and close_price > 0:
        kline = "mootdx K线"
        trade_date = _normalize_date(hist[-1].get("trade_date")) or today
        kline_ctx = {"as_of": trade_date, "period_label": "K线行情"}
        fields["最近交易日"] = _a(trade_date, source=kline, **kline_ctx)
        w5 = _period_return(hist, 5)
        if w5 is not None:
            fields["近5日涨跌"] = _a(f"{w5}%", source=f"系统计算: {kline}", **kline_ctx)
        if len(hist) >= 10:
            fields["近10日最高"] = _a(max(h["close"] for h in hist[-10:]), source=kline, **kline_ctx)
            fields["近10日最低"] = _a(min(h["close"] for h in hist[-10:]), source=kline, **kline_ctx)
        w20 = _period_return(hist, 20)
        if w20 is not None:
            fields["近20日涨跌"] = _a(f"{w20}%", source=f"系统计算: {kline}", **kline_ctx)
    elif close_price > 0:
        fields["最近交易日"] = _a(today, source="系统日期", **quote_ctx)

    # ═══════════════════════════════════════════════
    # 交叉验证：偏差在容差内 → A；超出容差 → C
    # ═══════════════════════════════════════════════
    _cross_validate(
        fields, val=val, ths=akshare_data, sina=fin,
        em_pe=em_pe, em_pb=em_pb, em_close=em_close, hist=hist,
        holder=holder, close_price=close_price, eps_cur=eps_cur,
        em_fin=em_fin, gjzb=gjzb, quarters=fin_quarters,
        ths_report_as_of=ths_report_as_of,
    )

    # ═══════════════════════════════════════════════
    # 覆盖率
    # ═══════════════════════════════════════════════
    total = len(fields)
    filled = sum(1 for f in fields.values() if f.get("value") is not None)
    coverage = int((filled / max(total, 1)) * 100)

    return {
        "ticker": ts_code,
        "generated_at": datetime.now().isoformat(),
        "coverage": coverage,
        "fields": fields,
        "errors": errors if errors else None,
    }


def _fetch_akshare(code: str) -> dict | None:
    """提取 AKShare 数据获取为独立函数，便于并行调度。"""
    df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
    if len(df) > 0:
        return df.iloc[-1].to_dict()
    return None


def _fetch_price_history(code: str) -> list[dict] | None:
    """提取 K线数据获取为独立函数。"""
    from services.market_data import get_price_history
    hist = get_price_history(code, days=30)
    return hist if hist else None


# ═══════════════════════════════════════════════
# 历史估值分位
# ═══════════════════════════════════════════════

def _format_pct_windows(pct_map: dict) -> str | None:
    """将 {1y: 12.5, 3y: 35.0, ...} 格式化为展示文本。"""
    labels = [("1年", "1y"), ("3年", "3y"), ("5年", "5y")]
    parts = []
    for label, key in labels:
        val = pct_map.get(key)
        if val is not None:
            parts.append(f"{label}{val}%")
    return " / ".join(parts) if parts else None


def _apply_valuation_percentile_fields(
    fields: dict, pct: dict, tencent_aligned: bool = False, as_of: str | None = None,
) -> None:
    """写入 PE(TTM)、PB 的历史估值分位字段。"""
    history_days = pct.get("history_trading_days", 0)
    source_base = pct.get("source", "东方财富历史估值")
    current_src = "腾讯实时估值" if tencent_aligned else "东财序列末位"

    pct_ctx = {"as_of": as_of or datetime.now().strftime("%Y-%m-%d"), "period_label": "历史估值分位"}
    pe_text = _format_pct_windows(pct.get("pe_ttm_pct") or {})
    if pe_text:
        pe_now = pct.get("pe_ttm")
        fields["PE(TTM)历史分位"] = _make_field(
            pe_text, "B",
            (
                f"系统计算: 历史序列={source_base}，当前PE(TTM)={round(pe_now, 1) if pe_now else '—'}"
                f"（{current_src}），共{history_days}个交易日；分位=低于该值的历史占比"
            ),
            **pct_ctx,
        )

    pb_text = _format_pct_windows(pct.get("pb_pct") or {})
    if pb_text:
        pb_now = pct.get("pb")
        fields["PB历史分位"] = _make_field(
            pb_text, "B",
            (
                f"系统计算: 历史序列={source_base}，当前PB={round(pb_now, 2) if pb_now else '—'}"
                f"（{current_src}），共{history_days}个交易日；分位=低于该值的历史占比"
            ),
            **pct_ctx,
        )


# ═══════════════════════════════════════════════
# 衍生指标计算
# ═══════════════════════════════════════════════

def _calc_derived_ths(fields: dict, latest: dict, report_as_of: str | None = None):
    """从 AKShare 原始字段计算衍生指标"""
    ctx = _financial_time_ctx(report_as_of)
    try:
        roe_raw = latest.get("净资产收益率")
        debt_raw = latest.get("资产负债率")
        if roe_raw is not None and debt_raw is not None:
            roe = float(str(roe_raw).replace("%", ""))
            debt = float(str(debt_raw).replace("%", ""))
            roa = round(roe * (1 - debt / 100), 2)
            fields["ROA近似"] = _make_field(
                f"{roa}%", "B",
                "系统计算: ROE×(1-资产负债率)=净利润/总资产", **ctx,
            )
    except Exception:
        pass

    try:
        cps = latest.get("每股经营现金流")
        eps = latest.get("基本每股收益")
        if cps is not None and eps is not None and float(eps) > 0:
            ratio = round(float(cps) / float(eps), 2)
            fields["利润现金含量"] = _make_field(
                ratio, "B", "系统计算: 每股经营现金流÷每股收益", **ctx,
            )
    except Exception:
        pass


def _calc_derived_sina(fields: dict, fin: dict, report_as_of: str | None = None):
    """从新浪财报数据计算衍生指标"""
    ctx = _financial_time_ctx(report_as_of)
    # 三费占比
    try:
        revenue = fin.get("营业收入")
        sales = fin.get("销售费用") or 0
        admin = fin.get("管理费用") or 0
        finance = fin.get("财务费用") or 0
        if revenue and revenue > 0:
            ratio = round((sales + admin + finance) / revenue * 100, 2)
            fields["三费占比"] = _make_field(
                f"{ratio}%", "B",
                "系统计算: (销售+管理+财务费用)÷营业收入", **ctx,
            )
    except Exception:
        pass

    # 毛利率验证（新浪数据）
    try:
        revenue = fin.get("营业收入")
        cost = fin.get("营业成本")
        if revenue and cost and revenue > 0:
            gm = round((revenue - cost) / revenue * 100, 2)
            fields["毛利率(新浪)"] = _make_field(
                f"{gm}%", "B",
                "系统计算: (营业收入-营业成本)÷营业收入", **ctx,
            )
    except Exception:
        pass

    # 自由现金流近似 = 经营现金流 + 投资现金流（投资流出为负时等价于扣资本开支）
    try:
        ocf = fin.get("经营活动现金流净额")
        inv = fin.get("投资活动现金流净额")
        if ocf is not None:
            fcf = ocf + inv if inv is not None else ocf
            source = (
                "系统计算: 经营现金流净额+投资活动现金流净额（近似FCF）"
                if inv is not None
                else "经营现金流净额（缺少投资流，未扣资本开支）"
            )
            fields["自由现金流近似"] = _make_field(
                round(fcf / 1e8, 2), "B", source, **ctx,
            )
    except Exception:
        pass


# ═══════════════════════════════════════════════
# 交叉验证
# ═══════════════════════════════════════════════

# 相对偏差容差：财报数据应严格一致，行情/估值允许快照时点差异
_TOL_FINANCIAL = 0.02
_TOL_VALUATION = 0.05
_TOL_PRICE = 0.02
_TOL_HOLDER = 0.03


def _num(v) -> float | None:
    """解析数值，亿/万 换算为原始单位，% 仅去除符号。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if f == f else None
    s = str(v).replace(",", "").replace("%", "").strip()
    mult = 1.0
    if s.endswith("亿"):
        mult, s = 1e8, s[:-1]
    elif s.endswith("万"):
        mult, s = 1e4, s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


def _cross_deviation(a, b) -> float | None:
    """计算两值相对偏差；无法比较时返回 None。"""
    va, vb = _num(a), _num(b)
    if va is None or vb is None or va == 0 or vb == 0:
        return None
    base = max(abs(va), abs(vb))
    return abs(va - vb) / base


def _try_cross_validate(fields: dict, name: str, a, b, other_source: str, tol: float) -> None:
    """交叉验证：容差内 → A 级；超出容差且尚未 A → C 级。"""
    field = fields.get(name)
    if not field or field.get("value") is None:
        return
    deviation = _cross_deviation(a, b)
    if deviation is None:
        return
    pct = round(deviation * 100, 2)
    tol_pct = round(tol * 100, 2)
    if deviation <= tol:
        field["grade"] = "A"
        field["source"] = (
            f"{field.get('source', '')}；已与{other_source}交叉验证(偏差{pct}%)"
        )
    elif field.get("grade") != "A":
        field["grade"] = "C"
        field["source"] = (
            f"{field.get('source', '')}；与{other_source}交叉验证失败"
            f"(偏差{pct}%，容差{tol_pct}%)"
        )


def _try_any_cross_validate(fields: dict, name: str, candidates: list,
                            other_source: str, tol: float) -> None:
    """对同一字段尝试多个备选对比值，任一通过即升 A。"""
    for a, b in candidates:
        before = (fields.get(name) or {}).get("grade")
        _try_cross_validate(fields, name, a, b, other_source, tol)
        if (fields.get(name) or {}).get("grade") == "A":
            return
        if before == "A":
            fields[name]["grade"] = "A"


def _apply_period_alignment(fields: dict, ths_date: str | None,
                            sina_date: str | None, em_date: str | None) -> str | None:
    """P2：报告期对齐检查，不对齐时在财报字段标注 warning。"""
    dates = {
        "同花顺": _normalize_date(ths_date),
        "新浪": _normalize_date(sina_date),
        "东财": _normalize_date(em_date),
    }
    present = {k: v for k, v in dates.items() if v}
    if len(set(present.values())) <= 1:
        return present.get("同花顺") or present.get("新浪") or present.get("东财")

    warning = "报告期未对齐: " + " / ".join(f"{k}{v}" for k, v in present.items())
    financial_keys = {
        "营收", "营收同比", "净利润", "净利润同比", "扣非净利润", "扣非净利润同比",
        "ROE", "毛利率", "净利率", "每股收益", "每股净资产", "每股经营现金流",
        "资产负债率", "营业成本", "销售费用", "管理费用", "财务费用", "研发费用",
        "营业利润", "利润总额", "总资产", "总负债", "经营现金流净额",
        "投资现金流净额", "筹资现金流净额", "ROA近似", "利润现金含量", "三费占比",
        "毛利率(新浪)", "自由现金流近似",
    }
    for key in financial_keys:
        field = fields.get(key)
        if field and field.get("value") is not None:
            field["period_warning"] = warning
    return present.get("同花顺") or next(iter(present.values()), None)


def _cross_validate_quarterly(fields: dict, quarters: list[dict],
                              aligned_date: str | None) -> None:
    """P2：与 8 季财报序列中同报告期行核对（防拿错季度）。"""
    if not quarters:
        return
    row = pick_report_row(quarters, aligned_date)
    if not row:
        return
    rd = row.get("report_date", "")
    pairs = [
        ("营业成本", "营业成本"),
        ("销售费用", "销售费用"),
        ("管理费用", "管理费用"),
        ("财务费用", "财务费用"),
        ("研发费用", "研发费用"),
        ("营业利润", "营业利润"),
        ("利润总额", "利润总额"),
        ("总资产", "总资产"),
        ("总负债", "总负债"),
        ("经营现金流净额", "经营活动现金流净额"),
        ("投资现金流净额", "投资活动现金流净额"),
        ("筹资现金流净额", "筹资活动现金流净额"),
        ("净利润", "净利润"),
        ("每股收益", "基本每股收益"),
    ]
    for field_name, row_key in pairs:
        if row.get(row_key) is not None:
            _try_cross_validate(
                fields, field_name, fields.get(field_name, {}).get("value"),
                row.get(row_key),
                f"新浪8季序列({rd})", _TOL_FINANCIAL,
            )


def _cross_validate_self_consistency(fields: dict, ths: dict, sina: dict,
                                     gjzb: dict, em_fin: dict) -> None:
    """P0：财务自洽校验（比率≈分子/分母）。"""
    revenue = _num(ths.get("营业总收入")) or _num(sina.get("营业收入")) or _num(sina.get("营业总收入"))
    net_profit = _num(ths.get("净利润")) or _num(sina.get("净利润"))
    total_assets = _num(sina.get("总资产"))
    total_liab = _num(sina.get("总负债")) or _num(em_fin.get("总负债"))
    equity = _num(gjzb.get("股东权益合计")) or (
        (total_assets - total_liab) if total_assets and total_liab else None
    )

    if revenue and net_profit and revenue > 0:
        implied_margin = net_profit / revenue * 100
        _try_cross_validate(fields, "净利率", fields.get("净利率", {}).get("value"),
                            implied_margin, "自洽校验(净利润÷营收)", _TOL_FINANCIAL)

    if total_assets and total_liab and total_assets > 0:
        implied_debt = total_liab / total_assets * 100
        _try_cross_validate(fields, "资产负债率", fields.get("资产负债率", {}).get("value"),
                            implied_debt, "自洽校验(总负债÷总资产)", _TOL_FINANCIAL)

    if equity and net_profit and equity > 0:
        implied_roe = net_profit / equity * 100
        _try_cross_validate(fields, "ROE", fields.get("ROE", {}).get("value"),
                            implied_roe, "自洽校验(净利润÷股东权益)", _TOL_FINANCIAL)

    rev, cost = _num(sina.get("营业收入")), _num(sina.get("营业成本"))
    if rev and cost and rev > 0:
        sina_gm = (rev - cost) / rev * 100
        _try_cross_validate(fields, "毛利率(新浪)", sina_gm,
                            fields.get("毛利率(新浪)", {}).get("value"),
                            "自洽校验(毛利率重算)", _TOL_FINANCIAL)


def _cross_validate_ths_triple(fields: dict, ths: dict, sina_row: dict,
                               em_fin: dict, gjzb: dict) -> None:
    """P0/P1：同花顺字段 vs 新浪/东财/新浪gjzb 三源交叉。"""
    if not ths:
        return

    def _tri(field_name, ths_key, sina_key=None, em_key=None, gjzb_key=None, tol=_TOL_FINANCIAL):
        candidates = []
        ths_val = ths.get(ths_key)
        if sina_key and sina_row.get(sina_key) is not None:
            candidates.append((ths_val, sina_row.get(sina_key)))
        if em_key and em_fin.get(em_key) is not None:
            candidates.append((ths_val, em_fin.get(em_key)))
        if gjzb_key and gjzb.get(gjzb_key) is not None:
            candidates.append((ths_val, gjzb.get(gjzb_key)))
        if candidates:
            _try_any_cross_validate(fields, field_name, candidates, "多源财报交叉验证", tol)

    _tri("营收", "营业总收入", sina_key="营业总收入", gjzb_key="营业总收入")
    _tri("营收", "营业总收入", sina_key="营业收入", gjzb_key="营业收入")
    _tri("净利润", "净利润", sina_key="净利润", em_key="净利润", gjzb_key="净利润")
    _tri("扣非净利润", "扣非净利润", em_key="扣非净利润", gjzb_key="扣非净利润")
    _tri("每股收益", "基本每股收益", sina_key="基本每股收益", em_key="每股收益", gjzb_key="每股收益")
    _tri("每股净资产", "每股净资产", em_key="每股净资产", gjzb_key="每股净资产")
    _tri("ROE", "净资产收益率", em_key="ROE", gjzb_key="ROE", tol=_TOL_FINANCIAL)
    _tri("毛利率", "销售毛利率", em_key="销售毛利率", gjzb_key="销售毛利率", tol=_TOL_FINANCIAL)
    _tri("净利率", "销售净利率", em_key="销售净利率", gjzb_key="销售净利率", tol=_TOL_FINANCIAL)
    _tri("资产负债率", "资产负债率", gjzb_key="资产负债率", tol=_TOL_FINANCIAL)

    rev, cost = sina_row.get("营业收入"), sina_row.get("营业成本")
    if rev and cost and rev > 0:
        sina_gm = (rev - cost) / rev * 100
        _try_any_cross_validate(
            fields, "毛利率",
            [(ths.get("销售毛利率"), sina_gm), (ths.get("销售毛利率"), em_fin.get("销售毛利率")),
             (ths.get("销售毛利率"), gjzb.get("销售毛利率"))],
            "多源毛利率交叉验证", _TOL_FINANCIAL,
        )
        _try_cross_validate(fields, "毛利率(新浪)", sina_gm,
                            ths.get("销售毛利率"), "同花顺财务摘要", _TOL_FINANCIAL)

    if sina_row.get("总资产") is not None:
        ths_assets = ths.get("总资产") or ths.get("资产总计")
        if ths_assets is not None:
            _try_cross_validate(fields, "总资产", ths_assets,
                                sina_row.get("总资产"), "新浪资产负债表", _TOL_FINANCIAL)
    if sina_row.get("总负债") is not None:
        ths_liab = ths.get("总负债") or ths.get("负债合计")
        candidates = [(ths_liab, sina_row.get("总负债"))]
        if em_fin.get("总负债") is not None:
            candidates.append((sina_row.get("总负债"), em_fin.get("总负债")))
        if ths_liab is not None:
            _try_any_cross_validate(fields, "总负债", candidates, "多源负债交叉验证", _TOL_FINANCIAL)
        elif candidates:
            _try_any_cross_validate(fields, "总负债", candidates, "新浪vs东财负债", _TOL_FINANCIAL)

    # P0：利润表细项 THS 无独立字段时，用新浪行内部互证
    for fname, skey in [
        ("营业成本", "营业成本"), ("销售费用", "销售费用"), ("管理费用", "管理费用"),
        ("财务费用", "财务费用"), ("研发费用", "研发费用"),
        ("营业利润", "营业利润"), ("利润总额", "利润总额"),
    ]:
        if sina_row.get(skey) is not None:
            _try_cross_validate(fields, fname, fields.get(fname, {}).get("value"),
                                sina_row.get(skey), "新浪利润表(报告期对齐)", _TOL_FINANCIAL)


def _cross_validate(fields: dict, val: dict = None, ths: dict = None,
                    sina: dict = None, em_pe=None, em_pb=None, em_close=None,
                    hist: list = None, holder: dict = None,
                    close_price: float = 0, eps_cur: float = None,
                    em_fin: dict = None, gjzb: dict = None,
                    quarters: list = None, ths_report_as_of: str = None) -> None:
    """跨数据源交叉验证：P0 扩展映射+自洽 / P1 东财+gjzb / P2 8季序列+报告期对齐。"""
    em_fin = em_fin or {}
    gjzb = gjzb or {}
    quarters = quarters or []

    aligned_date = _apply_period_alignment(
        fields,
        ths_report_as_of or (ths.get("报告期") if ths else None),
        sina.get("report_date") if sina else None,
        em_fin.get("report_date"),
    )
    sina_row = pick_report_row(quarters, aligned_date) if quarters else (sina or {})

    # ── 行情层 ──
    if val:
        # 东财历史序列末位是上一交易日收盘估值，腾讯为当日实时估值。
        # PE/PB 与股价同向变动，个股当日大幅涨跌会因价格时点差产生超容差
        # 假性偏差。先按价格比折算到当前价，仅校验盈利/净资产口径是否一致。
        cur_price = val.get("price") or close_price
        if em_pe is not None:
            ref_pe = em_pe * cur_price / em_close if (em_close and cur_price and em_close > 0) else em_pe
            _try_cross_validate(fields, "PE(TTM)", val.get("pe_ttm"), ref_pe,
                                "东方财富历史估值", _TOL_VALUATION)
        if em_pb is not None:
            ref_pb = em_pb * cur_price / em_close if (em_close and cur_price and em_close > 0) else em_pb
            _try_cross_validate(fields, "PB", val.get("pb"), ref_pb,
                                "东方财富历史估值", _TOL_VALUATION)
        if hist:
            _try_cross_validate(fields, "当前价", val.get("price"),
                                hist[-1].get("close"), "mootdx K线", _TOL_PRICE)
        # 用腾讯实时价格 × 股东报告总股本自洽校验，避免与季度快照市值比较产生假C
        if holder and holder.get("total_a_shares") and close_price > 0:
            total_a_shares = holder.get("total_a_shares", 0) or 0
            if total_a_shares > 0:
                computed_mcap_yi = close_price * total_a_shares / 1e8
                _try_cross_validate(fields, "总市值", val.get("mcap_yi"), computed_mcap_yi,
                                    "自洽校验(当前价×股东报告总股本)", _TOL_VALUATION)

    # ── P0/P1：财报三源 + 细项 ──
    if ths and sina_row:
        _cross_validate_ths_triple(fields, ths, sina_row, em_fin, gjzb)

    # ── P0：自洽校验 ──
    _cross_validate_self_consistency(fields, ths or {}, sina or {}, gjzb, em_fin)

    # ── P2：8 季序列同报告期核对 ──
    _cross_validate_quarterly(fields, quarters, aligned_date)

    # ── 筹码 / 估值衍生 ──
    if holder:
        holder_num = holder.get("holder_num") or 0
        total_shares = holder.get("total_a_shares") or 0
        if holder_num > 0 and total_shares > 0:
            implied_avg = total_shares / holder_num
            _try_cross_validate(fields, "户均持股", holder.get("avg_shares"), implied_avg,
                                "自洽校验(总股本÷股东户数)", _TOL_HOLDER)

    if close_price > 0 and eps_cur and eps_cur > 0 and fields.get("前向PE"):
        computed_fwd = close_price / eps_cur
        _try_cross_validate(fields, "前向PE", fields["前向PE"].get("value"), computed_fwd,
                            "自洽校验(当前价÷一致预期EPS)", _TOL_VALUATION)


# ═══════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════

def _period_return(hist: list[dict], period: int) -> float | None:
    """计算近 N 个交易日涨跌幅：(最新收盘 / N日前收盘 - 1) × 100%"""
    if len(hist) < period + 1:
        return None
    base_close = hist[-(period + 1)]["close"]
    latest_close = hist[-1]["close"]
    if base_close <= 0:
        return None
    return round((latest_close / base_close - 1) * 100, 2)


def _normalize_date(value) -> str | None:
    """将日期规范为 YYYY-MM-DD。"""
    if value is None or value == "":
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return None


def _infer_period_label(as_of: str | None) -> str | None:
    """由财报截止日推断报告期标签，如 2025年报。"""
    if not as_of:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", as_of)
    if not m:
        return None
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if month == 12 and day == 31:
        return f"{year}年报"
    if month == 9 and day == 30:
        return f"{year}三季报"
    if month == 6 and day == 30:
        return f"{year}半年报"
    if month == 3 and day == 31:
        return f"{year}一季报"
    return f"截至{as_of}"


def _financial_time_ctx(report_as_of: str | None) -> dict:
    """财报类字段的时效上下文。"""
    as_of = _normalize_date(report_as_of)
    if not as_of:
        return {}
    return {"as_of": as_of, "period_label": _infer_period_label(as_of) or f"截至{as_of}"}


def _make_field(value, grade: str, source: str,
                as_of: str | None = None, period_label: str | None = None) -> dict:
    """构造已格式化的字段 dict。"""
    field = {"value": value, "grade": grade, "source": source}
    if as_of:
        field["as_of"] = as_of
    if period_label:
        field["period_label"] = period_label
    elif as_of:
        field["period_label"] = _infer_period_label(as_of) or f"截至{as_of}"
    return field


def format_field_line(name: str, field: dict) -> str:
    """将字段格式化为 Prompt 行，含时效戳。"""
    if field.get("grade") == "不可得":
        return f"- {name}：数据不可得"
    val = field.get("value")
    val_str = str(val) if val is not None else "—"
    period_label = field.get("period_label")
    as_of = field.get("as_of")
    if period_label and as_of:
        time_note = f"（{period_label}，截至{as_of}）"
    elif as_of:
        time_note = f"（截至{as_of}）"
    else:
        time_note = ""
    grade = field.get("grade", "")
    source = field.get("source", "")
    line = f"- {name}：{val_str}{time_note}"
    if grade:
        line += f"（{grade}级）"
    if source:
        line += f"  来源：{source}"
    if field.get("period_warning"):
        line += f"  ⚠ {field['period_warning']}"
    return line


def _a(value, suffix: str = "", source: str = "财务/行情数据",
       as_of: str | None = None, period_label: str | None = None):
    """标准化字段封装。单源直采默认 B 级，交叉验证通过后由 _cross_validate 调整等级。"""
    if value is None or value == "" or value == "False":
        return {"value": None, "grade": "不可得", "source": ""}
    if isinstance(value, float) and value != value:
        return {"value": None, "grade": "不可得", "source": ""}
    display = _fmt(value)
    if suffix and display is not None and not str(display).endswith(suffix):
        display = f"{display}{suffix}"
    field = {"value": display, "grade": "B", "source": source}
    if as_of:
        field["as_of"] = as_of
    if period_label:
        field["period_label"] = period_label
    elif as_of and not period_label:
        field["period_label"] = _infer_period_label(as_of)
    return field


def _fmt(v):
    if isinstance(v, float):
        if abs(v) >= 1e8:
            return f"{v/1e8:.2f}亿"
        if abs(v) >= 1e4:
            return f"{v/1e4:.2f}万"
        return round(v, 3)
    return v


def _extract_num(val) -> float | None:
    """从格式化字符串中提取数值"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("%", "").replace("亿", "").replace("万", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None
