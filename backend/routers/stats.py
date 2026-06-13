"""路由：决策质量统计"""

from fastapi import APIRouter

from backend.helpers import compute_decision_quality
from backend.schemas import DecisionQualityResponse, DecisionQualityBucket, DecisionQualityItem

router = APIRouter()


@router.get("/api/stats/decision-quality", response_model=DecisionQualityResponse)
async def decision_quality():
    """比较辩论裁决与实际交易，返回决策质量得分。"""
    raw = compute_decision_quality()
    return DecisionQualityResponse(
        all_time=DecisionQualityBucket(**raw["all_time"]),
        month=DecisionQualityBucket(**raw["month"]),
        recent_items=[DecisionQualityItem(**item) for item in raw["recent_items"]],
    )
