import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from trading_bot.metrics.performance import calculate_performance_metrics


REGIMES = ("trend", "range", "compression", "unknown")
DIRECTIONS = ("long", "short")
SWEEP_TYPES = ("high_sweep", "low_sweep")
CONTEXT_BUCKETS = ("0-59", "60-69", "70-79", "80+")
ENTRY_BUCKETS = ("0-64", "65-74", "75-84", "85+")


def load_trade_journal(path: str | Path) -> list[dict[str, Any]]:
    journal_path = Path(path)
    if not journal_path.exists():
        return []
    return [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def analyze_trade_segments(trades: list[dict[str, Any]]) -> dict[str, Any]:
    dimensions = {
        "Market Regime": _segment(
            trades,
            REGIMES,
            lambda trade: str(trade.get("market_regime", "unknown")).lower(),
        ),
        "Direction": _segment(
            trades,
            DIRECTIONS,
            lambda trade: str(trade["direction"]).lower(),
        ),
        "Sweep Type": _segment(trades, SWEEP_TYPES, _sweep_type),
        "Context Score": _segment(
            trades,
            CONTEXT_BUCKETS,
            lambda trade: _context_bucket(float(trade["context_score"])),
        ),
        "Entry Score": _segment(
            trades,
            ENTRY_BUCKETS,
            lambda trade: _entry_bucket(float(trade["entry_score"])),
        ),
    }
    ranked = [
        {"dimension": dimension, **segment}
        for dimension, segments in dimensions.items()
        for segment in segments
        if segment["trades"] > 0
    ]
    top = sorted(ranked, key=_best_sort_key, reverse=True)[:10]
    bottom = sorted(ranked, key=_worst_sort_key)[:10]
    return {
        "overall": calculate_performance_metrics(trades),
        "dimensions": dimensions,
        "top_segments": top,
        "bottom_segments": bottom,
        "conclusions": _conclusions(dimensions),
    }


def generate_segmentation_report(
    analysis: dict[str, Any],
    output: str | Path,
) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Trade Segmentation Analysis", ""]
    if analysis["overall"]["total_trades"] == 0:
        lines.extend(["No completed trades available.", ""])
    else:
        lines.extend(
            [
                f"Overall completed trades: {analysis['overall']['total_trades']}",
                "",
            ]
        )

    for dimension, segments in analysis["dimensions"].items():
        lines.extend([f"## {dimension}", "", _table_header()])
        lines.extend(_table_row(segment) for segment in segments)
        lines.append("")

    lines.extend(["## Top 10 Best Performing Segments", "", _rank_header()])
    lines.extend(_rank_row(segment) for segment in analysis["top_segments"])
    lines.extend(["", "## Bottom 10 Worst Performing Segments", "", _rank_header()])
    lines.extend(_rank_row(segment) for segment in analysis["bottom_segments"])
    lines.extend(["", "## Conclusions", ""])
    lines.extend(f"- {conclusion}" for conclusion in analysis["conclusions"])
    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _segment(
    trades: list[dict[str, Any]],
    categories: tuple[str, ...],
    classifier: Callable[[dict[str, Any]], str],
) -> list[dict[str, Any]]:
    classified = [(trade, classifier(trade)) for trade in trades]
    result = []
    for category in categories:
        members = [trade for trade, value in classified if value == category]
        metrics = calculate_performance_metrics(members)
        result.append(
            {
                "segment": category,
                "trades": metrics["total_trades"],
                "wins": metrics["wins"],
                "losses": metrics["losses"],
                "win_rate": metrics["win_rate"],
                "expectancy": metrics["expectancy"],
                "profit_factor": metrics["profit_factor"],
                "average_r": metrics["average_r"],
                "net_pnl": metrics["net_pnl"],
            }
        )
    return result


def _sweep_type(trade: dict[str, Any]) -> str:
    if trade.get("sweep_type") in SWEEP_TYPES:
        return str(trade["sweep_type"])
    return "low_sweep" if str(trade["direction"]).upper() == "LONG" else "high_sweep"


def _context_bucket(score: float) -> str:
    if score < 60:
        return "0-59"
    if score < 70:
        return "60-69"
    if score < 80:
        return "70-79"
    return "80+"


def _entry_bucket(score: float) -> str:
    if score < 65:
        return "0-64"
    if score < 75:
        return "65-74"
    if score < 85:
        return "75-84"
    return "85+"


def _best_sort_key(segment: dict[str, Any]) -> tuple[float, float]:
    profit_factor = segment["profit_factor"]
    return (
        float(profit_factor) if profit_factor is not None else float("-inf"),
        float(segment["expectancy"]),
    )


def _worst_sort_key(segment: dict[str, Any]) -> tuple[float, float]:
    profit_factor = segment["profit_factor"]
    return (
        float(profit_factor) if profit_factor is not None else float("inf"),
        float(segment["expectancy"]),
    )


def _conclusions(dimensions: dict[str, list[dict[str, Any]]]) -> list[str]:
    regimes = _nonempty(dimensions["Market Regime"])
    conclusions = []
    if regimes:
        best = max(regimes, key=lambda row: row["expectancy"])
        worst = min(regimes, key=lambda row: row["expectancy"])
        conclusions.append(
            f"Best market regime by expectancy: {best['segment']} "
            f"({_number(best['expectancy'])})."
        )
        conclusions.append(
            f"Worst market regime by expectancy: {worst['segment']} "
            f"({_number(worst['expectancy'])})."
        )
    else:
        conclusions.extend(
            [
                "Best market regime: insufficient data.",
                "Worst market regime: insufficient data.",
            ]
        )
    conclusions.append(_comparison("Longs vs shorts", dimensions["Direction"]))
    conclusions.append(
        _comparison("High sweeps vs low sweeps", dimensions["Sweep Type"])
    )
    conclusions.append(
        _score_trend("Higher Context Score", dimensions["Context Score"])
    )
    conclusions.append(_score_trend("Higher Entry Score", dimensions["Entry Score"]))
    return conclusions


def _comparison(label: str, segments: list[dict[str, Any]]) -> str:
    populated = _nonempty(segments)
    if len(populated) < 2:
        return f"{label}: insufficient data."
    first, second = populated[:2]
    if first["expectancy"] == second["expectancy"]:
        return f"{label}: equal expectancy ({_number(first['expectancy'])})."
    winner = max(populated, key=lambda row: row["expectancy"])
    loser = min(populated, key=lambda row: row["expectancy"])
    return (
        f"{label}: {winner['segment']} has higher expectancy "
        f"({_number(winner['expectancy'])} vs {_number(loser['expectancy'])})."
    )


def _score_trend(label: str, segments: list[dict[str, Any]]) -> str:
    populated = _nonempty(segments)
    if len(populated) < 2:
        return f"{label}: insufficient data."
    expectations = [float(segment["expectancy"]) for segment in populated]
    improves = all(
        current >= previous
        for previous, current in zip(expectations, expectations[1:])
    )
    fact = "is non-decreasing" if improves else "is not consistently increasing"
    return f"{label}: expectancy {fact} across populated score buckets."


def _nonempty(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [segment for segment in segments if segment["trades"] > 0]


def _table_header() -> str:
    return (
        "| Segment | Trades | Wins | Losses | Win Rate | Expectancy | "
        "Profit Factor | Average R | Net PnL |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"
    )


def _table_row(segment: dict[str, Any]) -> str:
    return (
        f"| {segment['segment']} | {segment['trades']} | {segment['wins']} | "
        f"{segment['losses']} | {_percent(segment['win_rate'])} | "
        f"{_number(segment['expectancy'])} | "
        f"{_number(segment['profit_factor'])} | "
        f"{_number(segment['average_r'])} | {_number(segment['net_pnl'])} |"
    )


def _rank_header() -> str:
    return (
        "| Dimension | Segment | Trades | Profit Factor | Expectancy |\n"
        "|---|---|---:|---:|---:|"
    )


def _rank_row(segment: dict[str, Any]) -> str:
    return (
        f"| {segment['dimension']} | {segment['segment']} | "
        f"{segment['trades']} | {_number(segment['profit_factor'])} | "
        f"{_number(segment['expectancy'])} |"
    )


def _number(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):.4f}"


def _percent(value: Any) -> str:
    return f"{float(value) * 100:.2f}%"
