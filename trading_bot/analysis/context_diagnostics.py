from collections import Counter
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

import pandas as pd

from trading_bot.signals.aqtf import ContextEngine


REGIMES = ("trend", "range", "compression", "unknown")
BIASES = ("long", "short", "neutral")


def evaluate_candle_contexts(
    candles: pd.DataFrame,
    context_engine: ContextEngine | None = None,
) -> list[dict[str, Any]]:
    """Evaluate each candle using only H1 bars closed by that timestamp."""
    if candles.empty:
        return []
    engine = context_engine or ContextEngine()
    indexed = candles.set_index("time")
    h1 = indexed.resample("1h", label="right", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "tick_volume": "sum",
        }
    )
    h1 = h1.dropna(subset=["open", "high", "low", "close"])

    evaluations = []
    for index in range(len(h1)):
        start = max(0, index + 1 - engine.moving_average_period)
        result = engine.evaluate(h1.iloc[start : index + 1].reset_index())
        evaluations.append({"time": h1.index[index], **result})

    context_frame = pd.DataFrame(evaluations)
    candle_times = candles[["time"]].sort_values("time")
    if context_frame.empty:
        unknown = engine.evaluate(pd.DataFrame())
        return [unknown.copy() for _ in range(len(candle_times))]
    merged = pd.merge_asof(
        candle_times,
        context_frame.sort_values("time"),
        on="time",
        direction="backward",
    )
    unknown = engine.evaluate(pd.DataFrame())
    fields = tuple(unknown)
    return [
        {
            field: unknown[field] if pd.isna(row[field]) else row[field]
            for field in fields
        }
        for _, row in merged.iterrows()
    ]


def score_statistics(values: list[float | int]) -> dict[str, Any]:
    numbers = [float(value) for value in values]
    if not numbers:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "stddev": None,
            "most_common_values": [],
        }
    counts = Counter(numbers)
    highest_frequency = max(counts.values())
    most_common = [
        {"value": _whole_number(value), "count": count}
        for value, count in sorted(counts.items())
        if count == highest_frequency
    ]
    return {
        "count": len(numbers),
        "min": _whole_number(min(numbers)),
        "max": _whole_number(max(numbers)),
        "mean": mean(numbers),
        "median": median(numbers),
        "stddev": pstdev(numbers),
        "most_common_values": most_common,
    }


def analyze_context_diagnostics(
    candle_contexts: list[dict[str, Any]],
    accepted_trades: list[dict[str, Any]],
) -> dict[str, Any]:
    all_context_scores = [row["context_score"] for row in candle_contexts]
    trade_context_scores = [row["context_score"] for row in accepted_trades]
    trade_entry_scores = [row["entry_score"] for row in accepted_trades]
    analysis = {
        "all_candles": {
            "count": len(candle_contexts),
            "market_regime": _distribution(
                candle_contexts, "market_regime", REGIMES
            ),
            "context_score": _value_distribution(all_context_scores),
            "context_bias": _distribution(candle_contexts, "context_bias", BIASES),
            "context_score_stats": score_statistics(all_context_scores),
        },
        "accepted_trades": {
            "count": len(accepted_trades),
            "market_regime": _distribution(
                accepted_trades, "market_regime", REGIMES
            ),
            "context_score": _value_distribution(trade_context_scores),
            "context_bias": _distribution(accepted_trades, "context_bias", BIASES),
            "entry_score": _value_distribution(trade_entry_scores),
            "context_score_stats": score_statistics(trade_context_scores),
            "entry_score_stats": score_statistics(trade_entry_scores),
        },
    }
    analysis["conclusions"] = _conclusions(analysis)
    return analysis


