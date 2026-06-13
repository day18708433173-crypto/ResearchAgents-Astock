"""策略条件解析与监控提醒"""

import json
import re
from datetime import datetime

from services.db_init import get_db
from services.market_data import get_valuation

# 接近阈值的比例（5%）
NEAR_THRESHOLD_PCT = 5.0


def _extract_section(text: str, heading: str) -> str:
    """提取 ### 标题 下的段落文本。"""
    pattern = rf"###\s*{re.escape(heading)}\s*\n([\s\S]*?)(?=\n###\s|\Z)"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def parse_strategy_triggers(strategy_text: str) -> list[dict]:
    """从策略正文解析可量化阈值（入场/退出）。"""
    if not strategy_text or not str(strategy_text).strip():
        return []

    text = str(strategy_text)
    triggers: list[dict] = []

    sections = [
        ("entry", _extract_section(text, "入场条件") or ""),
        ("exit", _extract_section(text, "退出/风控条件") or ""),
    ]
    # 兼容无 ### 标题的整段文本
    if not any(s[1] for s in sections):
        sections = [("entry", text), ("exit", text)]

    price_patterns = [
        (r"(?:价格|股价|现价|元/?股?)[^\d]{0,12}(?:低于|≤|<=|<|不高于|回落至|跌至)\s*(\d+(?:\.\d+)?)", "lte", "price"),
        (r"(?:价格|股价|现价|突破|高于|≥|>=|>|不低于)\s*(\d+(?:\.\d+)?)\s*(?:元|以上)?", "gte", "price"),
        (r"(?:止损|退出|风控)[^\d]{0,20}(\d+(?:\.\d+)?)\s*(?:元)?", "lte", "price"),
        (r"(\d+(?:\.\d+)?)\s*元[^\n]{0,8}(?:以下|下方|跌破)", "lte", "price"),
        (r"(\d+(?:\.\d+)?)\s*元[^\n]{0,8}(?:以上|突破|站上)", "gte", "price"),
    ]
    pe_patterns = [
        (r"(?:PE|市盈率|pe)[^\d]{0,12}(?:低于|≤|<=|<|回落至|跌至)\s*(\d+(?:\.\d+)?)", "lte", "pe_ttm"),
        (r"(?:PE|市盈率|pe)[^\d]{0,12}(?:高于|≥|>=|>|超过)\s*(\d+(?:\.\d+)?)", "gte", "pe_ttm"),
        (r"PE\s*(\d+(?:\.\d+)?)\s*(?:以下|下方)", "lte", "pe_ttm"),
    ]
    pb_patterns = [
        (r"(?:PB|市净率)[^\d]{0,12}(?:低于|≤|<=|<)\s*(\d+(?:\.\d+)?)", "lte", "pb"),
        (r"(?:PB|市净率)[^\d]{0,12}(?:高于|≥|>=|>)\s*(\d+(?:\.\d+)?)", "gte", "pb"),
    ]

    def _scan(section_type: str, section_text: str, patterns: list):
        for line in section_text.split("\n"):
            line = line.strip().lstrip("-•* ").strip()
            if not line:
                continue
            for pattern, condition, metric in patterns:
                for m in re.finditer(pattern, line, re.IGNORECASE):
                    try:
                        threshold = float(m.group(1))
                    except (ValueError, IndexError):
                        continue
                    if threshold <= 0:
                        continue
                    triggers.append({
                        "section": section_type,
                        "metric": metric,
                        "condition": condition,
                        "threshold": threshold,
                        "source_text": line[:120],
                    })

    for section_type, section_text in sections:
        if not section_text:
            continue
        _scan(section_type, section_text, price_patterns)
        _scan(section_type, section_text, pe_patterns)
        _scan(section_type, section_text, pb_patterns)

    # 去重（同 section/metric/condition/threshold）
    seen: set[tuple] = set()
    unique: list[dict] = []
    for t in triggers:
        key = (t["section"], t["metric"], t["condition"], t["threshold"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(t)
    return unique


def save_strategy_alerts(
    dossier_id: int,
    version_id: int,
    strategy_text: str,
) -> int:
    """解析策略并写入 strategy_alert 表，返回新建提醒数。"""
    triggers = parse_strategy_triggers(strategy_text)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE strategy_alert SET is_active = 0 WHERE dossier_id = ? AND version_id != ?",
        (dossier_id, version_id),
    )
    now = datetime.now().isoformat()
    count = 0
    for t in triggers:
        cursor.execute(
            """INSERT INTO strategy_alert
               (dossier_id, version_id, section, metric, condition_type,
                threshold, source_text, status, is_active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'watching', 1, ?, ?)""",
            (
                dossier_id,
                version_id,
                t["section"],
                t["metric"],
                t["condition"],
                t["threshold"],
                t["source_text"],
                now,
                now,
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def _metric_value(metric: str, valuation: dict, current_price: float) -> float | None:
    if metric == "price":
        return current_price if current_price > 0 else None
    if metric == "pe_ttm":
        v = valuation.get("pe_ttm") or 0
        return float(v) if v > 0 else None
    if metric == "pb":
        v = valuation.get("pb") or 0
        return float(v) if v > 0 else None
    return None


def _metric_label(metric: str) -> str:
    """指标中文名，用于提醒文案。"""
    labels = {
        "price": "股价",
        "pe_ttm": "PE(TTM)",
        "pb": "PB",
    }
    return labels.get(metric, metric)


def _evaluate_trigger(
    current: float, condition: str, threshold: float, metric: str = "price"
) -> tuple[str, str]:
    """返回 (status, message)。status: watching | near | triggered"""
    label = _metric_label(metric)
    unit = " 元" if metric == "price" else ""

    if condition == "lte":
        if current <= threshold:
            return "triggered", f"{label} 当前 {current:.2f}{unit} 已 ≤ 阈值 {threshold:.2f}{unit}"
        gap_pct = (current - threshold) / threshold * 100 if threshold > 0 else 999
        if gap_pct <= NEAR_THRESHOLD_PCT:
            return "near", f"{label} 当前 {current:.2f}{unit}，距阈值 {threshold:.2f}{unit} 仅 {gap_pct:.1f}%"
        return "watching", f"{label} 当前 {current:.2f}{unit}，阈值 {threshold:.2f}{unit}（≤触发）"
    if condition == "gte":
        if current >= threshold:
            return "triggered", f"{label} 当前 {current:.2f}{unit} 已 ≥ 阈值 {threshold:.2f}{unit}"
        gap_pct = (threshold - current) / threshold * 100 if threshold > 0 else 999
        if gap_pct <= NEAR_THRESHOLD_PCT:
            return "near", f"{label} 当前 {current:.2f}{unit}，距阈值 {threshold:.2f}{unit} 仅 {gap_pct:.1f}%"
        return "watching", f"{label} 当前 {current:.2f}{unit}，阈值 {threshold:.2f}{unit}（≥触发）"
    return "watching", ""


def check_strategy_alerts(
    dossier_id: int | None = None,
    stock_code: str | None = None,
    current_price: float | None = None,
    valuation: dict | None = None,
) -> list[dict]:
    """按需检查策略提醒，更新 status 并返回活跃提醒列表。"""
    conn = get_db()
    query = """SELECT sa.*, d.stock_code, d.stock_name
               FROM strategy_alert sa
               JOIN dossier d ON sa.dossier_id = d.dossier_id
               WHERE sa.is_active = 1"""
    params: list = []
    if dossier_id is not None:
        query += " AND sa.dossier_id = ?"
        params.append(dossier_id)
    rows = conn.execute(query, params).fetchall()

    if not rows:
        conn.close()
        return []

    code = (stock_code or "").split(".")[0]
    if not code and rows:
        code = (rows[0]["stock_code"] or "").split(".")[0]

    if valuation is None and code:
        valuation = get_valuation(code)
    valuation = valuation or {}

    if current_price is None and code:
        current_price = float(valuation.get("price") or 0)

    results: list[dict] = []
    now = datetime.now().isoformat()
    for row in rows:
        item = dict(row)
        metric = item.get("metric", "price")
        val = _metric_value(metric, valuation, float(current_price or 0))
        if val is None:
            item["status"] = "watching"
            item["message"] = f"暂无{_metric_label(metric)}数据，无法评估"
            results.append(item)
            continue

        status, message = _evaluate_trigger(
            val,
            item.get("condition_type", "lte"),
            float(item.get("threshold") or 0),
            metric,
        )
        item["status"] = status
        item["message"] = message
        item["current_value"] = val
        conn.execute(
            "UPDATE strategy_alert SET status = ?, updated_at = ? WHERE alert_id = ?",
            (status, now, item["alert_id"]),
        )
        results.append(item)

    conn.commit()
    conn.close()
    return results


def get_active_alerts_summary(dossier_ids: list[int] | None = None) -> dict:
    """批量检查所有活跃策略提醒，返回按卷宗聚合的摘要。"""
    conn = get_db()
    query = """SELECT sa.*, d.stock_code, d.stock_name
               FROM strategy_alert sa
               JOIN dossier d ON sa.dossier_id = d.dossier_id
               WHERE sa.is_active = 1"""
    params: list = []
    if dossier_ids:
        placeholders = ",".join("?" * len(dossier_ids))
        query += f" AND sa.dossier_id IN ({placeholders})"
        params.extend(dossier_ids)
    rows = conn.execute(query, params).fetchall()

    if not rows:
        conn.close()
        return {"alerts": [], "near_count": 0, "triggered_count": 0}

    codes = list({(r["stock_code"] or "").split(".")[0] for r in rows if r["stock_code"]})
    val_map: dict[str, dict] = {code: get_valuation(code) for code in codes if code}

    all_alerts: list[dict] = []
    now = datetime.now().isoformat()
    near_count = 0
    triggered_count = 0

    for row in rows:
        item = dict(row)
        code = (item["stock_code"] or "").split(".")[0]
        val = val_map.get(code, {})
        price = float(val.get("price") or 0)
        metric = item.get("metric", "price")
        val_current = _metric_value(metric, val, price)
        if val_current is None:
            item["status"] = "watching"
            item["message"] = f"暂无{_metric_label(metric)}数据，无法评估"
            item["current_value"] = None
        else:
            status, message = _evaluate_trigger(
                val_current,
                item.get("condition_type", "lte"),
                float(item.get("threshold") or 0),
                metric,
            )
            item["status"] = status
            item["message"] = message
            item["current_value"] = val_current
            conn.execute(
                "UPDATE strategy_alert SET status = ?, updated_at = ? WHERE alert_id = ?",
                (status, now, item["alert_id"]),
            )
            if status == "near":
                near_count += 1
            elif status == "triggered":
                triggered_count += 1
        all_alerts.append(item)

    conn.commit()
    conn.close()
    return {
        "alerts": all_alerts,
        "near_count": near_count,
        "triggered_count": triggered_count,
    }


def parse_strategy_content_json(raw) -> str:
    """从 strategy_content JSON 提取 current_strategy 文本。"""
    if not raw:
        return ""
    if isinstance(raw, dict):
        return raw.get("current_strategy") or raw.get("coach_conclusion") or ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed.get("current_strategy") or parsed.get("coach_conclusion") or ""
    except (json.JSONDecodeError, TypeError):
        pass
    return str(raw)
