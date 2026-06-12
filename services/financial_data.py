"""新浪财报三表客户端 — 资产负债表/利润表/现金流量表"""
import requests


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Sina item_field → 标准字段名映射
_LRB_MAP = {
    "BIZTOTINCO": "营业总收入",
    "BIZINCO": "营业收入",
    "BIZCOST": "营业成本",
    "BIZTOTCOST": "营业总成本",
    "SALESEXPE": "销售费用",
    "MANAEXPE": "管理费用",
    "FINEXPE": "财务费用",
    "DEVEEXPE": "研发费用",
    "BIZTAX": "营业税金及附加",
    "PERPROFIT": "营业利润",
    "TOTPROFIT": "利润总额",
    "NETPROFIT": "净利润",
    "PARENETP": "归属母公司净利润",
    "BASICEPS": "基本每股收益",
    "DILUTEDEPS": "稀释每股收益",
    "INVEINCO": "投资收益",
    "INCOTAXEXPE": "所得税费用",
}

_FZB_MAP = {
    "TOTASSET": "总资产",
    "TOTLIAB": "总负债",
    "CURRASSETS": "流动资产",
    "CURRLIAB": "流动负债",
    "INVENTORY": "存货",
    "ACCTRECV": "应收账款",
    "MONYFUND": "货币资金",
    "FIXEDASSET": "固定资产",
    "TOTEQUY": "股东权益",
    "PARESHARRIGH": "归属母公司股东权益",
}

_LLB_MAP = {
    "MANANETR": "经营活动现金流净额",
    "INVNETCASHFLOW": "投资活动现金流净额",
    "FINNETCFLOW": "筹资活动现金流净额",
    "CASHNETR": "现金净增加额",
    "BIZCASHINFL": "经营活动现金流入",
    "BIZCASHOUTF": "经营活动现金流出",
}


def _secu_code(code: str) -> str:
    """6 开头 → .SH，其余 → .SZ"""
    return f"{code}.{'SH' if code.startswith('6') else 'SZ'}"


def _normalize_report_date(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return None


def _sina_report(code: str, report_type: str, num: int = 8) -> list[dict]:
    """新浪财报通用请求。
    report_type: "fzb"(资产负债表) / "lrb"(利润表) / "llb"(现金流量表)
    返回 [{report_date, field_name: value, ...}]
    """
    prefix = "sh" if code.startswith("6") else "sz"
    paper_code = f"{prefix}{code}"
    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {
        "paperCode": paper_code,
        "source": report_type,
        "type": "0",
        "page": "1",
        "num": str(num),
    }
    headers = {"User-Agent": UA}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        d = r.json()
        report_list = d.get("result", {}).get("data", {}).get("report_list", {})
    except Exception:
        return []

    if not isinstance(report_list, dict):
        return []

    # 按日期排序（新到旧）
    map_table = {"lrb": _LRB_MAP, "fzb": _FZB_MAP, "llb": _LLB_MAP}.get(report_type, {})
    results = []
    for date_key in sorted(report_list.keys(), reverse=True):
        entry = report_list[date_key]
        items = entry.get("data", [])
        if not isinstance(items, list):
            continue
        row = {"report_date": date_key}
        for item in items:
            field_code = item.get("item_field", "")
            field_name = map_table.get(field_code)
            if field_name:
                val = item.get("item_value")
                row[field_name] = float(val) if val and val != "None" else None
        results.append(row)
    return results


def get_income_statement(code: str) -> list[dict]:
    """利润表。最新在前。"""
    return _sina_report(code, "lrb")


def get_balance_sheet(code: str) -> list[dict]:
    """资产负债表。最新在前。"""
    return _sina_report(code, "fzb")


def get_cash_flow(code: str) -> list[dict]:
    """现金流量表。最新在前。"""
    return _sina_report(code, "llb")


def get_latest_financials(code: str) -> dict:
    """获取最新一期财报核心数据汇总。

    并行请求利润表、资产负债表、现金流量表（3个独立API），
    将原来 ~3-6s 的串行调用压缩到 ~1-2s。
    返回字段见 _LRB_MAP, _FZB_MAP, _LLB_MAP 中的映射。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    result = {}

    def _fetch_one(report_type: str):
        """包装单个报表请求，返回 (report_type, data_list) 或 (report_type, None)"""
        try:
            return (report_type, _sina_report(code, report_type))
        except Exception:
            return (report_type, None)

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_fetch_one, "lrb"): "lrb",
            pool.submit(_fetch_one, "fzb"): "fzb",
            pool.submit(_fetch_one, "llb"): "llb",
        }
        reports = {}
        for future in as_completed(futures):
            rt, data = future.result()
            reports[rt] = data

    # 按顺序合并（利润表优先，可为后续衍生计算提供基础字段）
    report_date = None
    for rt in ("lrb", "fzb", "llb"):
        data = reports.get(rt)
        if data and len(data) > 0:
            if report_date is None:
                report_date = data[0].get("report_date")
            for k, v in data[0].items():
                if k != "report_date":
                    result[k] = v

    if report_date:
        result["report_date"] = _normalize_report_date(report_date)

    return result


def _merge_quarterly_rows(lrb: list[dict], fzb: list[dict], llb: list[dict]) -> list[dict]:
    """按 report_date 合并三表为多期财报行（新→旧）。"""
    by_date: dict[str, dict] = {}

    def _ingest(rows: list[dict] | None):
        if not rows:
            return
        for row in rows:
            rd = _normalize_report_date(row.get("report_date"))
            if not rd:
                continue
            bucket = by_date.setdefault(rd, {"report_date": rd})
            for k, v in row.items():
                if k != "report_date" and v is not None:
                    bucket[k] = v

    _ingest(lrb)
    _ingest(fzb)
    _ingest(llb)
    return [by_date[k] for k in sorted(by_date.keys(), reverse=True)]


def get_financial_bundle(code: str, num: int = 8) -> dict:
    """一次拉取新浪三表 + 8 季合并序列（供数据卡交叉验证与报告期对齐）。

    返回: {latest: dict, quarters: list[dict], report_date: str|None}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _fetch(rt: str):
        try:
            return rt, _sina_report(code, rt, num=num)
        except Exception:
            return rt, []

    reports: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_fetch, rt) for rt in ("lrb", "fzb", "llb")]
        for fut in futures:
            rt, data = fut.result()
            reports[rt] = data or []

    quarters = _merge_quarterly_rows(reports.get("lrb"), reports.get("fzb"), reports.get("llb"))
    latest = dict(quarters[0]) if quarters else {}
    return {
        "latest": latest,
        "quarters": quarters,
        "report_date": latest.get("report_date"),
    }