def generate_context_diagnostics_report(
    analysis: dict[str, Any],
    output: str | Path,
) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Context Diagnostics v1", ""]
    if not analysis["all_candles"]["count"] and not analysis["accepted_trades"]["count"]:
        lines.extend(["No candle or accepted-trade data available.", ""])

    lines.extend(
        _population_section("All Backtest Candles", analysis["all_candles"])
    )
    lines.extend(
        _population_section("Accepted Trades", analysis["accepted_trades"])
    )
    lines.extend(["## Score Statistics", ""])
    lines.extend(
        _statistics_table(
            [
                (
                    "All candles context_score",
                    analysis["all_candles"]["context_score_stats"],
                ),
                (
                    "Accepted trades context_score",
                    analysis["accepted_trades"]["context_score_stats"],
                ),
                (
                    "Accepted trades entry_score",
                    analysis["accepted_trades"]["entry_score_stats"],
                ),
            ]
        )
    )
    lines.extend(["", "## Conclusions", ""])
    lines.extend(f"- {conclusion}" for conclusion in analysis["conclusions"])
    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _distribution(
    records: list[dict[str, Any]],
    field: str,
    categories: tuple[str, ...],
) -> dict[str, int]:
    counts = Counter(str(record.get(field, "unknown")).lower() for record in records)
    return {category: counts.get(category, 0) for category in categories}


def _value_distribution(values: list[float | int]) -> dict[str, int]:
    counts = Counter(_whole_number(float(value)) for value in values)
    return {str(value): counts[value] for value in sorted(counts)}


def _conclusions(analysis: dict[str, Any]) -> list[str]:
    candles = analysis["all_candles"]
    trades = analysis["accepted_trades"]
    active_regimes = sum(count > 0 for count in candles["market_regime"].values())
    unique_scores = len(candles["context_score"])
    enough_variation = active_regimes >= 2 and unique_scores >= 3
    context_stats = candles["context_score_stats"]
    accepted_context_stats = trades["context_score_stats"]
    accepted_unique_scores = len(trades["context_score"])
    tightly_clustered = (
        accepted_context_stats["count"] > 0
        and (
            accepted_context_stats["stddev"] < 5
            or accepted_unique_scores <= 2
        )
    )
    range_count = candles["market_regime"]["range"]
    compression_count = candles["market_regime"]["compression"]
    entry_distribution = trades["entry_score"]
    accepted_count = trades["count"]
    saturated_count = sum(
        count
        for value, count in entry_distribution.items()
        if float(value) >= 85
    )
    saturation = saturated_count / accepted_count if accepted_count else 0.0
    return [
        (
            f"ContextEngine variation sufficient: {'yes' if enough_variation else 'no'}; "
            f"{active_regimes} regimes and {unique_scores} context-score values observed."
        ),
        (
            f"Context score tightly clustered in accepted trades: "
            f"{'yes' if tightly_clustered else 'no'}; accepted-trade standard "
            f"deviation {_format(accepted_context_stats['stddev'])}, versus "
            f"{_format(context_stats['stddev'])} across all candles."
        ),
        (
            f"Range detected: {'yes' if range_count else 'no'} ({range_count} candles); "
            f"compression detected: {'yes' if compression_count else 'no'} "
            f"({compression_count} candles)."
        ),
        (
            f"EntryScore saturation at 85+: "
            f"{'yes' if saturation >= 0.8 else 'no'} "
            f"({saturation * 100:.2f}% of accepted trades)."
        ),
    ]


def _population_section(title: str, population: dict[str, Any]) -> list[str]:
    lines = [f"## {title}", "", f"Observations: {population['count']}", ""]
    for label, key in (
        ("Market Regime", "market_regime"),
        ("Context Score", "context_score"),
        ("Context Bias", "context_bias"),
        ("Entry Score", "entry_score"),
    ):
        if key not in population:
            continue
        lines.extend([f"### {label}", "", "| Value | Count | Percentage |"])
        lines.append("|---|---:|---:|")
        total = population["count"]
        for value, count in population[key].items():
            percentage = count / total * 100 if total else 0.0
            lines.append(f"| {value} | {count} | {percentage:.2f}% |")
        lines.append("")
    return lines


def _statistics_table(
    rows: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    lines = [
        "| Score | Count | Min | Max | Mean | Median | Std Dev | Most Common |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for label, stats in rows:
        common = ", ".join(
            f"{item['value']} ({item['count']})"
            for item in stats["most_common_values"]
        ) or "N/A"
        lines.append(
            f"| {label} | {stats['count']} | {_format(stats['min'])} | "
            f"{_format(stats['max'])} | {_format(stats['mean'])} | "
            f"{_format(stats['median'])} | {_format(stats['stddev'])} | "
            f"{common} |"
        )
    return lines


def _whole_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _format(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):.4f}"
