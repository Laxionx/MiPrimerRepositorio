import csv
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


AVERAGE_FIELDS = (
    "pnl",
    "r_multiple",
    "context_score",
    "entry_score",
    "extension_atr",
    "spread",
    "volatility",
    "atr",
    "candle_range",
    "risk_points",
    "reward_points",
    "planned_rr",
    "entry_distance_from_sweep",
    "bars_held",
    "distance_to_h1_high",
    "distance_to_h1_low",
    "distance_to_h1_mid",
)
CATEGORY_FIELDS = (
    "market_regime",
    "context_bias",
    "direction",
    "sweep_type",
    "exit_reason",
)
EXPORT_FIELDS = (
    "trade_id",
    "timestamp_open",
    "timestamp_close",
    "symbol",
    "timeframe",
    "direction",
    "entry",
    "stop_loss",
    "take_profit",
    "exit_price",
    "pnl",
    "r_multiple",
    "outcome",
    "market_regime",
    "context_bias",
    "context_score",
    "entry_score",
    "extension_atr",
    "spread",
    "volatility",
    "atr",
    "candle_range",
    "risk_points",
    "reward_points",
    "planned_rr",
    "entry_distance_from_sweep",
    "bars_held",
    "exit_reason",
    "sweep_type",
    "distance_to_h1_high",
    "distance_to_h1_low",
    "distance_to_h1_mid",
)


def select_trade_groups(
    trades: list[dict[str, Any]],
    *,
    limit: int = 100,
    rank_by: str = "pnl",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if rank_by not in {"pnl", "r_multiple"}:
        raise ValueError("rank_by must be pnl or r_multiple")
    if limit <= 0:
        raise ValueError("limit must be greater than zero")
    winners = sorted(
        (trade for trade in trades if float(trade["pnl"]) > 0),
        key=lambda trade: float(trade[rank_by]),
        reverse=True,
    )[:limit]
    losers = sorted(
        (trade for trade in trades if float(trade["pnl"]) < 0),
        key=lambda trade: float(trade[rank_by]),
    )[:limit]
    return winners, losers


def analyze_trade_review(
    trades: list[dict[str, Any]],
    *,
    limit: int = 100,
    rank_by: str = "pnl",
) -> dict[str, Any]:
    winners, losers = select_trade_groups(trades, limit=limit, rank_by=rank_by)
    winner_summary = _summarize(winners)
    loser_summary = _summarize(losers)
    return {
        "rank_by": rank_by,
        "selected_winners": winners,
        "selected_losers": losers,
        "winners": winner_summary,
        "losers": loser_summary,
        "key_differences": _differences(winner_summary, loser_summary),
        "clues": _clues(winner_summary, loser_summary),
    }


def generate_trade_review_report(
    analysis: dict[str, Any],
    output: str | Path,
) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Best vs Worst Trade Review",
        "",
        f"Ranking field: {analysis['rank_by']}",
        "",
        "## Top Winners Summary",
        "",
        *_summary_table(analysis["winners"]),
        "",
        "## Worst Losers Summary",
        "",
        *_summary_table(analysis["losers"]),
        "",
        "## Key Differences",
        "",
    ]
    differences = analysis["key_differences"] or ["No comparable numeric data."]
    lines.extend(f"- {difference}" for difference in differences)
    lines.extend(["", "## Possible Edge V2 Clues", ""])
    clues = analysis["clues"] or ["No factual differences available."]
    lines.extend(f"- {clue}" for clue in clues)
    lines.extend(
        [
            "",
            "These observations describe the selected samples only; "
            "they do not establish that an edge exists.",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def export_trade_groups(
    analysis: dict[str, Any],
    winners_output: str | Path,
    losers_output: str | Path,
) -> tuple[Path, Path]:
    winners_path = _write_csv(winners_output, analysis["selected_winners"])
    losers_path = _write_csv(losers_output, analysis["selected_losers"])
    return winners_path, losers_path


def _summarize(trades: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "trades": len(trades),
        "wins": sum(float(trade["pnl"]) > 0 for trade in trades),
        "losses": sum(float(trade["pnl"]) < 0 for trade in trades),
    }
    for field in AVERAGE_FIELDS:
        values = [
            float(trade[field])
            for trade in trades
            if trade.get(field) is not None
        ]
        summary[f"average_{field}"] = mean(values) if values else None
    for field in CATEGORY_FIELDS:
        values = [_category_value(trade, field) for trade in trades]
        summary[f"most_common_{field}"] = _most_common(values)
    return summary


def _category_value(trade: dict[str, Any], field: str) -> str | None:
    if field == "sweep_type":
        if trade.get(field):
            return str(trade[field]).lower()
        direction = str(trade.get("direction", "")).upper()
        if direction == "LONG":
            return "low_sweep"
        if direction == "SHORT":
            return "high_sweep"
        return None
    value = trade.get(field)
    return str(value).lower() if value is not None else None


def _most_common(values: list[str | None]) -> str | None:
    populated = [value for value in values if value is not None]
    if not populated:
        return None
    counts = Counter(populated)
    highest = max(counts.values())
    return sorted(value for value, count in counts.items() if count == highest)[0]


def _differences(
    winners: dict[str, Any],
    losers: dict[str, Any],
) -> list[str]:
    differences = []
    for field in AVERAGE_FIELDS:
        winner_value = winners[f"average_{field}"]
        loser_value = losers[f"average_{field}"]
        if winner_value is None or loser_value is None:
            continue
        differences.append(
            f"Average {field}: winners {_format(winner_value)}, "
            f"losers {_format(loser_value)}, difference "
            f"{_format(winner_value - loser_value)}."
        )
    for field in CATEGORY_FIELDS:
        winner_value = winners[f"most_common_{field}"]
        loser_value = losers[f"most_common_{field}"]
        differences.append(
            f"Most common {field}: winners {_format(winner_value)}, "
            f"losers {_format(loser_value)}."
        )
    return differences


def _clues(
    winners: dict[str, Any],
    losers: dict[str, Any],
) -> list[str]:
    numeric_differences = []
    missing = []
    for field in AVERAGE_FIELDS:
        winner_value = winners[f"average_{field}"]
        loser_value = losers[f"average_{field}"]
        if winner_value is None or loser_value is None:
            missing.append(field)
            continue
        if field in {"pnl", "r_multiple"}:
            continue
        numeric_differences.append(
            (abs(winner_value - loser_value), field, winner_value - loser_value)
        )
    numeric_differences.sort(reverse=True)
    clues = [
        f"Observed average {field} difference: {_format(difference)}."
        for _, field, difference in numeric_differences[:3]
    ]
    if missing:
        clues.append(
            "Not available in the current journal: " + ", ".join(missing) + "."
        )
    return clues


def _summary_table(summary: dict[str, Any]) -> list[str]:
    rows = [
        ("trades", summary["trades"]),
        ("wins", summary["wins"]),
        ("losses", summary["losses"]),
    ]
    rows.extend(
        (f"average {field}", summary[f"average_{field}"])
        for field in AVERAGE_FIELDS
    )
    rows.extend(
        (f"most common {field}", summary[f"most_common_{field}"])
        for field in CATEGORY_FIELDS
    )
    lines = ["| Metric | Value |", "|---|---:|"]
    lines.extend(f"| {label} | {_format(value)} |" for label, value in rows)
    return lines


def _write_csv(path: str | Path, trades: list[dict[str, Any]]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for trade in trades:
            row = dict(trade)
            row["sweep_type"] = _category_value(trade, "sweep_type")
            writer.writerow(row)
    return output_path


def _format(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, (int, float)):
        return f"{float(value):.4f}"
    return str(value)
