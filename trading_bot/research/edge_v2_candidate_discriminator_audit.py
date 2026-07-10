"""Diagnostic-only audit of fixed Edge V2 discriminator candidates."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from trading_bot.research.edge_v2_cohort_report import cohort_metrics
from trading_bot.research.edge_v2_feature_separation import (
    calculate_effect_size,
    load_journal_records,
)


DEFAULT_CONDITION = "lower_quartile_closes_eq_0"
PREDEFINED_CONDITIONS = (DEFAULT_CONDITION,)
CANDIDATES = ("risk_points", "candle_range", "reward_points")
OUTCOME_FIELDS = {"pnl", "r_multiple"}
TIMESTAMP_FIELDS = ("timestamp_open", "entry_time", "open_time", "timestamp", "time")
ALLOWED_FLAGS = {
    "insufficient_data",
    "mixed",
    "possible_valid_discriminator",
    "possible_leakage_risk",
    "normalization_needed",
    "failed_calibration_test",
    "no_actionable_rule",
}
NORMALIZATION_SPECS = {
    "risk_points_over_candle_range": ("risk_points", "candle_range"),
    "reward_points_over_candle_range": ("reward_points", "candle_range"),
    "reward_to_risk_planned": ("reward_points", "risk_points"),
    "candle_range_over_prior_range_points": ("candle_range", "prior_range_points"),
    "risk_points_over_prior_range_points": ("risk_points", "prior_range_points"),
    "reward_points_over_prior_range_points": ("reward_points", "prior_range_points"),
    "candle_range_over_atr": ("candle_range", "atr"),
    "risk_points_over_atr": ("risk_points", "atr"),
    "reward_points_over_atr": ("reward_points", "atr"),
}


def field_leakage_metadata(field: str) -> dict[str, str]:
    """Classify timing conservatively; journals do not prove provenance."""
    if field in OUTCOME_FIELDS:
        return {
            "availability_timing": "post_trade",
            "leakage_risk": "high",
            "reason": "Outcome-derived field is only known after trade completion.",
        }
    reasons = {
        "risk_points": "Stop-distance provenance is not recorded at field level.",
        "reward_points": "Target-distance provenance is not recorded at field level.",
        "candle_range": "Journal data does not prove the candle was closed at signal time.",
    }
    return {
        "availability_timing": "unknown",
        "leakage_risk": "unknown",
        "reason": reasons.get(field, "Journal records do not provide field-level timing provenance."),
    }


def analyze_candidate_discriminator_records(
    records: list[dict[str, Any]], *, condition: str = DEFAULT_CONDITION
) -> dict[str, Any]:
    """Audit fixed candidates inside a preselected condition without tuning."""
    selected = _select_condition_records(records, condition)
    first_half, second_half, timestamp_excluded = _chronological_halves(selected)
    raw = {candidate: _raw_discriminator(candidate, selected) for candidate in CANDIDATES}
    normalized, unavailable = _normalized_discriminators(selected)
    calibration = _calibration_diagnostic(first_half, second_half)
    segments = _segment_checks(selected, first_half, second_half)
    subset_metrics = cohort_metrics(selected)
    flags = _conclusion_flags(subset_metrics, raw, calibration, unavailable, timestamp_excluded)
    return {
        "schema_version": "aqtf_edge_v2_candidate_discriminator_audit.v1",
        "diagnostic_only": True,
        "condition": condition,
        "condition_definition": {
            "feature": "lower_quartile_closes",
            "operator": "eq",
            "value": 0,
        },
        "candidate_list": list(CANDIDATES),
        "total_trade_count": len(records),
        "subset_trade_count": len(selected),
        "subset_metrics": subset_metrics,
        "raw_discriminators": raw,
        "normalized_discriminators": normalized,
        "normalized_features_unavailable": unavailable,
        "diagnostic_groups_optimized": False,
        "segment_checks": segments,
        "timestamp_excluded_from_halves": timestamp_excluded,
        "calibration_diagnostic": calibration,
        "outcome_field_metadata": {
            field: field_leakage_metadata(field)
            for field in sorted(OUTCOME_FIELDS)
            if any(field in record for record in records)
        },
        "conclusion_flags": flags,
        "disclaimer": (
            "Diagnostic only. Candidate timing is unknown unless source provenance "
            "verifies it; no group or calibration result is a strategy rule."
        ),
    }


def analyze_candidate_discriminator_journals(
    journal_paths: list[str | Path], *, condition: str = DEFAULT_CONDITION
) -> dict[str, Any]:
    _validate_condition(condition)
    runs = []
    valid_records: list[dict[str, Any]] = []
    for source in journal_paths:
        path = Path(source)
        try:
            rows = load_journal_records(path)
        except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            runs.append({"journal_path": str(path), "status": "invalid_or_missing", "reason": str(exc)})
            continue
        report = analyze_candidate_discriminator_records(rows, condition=condition)
        runs.append(
            {
                "journal_path": str(path),
                "status": "success",
                "input_trade_count": len(rows),
                "subset_trade_count": report["subset_trade_count"],
                "report": report,
            }
        )
        valid_records.extend(rows)
    return {
        "schema_version": "aqtf_edge_v2_candidate_discriminator_audit_batch.v1",
        "diagnostic_only": True,
        "condition": condition,
        "source_count": len(journal_paths),
        "valid_source_count": sum(run["status"] == "success" for run in runs),
        "invalid_source_count": sum(run["status"] != "success" for run in runs),
        "runs": runs,
        "aggregate": analyze_candidate_discriminator_records(valid_records, condition=condition),
    }


def discover_batch_journals(batch_dirs: list[str | Path]) -> list[Path]:
    paths: set[Path] = set()
    for item in batch_dirs:
        root = Path(item)
        if root.is_file() and root.name == "trades.jsonl":
            paths.add(root)
        elif root.exists():
            paths.update(root.rglob("trades.jsonl"))
    return sorted(paths, key=lambda path: str(path).lower())


def write_candidate_discriminator_report(report: dict[str, Any], output: str | Path) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def _select_condition_records(records: list[dict[str, Any]], condition: str) -> list[dict[str, Any]]:
    _validate_condition(condition)
    return [
        record
        for record in records
        if _number(record.get("lower_quartile_closes")) == 0
        and _number(record.get("pnl")) is not None
    ]


def _validate_condition(condition: str) -> None:
    if condition not in PREDEFINED_CONDITIONS:
        raise ValueError(f"Unknown predefined condition: {condition}")


def _raw_discriminator(candidate: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "available": bool(_feature_values(records, candidate)),
        "leakage_metadata": field_leakage_metadata(candidate),
        "winner_loser_separation": _separation(records, candidate),
        "diagnostic_groups": _rank_groups(records, candidate),
    }


def _normalized_discriminators(
    records: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    reports = {}
    unavailable = []
    for name, (numerator, denominator) in NORMALIZATION_SPECS.items():
        augmented = []
        for record in records:
            numerator_value = _number(record.get(numerator))
            denominator_value = _number(record.get(denominator))
            if numerator_value is None or denominator_value in {None, 0}:
                continue
            augmented.append({**record, name: numerator_value / denominator_value})
        if not augmented:
            reports[name] = {"available": False, "reason": f"requires {numerator} and nonzero {denominator}"}
            unavailable.append(name)
            continue
        reports[name] = {
            "available": True,
            "report_only": True,
            "winner_loser_separation": _separation(augmented, name),
            "diagnostic_groups": _normalized_groups(augmented, name),
        }
    return reports, unavailable


def _segment_checks(
    records: list[dict[str, Any]], first_half: list[dict[str, Any]], second_half: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    definitions = {
        "all": records,
        "LONG": [record for record in records if _direction(record) == "LONG"],
        "SHORT": [record for record in records if _direction(record) == "SHORT"],
        "M5": [record for record in records if _timeframe(record) == "M5"],
        "M15": [record for record in records if _timeframe(record) == "M15"],
        "first_half": first_half,
        "second_half": second_half,
    }
    return {
        name: {
            "trade_count": len(rows),
            "metrics": cohort_metrics(rows),
            "candidate_separation": (
                {candidate: _separation(rows, candidate) for candidate in CANDIDATES}
                if len(rows) >= 2
                else None
            ),
        }
        for name, rows in definitions.items()
    }


def _chronological_halves(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    dated = [
        (timestamp, index, record)
        for index, record in enumerate(records)
        if (timestamp := _timestamp(record)) is not None
    ]
    dated.sort(key=lambda item: (item[0], item[1]))
    midpoint = len(dated) // 2
    return (
        [item[2] for item in dated[:midpoint]],
        [item[2] for item in dated[midpoint:]],
        len(records) - len(dated),
    )


def _calibration_diagnostic(
    calibration_rows: list[dict[str, Any]], test_rows: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    reports = {}
    for candidate in CANDIDATES:
        winners = _outcome_values(calibration_rows, candidate, winner=True)
        losers = _outcome_values(calibration_rows, candidate, winner=False)
        values = _feature_values(calibration_rows, candidate)
        winner_median = _median(winners)
        loser_median = _median(losers)
        threshold = _median(values)
        direction = _calibration_direction(winner_median, loser_median)
        selected = _apply_calibration(test_rows, candidate, direction, threshold)
        metrics = cohort_metrics(selected)
        reports[candidate] = {
            "calibration_trade_count": len(calibration_rows),
            "test_trade_count": len(test_rows),
            "discriminator_name": candidate,
            "calibration_winner_median": winner_median,
            "calibration_loser_median": loser_median,
            "selected_direction": direction,
            "threshold_used": threshold,
            "test_selected_trade_count": len(selected),
            "test_winner_count": metrics["winner_count"],
            "test_loser_count": metrics["loser_count"],
            "test_profit_factor": metrics["profit_factor"],
            "test_expectancy": metrics["expectancy"],
            "sample_size_warning": (
                direction is None
                or threshold is None
                or metrics["sample_size_warning"]
            ),
            "interpretation_flag": metrics["interpretation_flag"],
        }
    return reports


def _calibration_direction(winner_median: float | None, loser_median: float | None) -> str | None:
    if winner_median is None or loser_median is None or winner_median == loser_median:
        return None
    return "higher" if winner_median > loser_median else "lower"


def _apply_calibration(
    records: list[dict[str, Any]], candidate: str, direction: str | None, threshold: float | None
) -> list[dict[str, Any]]:
    if direction is None or threshold is None:
        return []
    return [
        record
        for record in records
        if (value := _number(record.get(candidate))) is not None
        and (value >= threshold if direction == "higher" else value <= threshold)
    ]


def _separation(records: list[dict[str, Any]], feature: str) -> dict[str, Any]:
    winners = _outcome_values(records, feature, winner=True)
    losers = _outcome_values(records, feature, winner=False)
    values = _feature_values(records, feature)
    winner = _summary(winners)
    loser = _summary(losers)
    effect = calculate_effect_size(winners, losers)
    return {
        "sample_count": len(values),
        "winner_count": len(winners),
        "loser_count": len(losers),
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
        "separation_flag": _separation_flag(effect, winners, losers),
    }


def _rank_groups(records: list[dict[str, Any]], feature: str) -> dict[str, dict[str, Any]]:
    ordered = sorted(
        [
            (value, index, record)
            for index, record in enumerate(records)
            if (value := _number(record.get(feature))) is not None
        ],
        key=lambda item: (item[0], item[1]),
    )
    quarter = len(ordered) // 4
    middle_end = len(ordered) - quarter
    groups = {
        "bottom_25": [item[2] for item in ordered[:quarter]],
        "middle_50": [item[2] for item in ordered[quarter:middle_end]],
        "top_25": [item[2] for item in ordered[middle_end:]],
    }
    return {name: cohort_metrics(rows) for name, rows in groups.items()}


def _normalized_groups(records: list[dict[str, Any]], feature: str) -> dict[str, dict[str, Any]]:
    if feature == "reward_to_risk_planned":
        definitions = {
            "lt_1": lambda value: value < 1,
            "1_to_lt_1_5": lambda value: 1 <= value < 1.5,
            "1_5_to_lt_2": lambda value: 1.5 <= value < 2,
            "gte_2": lambda value: value >= 2,
        }
    else:
        definitions = {
            "lte_0_5": lambda value: value <= 0.5,
            "gt_0_5_to_lte_1": lambda value: 0.5 < value <= 1,
            "gt_1_to_lte_2": lambda value: 1 < value <= 2,
            "gt_2": lambda value: value > 2,
        }
    return {
        name: cohort_metrics(
            [record for record in records if (value := _number(record.get(feature))) is not None and predicate(value)]
        )
        for name, predicate in definitions.items()
    }


def _conclusion_flags(
    metrics: dict[str, Any],
    raw: dict[str, dict[str, Any]],
    calibration: dict[str, dict[str, Any]],
    unavailable: list[str],
    timestamp_excluded: int,
) -> list[str]:
    flags = ["no_actionable_rule", "possible_leakage_risk"]
    if metrics["sample_size_warning"]:
        flags.append("insufficient_data")
    if unavailable:
        flags.append("normalization_needed")
    if timestamp_excluded:
        flags.append("insufficient_data")
    if any(
        report["test_selected_trade_count"]
        and (report["test_expectancy"] or 0) <= 0
        for report in calibration.values()
    ):
        flags.append("failed_calibration_test")
    if any(
        report["leakage_metadata"]["leakage_risk"] in {"low", "medium"}
        and (report["winner_loser_separation"]["simple_effect_size"] or 0) >= 0.5
        for report in raw.values()
    ):
        flags.append("possible_valid_discriminator")
    return sorted(set(flags))


def _feature_values(records: list[dict[str, Any]], feature: str) -> list[float]:
    return [value for record in records if (value := _number(record.get(feature))) is not None]


def _outcome_values(records: list[dict[str, Any]], feature: str, *, winner: bool) -> list[float]:
    return [
        value
        for record in records
        if (pnl := _number(record.get("pnl"))) is not None
        and (pnl > 0 if winner else pnl < 0)
        and (value := _number(record.get(feature))) is not None
    ]


def _timestamp(record: dict[str, Any]) -> datetime | None:
    value = next((record[field] for field in TIMESTAMP_FIELDS if record.get(field)), None)
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _direction(record: dict[str, Any]) -> str:
    return str(record.get("direction", record.get("side", ""))).upper()


def _timeframe(record: dict[str, Any]) -> str:
    return str(record.get("timeframe", "")).upper()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


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


def _median(values: list[float]) -> float | None:
    return median(values) if values else None


def _separation_flag(effect: float | None, winners: list[float], losers: list[float]) -> str:
    if len(winners) < 2 or len(losers) < 2:
        return "insufficient_data"
    if effect is None or abs(effect) < 0.2:
        return "no_clear_separation"
    if abs(effect) < 0.5:
        return "weak_separation"
    if abs(effect) < 0.8:
        return "moderate_separation"
    return "strong_separation"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a diagnostic-only Edge V2 candidate discriminator audit"
    )
    parser.add_argument("--journal", action="append", type=Path, default=[])
    parser.add_argument("--batch-dir", action="append", type=Path, default=[])
    parser.add_argument("--condition", choices=PREDEFINED_CONDITIONS, default=DEFAULT_CONDITION)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    journals = [*args.journal, *discover_batch_journals(args.batch_dir)]
    if not journals:
        parser.error("provide at least one --journal or --batch-dir")
    print(write_candidate_discriminator_report(analyze_candidate_discriminator_journals(journals, condition=args.condition), args.out))


if __name__ == "__main__":
    main()
