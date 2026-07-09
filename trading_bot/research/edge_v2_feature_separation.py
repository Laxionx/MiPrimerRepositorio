from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from trading_bot.analysis.edge_v2 import EDGE_V2_FIELDS


CATEGORICAL_FEATURES = {"pressure_direction"}
MINIMUM_GROUP_SIZE = 2


def load_journal_records(path: str | Path) -> list[dict[str, Any]]:
    """Load existing JSONL, JSON-array, or CSV journal/export records."""
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    if source.suffix.lower() == ".csv":
        with source.open(newline="", encoding="utf-8") as stream:
            return [dict(record) for record in csv.DictReader(stream)]

    contents = source.read_text(encoding="utf-8").strip()
    if not contents:
        return []
    if source.suffix.lower() == ".json" and contents.startswith("["):
        parsed = json.loads(contents)
        if not isinstance(parsed, list):
            raise ValueError("JSON journal must contain an array of records")
        return [dict(record) for record in parsed]
    return [json.loads(line) for line in contents.splitlines() if line.strip()]


def analyze_feature_separation(
    records: list[dict[str, Any]],
    *,
    top_n: int = 10,
) -> dict[str, Any]:
    """Describe winner/loser separation without recommending strategy changes."""
    if top_n <= 0:
        raise ValueError("top_n must be greater than zero")

    features = _available_features(records)
    winners = _ranked_records(records, winner=True)[:top_n]
    losers = _ranked_records(records, winner=False)[:top_n]
    return {
        "schema_version": "aqtf_edge_v2_feature_separation.v1",
        "diagnostic_only": True,
        "total_records": len(records),
        "available_features": features,
        "top_n": top_n,
        "features": {
            feature: _feature_report(feature, records, winners, losers, top_n)
            for feature in features
        },
        "disclaimer": (
            "Diagnostic only: this report does not establish profitability and "
            "does not recommend strategy changes."
        ),
    }


def calculate_effect_size(
    winner_values: list[float],
    loser_values: list[float],
) -> float | None:
    """Return a transparent pooled-population standardized mean difference."""
    if len(winner_values) < MINIMUM_GROUP_SIZE or len(loser_values) < MINIMUM_GROUP_SIZE:
        return None
    pooled_std = math.sqrt(
        (pstdev(winner_values) ** 2 + pstdev(loser_values) ** 2) / 2
    )
    if pooled_std == 0:
        return None
    return round((mean(winner_values) - mean(loser_values)) / pooled_std, 6)


def write_feature_separation_report(
    report: dict[str, Any],
    output: str | Path,
) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def _available_features(records: list[dict[str, Any]]) -> list[str]:
    return [
        feature
        for feature in EDGE_V2_FIELDS
        if any(feature in record for record in records)
    ]


def _feature_report(
    feature: str,
    records: list[dict[str, Any]],
    top_winners: list[dict[str, Any]],
    worst_losers: list[dict[str, Any]],
    top_n: int,
) -> dict[str, Any]:
    if feature in CATEGORICAL_FEATURES:
        return _categorical_report(feature, records, top_winners, worst_losers, top_n)
    return _numeric_report(feature, records, top_winners, worst_losers, top_n)


def _numeric_report(
    feature: str,
    records: list[dict[str, Any]],
    top_winners: list[dict[str, Any]],
    worst_losers: list[dict[str, Any]],
    top_n: int,
) -> dict[str, Any]:
    winner_values = _numeric_values(records, feature, winner=True)
    loser_values = _numeric_values(records, feature, winner=False)
    all_values = _numeric_values(records, feature)
    comparison = _numeric_comparison(winner_values, loser_values)
    return {
        "feature_type": "numeric",
        "sample_count": len(all_values),
        **comparison,
        "separation": _separation_flag(comparison["simple_effect_size"], winner_values, loser_values),
        "top_vs_worst": {
            "top_n": top_n,
            **_numeric_comparison(
                _numeric_values(top_winners, feature),
                _numeric_values(worst_losers, feature),
            ),
        },
    }


