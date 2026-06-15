"""路由：辩论系统（头脑风暴室）、策略教练、金融科普

注意：静态路由（/api/debate/run、/api/debate/history 等）必须放在
动态路由（/api/debate/{debate_id}/...）之前。
"""

import asyncio
import json
import logging
from typing import List

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from services.db_init import get_db
from services.llm_client import chat, astream_chat, vision_chat
from modules.debate.orchestrator import (
    run_debate as _run_debate,
    stream_debate as _stream_debate,
    stream_single_round as _stream_single_round,
    stream_judge_verdict as _stream_judge_verdict,
)
from modules.debate.agents import build_knowledge_prompt

from backend.schemas import (
    CoachChatRequest,
    CoachChatResponse,
    CoachTranscriptSaveRequest,
    DebateHistoryDetail,
    DebateHistoryItem,
    DebateRequest,
    DebateResponse,
    DebateRoundResponse,
    KnowledgeRequest,
    KnowledgeResponse,
)
from backend.helpers import (
    _coach_save_done_meta,
    _compute_coach_meta,
    _is_coach_save_intent,
    _parse_knowledge_context,
    _parse_knowledge_reply,
    _persist_coach_strategy,
    _prepare_coach_prompts,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _llm_config_from_request(request: Request) -> dict[str, str] | None:
    """Read optional OpenAI-compatible LLM config from request headers."""
    api_key = (request.headers.get("x-jh-llm-api-key") or "").strip()
    base_url = (request.headers.get("x-jh-llm-base-url") or "").strip()
    model = (request.headers.get("x-jh-llm-model") or "").strip()
    reasoning_model = (request.headers.get("x-jh-llm-reasoning-model") or "").strip()

    supplied = any([api_key, base_url, model, reasoning_model])
    if not supplied:
        return None
    if not api_key or not base_url or not model:
        raise HTTPException(status_code=400, detail="自定义 LLM 配置需同时提供 API Key、Base URL 和模型名")
    return {
        "api_key": api_key,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "reasoning_model": reasoning_model or model,
    }


@router.post("/api/debate/analyze-image")
async def analyze_image(request: Request, file: UploadFile = File(...)):
    """用视觉模型分析上传图片，提取金融数据文字。

    复用首页「模型接入」配置的模型（通过 x-jh-llm-* 请求头传入）。
    若用户未配置模型或模型不支持图片（如 DeepSeek V4），会返回 400 错误。
    """
    import base64

    llm_config = _llm_config_from_request(request)
    if not llm_config:
        raise HTTPException(
            status_code=400,
            detail="图片分析需要配置支持视觉的模型。请在首页「模型接入」处配置 GPT-4o 或 Claude 等视觉模型后保存，再重试。",
        )

    allowed_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    media_type = (file.content_type or "image/jpeg").split(";")[0].strip()
    if media_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"不支持的图片格式：{media_type}")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片大小不能超过 10 MB")

    image_b64 = base64.b64encode(content).decode()
    try:
        result = vision_chat(image_b64, media_type, llm_config)
        return {"text": result}
    except Exception as exc:
        logger.error("图片分析失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"图片分析失败：{exc}") from exc


@router.post("/api/debate/run", response_model=DebateResponse)
async def debate_run(req: DebateRequest, request: Request):
    """运行辩论（同步）：生成多角度通用股票分析内容。"""
    llm_config = _llm_config_from_request(request)
    try:
        result = _run_debate(
            ticker=req.ticker,
            ticker_name=req.ticker_name,
            focus_question=req.focus_question or "",
            llm_config=llm_config,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if result.get("error"):
        return DebateResponse(
            success=False,
            ticker=req.ticker,
            ticker_name=req.ticker_name,
            coverage=result.get("coverage", 0),
            rounds=[],
            data_card={},
            total_llm_calls=0,
            estimated_cost=0.0,
            error=result["error"],
        )

    # 转换为简化格式
    rounds = []
    for rd in result.get("rounds", []):
        rounds.append(DebateRoundResponse(
            round=rd["round"],
            bull_content=rd.get("bull", ""),
            bear_content=rd.get("bear", ""),
        ))

    return DebateResponse(
        success=True,
        ticker=req.ticker,
        ticker_name=req.ticker_name,
        coverage=result.get("coverage", 0),
        rounds=rounds,
        data_card=result.get("data_card", {}),
        rag_context=result.get("rag_context"),
        judge_verdict=result.get("judge_verdict"),
        total_llm_calls=result.get("total_llm_calls", 0),
        estimated_cost=result.get("estimated_cost", 0.0),
        error=None,
    )


@router.get("/api/debate/history", response_model=List[DebateHistoryItem])
async def debate_history(limit: int = Query(default=20, ge=1, le=100)):
    """获取最近的辩论历史记录。"""
    conn = get_db()
    rows = conn.execute(
        """SELECT id, ticker, ticker_name, coverage, rounds,
                  judge_verdict, created_at
           FROM debate_record
           ORDER BY created_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()

    items = []
    for row in rows:
        record = dict(row)
        try:
            judge = json.loads(record.get("judge_verdict") or "{}")
        except Exception:
            judge = {}
        try:
            rounds = json.loads(record.get("rounds") or "[]")
        except Exception:
            rounds = []
        items.append(DebateHistoryItem(
            id=record["id"],
            ticker=record.get("ticker") or "",
            ticker_name=record.get("ticker_name") or "",
            coverage=record.get("coverage") or 0,
            rating=judge.get("rating", ""),
            summary=judge.get("summary", ""),
            rounds_count=len(rounds) if isinstance(rounds, list) else 0,
            created_at=str(record.get("created_at") or ""),
        ))
    return items


@router.get("/api/debate/history/{debate_id}", response_model=DebateHistoryDetail)
async def debate_history_detail(debate_id: int):
    """获取单条辩论完整记录，包含辩论轮次、裁判和策略教练对话。"""
    conn = get_db()
    row = conn.execute(
        """SELECT id, ticker, ticker_name, coverage, rounds, data_card_id,
                  judge_verdict, created_at
           FROM debate_record
           WHERE id = ?""",
        (debate_id,),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="辩论记录不存在")

    record = dict(row)
    try:
        rounds = json.loads(record.get("rounds") or "[]")
    except Exception:
        rounds = []
    try:
        judge = json.loads(record.get("judge_verdict") or "{}")
    except Exception:
        judge = {}

    data_card = None
    data_card_id = record.get("data_card_id")
    if data_card_id:
        card_row = conn.execute(
            "SELECT ticker, coverage, fields, generated_at FROM data_cards WHERE id = ?",
            (data_card_id,),
        ).fetchone()
        if card_row:
            card = dict(card_row)
            try:
                fields = json.loads(card.get("fields") or "{}")
            except Exception:
                fields = {}
            data_card = {
                "ticker": card.get("ticker"),
                "coverage": card.get("coverage") or record.get("coverage") or 0,
                "fields": fields,
                "generated_at": card.get("generated_at") or "",
            }

    coach_rows = conn.execute(
        """SELECT agent_role, content, created_at
           FROM agent_conversation
           WHERE debate_id = ? AND agent_role IN ('coach', 'user')
           ORDER BY id ASC""",
        (debate_id,),
    ).fetchall()
    conn.close()

    coach_messages = [
        {
            "role": "coach" if row["agent_role"] == "coach" else "user",
            "content": row["content"] or "",
            "timestamp": str(row["created_at"] or ""),
        }
        for row in coach_rows
    ]

    return DebateHistoryDetail(
        id=record["id"],
        ticker=record.get("ticker") or "",
        ticker_name=record.get("ticker_name") or "",
        coverage=record.get("coverage") or 0,
        rounds=rounds if isinstance(rounds, list) else [],
        data_card=data_card,
        judge_verdict=judge,
        coach_messages=coach_messages,
        created_at=str(record.get("created_at") or ""),
    )


@router.api_route("/api/debate/stream", methods=["GET", "POST"])
async def debate_stream(
    request: Request,
    ticker: str = Query(..., description="股票代码"),
    ticker_name: str = Query(default="", description="股票名称"),
    focus_question: str = Query(default="", description="可选聚焦问题"),
):
    """SSE 流式辩论：实时推送每轮发言
    
    事件类型：
    - status: 状态更新（如"正在生成数据卡..."）
    - data_card: 数据卡生成完成
    - round_start: 开始新一轮
    - bull_speak: 多头发言
    - bear_speak: 空头发言
    - judge: 裁判裁决
    - complete: 辩论完成
    - error: 错误
    """
    llm_config = _llm_config_from_request(request)

    async def event_generator():
        import threading

        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        cancel_event = threading.Event()

        def producer():
            try:
                for event in _stream_debate(
                    ticker,
                    ticker_name,
                    focus_question=focus_question,
                    llm_config=llm_config,
                    cancel_event=cancel_event,
                ):
                    if cancel_event.is_set():
                        break
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as e:
                if not cancel_event.is_set():
                    loop.call_soon_threadsafe(
                        queue.put_nowait, {"type": "error", "message": str(e)}
                    )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=producer, daemon=True).start()

        try:
            while True:
                if await request.is_disconnected():
                    cancel_event.set()
                    logger.info("辩论 SSE 客户端已断开，正在取消后续 LLM 调用")
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if event is None:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            cancel_event.set()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/debate/round")
async def debate_round(
    request: Request,
    ticker: str = Query(..., description="股票代码"),
    ticker_name: str = Query(default="", description="股票名称"),
    round_num: int = Query(default=1, ge=1, le=10, description="本轮编号（从1开始）"),
    debate_id: int = Query(default=None, description="已有辩论ID（第1轮不传）"),
    focus_question: str = Query(default="", description="本轮聚焦问题（可选）"),
    supplement_data: str = Query(default="", description="用户补充数据，JSON字符串，如 {\"PE\": \"15\"}"),
):
    """SSE 流式单轮辩论（轮间暂停模式）。

    第1轮不传 debate_id，会自动生成数据卡并创建辩论记录。
    后续轮传入 debate_id，从数据库加载已有数据卡和上轮发言。
    """
    llm_config = _llm_config_from_request(request)

    parsed_supplement: dict | None = None
    if supplement_data.strip():
        try:
            parsed_supplement = json.loads(supplement_data)
        except Exception:
            raise HTTPException(status_code=400, detail="supplement_data 必须是合法的 JSON 对象")

    async def event_generator():
        import threading

        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        cancel_event = threading.Event()

        def producer():
            try:
                for event in _stream_single_round(
                    ticker=ticker,
                    ticker_name=ticker_name,
                    round_num=round_num,
                    debate_id=debate_id,
                    focus_question=focus_question,
                    supplement_data=parsed_supplement,
                    llm_config=llm_config,
                    cancel_event=cancel_event,
                ):
                    if cancel_event.is_set():
                        break
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as e:
                if not cancel_event.is_set():
                    loop.call_soon_threadsafe(
                        queue.put_nowait, {"type": "error", "message": str(e)}
                    )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=producer, daemon=True).start()

        try:
            while True:
                if await request.is_disconnected():
                    cancel_event.set()
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if event is None:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            cancel_event.set()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/api/debate/judge")
async def debate_judge(
    request: Request,
    ticker: str = Query(..., description="股票代码"),
    ticker_name: str = Query(default="", description="股票名称"),
    debate_id: int = Query(..., description="辩论ID"),
    focus_question: str = Query(default="", description="裁判聚焦问题（可选）"),
):
    """SSE 流式裁判裁决（从 DB 加载所有轮次，生成综合裁决）。"""
    llm_config = _llm_config_from_request(request)

    async def event_generator():
        import threading

        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        cancel_event = threading.Event()

        def producer():
            try:
                for event in _stream_judge_verdict(
                    ticker=ticker,
                    ticker_name=ticker_name,
                    debate_id=debate_id,
                    focus_question=focus_question,
                    llm_config=llm_config,
                    cancel_event=cancel_event,
                ):
                    if cancel_event.is_set():
                        break
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as e:
                if not cancel_event.is_set():
                    loop.call_soon_threadsafe(
                        queue.put_nowait, {"type": "error", "message": str(e)}
                    )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=producer, daemon=True).start()

        try:
            while True:
                if await request.is_disconnected():
                    cancel_event.set()
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if event is None:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            cancel_event.set()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/api/debate/coach", response_model=CoachChatResponse)
async def debate_coach(request: CoachChatRequest, http_request: Request):
    """策略教练对话接口（同步，保留兼容）"""
    llm_config = _llm_config_from_request(http_request)
    try:
        _, _, user_input = _prepare_coach_prompts(request)
        if _is_coach_save_intent(user_input):
            try:
                saved = _persist_coach_strategy(request)
                meta = _coach_save_done_meta(saved)
                meta["strategy_saved"] = True
            except Exception as e:
                logger.error(f"教练保存策略失败: {e}")
                meta = _coach_save_done_meta(error=str(e))
                meta["strategy_saved"] = False
            return CoachChatResponse(reply=meta.pop("reply"), **meta)

        system_prompt, user_prompt, user_input = _prepare_coach_prompts(request)
        reply = chat(
            user_prompt,
            system_prompt,
            scenario="coach",
            llm_config=llm_config,
        )
        meta = _compute_coach_meta(request, reply, user_input)
        return CoachChatResponse(reply=reply, **meta)
    except Exception as e:
        logger.error(f"策略教练对话失败: {e}")
        raise HTTPException(status_code=500, detail=f"策略教练对话失败: {str(e)}")


@router.post("/api/debate/coach/stream")
async def debate_coach_stream(request: CoachChatRequest, http_request: Request):
    """策略教练 SSE 流式对话"""
    llm_config = _llm_config_from_request(http_request)

    async def event_generator():
        try:
            _, _, user_input = _prepare_coach_prompts(request)
            if _is_coach_save_intent(user_input):
                try:
                    saved = _persist_coach_strategy(request)
                    meta = _coach_save_done_meta(saved)
                    meta["strategy_saved"] = True
                except Exception as e:
                    logger.error(f"教练保存策略失败: {e}")
                    meta = _coach_save_done_meta(error=str(e))
                    meta["strategy_saved"] = False
                reply = meta.pop("reply")
                yield f"data: {json.dumps({'type': 'token', 'delta': reply}, ensure_ascii=False)}\n\n"
                done_payload = {"type": "done", "reply": reply, **meta}
                yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
                return

            system_prompt, user_prompt, user_input = _prepare_coach_prompts(request)
            reply = ""
            async for token in astream_chat(
                user_prompt,
                system_prompt,
                scenario="coach",
                llm_config=llm_config,
            ):
                reply += token
                yield f"data: {json.dumps({'type': 'token', 'delta': token}, ensure_ascii=False)}\n\n"
            meta = _compute_coach_meta(request, reply, user_input)
            done_payload = {"type": "done", "reply": reply, **meta}
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"策略教练流式对话失败: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/debate/knowledge")
async def debate_knowledge(request: KnowledgeRequest, http_request: Request):
    """金融科普 Agent：解释辩论中的术语，支持多轮追问。"""
    llm_config = _llm_config_from_request(http_request)
    try:
        context_type, context_detail = _parse_knowledge_context(request.context)
        history = [m.dict() if hasattr(m, "dict") else m for m in request.history]

        user_question = request.question.strip()
        if not user_question:
            user_question = f"请解释「{request.selected_text}」的含义和投资意义。"

        system_prompt, user_prompt = build_knowledge_prompt(
            selected_text=request.selected_text,
            context_type=context_type,
            context_detail=context_detail,
            ticker=request.ticker,
            ticker_name=request.ticker_name,
            question=user_question,
            history=history,
        )

        reply = chat(
            user_prompt,
            system=system_prompt,
            scenario="knowledge",
            llm_config=llm_config,
        )
        explanation, related_terms = _parse_knowledge_reply(reply)

        return KnowledgeResponse(
            explanation=explanation,
            examples=[],
            related_terms=related_terms,
        )

    except Exception as e:
        logger.error(f"金融科普Agent调用失败: {e}")
        raise HTTPException(status_code=500, detail=f"金融科普请求失败: {str(e)}")


# 动态路由放在最后
@router.post("/api/debate/{debate_id}/coach-transcript")
async def save_coach_transcript(debate_id: int, request: CoachTranscriptSaveRequest):
    """保存某次辩论关联的策略教练对话快照。"""
    conn = get_db()
    exists = conn.execute("SELECT id FROM debate_record WHERE id = ?", (debate_id,)).fetchone()
    if not exists:
        conn.close()
        raise HTTPException(status_code=404, detail="辩论记录不存在")

    conn.execute(
        "DELETE FROM agent_conversation WHERE debate_id = ? AND agent_role IN ('coach', 'user')",
        (debate_id,),
    )
    for idx, message in enumerate(request.messages, 1):
        role = "coach" if message.role == "coach" else "user"
        conn.execute(
            """INSERT INTO agent_conversation (debate_id, round_num, agent_role, content)
               VALUES (?, ?, ?, ?)""",
            (debate_id, 0, role, message.content),
        )
    conn.commit()
    conn.close()
    return {"success": True, "count": len(request.messages)}
