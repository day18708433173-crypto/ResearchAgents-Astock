"""镜衡 Backend — 共享工具函数（卷宗、持仓、策略教练）"""

import json
import logging
from datetime import datetime

from services.db_init import get_db, _table_columns
from services.commission import build_trading_metrics, get_dossier_commission
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
    for table in ("alert", "alert_rule"):
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
    return summary


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


def _is_trailing_chitchat_line(line: str) -> bool:
    """判断是否为策略块末尾的寒暄/追问行。"""
    s = line.strip()
    if not s:
        return False
    if s.endswith("？") or s.endswith("?"):
        return True
    prefixes = (
        "还有什么", "欢迎", "如果", "你可以", "需要我", "随时", "接下来",
        "以上", "希望这", "请告诉我", "想深入讨论", "可以继续追问",
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
            kept.append(line)
        while kept and not kept[-1].strip():
            kept.pop()
        while kept and _is_trailing_chitchat_line(kept[-1]):
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

    return StrategyCreateResponse(
        version_id=version_id,
        dossier_id=dossier_id,
        created_at=datetime.now().isoformat(),
        message="策略版本已保存",
        quantifiable_triggers_count=0,
    )


def _persist_coach_strategy(request: CoachChatRequest) -> StrategyCreateResponse:
    """将教练对话中的策略写入卷宗。"""
    current_strategy = _extract_coach_strategy_content(request)
    if not current_strategy.strip():
        raise ValueError("暂无可保存的策略内容，请先与教练完成「当前策略」讨论")

    return _create_strategy_version_impl(StrategyCreateRequest(
        ticker=request.ticker,
        ticker_name=request.ticker_name,
        current_strategy=current_strategy,
    ))


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
