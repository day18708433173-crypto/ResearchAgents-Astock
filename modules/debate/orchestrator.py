"""头脑风暴室辩论编排器

支持两种模式：
1. 同步模式：run_debate() 返回完整结果
2. 流式模式：stream_debate() 返回Generator，实时推送每轮发言

新增功能：
- SSE实时输出
"""
import json
import logging
import re
import sqlite3
import threading
import time
import yaml
from pathlib import Path
from typing import Generator, Mapping, Optional
from services.llm_client import chat, stream_chat
from modules.debate.data_card import generate as gen_data_card
from modules.debate.agents import (
    build_debate_prompt, build_judge_prompt, parse_judge_llm_output,
)
from modules.debate.source_tagger import tag_output
from modules.debate.fact_check import verify

ROOT = Path(__file__).parent.parent.parent

logger = logging.getLogger(__name__)


def _resolve_max_rounds(coverage: int) -> int:
    """从 config.yaml 读取辩论轮数；覆盖率 <50% 时降级为 1 轮。"""
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        configured = yaml.safe_load(f).get("debate", {}).get("max_rounds", 3)
    if coverage < 50:
        return min(configured, 1)
    return configured


def _strip_html(text: str) -> str:
    """清洗 LLM 输出中的 HTML 标签"""
    if not text:
        return text
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    return text.strip()


# ═══════════════════════════════════════════════
#  同步辩论模式
# ═══════════════════════════════════════════════

