"""路由：卷宗系统（创建/列表/详情/删除/导出/收益曲线）

注意：静态路由必须放在动态路由（/api/dossier/{id}）之前。
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException

from services.db_init import get_db
from services.akshare_client import search_stocks as _search_stocks
from services.commission import build_trading_metrics, get_dossier_commission
from backend.schemas import (
    DossierCreateRequest,
    DossierDetailResponse,
    DossierResponse,
    PortfolioSummaryResponse,
    ResearchNoteUpdateRequest,
    ReturnCurvePoint,
    ReturnCurveResponse,
    StrategyVersionResponse,
    TransactionResponse,
)
from backend.helpers import _calculate_position, _delete_dossier_cascade, compute_portfolio_summary

router = APIRouter()


def _ensure_dossier(conn, stock_code: str, fallback_name: str = ""):
    existing = conn.execute(
        "SELECT * FROM dossier WHERE stock_code = ?", (stock_code,)
    ).fetchone()
    if existing:
        return existing

    stock_info = _search_stocks(stock_code)
    stock_name = stock_info[0].get("name", "") if stock_info else (fallback_name or stock_code)
    industry = stock_info[0].get("industry", "") if stock_info else ""

    if not industry:
        try:
            import akshare as ak
            code_only = stock_code.split(".")[0]
            info_df = ak.stock_individual_info_em(symbol=code_only)
            for col_name in ["所属板块", "行业", "申万行业"]:
                row = info_df[info_df.iloc[:, 0] == col_name]
                if len(row) > 0:
                    industry = str(row.iloc[0, 1]).strip()
                    break
        except Exception:
            pass

    conn.execute(
        """INSERT INTO dossier (stock_code, stock_name, industry)
           VALUES (?, ?, ?)""",
        (stock_code, stock_name, industry),
    )
    return conn.execute(
        "SELECT * FROM dossier WHERE stock_code = ?", (stock_code,)
    ).fetchone()


@router.post("/api/dossier/create", response_model=DossierResponse)
async def create_dossier(req: DossierCreateRequest):
    """创建卷宗：首次进入头脑风暴室时触发"""
    conn = get_db()
    dossier = _ensure_dossier(conn, req.stock_code)
    conn.commit()
    conn.close()

    return DossierResponse(**dict(dossier))


@router.get("/api/dossier/list", response_model=List[DossierResponse])
async def list_dossiers():
    """获取用户所有卷宗"""
    conn = get_db()
    dossiers = conn.execute(
        "SELECT * FROM dossier ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()

    return [DossierResponse(**dict(d)) for d in dossiers]


@router.get("/api/dossier/by-stock/{stock_code}", response_model=DossierResponse)
async def get_dossier_by_stock(stock_code: str):
    """按股票代码获取卷宗，用于研究台加载常驻笔记。"""
    conn = get_db()
    dossier = conn.execute(
        "SELECT * FROM dossier WHERE stock_code = ?", (stock_code,)
    ).fetchone()
    conn.close()

    if not dossier:
        raise HTTPException(status_code=404, detail="卷宗不存在")

    return DossierResponse(**dict(dossier))


@router.get("/api/portfolio/summary", response_model=PortfolioSummaryResponse)
async def portfolio_summary():
    """投资组合全局概览：累计买入、已实现盈亏、持仓总市值（实时价）。"""
    conn = get_db()
    dossiers = [dict(row) for row in conn.execute(
        "SELECT * FROM dossier ORDER BY updated_at DESC"
    ).fetchall()]

    position_map: dict[int, dict] = {}
    for dossier in dossiers:
        txns = conn.execute(
            'SELECT * FROM "transaction" WHERE dossier_id = ? ORDER BY txn_time ASC',
            (dossier["dossier_id"],),
        ).fetchall()
        position_map[dossier["dossier_id"]] = _calculate_position(txns, dossier)
    conn.close()

    summary = compute_portfolio_summary(dossiers, position_map)
    return PortfolioSummaryResponse(**summary)


@router.put("/api/dossier/research-note", response_model=DossierResponse)
async def update_research_note(req: ResearchNoteUpdateRequest):
    """保存研究笔记到卷宗；若卷宗不存在则自动创建。"""
    conn = get_db()
    dossier = _ensure_dossier(conn, req.stock_code, req.ticker_name)
    conn.execute(
        "UPDATE dossier SET research_note = ?, updated_at = ? WHERE dossier_id = ?",
        (req.research_note, datetime.now().isoformat(), dossier["dossier_id"]),
    )
    conn.commit()
    updated = conn.execute(
        "SELECT * FROM dossier WHERE dossier_id = ?", (dossier["dossier_id"],)
    ).fetchone()
    conn.close()
    return DossierResponse(**dict(updated))


# 动态路由放在最后
@router.get("/api/dossier/{dossier_id}", response_model=DossierResponse)
async def get_dossier(dossier_id: int):
    """获取卷宗详情"""
    conn = get_db()
    dossier = conn.execute(
        "SELECT * FROM dossier WHERE dossier_id = ?", (dossier_id,)
    ).fetchone()
    conn.close()

    if not dossier:
        raise HTTPException(status_code=404, detail="卷宗不存在")

    return DossierResponse(**dict(dossier))


@router.delete("/api/dossier/{dossier_id}")
async def delete_dossier(dossier_id: int):
    """删除卷宗（不可恢复），删除后可对该股票重新创建卷宗。"""
    conn = get_db()
    deleted = _delete_dossier_cascade(conn, dossier_id)
    if not deleted:
        conn.close()
        raise HTTPException(status_code=404, detail="卷宗不存在")
    conn.commit()
    conn.close()
    return {"success": True, "dossier_id": dossier_id}


@router.get("/api/dossier/{dossier_id}/detail", response_model=DossierDetailResponse)
async def get_dossier_detail(dossier_id: int):
    """获取卷宗完整详情：包含策略版本、交易记录和持仓推算"""
    conn = get_db()

    # 1. 获取卷宗基础信息
    dossier = conn.execute(
        "SELECT * FROM dossier WHERE dossier_id = ?", (dossier_id,)
    ).fetchone()
    if not dossier:
        conn.close()
        raise HTTPException(status_code=404, detail="卷宗不存在")

    # 2. 获取所有策略版本
    strategies = conn.execute(
        "SELECT * FROM strategy_version WHERE dossier_id = ? ORDER BY version_number DESC",
        (dossier_id,)
    ).fetchall()

    # 3. 获取所有交易记录
    transactions = conn.execute(
        'SELECT * FROM "transaction" WHERE dossier_id = ? ORDER BY txn_time DESC',
        (dossier_id,)
    ).fetchall()

    # 4. 计算持仓推算（将 dossier 转换为 dict）
    position_summary = _calculate_position(transactions, dict(dossier))

    conn.close()

    return DossierDetailResponse(
        dossier=DossierResponse(**dict(dossier)),
        strategies=[StrategyVersionResponse(**dict(s)) for s in strategies],
        transactions=[TransactionResponse(**dict(t)) for t in transactions],
        position_summary=position_summary
    )


@router.get("/api/dossier/{dossier_id}/strategies", response_model=List[StrategyVersionResponse])
async def get_strategies(dossier_id: int):
    """获取卷宗的所有策略版本"""
    conn = get_db()
    strategies = conn.execute(
        "SELECT * FROM strategy_version WHERE dossier_id = ? ORDER BY version_number DESC",
        (dossier_id,)
    ).fetchall()
    conn.close()
    return [StrategyVersionResponse(**dict(s)) for s in strategies]


@router.get("/api/dossier/{dossier_id}/transactions", response_model=List[TransactionResponse])
async def get_transactions(dossier_id: int):
    """获取卷宗的所有交易记录"""
    conn = get_db()
    transactions = conn.execute(
        'SELECT * FROM "transaction" WHERE dossier_id = ? ORDER BY txn_time DESC',
        (dossier_id,)
    ).fetchall()
    conn.close()
    return [TransactionResponse(**dict(t)) for t in transactions]


@router.get("/api/export/dossier/{dossier_id}")
async def export_dossier(dossier_id: int, format: str = "json"):
    """导出卷宗数据"""
    conn = get_db()

    # 获取卷宗基本信息
    dossier = conn.execute("SELECT * FROM dossier WHERE dossier_id = ?", (dossier_id,)).fetchone()
    if not dossier:
        conn.close()
        raise HTTPException(status_code=404, detail="卷宗不存在")

    # 获取策略版本
    strategies = conn.execute(
        "SELECT * FROM strategy_version WHERE dossier_id = ? ORDER BY created_at",
        (dossier_id,)
    ).fetchall()

    # 获取交易记录
    transactions = conn.execute(
        'SELECT * FROM "transaction" WHERE dossier_id = ? ORDER BY txn_time',
        (dossier_id,)
    ).fetchall()

    conn.close()

    data = {
        "dossier": dict(dossier),
        "strategies": [dict(s) for s in strategies],
        "transactions": [dict(t) for t in transactions],
        "exported_at": datetime.now().isoformat()
    }

    if format == "json":
        return data
    else:
        # CSV 格式需要特殊处理，返回文本
        import io
        output = io.StringIO()

        # 写入卷宗基本信息
        output.write("# 卷宗基本信息\n")
        output.write(f"股票代码,{dossier['stock_code']}\n")
        output.write(f"股票名称,{dossier['stock_name']}\n")
        output.write(f"创建时间,{dossier['created_at']}\n")
        if dossier.get("research_note"):
            output.write("\n# 研究笔记\n")
            output.write(f"{dossier['research_note']}\n")
        output.write("\n")

        # 写入交易记录
        output.write("# 交易记录\n")
        output.write("时间,方向,价格,数量,金额,备注\n")
        for t in transactions:
            amount = float(t['price']) * float(t['quantity'])
            output.write(f"{t['txn_time']},{t['direction']},{t['price']},{t['quantity']},{amount},{t['notes'] or ''}\n")
        output.write("\n")

        # 写入策略版本
        output.write("# 策略版本\n")
        output.write("创建时间,版本,内容\n")
        for s in strategies:
            output.write(f"{s['created_at']},{s['version_number']},{s['strategy_content']}\n")

        return {"format": "csv", "content": output.getvalue()}


@router.get("/api/dossier/{dossier_id}/return-curve")
async def get_return_curve(dossier_id: int):
    """获取收益曲线数据"""
    conn = get_db()

    # 获取卷宗信息
    dossier = conn.execute("SELECT * FROM dossier WHERE dossier_id = ?", (dossier_id,)).fetchone()
    if not dossier:
        conn.close()
        raise HTTPException(status_code=404, detail="卷宗不存在")

    # 获取所有交易记录，按时间排序
    transactions = conn.execute(
        'SELECT * FROM "transaction" WHERE dossier_id = ? ORDER BY txn_time ASC',
        (dossier_id,)
    ).fetchall()

    conn.close()

    if not transactions:
        return ReturnCurveResponse(curve=[], summary={"total_transactions": 0})

    commission_min, commission_rate = get_dossier_commission(dict(dossier))
    pos = _calculate_position(transactions, dict(dossier))
    metrics = build_trading_metrics(transactions, commission_min, commission_rate)
    curve_points = [ReturnCurvePoint(**p) for p in metrics["curve_points"]]
    last_point = curve_points[-1] if curve_points else None
    summary = {
        "total_transactions": len(transactions),
        "final_holdings": last_point.holdings if last_point else 0,
        "total_realized_profit": last_point.realized_profit if last_point else 0,
        "total_unrealized_profit": pos.get("unrealized_profit", last_point.unrealized_profit if last_point else 0),
        "total_return_pct": last_point.total_return if last_point else 0,
        "total_commission": pos.get("total_commission", 0),
        "buy_commission": pos.get("buy_commission", 0),
        "sell_commission": pos.get("sell_commission", 0),
        "commission_min": pos.get("commission_min"),
        "commission_rate": pos.get("commission_rate"),
        "commission_rate_label": pos.get("commission_rate_label", ""),
        "current_price": pos.get("current_price", 0),
        "market_value": pos.get("market_value", 0),
        "unrealized_profit_pct": pos.get("unrealized_profit_pct", 0),
        "holding_return_pct": pos.get("holding_return_pct", 0),
        "price_updated_at": pos.get("price_updated_at"),
    }

    return ReturnCurveResponse(curve=curve_points, summary=summary)


@router.get("/api/dossier/{dossier_id}/position")
async def get_dossier_position(dossier_id: int):
    """获取卷宗实时持仓与浮动盈亏。"""
    conn = get_db()
    dossier = conn.execute(
        "SELECT * FROM dossier WHERE dossier_id = ?", (dossier_id,)
    ).fetchone()
    if not dossier:
        conn.close()
        raise HTTPException(status_code=404, detail="卷宗不存在")

    transactions = conn.execute(
        'SELECT * FROM "transaction" WHERE dossier_id = ? ORDER BY txn_time ASC',
        (dossier_id,),
    ).fetchall()
    conn.close()

    position = _calculate_position(transactions, dict(dossier))
    return {
        "dossier_id": dossier_id,
        "stock_code": dossier["stock_code"],
        "stock_name": dossier["stock_name"],
        "position_summary": position,
    }
