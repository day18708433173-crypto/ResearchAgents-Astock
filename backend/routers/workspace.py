"""路由：投研工作台聚合数据"""

from datetime import datetime

from fastapi import APIRouter

from services.db_init import get_db
from services.market_data import get_realtime_prices_batch
from backend.helpers import (
    _calculate_position,
    _fetch_latest_debates_by_ticker,
    _fetch_last_debate_time_by_ticker,
    compute_blind_spot_radar,
    compute_portfolio_summary,
    compute_stale_alerts,
    compute_workspace_queue,
)
from services.strategy_alerts import get_active_alerts_summary
from backend.schemas import (
    BlindSpotRadarResponse,
    StaleAlertsResponse,
    WorkspaceOverviewResponse,
    WorkspaceQueueItem,
)

router = APIRouter()


def _load_workspace_context():
    conn = get_db()
    dossiers = [dict(row) for row in conn.execute(
        "SELECT * FROM dossier ORDER BY updated_at DESC"
    ).fetchall()]

    latest_debates = _fetch_latest_debates_by_ticker(conn)
    last_debate_map = _fetch_last_debate_time_by_ticker(conn)

    strategy_map: dict[int, str] = {}
    for row in conn.execute(
        """SELECT sv.dossier_id, sv.strategy_content
           FROM strategy_version sv
           INNER JOIN (
               SELECT dossier_id, MAX(version_number) AS max_version
               FROM strategy_version
               GROUP BY dossier_id
           ) latest ON sv.dossier_id = latest.dossier_id
               AND sv.version_number = latest.max_version"""
    ).fetchall():
        strategy_map[row["dossier_id"]] = row["strategy_content"]

    position_map: dict[int, dict] = {}
    for dossier in dossiers:
        txns = conn.execute(
            'SELECT * FROM "transaction" WHERE dossier_id = ? ORDER BY txn_time ASC',
            (dossier["dossier_id"],),
        ).fetchall()
        position_map[dossier["dossier_id"]] = _calculate_position(txns, dossier)

    conn.close()

    codes = []
    for dossier in dossiers:
        code = (dossier.get("stock_code") or "").split(".")[0]
        if code:
            codes.append(code)
    price_map = get_realtime_prices_batch(list(dict.fromkeys(codes)))

    return dossiers, latest_debates, last_debate_map, strategy_map, position_map, price_map


@router.get("/api/workspace/overview", response_model=WorkspaceOverviewResponse)
async def workspace_overview():
    """工作台首页聚合：研究队列、观点过期预警、盲点雷达。"""
    now = datetime.now()
    dossiers, latest_debates, last_debate_map, strategy_map, position_map, price_map = (
        _load_workspace_context()
    )

    queue_raw = compute_workspace_queue(
        dossiers, latest_debates, price_map, strategy_map, position_map
    )
    stale_raw = compute_stale_alerts(dossiers, last_debate_map, now)
    blind_raw = compute_blind_spot_radar(dossiers, latest_debates, last_debate_map, now)
    portfolio = compute_portfolio_summary(dossiers, position_map)
    strategy_alerts = get_active_alerts_summary()

    return WorkspaceOverviewResponse(
        queue=[WorkspaceQueueItem(**item) for item in queue_raw],
        stale_alerts=StaleAlertsResponse(**stale_raw),
        blind_spot=BlindSpotRadarResponse(**blind_raw),
        portfolio=portfolio,
        strategy_alerts=strategy_alerts,
    )


@router.get("/api/workspace/stale-alerts", response_model=StaleAlertsResponse)
async def stale_alerts():
    """观点过期预警列表。"""
    conn = get_db()
    dossiers = [dict(row) for row in conn.execute("SELECT * FROM dossier").fetchall()]
    last_debate_map = _fetch_last_debate_time_by_ticker(conn)
    conn.close()
    stale_raw = compute_stale_alerts(dossiers, last_debate_map)
    return StaleAlertsResponse(**stale_raw)