def run_debate(ticker: str, ticker_name: str = "",
               decision_context: dict = None,
               existing_debate_id: int = None,
               focus_question: str = "",
               llm_config: Mapping[str, str] | None = None) -> dict:
    """执行完整辩论流程（同步模式）。

    Args:
        ticker: 股票代码
        ticker_name: 股票名称
        decision_context: 用户决策背景信息（可选）
        existing_debate_id: 后台异步模式时传入的辩论ID

    Returns:
        dict: 完整辩论结果，包含rounds、data_card、judge_verdict等
    """
    result = {
        "ticker": ticker,
        "ticker_name": ticker_name,
        "decision_context": decision_context,
        "rounds": [],
        "fact_check": None,
        "total_llm_calls": 0,
        "estimated_cost": 0.0,
        "hallucination_terminated": False,
        "error": None,
    }

    # Step 1: 数据卡
    card = gen_data_card(ticker)
    result["data_card"] = card
    result["coverage"] = card["coverage"]
    data_card_id = _save_data_card(card)
    result["data_card_id"] = data_card_id

    # Step 1.5: RAG 知识增强
    rag_context = None
    try:
        from services.rag.context_builder import enrich_data_card
        rag_context = enrich_data_card(ticker, card)
        card["rag_context"] = rag_context
        result["rag_context"] = rag_context
    except Exception as e:
        result["rag_warning"] = f"RAG enrichment skipped: {e}"

    if card["coverage"] < 30:
        result["error"] = f"数据卡覆盖率仅{card['coverage']}%，数据不足，无法启动辩论"
        return result

    max_rounds = _resolve_max_rounds(card["coverage"])
    result["max_rounds"] = max_rounds
    if max_rounds < 3:
        result["degraded"] = True

    # Step 2-4: 多轮辩论
    fields = card.get("fields", {})
    bull_msg = ""
    bear_msg = ""
    hallucination_count = 0
    cost_per_call = 0.003

    for r in range(1, max_rounds + 1):
        # Bull 发言
        try:
            sys_bull, user_bull = build_debate_prompt("bull", card, bear_msg, r, rag_context, focus_question)
            bull_msg = _strip_html(chat(user_bull, system=sys_bull, scenario="debate", llm_config=llm_config))
            result["total_llm_calls"] += 1
            result["estimated_cost"] += cost_per_call
        except Exception as e:
            bull_msg = f"[多头发言生成失败: {e}]"

        # Bear 发言
        try:
            sys_bear, user_bear = build_debate_prompt("bear", card, bull_msg, r, rag_context, focus_question)
            bear_msg = _strip_html(chat(user_bear, system=sys_bear, scenario="debate", llm_config=llm_config))
            result["total_llm_calls"] += 1
            result["estimated_cost"] += cost_per_call
        except Exception as e:
            bear_msg = f"[空头发言生成失败: {e}]"

        # 信源标注
        bull_tags = tag_output(bull_msg, fields, rag_context)
        bear_tags = tag_output(bear_msg, fields, rag_context)

        # 幻觉检测
        bull_unverified = sum(1 for t in bull_tags if t["tag"] == "待核实")
        bear_unverified = sum(1 for t in bear_tags if t["tag"] == "待核实")
        hallucination_count += bull_unverified + bear_unverified

        round_data = {
            "round": r,
            "bull": bull_msg,
            "bear": bear_msg,
            "bull_tags": bull_tags,
            "bear_tags": bear_tags,
        }
        result["rounds"].append(round_data)

        if hallucination_count > 8:
            result["hallucination_terminated"] = True
            break

    # Step 5: 事实校验
    fact_result = verify(result["rounds"], card)
    result["fact_check"] = fact_result
    result["accuracy_grade"] = fact_result.get("accuracy_grade", "B")

    # Step 6: 裁判裁决
    try:
        judge_sys, judge_usr = build_judge_prompt(
            ticker=ticker, name=ticker_name,
            rounds=result["rounds"],
            fact_check=fact_result,
            rag_context=rag_context,
            data_card=card,
            focus_question=focus_question,
        )
        judge_raw = chat(judge_usr, system=judge_sys, scenario="judge", llm_config=llm_config)
        result["total_llm_calls"] += 1
        result["estimated_cost"] += cost_per_call
        judge_verdict = parse_judge_llm_output(judge_raw)
        result["judge_verdict"] = judge_verdict
    except Exception as e:
        logger.exception("裁判裁决失败")
        result["judge_verdict"] = {
            "rating": "持有",
            "confidence": 0.0,
            "summary": f"裁判 LLM 调用失败: {e}",
            "bull_strengths": [],
            "bear_strengths": [],
            "bull_weaknesses": [],
            "bear_weaknesses": [],
            "key_risk": "",
            "key_opportunity": "",
            "missing_info": "",
            "action_hint": "请手动分析辩论内容",
        }

    # 存档
    if existing_debate_id is not None:
        _update_debate_completion(existing_debate_id, result)
        result["debate_id"] = existing_debate_id
    else:
        result["debate_id"] = _save_debate_log(result)

    return result


# ═══════════════════════════════════════════════
#  流式辩论模式（SSE）
# ═══════════════════════════════════════════════

