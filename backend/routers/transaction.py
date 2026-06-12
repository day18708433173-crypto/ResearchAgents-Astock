"""路由：交易记录管理（不可编辑/删除）"""

from fastapi import APIRouter, HTTPException

from services.db_init import get_db
from services.commission import commission_configured, parse_rate_wan
from backend.schemas import TransactionCreateRequest, TransactionResponse

router = APIRouter()


@router.post("/api/transaction/create", response_model=TransactionResponse)
async def create_transaction(req: TransactionCreateRequest):
    """创建交易记录（买入或卖出，不可编辑）"""
    conn = get_db()

    # 检查卷宗是否存在
    dossier = conn.execute(
        "SELECT * FROM dossier WHERE dossier_id = ?", (req.dossier_id,)
    ).fetchone()
    if not dossier:
        conn.close()
        raise HTTPException(status_code=404, detail="卷宗不存在")

    dossier_dict = dict(dossier)
    txn_count = conn.execute(
        'SELECT COUNT(*) FROM "transaction" WHERE dossier_id = ?', (req.dossier_id,)
    ).fetchone()[0]

    if not commission_configured(dossier_dict):
        if txn_count == 0:
            if req.commission_min is None or req.commission_rate_wan is None:
                conn.close()
                raise HTTPException(
                    status_code=400,
                    detail="首次录入交易需设置佣金：单笔最低佣金（元）和费率（万几）",
                )
            conn.execute(
                """UPDATE dossier SET commission_min = ?, commission_rate = ?, updated_at = datetime('now')
                   WHERE dossier_id = ?""",
                (req.commission_min, parse_rate_wan(req.commission_rate_wan), req.dossier_id),
            )
        # 有历史交易但未配置佣金：按 0 处理，兼容旧数据

    # 卖出时验证持仓数量
    if req.direction == 'sell':
        current_shares = dossier_dict.get('current_hold_shares', 0) or 0
        if current_shares < req.quantity:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=f"卖出数量({req.quantity}股)超过当前持仓({current_shares}股)，请检查后重新录入"
            )

    # 插入交易记录
    conn.execute(
        '''INSERT INTO "transaction" 
           (dossier_id, direction, price, quantity, txn_time, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'))''',
        (req.dossier_id, req.direction, req.price, req.quantity, req.txn_time, req.notes)
    )

    # 更新持仓股数
    if req.direction == 'buy':
        conn.execute(
            "UPDATE dossier SET current_hold_shares = current_hold_shares + ?, updated_at = datetime('now') WHERE dossier_id = ?",
            (req.quantity, req.dossier_id)
        )
    else:
        conn.execute(
            "UPDATE dossier SET current_hold_shares = current_hold_shares - ?, updated_at = datetime('now') WHERE dossier_id = ?",
            (req.quantity, req.dossier_id)
        )

    conn.commit()

    # 获取刚创建的记录
    txn = conn.execute(
        'SELECT * FROM "transaction" WHERE dossier_id = ? ORDER BY created_at DESC LIMIT 1',
        (req.dossier_id,)
    ).fetchone()
    conn.close()

    return TransactionResponse(**dict(txn))