def pick_report_row(quarters: list[dict], target_date: str | None) -> dict | None:
    """从 8 季序列中选取与目标报告期一致的行。"""
    target = _normalize_report_date(target_date)
    if not target or not quarters:
        return quarters[0] if quarters else None
    for row in quarters:
        if _normalize_report_date(row.get("report_date")) == target:
            return row
    return quarters[0]


def get_em_latest_indicators(code: str) -> dict:
    """东财 F10 主要指标（第三数据源）。失败返回空 dict。"""
    try:
        import akshare as ak
        df = ak.stock_financial_analysis_indicator_em(
            symbol=_secu_code(code), indicator="按报告期",
        )
        if df is None or len(df) == 0:
            return {}
        row = df.iloc[0]
        rd = _normalize_report_date(row.get("REPORT_DATE"))
        return {
            "report_date": rd,
            "净利润": row.get("PARENTNETPROFIT"),
            "扣非净利润": row.get("KCFJCXSYJLR"),
            "每股收益": row.get("EPSJB"),
            "每股净资产": row.get("BPS"),
            "ROE": row.get("ROEJQ"),
            "销售毛利率": row.get("XSMLL"),
            "销售净利率": row.get("XSJLL"),
            "总负债": row.get("LIABILITY"),
        }
    except Exception:
        return {}


_GJZB_FIELD_MAP = {
    "PARENETP": "归属母公司净利润",
    "NETPROFIT": "净利润",
    "NPCUT": "扣非净利润",
    "EPSBASIC": "每股收益",
    "NAPS": "每股净资产",
    "ROEWEIGHTED": "ROE",
    "SGPMARGIN": "销售毛利率",
    "SNPMARGINCONMS": "销售净利率",
    "ASSLIABRT": "资产负债率",
    "BIZTOTINCO": "营业总收入",
    "BIZINCO": "营业收入",
    "RIGHAGGR": "股东权益合计",
    "MANANETR": "经营活动现金流净额",
}


def get_sina_gjzb_latest(code: str) -> dict:
    """新浪关键指标 gjzb（第三数据源，含 ROE/扣非等）。"""
    prefix = "sh" if code.startswith("6") else "sz"
    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {
        "paperCode": f"{prefix}{code}",
        "source": "gjzb",
        "type": "0",
        "page": "1",
        "num": "3",
    }
    headers = {"User-Agent": UA}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        report_list = (
            r.json().get("result", {}).get("data", {}).get("report_list", {})
        )
        if not isinstance(report_list, dict) or not report_list:
            return {}
        latest_key = sorted(report_list.keys(), reverse=True)[0]
        row = {"report_date": _normalize_report_date(latest_key)}
        for item in report_list[latest_key].get("data", []):
            field = _GJZB_FIELD_MAP.get(item.get("item_field", ""))
            if not field:
                continue
            val = item.get("item_value")
            try:
                row[field] = float(val) if val not in (None, "", "None") else None
            except (TypeError, ValueError):
                pass
        return row
    except Exception:
        return {}