def stream_debate(
    ticker: str,
    ticker_name: str = "",
    focus_question: str = "",
    llm_config: Mapping[str, str] | None = None,
    cancel_event: threading.Event | None = None,
) -> Generator[dict, None, None]:
    """流式辩论（实时推送每轮发言）

    Yields:
        dict: 每次推送一个事件，类型包括：
        - {"type": "status", "message": "..."} 状态更新
        - {"type": "data_card", "data": {...}} 数据卡生成完成
        - {"type": "round_start", "round": 1} 开始新一轮
        - {"type": "bull_token", "round": 1, "delta": "..."} 多头发言 token
        - {"type": "bull_speak", "round": 1, "content": "..."} 多头发言完成
        - {"type": "bear_token", "round": 1, "delta": "..."} 空头发言 token
        - {"type": "bear_speak", "round": 1, "content": "..."} 空头发言完成
        - {"type": "judge", "data": {...}} 裁判裁决
        - {"type": "complete", "data": {...}} 辩论完成
        - {"type": "error", "message": "..."} 错误
    """
    result = {
        "ticker": ticker,
        "ticker_name": ticker_name,
        "rounds": [],
        "total_llm_calls": 0,
        "estimated_cost": 0.0,
    }

    def _cancelled() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    # Step 1: 数据卡
    yield {"type": "status", "message": "正在生成数据卡..."}
    if _cancelled():
        logger.info("辩论已取消（客户端断开）")
        return
    try:
        card = gen_data_card(ticker)
        result["data_card"] = card
        result["coverage"] = card["coverage"]
        yield {"type": "data_card", "data": card}
    except Exception as e:
        yield {"type": "error", "message": f"数据卡生成失败: {e}"}
        return

    if card["coverage"] < 30:
        yield {"type": "error", "message": f"数据覆盖率仅{card['coverage']}%，不足30%，无法辩论"}
        return

    if _cancelled():
        logger.info("辩论已取消（客户端断开）")
        return

    # RAG增强
    rag_context = None
    try:
        from services.rag.context_builder import enrich_data_card
        rag_context = enrich_data_card(ticker, card)
        result["rag_context"] = rag_context
        yield {"type": "status", "message": "RAG知识增强完成"}
    except Exception:
        pass

    max_rounds = _resolve_max_rounds(card["coverage"])
    result["max_rounds"] = max_rounds

    fields = card.get("fields", {})
    bull_msg = ""
    bear_msg = ""
    cost_per_call = 0.003

    for r in range(1, max_rounds + 1):
        if _cancelled():
            logger.info("辩论已取消（客户端断开），停在第 %d 轮之前", r)
            return

        yield {"type": "round_start", "round": r}

        # Bull发言（token 级流式）
        yield {"type": "status", "message": f"多头第{r}轮发言..."}
        try:
            sys_bull, user_bull = build_debate_prompt("bull", card, bear_msg, r, rag_context, focus_question)
            bull_raw = ""
            for token in stream_chat(user_bull, system=sys_bull, scenario="debate", llm_config=llm_config):
                if _cancelled():
                    logger.info("辩论已取消（客户端断开），中断多头发言")
                    return
                bull_raw += token
                yield {"type": "bull_token", "round": r, "delta": token}
            bull_msg = _strip_html(bull_raw)
            result["total_llm_calls"] += 1
            result["estimated_cost"] += cost_per_call
            yield {"type": "bull_speak", "round": r, "content": bull_msg}
        except Exception as e:
            bull_msg = f"[生成失败: {e}]"
            yield {"type": "bull_speak", "round": r, "content": bull_msg}

        # Bear发言（token 级流式）
        yield {"type": "status", "message": f"空头第{r}轮发言..."}
        try:
            sys_bear, user_bear = build_debate_prompt("bear", card, bull_msg, r, rag_context, focus_question)
            bear_raw = ""
            for token in stream_chat(user_bear, system=sys_bear, scenario="debate", llm_config=llm_config):
                if _cancelled():
                    logger.info("辩论已取消（客户端断开），中断空头发言")
                    return
                bear_raw += token
                yield {"type": "bear_token", "round": r, "delta": token}
            bear_msg = _strip_html(bear_raw)
            result["total_llm_calls"] += 1
            result["estimated_cost"] += cost_per_call
            yield {"type": "bear_speak", "round": r, "content": bear_msg}
        except Exception as e:
            bear_msg = f"[生成失败: {e}]"
            yield {"type": "bear_speak", "round": r, "content": bear_msg}

        result["rounds"].append({
            "round": r,
            "bull": bull_msg,
            "bear": bear_msg,
        })

        time.sleep(0.1)  # 短暂延迟让前端有时间渲染

    if _cancelled():
        logger.info("辩论已取消（客户端断开），跳过裁判")
        return

    # 裁判裁决
    yield {"type": "status", "message": "裁判正在综合评判..."}
    try:
        judge_sys, judge_usr = build_judge_prompt(
            ticker, ticker_name, result["rounds"],
            rag_context=rag_context,
            data_card=card,
            focus_question=focus_question,
        )
        judge_raw = chat(judge_usr, system=judge_sys, scenario="judge", llm_config=llm_config)
        result["total_llm_calls"] += 1
        result["estimated_cost"] += cost_per_call
        judge_verdict = parse_judge_llm_output(judge_raw)
        result["judge_verdict"] = judge_verdict
        yield {"type": "judge", "data": judge_verdict}
    except Exception as e:
        logger.exception("流式辩论裁判失败")
        yield {"type": "error", "message": f"裁判失败: {e}"}
        return

    # 存档
    debate_id = _save_debate_log(result)
    result["debate_id"] = debate_id
    yield {"type": "complete", "data": result}


