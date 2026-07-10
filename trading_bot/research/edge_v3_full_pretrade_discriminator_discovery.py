"""Univariate, research-only Edge V3 pre-trade discriminator discovery."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from trading_bot.research.edge_v2_feature_separation import calculate_effect_size
from trading_bot.research.edge_v2_cohort_report import cohort_metrics


RATIO_FEATURE_MARKERS = ("_over_", "reward_to_risk")


def discover_pretrade_discriminators(matrix: dict[str, Any]) -> dict[str, Any]:
    records = list(matrix.get("records", []))
    predictors = [name for name in matrix.get("predictors", []) if name != "lower_quartile_closes"]
    groups = _segment_groups(records)
    features = {}
    for feature in predictors:
        global_rows = _rows_with_feature(records, feature)
        segments = {
            kind: {
                key: _feature_report(rows, feature, include_record_ids=False)
                for key, rows in values.items()
            }
            for kind, values in groups.items()
        }
        features[feature] = {
            "provenance": matrix.get("feature_provenance", {}).get(feature, {}),
            "global": _feature_report(global_rows, feature, include_record_ids=True),
            "segments": segments,
            "consistency": _sign_consistency(segments.get("symbol_timeframe", {})),
        }
    return {
        "schema_version": "aqtf_edge_v3_univariate_discovery.v1",
        "diagnostic_only": True,
        "lqc_excluded": True,
        "total_records": len(records),
        "features": features,
        "pnl_comparability": "PF and expectancy are descriptive only within homogeneous segments; cross-instrument values are not pooled as comparable performance.",
        "disclaimer": "Discovery is descriptive and creates no trading signal or strategy rule.",
    }


def _feature_report(rows: list[dict[str, Any]], feature: str, *, include_record_ids: bool) -> dict[str, Any]:
    values = [(row, _value(row, feature)) for row in rows]
    values = [(row, value) for row, value in values if value is not None]
    winner_values = [value for row, value in values if _pnl(row) > 0]
    loser_values = [value for row, value in values if _pnl(row) < 0]
    ordered = sorted(values, key=lambda item: (item[1], item[0]["record_id"]))
    definitions = cohort_definitions([value for _, value in ordered], feature)
    cohorts = assign_cohorts(ordered, feature, definitions, include_record_ids=include_record_ids)
    winner = _distribution(winner_values)
    loser = _distribution(loser_values)
    return {
        "count": len(values), "winners": len(winner_values), "losers": len(loser_values),
        "win_rate": len(winner_values) / len(values) if values else 0.0,
        "effect_size": calculate_effect_size(winner_values, loser_values),
        "mean_winner": winner["mean"], "mean_loser": loser["mean"],
        "median_winner": winner["median"], "median_loser": loser["median"],
        "mean_difference": _difference(winner["mean"], loser["mean"]),
        "median_difference": _difference(winner["median"], loser["median"]),
        "quantiles": _distribution([value for _, value in ordered]),
        "dispersion": {"winner_std": winner["std"], "loser_std": loser["std"]},
        "outlier_sensitivity": _outlier_sensitivity(winner_values, loser_values),
        "cohort_definitions": definitions,
        "cohorts": cohorts,
    }


def cohort_definitions(values: list[float], feature: str) -> dict[str, dict[str, float | str]]:
    if any(marker in feature for marker in RATIO_FEATURE_MARKERS):
        return {
            "lte_0_5": {"kind": "fixed", "lower": None, "upper": 0.5},
            "gt_0_5_to_lte_1": {"kind": "fixed", "lower": 0.5, "upper": 1.0},
            "gt_1_to_lte_2": {"kind": "fixed", "lower": 1.0, "upper": 2.0},
            "gt_2": {"kind": "fixed", "lower": 2.0, "upper": None},
        }
    ordered = sorted(values)
    return {
        "bottom_25": {"kind": "rank", "start": 0, "end": len(ordered) // 4},
        "middle_50": {"kind": "rank", "start": len(ordered) // 4, "end": len(ordered) - len(ordered) // 4},
        "top_25": {"kind": "rank", "start": len(ordered) - len(ordered) // 4, "end": len(ordered)},
    }


def assign_cohorts(
    ordered: list[tuple[dict[str, Any], float]], feature: str, definitions: dict[str, dict[str, Any]], *, include_record_ids: bool
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, definition in definitions.items():
        if definition["kind"] == "rank":
            selected = ordered[int(definition["start"]):int(definition["end"])]
        else:
            selected = [item for item in ordered if _in_fixed_bin(item[1], name, definition)]
        rows = [row for row, _ in selected]
        metrics = cohort_metrics([{"pnl": _pnl(row)} for row in rows])
        result[name] = {
            "trade_count": metrics["trade_count"], "winner_count": metrics["winner_count"],
            "loser_count": metrics["loser_count"], "win_rate": metrics["win_rate"],
            "profit_factor": metrics["profit_factor"], "expectancy": metrics["expectancy"],
            "payoff_ratio": metrics["payoff_ratio"],
            "sample_size_warning": metrics["sample_size_warning"],
            **({"record_ids": [row["record_id"] for row in rows]} if include_record_ids else {}),
        }
    return result


def _in_fixed_bin(value: float, name: str, definition: dict[str, Any]) -> bool:
    lower, upper = definition.get("lower"), definition.get("upper")
    return (lower is None or value > float(lower)) and (upper is None or value <= float(upper))


def _segment_groups(records: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {
        "symbol": defaultdict(list), "timeframe": defaultdict(list), "direction": defaultdict(list), "symbol_timeframe": defaultdict(list),
    }
    for row in records:
        segment = row.get("segment", {})
        symbol, timeframe, direction = segment.get("symbol"), segment.get("timeframe"), segment.get("direction")
        if symbol is not None:
            grouped["symbol"][str(symbol)].append(row)
        if timeframe is not None:
            grouped["timeframe"][str(timeframe)].append(row)
        if direction is not None:
            grouped["direction"][str(direction)].append(row)
        if symbol is not None and timeframe is not None:
            grouped["symbol_timeframe"][f"{symbol}/{timeframe}"].append(row)
    return {kind: dict(values) for kind, values in grouped.items()}


def _sign_consistency(segments: dict[str, dict[str, Any]]) -> dict[str, Any]:
    signs = []
    for report in segments.values():
        effect = report.get("effect_size")
        if effect is not None and effect != 0:
            signs.append(effect > 0)
    return {
        "positive": sum(signs), "negative": len(signs) - sum(signs),
        "independent_segments": len(signs), "consistent": bool(signs) and (all(signs) or not any(signs)),
    }


def _rows_with_feature(records: list[dict[str, Any]], feature: str) -> list[dict[str, Any]]:
    return [row for row in records if _value(row, feature) is not None]


def _value(row: dict[str, Any], feature: str) -> float | None:
    try:
        value = float(row.get("predictors", {}).get(feature))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _pnl(row: dict[str, Any]) -> float:
    try:
        return float(row.get("labels", {}).get("pnl", 0))
    except (TypeError, ValueError):
        return 0.0


def _distribution(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {key: None for key in ("mean", "median", "std", "p25", "p75")}
    ordered = sorted(values)
    return {
        "mean": mean(values), "median": median(values), "std": pstdev(values),
        "p25": _percentile(ordered, 0.25), "p75": _percentile(ordered, 0.75),
    }


def _outlier_sensitivity(winners: list[float], losers: list[float]) -> dict[str, Any]:
    if len(winners) < 3 or len(losers) < 3:
        return {"available": False, "trimmed_mean_difference": None, "mean_difference": None, "material_conflict": False}
    raw = mean(winners) - mean(losers)
    trimmed = mean(_trim(winners)) - mean(_trim(losers))
    magnitude_shift = raw != 0 and abs(trimmed / raw) < 0.2
    return {"available": True, "mean_difference": raw, "trimmed_mean_difference": trimmed, "material_conflict": raw * trimmed < 0 or magnitude_shift}


def _trim(values: list[float]) -> list[float]:
    ordered = sorted(values)
    trim = max(1, len(ordered) // 10)
    return ordered[trim:-trim] or ordered


def _percentile(values: list[float], fraction: float) -> float:
    point = (len(values) - 1) * fraction
    lower, upper = math.floor(point), math.ceil(point)
    return values[lower] if lower == upper else values[lower] + (values[upper] - values[lower]) * (point - lower)


def _difference(left: float | None, right: float | None) -> float | None:
    return left - right if left is not None and right is not None else None


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(value: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run research-only Edge V3 univariate discovery")
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    _write_json(discover_pretrade_discriminators(_read_json(args.matrix)), args.out)
    print(args.out)


if __name__ == "__main__":
    main()