def _categorical_report(
    feature: str,
    records: list[dict[str, Any]],
    top_winners: list[dict[str, Any]],
    worst_losers: list[dict[str, Any]],
    top_n: int,
) -> dict[str, Any]:
    winner_values = _categorical_values(records, feature, winner=True)
    loser_values = _categorical_values(records, feature, winner=False)
    all_values = _categorical_values(records, feature)
    empty_metrics = {
        "winner_mean": None,
        "loser_mean": None,
        "winner_median": None,
        "loser_median": None,
        "winner_std": None,
        "loser_std": None,
        "winner_p25": None,
        "winner_p75": None,
        "loser_p25": None,
        "loser_p75": None,
        "mean_difference": None,
        "median_difference": None,
        "simple_effect_size": None,
    }
    return {
        "feature_type": "categorical",
        "sample_count": len(all_values),
        "winner_count": len(winner_values),
        "loser_count": len(loser_values),
        **empty_metrics,
        "winner_distribution": _distribution(winner_values),
        "loser_distribution": _distribution(loser_values),
        "separation": "no_clear_separation",
        "top_vs_worst": {
            "top_n": top_n,
            "winner_distribution": _distribution(
                _categorical_values(top_winners, feature)
            ),
            "loser_distribution": _distribution(
                _categorical_values(worst_losers, feature)
            ),
            "simple_effect_size": None,
        },
    }


def _numeric_comparison(
    winner_values: list[float],
    loser_values: list[float],
) -> dict[str, Any]:
    winner_stats = _summary(winner_values)
    loser_stats = _summary(loser_values)
    winner_mean = winner_stats["mean"]
    loser_mean = loser_stats["mean"]
    winner_median = winner_stats["median"]
    loser_median = loser_stats["median"]
    return {
        "winner_count": len(winner_values),
        "loser_count": len(loser_values),
        "winner_mean": winner_mean,
        "loser_mean": loser_mean,
        "winner_median": winner_median,
        "loser_median": loser_median,
        "winner_std": winner_stats["std"],
        "loser_std": loser_stats["std"],
        "winner_p25": winner_stats["p25"],
        "winner_p75": winner_stats["p75"],
        "loser_p25": loser_stats["p25"],
        "loser_p75": loser_stats["p75"],
        "mean_difference": _difference(winner_mean, loser_mean),
        "median_difference": _difference(winner_median, loser_median),
        "simple_effect_size": calculate_effect_size(winner_values, loser_values),
    }


def _summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "median": None, "std": None, "p25": None, "p75": None}
    return {
        "mean": round(mean(values), 6),
        "median": round(median(values), 6),
        "std": round(pstdev(values), 6),
        "p25": _percentile(values, 0.25),
        "p75": _percentile(values, 0.75),
    }


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return round(
        ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower),
        6,
    )


def _numeric_values(
    records: list[dict[str, Any]],
    feature: str,
    *,
    winner: bool | None = None,
) -> list[float]:
    values = []
    for record in records:
        if not _matches_group(record, winner):
            continue
        value = _as_float(record.get(feature))
        if value is not None:
            values.append(value)
    return values


def _categorical_values(
    records: list[dict[str, Any]],
    feature: str,
    *,
    winner: bool | None = None,
) -> list[str]:
    values = []
    for record in records:
        if not _matches_group(record, winner):
            continue
        value = record.get(feature)
        if value is not None and str(value).strip():
            values.append(str(value))
    return values


def _ranked_records(records: list[dict[str, Any]], *, winner: bool) -> list[dict[str, Any]]:
    selected = [record for record in records if _matches_group(record, winner)]
    return sorted(selected, key=_pnl, reverse=winner)


def _is_winner(record: dict[str, Any]) -> bool:
    return _pnl(record) > 0


def _matches_group(record: dict[str, Any], winner: bool | None) -> bool:
    if winner is None:
        return True
    pnl = _pnl(record)
    return pnl > 0 if winner else pnl < 0


def _pnl(record: dict[str, Any]) -> float:
    return _as_float(record.get("pnl")) or 0.0


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _difference(first: float | None, second: float | None) -> float | None:
    return round(first - second, 6) if first is not None and second is not None else None


def _distribution(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _separation_flag(
    effect_size: float | None,
    winner_values: list[float],
    loser_values: list[float],
) -> str:
    if len(winner_values) < MINIMUM_GROUP_SIZE or len(loser_values) < MINIMUM_GROUP_SIZE:
        return "insufficient_data"
    if effect_size is None or abs(effect_size) < 0.2:
        return "no_clear_separation"
    if abs(effect_size) < 0.5:
        return "weak_separation"
    if abs(effect_size) < 0.8:
        return "moderate_separation"
    return "strong_separation"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a diagnostic-only AQTF Edge V2 feature separation report"
    )
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--top-n", type=int, default=10)
    args = parser.parse_args()
    report = analyze_feature_separation(load_journal_records(args.journal), top_n=args.top_n)
    output = write_feature_separation_report(report, args.out)
    print(output)


if __name__ == "__main__":
    main()