# ═══════════════════════════════════════════════
#  分轮辩论模式（轮间暂停）
# ═══════════════════════════════════════════════

def stream_single_round(
    ticker: str,
    ticker_name: str = "",
    round_num: int = 1,
    debate_id: Optional[int] = None,
    focus_question: str = "",
    supplement_data: Optional[dict] = None,
    llm_config: Mapping[str, str] | None = None,
    cancel_event: threading.Event | None = None,
) -> Generator[dict, None, None]:
    """执行单轮辩论（轮间暂停模式）。

    - round_num=1 且 debate_id=None：生成数据卡、创建辩论记录，再执行第一轮
    - round_num>1 且 debate_id 已知：从 DB 加载数据卡和上一轮发言，执行下一轮

    Yields:
        - {"type": "status", "message": "..."}
        - {"type": "data_card", "data": {...}}  (仅第1轮)
        - {"type": "round_start", "round": N}
        - {"type": "bull_token", "round": N, "delta": "..."}
        - {"type": "bull_speak", "round": N, "content": "..."}
        - {"type": "bear_token", "round": N, "delta": "..."}
        - {"type": "bear_speak", "round": N, "content": "..."}
        - {"type": "round_complete", "round": N, "debate_id": ID, "max_rounds_suggested": M}
        - {"type": "error", "message": "..."}
    """

    def _cancelled() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    # ── 数据卡准备 ──────────────────────────────
    if debate_id is None:
        yield {"type": "status", "message": "正在生成数据卡..."}
        if _cancelled():
            return
        try:
            card = gen_data_card(ticker)
        except Exception as e:
            yield {"type": "error", "message": f"数据卡生成失败: {e}"}
            return

        if supplement_data:
            for k, v in supplement_data.items():
                card["fields"][k] = {"value": v, "grade": "U", "source": "用户补充"}

        if card["coverage"] < 30:
            yield {"type": "error", "message": f"数据覆盖率仅{card['coverage']}%，不足30%，无法辩论"}
            return

        yield {"type": "data_card", "data": card}

        rag_context = None
        try:
            from services.rag.context_builder import enrich_data_card
            rag_context = enrich_data_card(ticker, card)
            card["rag_context"] = rag_context  # 持久化，供第2/3轮恢复
            yield {"type": "status", "message": "RAG知识增强完成"}
        except Exception:
            pass

        data_card_id = _save_data_card(card)
        debate_id = _create_debate_record(ticker, ticker_name, data_card_id)
        prev_bull = ""
        prev_bear = ""
    else:
        card, rag_context = _load_data_card_for_debate(debate_id)
        if supplement_data:
            for k, v in supplement_data.items():
                card["fields"][k] = {"value": v, "grade": "U", "source": "用户补充"}
            yield {"type": "data_card_update", "data": {"fields": card["fields"], "coverage": card["coverage"]}}
        prev_bull, prev_bear = _load_last_round_content(debate_id)

    if _cancelled():
        return

    max_suggested = _resolve_max_rounds(card["coverage"])

    yield {"type": "round_start", "round": round_num}

    # ── 多头发言 ─────────────────────────────────
    yield {"type": "status", "message": f"多头第{round_num}轮发言..."}
    bull_msg = ""
    try:
        sys_bull, user_bull = build_debate_prompt("bull", card, prev_bear, round_num, rag_context, focus_question)
        bull_raw = ""
        for token in stream_chat(user_bull, system=sys_bull, scenario="debate", llm_config=llm_config):
            if _cancelled():
                return
            bull_raw += token
            yield {"type": "bull_token", "round": round_num, "delta": token}
        bull_msg = _strip_html(bull_raw)
        yield {"type": "bull_speak", "round": round_num, "content": bull_msg}
    except Exception as e:
        bull_msg = f"[生成失败: {e}]"
        yield {"type": "bull_speak", "round": round_num, "content": bull_msg}

    if _cancelled():
        return

    # ── 空头发言 ─────────────────────────────────
    yield {"type": "status", "message": f"空头第{round_num}轮发言..."}
    bear_msg = ""
    try:
        sys_bear, user_bear = build_debate_prompt("bear", card, bull_msg, round_num, rag_context, focus_question)
        bear_raw = ""
        for token in stream_chat(user_bear, system=sys_bear, scenario="debate", llm_config=llm_config):
            if _cancelled():
                return
            bear_raw += token
            yield {"type": "bear_token", "round": round_num, "delta": token}
        bear_msg = _strip_html(bear_raw)
        yield {"type": "bear_speak", "round": round_num, "content": bear_msg}
    except Exception as e:
        bear_msg = f"[生成失败: {e}]"
        yield {"type": "bear_speak", "round": round_num, "content": bear_msg}

    # ── 保存本轮到 DB ─────────────────────────────
    _append_round_to_debate(debate_id, {"round": round_num, "bull": bull_msg, "bear": bear_msg})

    yield {
        "type": "round_complete",
        "round": round_num,
        "debate_id": debate_id,
        "max_rounds_suggested": max_suggested,
    }


