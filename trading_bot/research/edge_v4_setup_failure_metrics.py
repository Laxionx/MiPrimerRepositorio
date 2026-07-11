"""Descriptive aggregates for the read-only Edge V4 audit."""

from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Any


def outcome_distribution(records: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = Counter(str(record.get("outcome")) for record in records)
    values = [float(record["r_multiple"]) for record in records if record.get("r_multiple") is not None]
    winners = [float(record["pnl"]) for record in records if float(record.get("pnl", 0)) > 0]
    losers = [abs(float(record["pnl"])) for record in records if float(record.get("pnl", 0)) < 0]
    return {
        "total_trades": len(records),
        "wins": outcomes["win"],
        "losses": outcomes["loss"],
        "breakeven": outcomes["breakeven"],
        "r_distribution": summary(values),
        "expectancy_r": mean(values),
        "payoff_ratio": mean(winners) / mean(losers) if losers and mean(losers) else None,
        "win_loss_ratio": len(winners) / len(losers) if losers else None,
        "bars_held_distribution": summary(
            [float(record["bars_held"]) for record in records if record.get("bars_held") is not None]
        ),
    }


def mfe_mae_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [record for record in records if record["data_quality_status"] == "complete"]
    return {
        "complete_trade_count": len(complete),
        "mfe": summary([float(record["mfe"]) for record in complete]),
        "mae": summary([float(record["mae"]) for record in complete]),
        "mfe_r": summary([float(record["mfe_r"]) for record in complete]),
        "mae_r": summary([float(record["mae_r"]) for record in complete]),
        "bars_to_mfe": summary([float(record["bars_to_mfe"]) for record in complete]),
        "bars_to_mae": summary([float(record["bars_to_mae"]) for record in complete]),
    }


def stop_efficiency(records: list[dict[str, Any]]) -> dict[str, Any]:
    stops = [
        record for record in records
        if record["data_quality_status"] == "complete"
        and record.get("exit_reason") == "stop_loss"
    ]
    return {
        "stop_loss_trade_count": len(stops),
        "mean_mfe_r_before_stop": mean([float(record["mfe_r"]) for record in stops]),
        "mean_mae_r_before_stop": mean([float(record["mae_r"]) for record in stops]),
    }


def take_profit_efficiency(records: list[dict[str, Any]]) -> dict[str, Any]:
    positive_mfe = [
        record for record in records
        if record["data_quality_status"] == "complete" and float(record["mfe_r"]) > 0
    ]
    ratios = [float(record.get("r_multiple", 0)) / float(record["mfe_r"]) for record in positive_mfe]
    return {
        "trades_with_positive_mfe": len(positive_mfe),
        "realized_r_over_mfe_r": summary(ratios),
    }


def loss_streaks(records: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(records, key=lambda record: str(record.get("timestamp_open", "")))
    streaks: list[int] = []
    current = 0
    for record in ordered:
        if record.get("outcome") == "loss":
            current += 1
        elif current:
            streaks.append(current)
            current = 0
    if current:
        streaks.append(current)
    return {
        "loss_streak_count": len(streaks),
        "maximum_consecutive_losses": max(streaks) if streaks else 0,
        "distribution": summary([float(streak) for streak in streaks]),
    }


def early_movement_by_bar(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paths = [
        record for record in records
        if record.get("data_quality_status") == "complete"
        and "_favorable_path_r" in record
    ]
    maximum_bars = max((len(record["_favorable_path_r"]) for record in paths), default=0)
    result = []
    for index in range(maximum_bars):
        favorable = [record["_favorable_path_r"][index] for record in paths if len(record["_favorable_path_r"]) > index]
        adverse = [record["_adverse_path_r"][index] for record in paths if len(record["_adverse_path_r"]) > index]
        result.append(
            {
                "bar_index": index,
                "trade_count": len(favorable),
                "mean_cumulative_mfe_r": mean(favorable),
                "mean_cumulative_mae_r": mean(adverse),
            }
        )
    return result


def exit_reason_excursions(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record.get("exit_reason")), []).append(record)
    return {
        reason: {
            "trade_count": len(items),
            "complete_trade_count": sum(item["data_quality_status"] == "complete" for item in items),
            "mean_mfe_r": mean([float(item["mfe_r"]) for item in items if item["data_quality_status"] == "complete"]),
            "mean_mae_r": mean([float(item["mae_r"]) for item in items if item["data_quality_status"] == "complete"]),
        }
        for reason, items in sorted(grouped.items())
    }


def ambiguity_summary(records: list[dict[str, Any]]) -> dict[str, int]:
    complete = [record for record in records if record["data_quality_status"] == "complete"]
    return {
        "complete_trade_count": len(complete),
        "ambiguous_both_levels_count": sum(bool(record["ambiguous_both_levels"]) for record in complete),
    }


def data_quality(records: list[dict[str, Any]]) -> dict[str, Any]:
    reasons = Counter(record.get("data_quality_reason") for record in records if record.get("data_quality_reason"))
    complete = sum(record["data_quality_status"] == "complete" for record in records)
    return {
        "complete_trade_count": complete,
        "data_unavailable_trade_count": len(records) - complete,
        "unavailable_by_reason": dict(sorted(reasons.items())),
    }


def summary(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "mean": mean(values),
        "median": float(median(values)) if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None
