"""路由：策略版本管理

注意：静态路由（/api/strategy/create）必须放在动态路由（/api/strategy/{version_id}）之前。
"""

import logging

from fastapi import APIRouter, HTTPException

from services.db_init import get_db
from backend.schemas import (
    StrategyCreateRequest,
    StrategyCreateResponse,
    StrategyUpdateRequest,
)
from backend.helpers import _create_strategy_version_impl

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/strategy/create", response_model=StrategyCreateResponse)
async def create_strategy_version(request: StrategyCreateRequest):
    """创建新的策略版本"""
    try:
        return _create_strategy_version_impl(request)
    except Exception as e:
        logger.error(f"创建策略版本失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建策略版本失败: {str(e)}")


@router.put("/api/strategy/{version_id}")
async def update_strategy(version_id: int, req: StrategyUpdateRequest):
    """更新策略版本内容（可编辑）"""
    conn = get_db()

    # 检查版本是否存在
    existing = conn.execute(
        "SELECT * FROM strategy_version WHERE version_id = ?", (version_id,)
    ).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="策略版本不存在")

    # 更新内容
    conn.execute(
        "UPDATE strategy_version SET strategy_content = ? WHERE version_id = ?",
        (req.strategy_content, version_id)
    )

    # 更新卷宗的 updated_at
    conn.execute(
        "UPDATE dossier SET updated_at = datetime('now') WHERE dossier_id = ?",
        (dict(existing)['dossier_id'],)
    )

    conn.commit()
    conn.close()
    return {"success": True, "message": "策略已更新"}