def stream_judge_verdict(
    ticker: str,
    ticker_name: str = "",
    debate_id: int = None,
    focus_question: str = "",
    llm_config: Mapping[str, str] | None = None,
    cancel_event: threading.Event | None = None,
) -> Generator[dict, None, None]:
    """从 DB 加载轮次，执行裁判裁决，更新 DB。

    Yields:
        - {"type": "status", "message": "..."}
        - {"type": "judge", "data": {...}}
        - {"type": "complete", "data": {"debate_id": ID}}
        - {"type": "error", "message": "..."}
    """

    def _cancelled() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    yield {"type": "status", "message": "正在加载辩论数据..."}

    rounds, card, rag_context = _load_debate_rounds(debate_id)
    if not rounds:
        yield {"type": "error", "message": "没有找到辩论轮次，请先完成至少一轮辩论"}
        return

    if _cancelled():
        return

    yield {"type": "status", "message": "裁判正在综合评判..."}
    try:
        fact_result = verify(rounds, card)
        judge_sys, judge_usr = build_judge_prompt(
            ticker=ticker,
            name=ticker_name,
            rounds=rounds,
            fact_check=fact_result,
            rag_context=rag_context,
            data_card=card,
            focus_question=focus_question,
        )
        judge_raw = chat(judge_usr, system=judge_sys, scenario="judge", llm_config=llm_config)
        judge_verdict = parse_judge_llm_output(judge_raw)

        _update_judge_verdict(debate_id, judge_verdict)
        yield {"type": "judge", "data": judge_verdict}
        yield {"type": "complete", "data": {"debate_id": debate_id}}
    except Exception as e:
        logger.exception("分轮裁判失败 debate_id=%s", debate_id)
        yield {"type": "error", "message": f"裁判失败: {e}"}


# ═══════════════════════════════════════════════
#  数据持久化
# ═══════════════════════════════════════════════

