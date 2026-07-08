import math
from collections.abc import Iterable, Mapping
from typing import Any


def calculate_performance_metrics(
    trades: Iterable[Mapping[str, Any]],
) -> dict[str, int | float | None]:
    """Calculate basic performance metrics from chronologically ordered trades."""
    records = list(trades)
    pnl_values = [_finite_number(record.get("pnl"), "pnl") for record in records]
    wins = [pnl for pnl in pnl_values if pnl > 0]
    losses = [pnl for pnl in pnl_values if pnl < 0]

    gross_profit = sum(wins, 0.0)
    gross_loss = sum(losses, 0.0)
    net_pnl = sum(pnl_values, 0.0)
    total_trades = len(pnl_values)
    r_values = [
        r_value
        for record, pnl in zip(records, pnl_values)
        if (r_value := _trade_r(record, pnl)) is not None
    ]

    return {
        "total_trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / total_trades if total_trades else 0.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_pnl": net_pnl,
        "average_win": gross_profit / len(wins) if wins else 0.0,
        "average_loss": gross_loss / len(losses) if losses else 0.0,
        "expectancy": net_pnl / total_trades if total_trades else 0.0,
        "profit_factor": (
            gross_profit / abs(gross_loss) if gross_loss < 0 else None
        ),
        "max_drawdown": _max_drawdown(pnl_values),
        "average_r": sum(r_values) / len(r_values) if r_values else 0.0,
        "largest_loss": min(losses) if losses else None,
        "largest_win": max(wins) if wins else None,
    }


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    return number


def _trade_r(record: Mapping[str, Any], pnl: float) -> float | None:
    if record.get("r_multiple") is not None:
        return _finite_number(record["r_multiple"], "r_multiple")
    if record.get("risk_amount") is None:
        return None
    risk_amount = _finite_number(record["risk_amount"], "risk_amount")
    if risk_amount <= 0:
        raise ValueError("risk_amount must be greater than zero")
    return pnl / risk_amount


def _max_drawdown(pnl_values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in pnl_values:
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown
