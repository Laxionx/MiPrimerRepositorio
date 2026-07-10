"""Diagnostic-only failure analysis for predefined Edge V2 trade conditions."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from trading_bot.research.edge_v2_cohort_report import (
    cohort_metrics,
    select_fixed_cohort_records,
)
from trading_bot.research.edge_v2_feature_separation import (
    calculate_effect_size,
    load_journal_records,
)


DEFAULT_CONDITION = "lower_quartile_closes_eq_0"
PREDEFINED_CONDITIONS = (
    DEFAULT_CONDITION,
    "lower_quartile_closes_bottom_25",
)
BREAKDOWN_FIELDS = (
    "symbol",
    "timeframe",
    "direction",
    "session",
    "hour",
    "day_of_week",
    "regime",
    "volatility_bucket",
    "spread_bucket",
)
TIMESTAMP_FIELDS = (
    "timestamp_open",
    "entry_time",
    "open_time",
    "timestamp",
    "time",
)
CASEBOOK_LIMIT = 10
CASEBOOK_EDGE_V2_FIELDS = (
    "lower_quartile_closes",
    "price_position_in_range",
    "pressure_score",
    "compression_score",
    "prior_range_points",
    "sweep_depth",
    "reclaim_speed",
)
OUTCOME_DERIVED_FEATURES = {"r_multiple", "exit_price", "bars_held"}


def analyze_conditional_failure_records(
    records: list[dict[str, Any]], *, condition: str = DEFAULT_CONDITION
) -> dict[str, Any]:
    """Describe a fixed condition without optimizing or changing a strategy."""
    selected = _select_condition_records(records, condition)
    feature_separation = _numeric_feature_separation(selected)
    conditional_metrics = cohort_metrics(selected)
    temporal = _temporal_splits(selected)
    breakdowns, unavailable_breakdowns = _breakdowns(selected)
    casebook = _casebook(selected)
    return {
        "schema_version": "aqtf_edge_v2_conditional_failure_analysis.v1",
        "diagnostic_only": True,
        "condition_name": condition,
        "condition_description": _condition_description(condition),
        "condition": condition,
        "condition_definition": _condition_definition(condition),
        "inputs_analyzed": 1,
        "total_trades_before_filter": len(records),
        "total_trades_after_filter": len(selected),
        "input_trade_count": len(records),
        "conditional_metrics": conditional_metrics,
        "subset_metrics": conditional_metrics,
        "conditional_feature_separation": feature_separation,
        "numeric_feature_separation": feature_separation,
        "strongest_candidate_features": _strongest_features(feature_separation),
        "temporal_failure_analysis": temporal,
        "temporal_splits": temporal,
        "segment_breakdowns": {
            "available": breakdowns,
            "unavailable_fields": unavailable_breakdowns,
        },
        "breakdowns": breakdowns,
        "casebook": casebook,
        "casebook_path": None,
        "warnings": _warnings(conditional_metrics, temporal, unavailable_breakdowns),
        "conclusion_flags": _conclusion_flags(
            conditional_metrics, feature_separation, temporal
        ),
        "disclaimer": (
            "Diagnostic only; this fixed-condition report does not establish "
            "profitability, an edge, or a strategy rule."
        ),
    }


def analyze_conditional_failure_journals(
    journal_paths: list[str | Path], *, condition: str = DEFAULT_CONDITION
) -> dict[str, Any]:
    """Analyze several existing journals and retain invalid-source evidence."""
    runs = []
    valid_records: list[dict[str, Any]] = []
    for source in journal_paths:
        path = Path(source)
        try:
            records = load_journal_records(path)
        except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            runs.append(
                {
                    "journal_path": str(path),
                    "status": "invalid_or_missing",
                    "reason": str(exc),
                }
            )
            continue
        report = analyze_conditional_failure_records(records, condition=condition)
        runs.append(
            {
                "journal_path": str(path),
                "status": "success",
                "input_trade_count": len(records),
                "subset_trade_count": report["subset_metrics"]["trade_count"],
                "report": report,
            }
        )
        valid_records.extend({**record, "source_journal": str(path)} for record in records)
    return {
        "schema_version": "aqtf_edge_v2_conditional_failure_batch.v1",
        "diagnostic_only": True,
        "condition": condition,
        "inputs_analyzed": runs,
        "source_count": len(journal_paths),
        "valid_source_count": sum(run["status"] == "success" for run in runs),
        "invalid_source_count": sum(run["status"] != "success" for run in runs),
        "runs": runs,
        "aggregate": analyze_conditional_failure_records(
            valid_records, condition=condition
        ),
        "disclaimer": (
            "Diagnostic only; multiple journals are summarized without "
            "optimization or strategy recommendations."
        ),
    }


def discover_batch_journals(batch_dirs: list[str | Path]) -> list[Path]:
    """Find standard journal files below already-created batch directories."""
    paths: set[Path] = set()
    for item in batch_dirs:
        root = Path(item)
        if root.is_file() and root.name == "trades.jsonl":
            paths.add(root)
        elif root.exists():
            paths.update(root.rglob("trades.jsonl"))
    return sorted(paths, key=lambda path: str(path).lower())


def write_conditional_failure_report(report: dict[str, Any], output: str | Path) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    casebook_path = output_path.with_name(f"{output_path.stem}_casebook.json")
    aggregate = report.get("aggregate", report)
    casebook_path.write_text(
        json.dumps(aggregate.get("casebook", {}), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    report["casebook_path"] = str(casebook_path)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def _select_condition_records(
    records: list[dict[str, Any]], condition: str
) -> list[dict[str, Any]]:
    if condition == DEFAULT_CONDITION:
        selected = [
            record
            for record in records
            if _number(record.get("lower_quartile_closes")) == 0
        ]
    elif condition == "lower_quartile_closes_bottom_25":
        selected = select_fixed_cohort_records(
            records, "lower_quartile_closes", "bottom_25"
        )
    else:
        raise ValueError(f"Unknown predefined condition: {condition}")
    return [record for record in selected if _number(record.get("pnl")) is not None]


def _condition_definition(condition: str) -> dict[str, Any]:
    if condition == DEFAULT_CONDITION:
        return {"feature": "lower_quartile_closes", "operator": "eq", "value": 0}
    if condition == "lower_quartile_closes_bottom_25":
        return {
            "feature": "lower_quartile_closes",
            "operator": "stable_rank_bucket",
            "value": "bottom_25",
        }
    raise ValueError(f"Unknown predefined condition: {condition}")


def _condition_description(condition: str) -> str:
    if condition == DEFAULT_CONDITION:
        return "Preselected raw slice lower_quartile_closes == 0."
    if condition == "lower_quartile_closes_bottom_25":
        return "Preselected deterministic lower_quartile_closes bottom_25 partition."
    raise ValueError(f"Unknown predefined condition: {condition}")


def _temporal_splits(records: list[dict[str, Any]]) -> dict[str, Any]:
    dated = []
    for index, record in enumerate(records):
        parsed = _timestamp(record)
        if parsed is not None:
            dated.append((parsed, index, record))
    dated.sort(key=lambda item: (item[0], item[1]))
    midpoint = len(dated) // 2
    earlier = [item[2] for item in dated[:midpoint]]
    later = [item[2] for item in dated[midpoint:]]
    splits = {
        "eligible_trade_count": len(dated),
        "excluded_missing_or_invalid_timestamp_count": len(records) - len(dated),
        "first_half": _temporal_half(earlier),
        "second_half": _temporal_half(later),
    }
    return splits


def _temporal_half(records: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = cohort_metrics(records)
    separation = _numeric_feature_separation(records)
    return {
        **metrics,
        "strongest_separating_features": _strongest_features(separation),
        "sample_size_warning": metrics["sample_size_warning"],
    }


def _breakdowns(
    records: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, dict[str, Any]]], list[str]]:
    breakdowns = {}
    unavailable = []
    for field in BREAKDOWN_FIELDS:
        groups: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            value = record.get(field)
            if value is not None and str(value).strip():
                groups.setdefault(str(value), []).append(record)
        if groups:
            breakdowns[field] = {
                value: cohort_metrics(rows) for value, rows in sorted(groups.items())
            }
        else:
            unavailable.append(field)
    return breakdowns, unavailable


def _casebook(records: list[dict[str, Any]]) -> dict[str, Any]:
    if len(records) <= CASEBOOK_LIMIT * 2:
        return {"selection": "all_matching_trades", "trades": [_compact_case(record) for record in records]}
    winners = sorted(
        (record for record in records if _number(record.get("pnl")) > 0),
        key=lambda record: _number(record.get("pnl")) or 0.0,
        reverse=True,
    )[:CASEBOOK_LIMIT]
    losers = sorted(
        (record for record in records if _number(record.get("pnl")) < 0),
        key=lambda record: _number(record.get("pnl")) or 0.0,
    )[:CASEBOOK_LIMIT]
    return {
        "selection": "top_winners_and_worst_losers",
        "trades": [_compact_case(record) for record in [*winners, *losers]],
    }


def _compact_case(record: dict[str, Any]) -> dict[str, Any]:
    timestamp = next(
        (record[field] for field in TIMESTAMP_FIELDS if record.get(field) is not None), None
    )
    case = {
        "trade_id": record.get("trade_id", record.get("id")),
        "entry_time": timestamp,
        "tradingview_timestamp": timestamp,
        "exit_time": record.get("timestamp_close", record.get("exit_time")),
        "pnl": _number(record.get("pnl")),
        "symbol": record.get("symbol"),
        "timeframe": record.get("timeframe"),
        "direction": record.get("direction", record.get("side")),
        "outcome": record.get("outcome"),
        "entry_price": record.get("entry", record.get("entry_price")),
        "exit_price": record.get("exit_price"),
        "stop_loss": record.get("stop_loss"),
        "take_profit": record.get("take_profit"),
        "pressure_direction": record.get("pressure_direction"),
        "source_journal": record.get("source_journal"),
    }
    case.update(
        {
            field: _number(record.get(field))
            for field in CASEBOOK_EDGE_V2_FIELDS
            if _number(record.get(field)) is not None
        }
    )
    return {key: value for key, value in case.items() if value is not None}


def _numeric_feature_separation(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    features = sorted({key for record in records for key in record} - {"pnl"})
    winners = [record for record in records if (_number(record.get("pnl")) or 0) > 0]
    losers = [record for record in records if (_number(record.get("pnl")) or 0) < 0]
    reports = {}
    for feature in features:
        winner_values = _feature_values(winners, feature)
        loser_values = _feature_values(losers, feature)
        all_values = _feature_values(records, feature)
        if not all_values:
            continue
        reports[feature] = {
            **_separation_metrics(winner_values, loser_values, all_values),
            "feature_role": (
                "outcome_derived" if feature in OUTCOME_DERIVED_FEATURES else "candidate"
            ),
        }
    return reports


def _feature_values(records: list[dict[str, Any]], feature: str) -> list[float]:
    return [value for record in records if (value := _number(record.get(feature))) is not None]


def _separation_metrics(
    winner_values: list[float], loser_values: list[float], all_values: list[float]
) -> dict[str, Any]:
    winner = _summary(winner_values)
    loser = _summary(loser_values)
    effect = calculate_effect_size(winner_values, loser_values)
    return {
        "sample_count": len(all_values),
        "winner_count": len(winner_values),
        "loser_count": len(loser_values),
        "winner_mean": winner["mean"],
        "loser_mean": loser["mean"],
        "winner_median": winner["median"],
        "loser_median": loser["median"],
        "winner_std": winner["std"],
        "loser_std": loser["std"],
        "winner_p25": winner["p25"],
        "winner_p75": winner["p75"],
        "loser_p25": loser["p25"],
        "loser_p75": loser["p75"],
        "mean_difference": _difference(winner["mean"], loser["mean"]),
        "median_difference": _difference(winner["median"], loser["median"]),
        "simple_effect_size": effect,
        "separation_flag": _separation_flag(effect, winner_values, loser_values),
    }


def _summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "median": None, "std": None, "p25": None, "p75": None}
    return {
        "mean": mean(values),
        "median": median(values),
        "std": pstdev(values),
        "p25": _percentile(values, 0.25),
        "p75": _percentile(values, 0.75),
    }


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _difference(first: float | None, second: float | None) -> float | None:
    return first - second if first is not None and second is not None else None


def _separation_flag(
    effect: float | None, winner_values: list[float], loser_values: list[float]
) -> str:
    if len(winner_values) < 2 or len(loser_values) < 2:
        return "insufficient_data"
    if effect is None or abs(effect) < 0.2:
        return "no_clear_separation"
    if abs(effect) < 0.5:
        return "weak_separation"
    if abs(effect) < 0.8:
        return "moderate_separation"
    return "strong_separation"


def _strongest_features(separation: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = [
        (feature, values)
        for feature, values in separation.items()
        if values["simple_effect_size"] is not None
        and values["feature_role"] == "candidate"
    ]
    return [
        {
            "feature": feature,
            "simple_effect_size": values["simple_effect_size"],
            "separation_flag": values["separation_flag"],
        }
        for feature, values in sorted(
            ranked, key=lambda item: abs(item[1]["simple_effect_size"]), reverse=True
        )[:3]
    ]


def _warnings(
    metrics: dict[str, Any], temporal: dict[str, Any], unavailable_breakdowns: list[str]
) -> list[str]:
    warnings = []
    if metrics["sample_size_warning"]:
        warnings.append("conditional_subset_insufficient_sample")
    if temporal["first_half"]["sample_size_warning"] or temporal["second_half"]["sample_size_warning"]:
        warnings.append("temporal_split_insufficient_sample")
    if unavailable_breakdowns:
        warnings.append("some_segment_fields_unavailable")
    return warnings


def _conclusion_flags(
    metrics: dict[str, Any],
    separation: dict[str, dict[str, Any]],
    temporal: dict[str, Any],
) -> list[str]:
    flags = ["no_actionable_rule"]
    if metrics["sample_size_warning"]:
        flags.append("insufficient_data")
    first = temporal["first_half"]["expectancy"]
    second = temporal["second_half"]["expectancy"]
    if first * second < 0:
        flags.extend(["mixed", "failure_cluster_detected"])
    if any(
        values["simple_effect_size"] is not None
        and abs(values["simple_effect_size"]) >= 0.5
        and values["feature_role"] == "candidate"
        for values in separation.values()
    ):
        flags.append("possible_missing_discriminator")
    return flags


def _timestamp(record: dict[str, Any]) -> datetime | None:
    value = next((record[field] for field in TIMESTAMP_FIELDS if record.get(field)), None)
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a diagnostic-only Edge V2 conditional failure report"
    )
    parser.add_argument("--journal", action="append", type=Path, default=[])
    parser.add_argument("--batch-dir", action="append", type=Path, default=[])
    parser.add_argument("--condition", choices=PREDEFINED_CONDITIONS, default=DEFAULT_CONDITION)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    journals = [*args.journal, *discover_batch_journals(args.batch_dir)]
    if not journals:
        parser.error("provide at least one --journal or --batch-dir")
    print(
        write_conditional_failure_report(
            analyze_conditional_failure_journals(journals, condition=args.condition),
            args.out,
        )
    )


if __name__ == "__main__":
    main()
