"""镜衡 Backend — 共享工具函数（卷宗、持仓、策略教练）"""

import json
import logging
import re
from datetime import datetime, timedelta

from services.db_init import get_db, _table_columns
from services.commission import build_trading_metrics, get_dossier_commission
from services.market_data import get_realtime_price, get_realtime_prices_batch
from modules.debate.agents import build_coach_prompt

from backend.schemas import (
    CoachChatRequest,
    StrategyCreateRequest,
    StrategyCreateResponse,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
#  卷宗 / 持仓
# ═══════════════════════════════════════════════

def _delete_dossier_cascade(conn, dossier_id: int) -> bool:
    """删除卷宗及关联的策略、交易、提醒等数据。"""
    dossier = conn.execute(
        "SELECT dossier_id FROM dossier WHERE dossier_id = ?", (dossier_id,)
    ).fetchone()
    if not dossier:
        return False

    # alert 表引用 strategy_version，须先于策略版本删除
    for table in ("alert", "alert_rule", "strategy_alert"):
        if conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone():
            conn.execute(f"DELETE FROM {table} WHERE dossier_id = ?", (dossier_id,))

    version_rows = conn.execute(
        "SELECT version_id FROM strategy_version WHERE dossier_id = ?", (dossier_id,)
    ).fetchall()
    version_ids = [row[0] for row in version_rows]
    if version_ids:
        placeholders = ",".join("?" * len(version_ids))
        conn.execute(
            f"DELETE FROM strategy_change_reason WHERE version_id IN ({placeholders})",
            version_ids,
        )

    conn.execute("DELETE FROM strategy_version WHERE dossier_id = ?", (dossier_id,))
    conn.execute('DELETE FROM "transaction" WHERE dossier_id = ?', (dossier_id,))

    if "dossier_id" in _table_columns(conn, "debate_record"):
        conn.execute("DELETE FROM debate_record WHERE dossier_id = ?", (dossier_id,))

    if "dossier_id" in _table_columns(conn, "agent_conversation"):
        conn.execute("DELETE FROM agent_conversation WHERE dossier_id = ?", (dossier_id,))

    conn.execute("DELETE FROM dossier WHERE dossier_id = ?", (dossier_id,))
    return True


def _calculate_position(transactions: list, dossier: dict) -> dict:
    """根据交易记录计算持仓推算（含佣金成本）"""
    commission_min, commission_rate = get_dossier_commission(dossier)
    metrics = build_trading_metrics(transactions, commission_min, commission_rate)
    summary = metrics["position_summary"]

    db_shares = dossier.get("current_hold_shares")
    if db_shares is not None:
        summary["current_shares"] = db_shares
    return enrich_position_with_market(summary, dossier.get("stock_code", ""))


def enrich_position_with_market(position_summary: dict, stock_code: str) -> dict:
    """用实时市价补充持仓：现价、市值、浮动盈亏。"""
    if not position_summary:
        return position_summary

    code = (stock_code or "").split(".")[0]
    current_price = get_realtime_price(code) if code else 0.0
    shares = int(position_summary.get("current_shares") or 0)
    total_cost = float(position_summary.get("total_cost") or 0)

    position_summary["current_price"] = round(current_price, 2) if current_price > 0 else 0
    position_summary["price_source"] = "tencent_realtime"
    position_summary["price_updated_at"] = datetime.now().isoformat()

    if shares > 0 and current_price > 0:
        market_value = round(shares * current_price, 2)
        unrealized = round(market_value - total_cost, 2)
        unrealized_pct = round(unrealized / total_cost * 100, 2) if total_cost > 0 else 0.0
        position_summary["market_value"] = market_value
        position_summary["unrealized_profit"] = unrealized
        position_summary["unrealized_profit_pct"] = unrealized_pct
        cost_basis = float(position_summary.get("cost_basis") or 0)
        if cost_basis > 0:
            position_summary["holding_return_pct"] = round(
                (current_price - cost_basis) / cost_basis * 100, 2
            )
        else:
            position_summary["holding_return_pct"] = 0.0
    else:
        position_summary["market_value"] = 0.0
        position_summary["unrealized_profit"] = 0.0
        position_summary["unrealized_profit_pct"] = 0.0
        position_summary["holding_return_pct"] = 0.0
        if shares > 0:
            position_summary["price_unavailable"] = True

    return position_summary


def compute_portfolio_summary(dossiers: list[dict], position_map: dict[int, dict]) -> dict:
    """聚合所有卷宗的投资组合概览（含实时市值）。"""
    codes = []
    for dossier in dossiers:
        code = (dossier.get("stock_code") or "").split(".")[0]
        if code:
            codes.append(code)
    price_map = get_realtime_prices_batch(list(dict.fromkeys(codes)))

    total_buy_deployment = 0.0
    total_realized_profit = 0.0
    total_market_value = 0.0
    total_unrealized_profit = 0.0
    items: list[dict] = []

    for dossier in dossiers:
        dossier_id = dossier["dossier_id"]
        pos = dict(position_map.get(dossier_id) or {})
        code = (dossier.get("stock_code") or "").split(".")[0]
        current_price = float(price_map.get(code, 0))
        shares = int(pos.get("current_shares") or dossier.get("current_hold_shares") or 0)
        total_cost = float(pos.get("total_cost") or 0)
        buy_deployment = float(pos.get("total_buy_deployment") or pos.get("total_buy_amount") or 0)
        realized = float(pos.get("realized_profit") or 0)

        market_value = round(shares * current_price, 2) if shares > 0 and current_price > 0 else 0.0
        unrealized = round(market_value - total_cost, 2) if shares > 0 else 0.0

        total_buy_deployment += buy_deployment
        total_realized_profit += realized
        total_market_value += market_value
        total_unrealized_profit += unrealized

        items.append({
            "dossier_id": dossier_id,
            "stock_code": dossier.get("stock_code", ""),
            "stock_name": dossier.get("stock_name", ""),
            "current_shares": shares,
            "current_price": round(current_price, 2),
            "market_value": market_value,
            "realized_profit": round(realized, 2),
            "unrealized_profit": unrealized,
            "buy_deployment": round(buy_deployment, 2),
        })

    grand_total = total_market_value + total_realized_profit
    for item in items:
        item["weight_pct"] = round(
            item["market_value"] / total_market_value * 100, 1
        ) if total_market_value > 0 else 0.0

    return {
        "total_buy_deployment": round(total_buy_deployment, 2),
        "total_realized_profit": round(total_realized_profit, 2),
        "total_market_value": round(total_market_value, 2),
        "total_unrealized_profit": round(total_unrealized_profit, 2),
        "total_assets": round(grand_total, 2),
        "items": items,
        "updated_at": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════════
#  策略教练
# ═══════════════════════════════════════════════

def _build_coach_debate_summary(request: CoachChatRequest) -> str:
    """从请求中构建辩论轮次摘要（裁判裁决由 build_coach_prompt 单独注入）。"""
    fallback = request.debate_summary or ""
    if not request.debate_result:
        return fallback

    rounds = request.debate_result.get("rounds", [])
    if not rounds:
        return fallback

    selected = rounds if len(rounds) <= 3 else rounds[-3:]
    summary_parts = [f"共 {len(rounds)} 轮辩论"]
    for i, rd in enumerate(selected):
        round_num = rd.get("round") or (len(rounds) - len(selected) + i + 1)
        bull = rd.get("bull_content") or rd.get("bull") or ""
        bear = rd.get("bear_content") or rd.get("bear") or ""
        char_limit = 500 if i == len(selected) - 1 else 320
        if bull:
            summary_parts.append(f"第{round_num}轮多头：{str(bull)[:char_limit]}")
        if bear:
            summary_parts.append(f"第{round_num}轮空头：{str(bear)[:char_limit]}")
    return "\n".join(summary_parts)


def _prepare_coach_prompts(request: CoachChatRequest) -> tuple[str, str, str]:
    """构建教练 system/user prompt，并返回 user_input。"""
    debate_summary = _build_coach_debate_summary(request)
    data_card = None
    judge = None
    if request.debate_result:
        data_card = request.debate_result.get("data_card")
        judge = request.debate_result.get("judge")
    history = [m.dict() if hasattr(m, "dict") else m for m in request.messages]
    user_input = ""
    if history and history[-1].get("role") == "user":
        user_input = history[-1].get("content", "")
    system_prompt, user_prompt = build_coach_prompt(
        state=request.state,
        ticker=request.ticker,
        ticker_name=request.ticker_name,
        debate_summary=debate_summary,
        user_input=user_input,
        history=history[:-1] if history and history[-1].get("role") == "user" else history,
        data_card=data_card,
        judge=judge,
    )
    return system_prompt, user_prompt, user_input


COACH_SAVE_PHRASES = ("保存当前策略", "确认保存策略")
COACH_SAVE_SUCCESS_REPLY = "保存成功，如果之后有什么思路也可以继续找我探讨。"


def _is_coach_save_intent(user_input: str) -> bool:
    return bool(user_input and any(p in user_input for p in COACH_SAVE_PHRASES))


def _is_coach_chitchat_line(line: str) -> bool:
    """判断是否为策略块外的寒暄、引导追问或编号列表。"""
    import re

    s = line.strip()
    if not s:
        return False
    if re.match(r"^\d+\.\s", s):
        return True
    if s.endswith("？") or s.endswith("?"):
        return True
    chitchat_keywords = (
        "以上就是", "初步策略", "继续深挖", "路线图", "随时保存",
        "告诉我你想", "往哪个方向", "探讨几件事", "操作参考",
    )
    if any(k in s for k in chitchat_keywords):
        return True
    if s.endswith("：") or s.endswith(":"):
        colon_prefixes = ("如果", "接下来", "欢迎", "你可以", "告诉", "以上", "想")
        if any(s.startswith(p) for p in colon_prefixes):
            return True
    prefixes = (
        "还有什么", "欢迎", "如果", "你可以", "需要我", "随时", "接下来",
        "以上", "希望这", "请告诉我", "想深入讨论", "可以继续追问", "告诉我",
    )
    return any(s.startswith(p) for p in prefixes)


def _extract_current_strategy_block(text: str) -> str:
    """从教练回复中提取「## 当前策略」块，去掉开场白与末尾追问。"""
    if not text or not str(text).strip():
        return ""
    text = str(text).strip()
    for marker in ("## 当前策略", "##当前策略"):
        idx = text.find(marker)
        if idx < 0:
            continue
        lines = text[idx:].split("\n")
        kept: list[str] = []
        for i, line in enumerate(lines):
            if i > 0 and line.startswith("## ") and not line.startswith("### "):
                break
            if i > 0 and _is_coach_chitchat_line(line):
                break
            kept.append(line)
        while kept and not kept[-1].strip():
            kept.pop()
        while kept and _is_coach_chitchat_line(kept[-1]):
            kept.pop()
            while kept and not kept[-1].strip():
                kept.pop()
        block = "\n".join(kept).strip()
        if block:
            return block
    return ""


def _extract_coach_strategy_content(request: CoachChatRequest) -> str:
    """从教练对话历史中提取待保存的「当前策略」正文。"""
    history = [m.dict() if hasattr(m, "dict") else m for m in request.messages]
    if history and history[-1].get("role") == "user":
        history = history[:-1]
    keywords = (
        "## 当前策略", "##当前策略", "策略已更新",
        "### 质量×价格判断", "### 入场条件", "### 退出/风控条件",
    )
    for msg in reversed(history):
        if msg.get("role") != "coach":
            continue
        content = (msg.get("content") or "").strip()
        if not content or not any(k in content for k in keywords):
            continue
        block = _extract_current_strategy_block(content)
        if block:
            return block
    return ""


def _create_strategy_version_impl(request: StrategyCreateRequest) -> StrategyCreateResponse:
    """创建策略版本（供 API 与教练保存共用）。"""
    conn = get_db()
    cursor = conn.cursor()

    dossier_id = request.dossier_id
    if not dossier_id:
        existing_dossier = cursor.execute(
            "SELECT dossier_id FROM dossier WHERE stock_code = ?", (request.ticker,)
        ).fetchone()
        if existing_dossier:
            dossier_id = existing_dossier[0]
        else:
            cursor.execute(
                "INSERT INTO dossier (stock_code, stock_name) VALUES (?, ?)",
                (request.ticker, request.ticker_name),
            )
            dossier_id = cursor.lastrowid

    raw = (request.current_strategy or request.coach_conclusion or "").strip()
    current_strategy = _extract_current_strategy_block(raw) or raw
    if not current_strategy:
        conn.close()
        raise ValueError("策略内容为空")

    strategy_content = {"current_strategy": current_strategy}

    cursor.execute(
        "SELECT MAX(version_number) FROM strategy_version WHERE dossier_id = ?",
        (dossier_id,),
    )
    max_version = cursor.fetchone()[0] or 0
    next_version = max_version + 1

    cursor.execute(
        """INSERT INTO strategy_version
           (dossier_id, version_number, is_active, strategy_content, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            dossier_id,
            next_version,
            1,
            json.dumps(strategy_content, ensure_ascii=False),
            datetime.now().isoformat(),
        ),
    )
    version_id = cursor.lastrowid
    cursor.execute(
        "UPDATE dossier SET current_strategy_version = ?, updated_at = ? WHERE dossier_id = ?",
        (next_version, datetime.now().isoformat(), dossier_id),
    )
    conn.commit()
    conn.close()

    from services.strategy_alerts import save_strategy_alerts

    triggers_count = save_strategy_alerts(dossier_id, version_id, current_strategy)

    return StrategyCreateResponse(
        version_id=version_id,
        dossier_id=dossier_id,
        created_at=datetime.now().isoformat(),
        message="策略版本已保存",
        quantifiable_triggers_count=triggers_count,
    )


def _persist_coach_strategy(request: CoachChatRequest) -> StrategyCreateResponse:
    """将教练对话中的策略写入卷宗。"""
    current_strategy = _extract_coach_strategy_content(request)
    if not current_strategy.strip():
        raise ValueError("暂无可保存的策略内容，请先与教练完成「当前策略」讨论")

    saved = _create_strategy_version_impl(StrategyCreateRequest(
        ticker=request.ticker,
        ticker_name=request.ticker_name,
        current_strategy=current_strategy,
    ))

    debate_id = request.debate_id
    if debate_id:
        conn = get_db()
        if "dossier_id" in _table_columns(conn, "debate_record"):
            conn.execute(
                "UPDATE debate_record SET dossier_id = ? WHERE id = ?",
                (saved.dossier_id, debate_id),
            )
            conn.commit()
        conn.close()

    return saved


def _coach_save_done_meta(saved: StrategyCreateResponse | None = None, error: str = "") -> dict:
    """保存策略后的教练元数据（简短回复，不再展开策略）。"""
    meta = {
        "state": "done",
        "can_confirm": True,
        "can_save_strategy": False,
        "suggested_questions": ["回到卷宗查看策略", "继续优化风险条件"],
        "reply": COACH_SAVE_SUCCESS_REPLY if not error else f"策略保存失败：{error}",
    }
    if saved:
        meta["dossier_id"] = saved.dossier_id
        meta["version_id"] = saved.version_id
    return meta


def _compute_coach_meta(request: CoachChatRequest, reply: str, user_input: str) -> dict:
    """根据回复计算教练状态机与建议问题。"""
    new_state = request.state
    can_confirm = False

    if user_input and ("保存当前策略" in user_input or "确认保存策略" in user_input):
        new_state = "done"
        can_confirm = True
    elif request.state in ("dimension_intro", "dimension_confirm"):
        new_state = "chatting"
    elif request.state == "opening":
        new_state = "chatting"
    elif request.state == "chatting":
        if user_input and ("确认" in user_input or "保存" in user_input or "总结" in user_input):
            new_state = "reviewing"
            can_confirm = True
    elif request.state == "reviewing":
        can_confirm = True
        if user_input and ("确认" in user_input or "保存" in user_input):
            new_state = "confirming"
    elif request.state == "confirming":
        new_state = "done"

    has_new_strategy = any(
        keyword in reply
        for keyword in ("## 当前策略", "策略已更新", "入场条件", "退出/风控", "持有观察点")
    )
    can_save_strategy = bool(has_new_strategy and new_state != "done")

    if new_state == "done":
        suggested_questions = ["继续优化风险条件", "回到卷宗查看策略"]
    elif request.state == "opening":
        suggested_questions = [
            "这个策略最大的风险是什么？",
            "现在价格是否值得入场？",
            "帮我把入场和退出条件写具体",
        ]
    elif can_save_strategy:
        suggested_questions = [
            "保存当前策略",
            "继续优化入场条件",
            "继续优化退出和风控条件",
        ]
    else:
        suggested_questions = [
            "这会如何改变入场条件？",
            "这会如何改变持有观察点？",
            "还缺哪些信息才能优化策略？",
        ]

    return {
        "state": new_state,
        "can_confirm": can_confirm,
        "suggested_questions": suggested_questions,
        "can_save_strategy": can_save_strategy,
    }


# ═══════════════════════════════════════════════
#  金融科普
# ═══════════════════════════════════════════════

def _parse_knowledge_context(context: str) -> tuple[str, str]:
    """将前端来源标签映射为 context_type 与详情。"""
    detail = (context or "").strip()
    if "多头" in detail:
        return "bull", detail
    if "空头" in detail:
        return "bear", detail
    if "裁判" in detail:
        return "judge", detail
    return "debate", detail


def _parse_knowledge_reply(reply: str) -> tuple[str, list[str]]:
    """从 LLM 回复中解析完整解释与相关术语。"""
    import re

    explanation = reply.strip()
    related_terms: list[str] = []

    term_match = re.search(r"###\s*相关术语\s*\n([^\n#]+)", reply)
    if term_match:
        related_terms = [
            t.strip()
            for t in re.split(r"[,，、]", term_match.group(1))
            if t.strip()
        ]

    return explanation, related_terms


# ═══════════════════════════════════════════════
#  工作台：观点过期 / 多空倾向 / 策略漂移 / 决策质量 / 盲点雷达
# ═══════════════════════════════════════════════

BULLISH_RATINGS = frozenset({"买入", "增持"})
BEARISH_RATINGS = frozenset({"减持", "卖出"})


def _normalize_ticker(ticker: str) -> str:
    return (ticker or "").strip().upper()


def _parse_judge_verdict(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00").split("+")[0])
    except ValueError:
        return None


def _days_between(start: datetime | None, end: datetime | None) -> int | None:
    if not start or not end:
        return None
    return max(0, (end.date() - start.date()).days)


def _rating_sentiment(rating: str) -> str:
    rating = (rating or "").strip()
    if rating in BULLISH_RATINGS:
        return "bull"
    if rating in BEARISH_RATINGS:
        return "bear"
    return "neutral"


def _extract_verdict_rating(judge: dict) -> str:
    rating = (judge.get("rating") or "持有").strip()
    return rating or "持有"


def _extract_strategy_text(strategy_content_raw) -> str:
    if not strategy_content_raw:
        return ""
    if isinstance(strategy_content_raw, dict):
        return (
            strategy_content_raw.get("current_strategy")
            or strategy_content_raw.get("coach_conclusion")
            or ""
        )
    try:
        parsed = json.loads(strategy_content_raw)
        if isinstance(parsed, dict):
            return parsed.get("current_strategy") or parsed.get("coach_conclusion") or ""
        return str(strategy_content_raw)
    except (json.JSONDecodeError, TypeError):
        return str(strategy_content_raw)


def _parse_stop_loss_price(strategy_text: str) -> float | None:
    if not strategy_text:
        return None
    patterns = [
        r"止损[^\d]{0,20}(\d+(?:\.\d+)?)",
        r"退出[^\d]{0,20}(\d+(?:\.\d+)?)",
        r"风控[^\d]{0,20}(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, strategy_text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def _compute_strategy_drift(strategy_content_raw, current_price: float, cost_basis: float) -> tuple[str, str]:
    text = _extract_strategy_text(strategy_content_raw)
    has_stop_keyword = any(k in text for k in ("止损", "退出", "风控"))
    stop_price = _parse_stop_loss_price(text)
    if not has_stop_keyword and stop_price is None:
        return "no_stop_defined", "策略未定义明确止损/退出条件"

    if current_price <= 0:
        return "no_stop_defined", "暂无实时价格，无法评估风控偏离"

    reference = stop_price
    if reference is None and cost_basis > 0:
        reference = round(cost_basis * 0.9, 2)
    if reference is None or reference <= 0:
        return "no_stop_defined", "未能解析止损价位"

    if current_price <= reference:
        return "triggered", f"现价 {current_price:.2f} 已触及风控参考位 {reference:.2f}"
    gap_pct = (current_price - reference) / current_price * 100
    if gap_pct <= 5:
        return "near_stop", f"距风控参考位 {reference:.2f} 仅 {gap_pct:.1f}%"
    return "none", ""


def _fetch_latest_debates_by_ticker(conn) -> dict[str, dict]:
    rows = conn.execute(
        """SELECT dr.*
           FROM debate_record dr
           INNER JOIN (
               SELECT ticker, MAX(created_at) AS max_created
               FROM debate_record
               GROUP BY ticker
           ) latest ON dr.ticker = latest.ticker AND dr.created_at = latest.max_created"""
    ).fetchall()
    result: dict[str, dict] = {}
    for row in rows:
        item = dict(row)
        result[_normalize_ticker(item.get("ticker", ""))] = item
    return result


def _fetch_last_debate_time_by_ticker(conn) -> dict[str, str]:
    rows = conn.execute(
        """SELECT ticker, MAX(created_at) AS last_debate_at
           FROM debate_record
           GROUP BY ticker"""
    ).fetchall()
    return {_normalize_ticker(row["ticker"]): row["last_debate_at"] for row in rows}


def compute_stale_alerts(dossiers: list[dict], last_debate_map: dict[str, str], now: datetime | None = None) -> dict:
    now = now or datetime.now()
    alerts = []
    critical_count = 0
    warning_count = 0

    for dossier in dossiers:
        stock_code = dossier.get("stock_code", "")
        hold_shares = int(dossier.get("current_hold_shares") or 0)
        last_at = last_debate_map.get(_normalize_ticker(stock_code))
        last_dt = _parse_iso_datetime(last_at)
        days = _days_between(last_dt, now)

        if hold_shares <= 0:
            level = "ok"
            message = "无持仓，观点更新压力较低"
        elif days is None:
            level = "critical"
            message = "持仓中但尚无辩论记录，建议尽快建立观点"
            critical_count += 1
        elif days > 30:
            level = "critical"
            message = f"持仓观点已 {days} 天未更新"
            critical_count += 1
        elif days >= 14:
            level = "warning"
            message = f"观点已 {days} 天未刷新，建议复盘"
            warning_count += 1
        else:
            level = "ok"
            message = f"观点较新（{days} 天内）"

        alerts.append({
            "dossier_id": dossier["dossier_id"],
            "stock_code": stock_code,
            "stock_name": dossier.get("stock_name", ""),
            "current_hold_shares": hold_shares,
            "days_since_debate": days,
            "last_debate_at": last_at,
            "level": level,
            "message": message,
        })

    alerts.sort(key=lambda x: (
        {"critical": 0, "warning": 1, "ok": 2}[x["level"]],
        -(x["days_since_debate"] or 9999),
    ))
    return {
        "alerts": alerts,
        "critical_count": critical_count,
        "warning_count": warning_count,
    }


def compute_blind_spot_radar(
    dossiers: list[dict],
    latest_debates: dict[str, dict],
    last_debate_map: dict[str, str],
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now()
    bullish_count = 0
    bearish_count = 0
    neutral_count = 0
    overdue_tickers: list[str] = []
    held_intervals: list[int] = []

    for dossier in dossiers:
        ticker = _normalize_ticker(dossier.get("stock_code", ""))
        hold_shares = int(dossier.get("current_hold_shares") or 0)
        debate = latest_debates.get(ticker)
        if debate:
            judge = _parse_judge_verdict(debate.get("judge_verdict"))
            sentiment = _rating_sentiment(judge.get("rating", ""))
            if sentiment == "bull":
                bullish_count += 1
            elif sentiment == "bear":
                bearish_count += 1
            else:
                neutral_count += 1

        if hold_shares > 0:
            last_at = last_debate_map.get(ticker)
            days = _days_between(_parse_iso_datetime(last_at), now)
            if days is not None:
                held_intervals.append(days)
            if days is None or days > 30:
                overdue_tickers.append(dossier.get("stock_name") or ticker)

    insights: list[dict] = []
    total_ratings = bullish_count + bearish_count + neutral_count
    if total_ratings > 0:
        bull_ratio = bullish_count / total_ratings * 100
        if bull_ratio >= 70:
            insights.append({
                "kind": "sentiment_skew",
                "severity": "warning",
                "message": f"近期裁决偏多（看多占比 {bull_ratio:.0f}%），可能存在确认偏误",
            })
        elif bull_ratio <= 30 and bearish_count > 0:
            insights.append({
                "kind": "sentiment_skew",
                "severity": "warning",
                "message": f"近期裁决偏空（看多占比 {bull_ratio:.0f}%），注意是否过度悲观",
            })
        else:
            insights.append({
                "kind": "sentiment_balance",
                "severity": "info",
                "message": f"多空裁决较为均衡（看多 {bullish_count} / 看空 {bearish_count} / 中性 {neutral_count}）",
            })

    if held_intervals:
        avg_days = round(sum(held_intervals) / len(held_intervals), 1)
        insights.append({
            "kind": "debate_cadence",
            "severity": "info" if avg_days <= 14 else "warning",
            "message": f"持仓标的平均 {avg_days} 天更新一次观点",
        })

    if overdue_tickers:
        preview = "、".join(overdue_tickers[:3])
        suffix = f" 等 {len(overdue_tickers)} 只" if len(overdue_tickers) > 3 else ""
        insights.append({
            "kind": "overdue_holdings",
            "severity": "critical",
            "message": f"持仓观点过期：{preview}{suffix}，建议优先复盘",
        })
    elif not insights:
        insights.append({
            "kind": "empty",
            "severity": "info",
            "message": "完成首次辩论后，这里会展示你的研究盲点提示",
        })

    return {
        "insights": insights,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "overdue_tickers": overdue_tickers,
    }


def compute_workspace_queue(
    dossiers: list[dict],
    latest_debates: dict[str, dict],
    price_map: dict[str, float],
    strategy_map: dict[int, str],
    position_map: dict[int, dict],
) -> list[dict]:
    queue = []
    for dossier in dossiers:
        ticker = _normalize_ticker(dossier.get("stock_code", ""))
        code_only = ticker.split(".")[0] if ticker else ""
        debate = latest_debates.get(ticker)
        judge = _parse_judge_verdict(debate.get("judge_verdict") if debate else None)
        rating = _extract_verdict_rating(judge)

        position = position_map.get(dossier["dossier_id"], {})
        cost_basis = float(position.get("cost_basis") or 0)
        current_price = float(price_map.get(code_only, 0))
        strategy_content = strategy_map.get(dossier["dossier_id"])
        drift_status, drift_message = _compute_strategy_drift(
            strategy_content, current_price, cost_basis
        )

        queue.append({
            "dossier_id": dossier["dossier_id"],
            "stock_code": dossier.get("stock_code", ""),
            "stock_name": dossier.get("stock_name", ""),
            "current_strategy_version": int(dossier.get("current_strategy_version") or 0),
            "current_hold_shares": int(dossier.get("current_hold_shares") or 0),
            "updated_at": dossier.get("updated_at", ""),
            "verdict_rating": rating,
            "drift_status": drift_status,
            "drift_message": drift_message,
        })
    return queue


def _evaluate_trade_decision(verdict_rating: str, direction: str, pnl_pct: float | None) -> tuple[bool, bool]:
    sentiment = _rating_sentiment(verdict_rating)
    trade_dir = direction.lower()
    pnl = pnl_pct if pnl_pct is not None else 0.0

    if trade_dir == "buy":
        aligned = sentiment != "bear"
        correct = aligned and sentiment == "bull"
        if sentiment == "neutral":
            correct = True
        return aligned, correct

    aligned = sentiment != "bull" or pnl > 0
    if sentiment == "bear":
        correct = pnl >= 0
    elif sentiment == "bull":
        correct = pnl > 0
    else:
        correct = pnl >= 0
    return aligned, correct


def compute_decision_quality(now: datetime | None = None, month_days: int = 30) -> dict:
    now = now or datetime.now()
    month_start = now - timedelta(days=month_days)
    conn = get_db()

    dossiers = [dict(row) for row in conn.execute("SELECT * FROM dossier").fetchall()]

    debates = conn.execute(
        "SELECT id, ticker, ticker_name, judge_verdict, created_at FROM debate_record ORDER BY created_at ASC"
    ).fetchall()

    transactions_by_dossier: dict[int, list] = {}
    for row in conn.execute('SELECT * FROM "transaction" ORDER BY txn_time ASC').fetchall():
        txn = dict(row)
        transactions_by_dossier.setdefault(txn["dossier_id"], []).append(txn)
    conn.close()

    def debates_before(ticker: str, txn_time: str) -> dict | None:
        ticker_key = _normalize_ticker(ticker)
        candidates = []
        txn_dt = _parse_iso_datetime(txn_time)
        for debate in debates:
            if _normalize_ticker(debate["ticker"]) != ticker_key:
                continue
            debate_dt = _parse_iso_datetime(debate["created_at"])
            if txn_dt and debate_dt and debate_dt <= txn_dt:
                candidates.append(debate)
        return candidates[-1] if candidates else None

    all_items: list[dict] = []
    month_items: list[dict] = []

    for dossier in dossiers:
        dossier_id = dossier["dossier_id"]
        txns = transactions_by_dossier.get(dossier_id, [])
        if not txns:
            continue

        commission_min, commission_rate = get_dossier_commission(dossier)
        metrics = build_trading_metrics(txns, commission_min, commission_rate)
        avg_cost = float(metrics["position_summary"].get("cost_basis") or 0)

        running_cost = avg_cost
        for txn in txns:
            direction = txn["direction"]
            price = float(txn["price"])
            txn_dt = _parse_iso_datetime(txn["txn_time"])
            debate = debates_before(dossier["stock_code"], txn["txn_time"])
            if not debate:
                continue
            judge = _parse_judge_verdict(debate["judge_verdict"])
            rating = (judge.get("rating") or "持有").strip()
            if not rating:
                continue

            pnl_pct = None
            if direction == "sell" and running_cost > 0:
                pnl_pct = round((price - running_cost) / running_cost * 100, 2)

            aligned, correct = _evaluate_trade_decision(rating, direction, pnl_pct)
            item = {
                "ticker": dossier["stock_code"],
                "ticker_name": dossier.get("stock_name") or debate["ticker_name"] or "",
                "verdict_rating": rating,
                "trade_direction": direction,
                "trade_time": txn["txn_time"],
                "pnl_pct": pnl_pct,
                "aligned": aligned,
                "correct": correct,
            }
            all_items.append(item)
            if txn_dt and txn_dt >= month_start:
                month_items.append(item)

    def bucket(items: list[dict]) -> dict:
        total = len(items)
        correct = sum(1 for x in items if x["correct"])
        accuracy = round(correct / total * 100, 1) if total else None
        return {"total": total, "correct": correct, "accuracy_pct": accuracy}

    recent_items = sorted(all_items, key=lambda x: x["trade_time"], reverse=True)[:8]
    return {
        "all_time": bucket(all_items),
        "month": bucket(month_items),
        "recent_items": recent_items,
    }
