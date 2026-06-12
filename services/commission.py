"""A 股交易佣金计算与持仓收益推算"""

from __future__ import annotations

from typing import Any


def calc_trade_commission(amount: float, commission_min: float, commission_rate: float) -> float:
    """单笔佣金 = max(最低佣金, 成交金额 × 费率)"""
    if commission_rate <= 0 and commission_min <= 0:
        return 0.0
    return round(max(commission_min, amount * commission_rate), 2)


def parse_rate_wan(wan: float) -> float:
    """万2.5 → 0.00025"""
    return wan / 10000.0


def format_rate_wan(rate: float) -> str:
    """0.00025 → 万2.5"""
    wan = rate * 10000
    if abs(wan - round(wan)) < 1e-9:
        return f"万{int(round(wan))}"
    text = f"{wan:g}"
    return f"万{text}"


def get_dossier_commission(dossier: dict) -> tuple[float, float]:
    """从卷宗读取佣金配置；未配置时视为 0（兼容旧数据）"""
    commission_min = dossier.get("commission_min")
    commission_rate = dossier.get("commission_rate")
    if commission_min is None or commission_rate is None:
        return 0.0, 0.0
    return float(commission_min), float(commission_rate)


def commission_configured(dossier: dict) -> bool:
    return dossier.get("commission_min") is not None and dossier.get("commission_rate") is not None


def build_trading_metrics(
    transactions: list,
    commission_min: float,
    commission_rate: float,
) -> dict[str, Any]:
    """按时间顺序推算持仓、盈亏与收益曲线（含佣金，移动加权平均成本法）"""
    sorted_txns = sorted(transactions, key=lambda t: dict(t)["txn_time"])

    cumulative_buy_quantity = 0
    cumulative_buy_cost = 0.0
    total_buy_amount_gross = 0.0
    total_buy_deployment = 0.0
    total_sell_amount_gross = 0.0
    total_buy_shares = 0
    total_sell_shares = 0
    total_commission = 0.0
    buy_commission = 0.0
    sell_commission = 0.0
    realized_profit = 0.0
    curve_points: list[dict] = []

    for txn in sorted_txns:
        t = dict(txn)
        quantity = int(t["quantity"])
        price = float(t["price"])
        amount = price * quantity
        comm = calc_trade_commission(amount, commission_min, commission_rate)
        total_commission += comm

        if t["direction"] == "buy":
            buy_commission += comm
            cumulative_buy_quantity += quantity
            cumulative_buy_cost += amount + comm
            total_buy_amount_gross += amount
            total_buy_deployment += amount + comm
            total_buy_shares += quantity
        else:
            sell_commission += comm
            avg_cost = cumulative_buy_cost / cumulative_buy_quantity if cumulative_buy_quantity > 0 else 0.0
            net_proceeds = amount - comm
            realized_profit += net_proceeds - avg_cost * quantity
            cumulative_buy_cost -= avg_cost * quantity
            cumulative_buy_quantity -= quantity
            total_sell_amount_gross += amount
            total_sell_shares += quantity

        unrealized_profit = cumulative_buy_quantity * price - cumulative_buy_cost
        total_return = 0.0
        if total_buy_deployment > 0:
            total_return = (realized_profit + unrealized_profit) / total_buy_deployment * 100

        curve_points.append({
            "date": t["txn_time"][:10],
            "total_cost": round(total_buy_deployment, 2),
            "total_value": round(cumulative_buy_quantity * price, 2),
            "realized_profit": round(realized_profit, 2),
            "unrealized_profit": round(unrealized_profit, 2),
            "total_return": round(total_return, 2),
            "holdings": cumulative_buy_quantity,
            "total_commission": round(total_commission, 2),
        })

    current_shares = cumulative_buy_quantity
    avg_buy_price = cumulative_buy_cost / current_shares if current_shares > 0 else (
        cumulative_buy_cost / total_buy_shares if total_buy_shares > 0 else 0.0
    )
    avg_sell_price = total_sell_amount_gross / total_sell_shares if total_sell_shares > 0 else 0.0

    return {
        "position_summary": {
            "current_shares": current_shares,
            "total_buy_shares": total_buy_shares,
            "total_sell_shares": total_sell_shares,
            "avg_buy_price": round(avg_buy_price, 2),
            "avg_sell_price": round(avg_sell_price, 2),
            "total_buy_amount": round(total_buy_amount_gross, 2),
            "total_buy_deployment": round(total_buy_deployment, 2),
            "total_sell_amount": round(total_sell_amount_gross, 2),
            "realized_profit": round(realized_profit, 2),
            "cost_basis": round(avg_buy_price, 2),
            "total_cost": round(cumulative_buy_cost, 2),
            "total_commission": round(total_commission, 2),
            "buy_commission": round(buy_commission, 2),
            "sell_commission": round(sell_commission, 2),
            "commission_min": commission_min,
            "commission_rate": commission_rate,
            "commission_rate_label": format_rate_wan(commission_rate) if commission_rate > 0 else "",
        },
        "curve_points": curve_points,
    }