def _save_data_card(card: dict) -> int:
    """保存数据卡到 data_cards 表，返回 row id"""
    db = ROOT / "data" / "jingheng.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS data_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        coverage INTEGER DEFAULT 0,
        fields TEXT,
        generated_at TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # 兼容旧库：补充 rag_context 列，使分轮辩论的后续轮次也能恢复 RAG 上下文
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(data_cards)").fetchall()}
    if "rag_context" not in existing_cols:
        conn.execute("ALTER TABLE data_cards ADD COLUMN rag_context TEXT DEFAULT '{}'")

    cur = conn.execute(
        "INSERT INTO data_cards (ticker, coverage, fields, generated_at, rag_context) VALUES (?, ?, ?, ?, ?)",
        (
            card["ticker"],
            card["coverage"],
            json.dumps(card.get("fields", {})),
            card.get("generated_at", ""),
            json.dumps(card.get("rag_context") or {}, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def _save_debate_log(result: dict) -> int:
    """保存辩论记录"""
    from services.db_init import get_db

    conn = get_db()

    cur = conn.execute(
        """INSERT INTO debate_record 
           (ticker, ticker_name, template_id, coverage, rounds, data_card_id, 
            judge_verdict, accuracy_grade, total_llm_calls, estimated_cost)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            result.get("ticker", ""),
            result.get("ticker_name", ""),
            "",
            result.get("coverage", 0),
            json.dumps(result.get("rounds", [])),
            result.get("data_card_id"),
            json.dumps(result.get("judge_verdict", {})),
            result.get("accuracy_grade", "B"),
            result.get("total_llm_calls", 0),
            result.get("estimated_cost", 0.0),
        ),
    )
    conn.commit()
    debate_id = cur.lastrowid
    conn.close()

    # 保存Agent对话
    for r in result.get("rounds", []):
        _save_agent_conversation(debate_id, r)

    return debate_id


def _save_agent_conversation(debate_id: int, round_data: dict):
    """保存每轮Agent对话"""
    from services.db_init import get_db

    conn = get_db()

    conn.execute(
        "INSERT INTO agent_conversation (debate_id, round_num, agent_role, content) VALUES (?, ?, ?, ?)",
        (debate_id, round_data.get("round", 1), "bull", round_data.get("bull", "")),
    )
    conn.execute(
        "INSERT INTO agent_conversation (debate_id, round_num, agent_role, content) VALUES (?, ?, ?, ?)",
        (debate_id, round_data.get("round", 1), "bear", round_data.get("bear", "")),
    )
    conn.commit()
    conn.close()


def _create_debate_record(ticker: str, ticker_name: str, data_card_id: Optional[int]) -> int:
    """创建空白辩论记录（分轮模式用），返回 debate_id。"""
    from services.db_init import get_db
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO debate_record
           (ticker, ticker_name, template_id, coverage, rounds, data_card_id,
            judge_verdict, accuracy_grade, total_llm_calls, estimated_cost)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticker, ticker_name, "", 0, "[]", data_card_id, "{}", "B", 0, 0.0),
    )
    conn.commit()
    debate_id = cur.lastrowid
    conn.close()
    return debate_id


def _load_data_card_for_debate(debate_id: int) -> tuple[dict, object]:
    """从 DB 加载 debate 对应的 data_card。返回 (card_dict, rag_context=None)。"""
    from services.db_init import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT data_card_id, coverage FROM debate_record WHERE id = ?", (debate_id,)
    ).fetchone()
    if not row:
        conn.close()
        return {"ticker": "", "coverage": 0, "fields": {}}, None

    data_card_id = row["data_card_id"]
    if data_card_id:
        try:
            card_row = conn.execute(
                "SELECT ticker, coverage, fields, rag_context FROM data_cards WHERE id = ?",
                (data_card_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            # 旧库尚无 rag_context 列时降级查询
            card_row = conn.execute(
                "SELECT ticker, coverage, fields FROM data_cards WHERE id = ?", (data_card_id,)
            ).fetchone()
        conn.close()
        if card_row:
            try:
                fields = json.loads(card_row["fields"] or "{}")
            except Exception:
                fields = {}
            rag_context = None
            if "rag_context" in card_row.keys():
                try:
                    rag_context = json.loads(card_row["rag_context"] or "{}") or None
                except Exception:
                    rag_context = None
            return {"ticker": card_row["ticker"], "coverage": card_row["coverage"], "fields": fields}, rag_context
    conn.close()
    return {"ticker": "", "coverage": row["coverage"] or 0, "fields": {}}, None


def _load_last_round_content(debate_id: int) -> tuple[str, str]:
    """加载最新一轮的 bull/bear 内容，供下一轮 prompt 使用。"""
    from services.db_init import get_db
    conn = get_db()
    row = conn.execute("SELECT rounds FROM debate_record WHERE id = ?", (debate_id,)).fetchone()
    conn.close()
    if not row:
        return "", ""
    try:
        rounds = json.loads(row["rounds"] or "[]")
        if rounds:
            last = rounds[-1]
            return last.get("bull", ""), last.get("bear", "")
    except Exception:
        pass
    return "", ""


def _append_round_to_debate(debate_id: int, round_data: dict):
    """将新一轮追加到 debate_record.rounds，并同步 agent_conversation。"""
    from services.db_init import get_db
    conn = get_db()
    row = conn.execute("SELECT rounds FROM debate_record WHERE id = ?", (debate_id,)).fetchone()
    if not row:
        conn.close()
        return
    try:
        rounds = json.loads(row["rounds"] or "[]")
    except Exception:
        rounds = []

    rounds = [r for r in rounds if r.get("round") != round_data.get("round")]
    rounds.append(round_data)
    rounds.sort(key=lambda r: r.get("round", 0))

    conn.execute(
        "UPDATE debate_record SET rounds = ? WHERE id = ?",
        (json.dumps(rounds, ensure_ascii=False), debate_id),
    )
    conn.commit()
    conn.close()
    _save_agent_conversation(debate_id, round_data)


def _load_debate_rounds(debate_id: int) -> tuple[list, dict, object]:
    """加载辩论所有轮次、数据卡。返回 (rounds, card, rag_context=None)。"""
    from services.db_init import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT rounds, data_card_id, coverage FROM debate_record WHERE id = ?", (debate_id,)
    ).fetchone()
    if not row:
        conn.close()
        return [], {"coverage": 0, "fields": {}}, None

    try:
        rounds = json.loads(row["rounds"] or "[]")
    except Exception:
        rounds = []

    data_card_id = row["data_card_id"]
    card = {"coverage": row["coverage"] or 0, "fields": {}}
    if data_card_id:
        card_row = conn.execute(
            "SELECT ticker, coverage, fields FROM data_cards WHERE id = ?", (data_card_id,)
        ).fetchone()
        if card_row:
            try:
                fields = json.loads(card_row["fields"] or "{}")
            except Exception:
                fields = {}
            card = {"ticker": card_row["ticker"], "coverage": card_row["coverage"], "fields": fields}
    conn.close()
    return rounds, card, None


def _update_judge_verdict(debate_id: int, verdict: dict):
    """更新裁判裁决到 DB。"""
    from services.db_init import get_db
    conn = get_db()
    conn.execute(
        "UPDATE debate_record SET judge_verdict = ? WHERE id = ?",
        (json.dumps(verdict, ensure_ascii=False), debate_id),
    )
    conn.commit()
    conn.close()


def _update_debate_completion(debate_id: int, result: dict):
    """更新已有辩论记录（后台异步模式）"""
    from services.db_init import get_db

    conn = get_db()
    conn.execute(
        """UPDATE debate_record SET
           coverage=?, rounds=?, judge_verdict=?, accuracy_grade=?,
           total_llm_calls=?, estimated_cost=? WHERE id=?""",
        (
            result.get("coverage", 0),
            json.dumps(result.get("rounds", [])),
            json.dumps(result.get("judge_verdict", {})),
            result.get("accuracy_grade", "B"),
            result.get("total_llm_calls", 0),
            result.get("estimated_cost", 0.0),
            debate_id,
        ),
    )
    conn.commit()
    conn.close()

    conn = get_db()
    conn.execute(
        "DELETE FROM agent_conversation WHERE debate_id = ? AND agent_role IN ('bull', 'bear')",
        (debate_id,),
    )
    conn.commit()
    conn.close()
    for r in result.get("rounds", []):
        _save_agent_conversation(debate_id, r)
