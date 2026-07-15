"""Diagnostic-only replication of provenance-verified Edge V2 candidates."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any

from trading_bot.research.edge_v2_cohort_report import cohort_metrics
from trading_bot.research.edge_v2_feature_separation import calculate_effect_size, load_journal_records
from trading_bot.research.edge_v2_feature_timing_provenance import (
    combine_source_provenance,
    get_field_provenance,
    load_provenance_file,
)


CONDITION_NAME = "lower_quartile_closes_eq_0"
FIXED_SLICE_NAMES = (
    "lower_quartile_closes_eq_0",
    "lower_quartile_closes_eq_0_long",
    "lower_quartile_closes_eq_0_short",
)
STRICT_FIELDS = (
    "risk_points",
    "reward_points",
    "reward_to_risk_planned",
    "risk_points_over_prior_range_points",
    "reward_points_over_prior_range_points",
    "risk_points_over_atr",
    "reward_points_over_atr",
)
FIELD_SOURCES = {
    "risk_points": ("risk_points",),
    "reward_points": ("reward_points",),
    "reward_to_risk_planned": ("reward_points", "risk_points"),
    "risk_points_over_prior_range_points": ("risk_points", "prior_range_points"),
    "reward_points_over_prior_range_points": ("reward_points", "prior_range_points"),
    "risk_points_over_atr": ("risk_points", "atr"),
    "reward_points_over_atr": ("reward_points", "atr"),
}
DECISION_FLAGS = (
    "insufficient_data",
    "mixed",
    "failed_replication",
    "weak_replicated",
    "promising_but_unconfirmed",
    "no_actionable_rule",
)
SEPARATION_KEYS = (
    "sample_count", "winner_count", "loser_count", "winner_mean", "loser_mean",
    "winner_median", "loser_median", "winner_std", "loser_std", "winner_p25",
    "winner_p75", "loser_p25", "loser_p75", "mean_difference",
    "median_difference", "simple_effect_size", "separation_flag",
)
MIN_TOTAL_FILTERED_TRADES = 100
MIN_FILTERED_TRADES_PER_RUN = 30
MIN_COHORT_TRADES = 20
MIN_WINNERS = 5
MIN_LOSERS = 5
MIN_TEST_SELECTED_TRADES = 20


def analyze_strict_pretrade_records(
    records: list[dict[str, Any]], *, provenance: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Analyze only fixed slices and provenance-qualified candidate fields."""
    if provenance is None:
        raise ValueError("provenance is required for strict pretrade replication")
    policy = _strict_policy(provenance)
    slices = {
        name: _slice_report(name, _select_slice(records, name), policy["included_fields"])
        for name in FIXED_SLICE_NAMES
    }
    return {
        "schema_version": "aqtf_edge_v2_strict_pretrade_replication.v1",
        "diagnostic_only": True,
        "condition": CONDITION_NAME,
        "fixed_slices": list(FIXED_SLICE_NAMES),
        "total_trades": len(records),
        "strict_field_policy": policy,
        "slices": slices,
        "decision_flags": _decision_flags(slices, successful_runs=1),
        "disclaimer": (
            "Diagnostic only. Positive observations do not confirm an edge, create "
            "a strategy rule, or change trading behaviour."
        ),
    }


def replicate_strict_pretrade(
    journal_paths: list[str | Path], *, provenance: dict[str, dict[str, Any]] | None = None,
    provenance_path: str | Path | None = None,
) -> dict[str, Any]:
    """Replicate the fixed report per journal and over all readable journals."""
    if provenance is not None and provenance_path is not None:
        raise ValueError("provide provenance or provenance_path, not both")
    active = load_provenance_file(provenance_path) if provenance_path is not None else provenance
    if active is None:
        raise ValueError("provenance is required for strict pretrade replication")
    per_run, aggregate_rows = [], []
    for source in journal_paths:
        path = Path(source)
        try:
            rows = load_journal_records(path)
        except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            per_run.append({"journal_path": str(path), "status": "skipped", "reason": str(exc)})
            continue
        report = analyze_strict_pretrade_records(rows, provenance=active)
        full_slice = report["slices"][FIXED_SLICE_NAMES[0]]
        per_run.append({
            "journal_path": str(path), "status": "success", **_metadata(rows),
            "total_trades": len(rows), "filtered_trades": full_slice["filtered_trade_count"],
            "filtered_winners": full_slice["filtered_winner_count"],
            "filtered_losers": full_slice["filtered_loser_count"], "slices": report["slices"],
            "candidate_field_results": full_slice["candidate_field_results"],
            "best_strict_pretrade_cohorts": _best_cohorts(full_slice),
            "sample_size_warnings": _sample_warnings(full_slice),
            "calibration_diagnostics": _calibrations(full_slice),
        })
        aggregate_rows.extend(rows)
    successful = [run for run in per_run if run["status"] == "success"]
    aggregate_report = analyze_strict_pretrade_records(aggregate_rows, provenance=active)
    aggregate = _aggregate_summary(aggregate_report, successful)
    aggregate["total_inputs"] = len(per_run)
    aggregate["skipped_inputs"] = len(per_run) - len(successful)
    return {
        "schema_version": "aqtf_edge_v2_strict_pretrade_replication_batch.v1",
        "diagnostic_only": True, "condition": CONDITION_NAME,
        "provenance_source": str(provenance_path) if provenance_path is not None else None,
        "strict_field_policy": aggregate_report["strict_field_policy"], "per_run": per_run,
        "aggregate_replication_summary": aggregate,
        "decision_flags": _decision_flags(aggregate_report["slices"], len(successful)),
        "disclaimer": aggregate_report["disclaimer"],
    }


def discover_batch_journals(batch_dirs: list[str | Path]) -> list[Path]:
    """Find supported existing journals without creating any research artifact."""
    paths: set[Path] = set()
    for item in batch_dirs:
        root = Path(item)
        if root.is_file():
            paths.add(root)
        elif root.exists():
            for name in ("trades.jsonl", "journal.jsonl", "journal.csv"):
                paths.update(root.rglob(name))
    return sorted(paths, key=lambda path: str(path).lower())


def write_strict_pretrade_replication_report(report: dict[str, Any], output: str | Path) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def _strict_policy(provenance: dict[str, dict[str, Any]]) -> dict[str, Any]:
    included, excluded, metadata = [], {}, {}
    for field, sources in FIELD_SOURCES.items():
        entries = [get_field_provenance(source, provenance) for source in sources]
        item = entries[0] if len(entries) == 1 else combine_source_provenance(field, entries)
        metadata[field] = item
        if _is_strict(item):
            included.append(field)
        else:
            excluded[field] = {"reason": _exclusion_reason(item), "provenance": item}
    for field in ("candle_range", "candle_range_over_prior_range_points", "candle_range_over_atr", "pnl", "r_multiple"):
        sources = ("candle_range", "prior_range_points") if field.endswith("prior_range_points") else ("candle_range", "atr") if field.endswith("_atr") else (field,)
        entries = [get_field_provenance(source, provenance) for source in sources]
        item = entries[0] if len(entries) == 1 else combine_source_provenance(field, entries)
        excluded[field] = {"reason": _exclusion_reason(item), "provenance": item}
    return {"required": {"availability_timing": "pre_decision", "leakage_risk": "low", "source_basis": "code_verified"}, "included_fields": included, "excluded_fields": excluded, "field_provenance": metadata}


def _is_strict(item: dict[str, Any]) -> bool:
    return all((item.get("availability_timing") == "pre_decision", item.get("leakage_risk") == "low", item.get("source_basis") == "code_verified", not item.get("uses_next_entry_bar"), not item.get("uses_spread_or_slippage"), not item.get("uses_spread"), not item.get("uses_slippage"), not item.get("uses_post_entry_information")))


def _exclusion_reason(item: dict[str, Any]) -> str:
    return "requires code_verified/pre_decision/low; got " + "/".join(str(item.get(key)) for key in ("source_basis", "availability_timing", "leakage_risk"))


def _select_slice(records: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    selected = [row for row in records if _number(row.get("lower_quartile_closes")) == 0 and _pnl(row) is not None]
    if name.endswith("_long"):
        return [row for row in selected if str(row.get("direction", "")).upper() == "LONG"]
    if name.endswith("_short"):
        return [row for row in selected if str(row.get("direction", "")).upper() == "SHORT"]
    return selected


def _slice_report(name: str, rows: list[dict[str, Any]], fields: list[str]) -> dict[str, Any]:
    direction_missing = sum(1 for row in rows if row.get("direction") in (None, ""))
    result = {field: _field_result(field, rows) for field in fields}
    winners, losers = _outcome_count(rows)
    return {"slice": name, "filtered_trade_count": len(rows), "filtered_winner_count": winners, "filtered_loser_count": losers, "direction_availability": "unavailable" if not any(row.get("direction") not in (None, "") for row in rows) else "available", "unavailable_direction_count": direction_missing, "candidate_field_results": result}


def _field_result(field: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = _with_field(rows, field)
    if not values:
        return {"availability": "unavailable", "reason": "field or required source values are absent", "winner_loser_separation": _separation([], field), "rank_cohorts": {}, "fixed_bins": {}}
    return {"availability": "available", "winner_loser_separation": _separation(values, field), "rank_cohorts": _rank_cohorts(values, field), "fixed_bins": _fixed_bins(values, field), "calibration": _calibration(values, field)}


def _with_field(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    calculated = []
    for row in rows:
        values = [_number(row.get(source)) for source in FIELD_SOURCES[field]]
        if any(value is None for value in values) or (len(values) > 1 and values[1] == 0):
            continue
        value = values[0] if len(values) == 1 else values[0] / values[1]
        calculated.append({**row, field: value})
    return calculated


def _separation(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    winners = [row[field] for row in rows if (_pnl(row) or 0) > 0]
    losers = [row[field] for row in rows if (_pnl(row) or 0) < 0]
    winner, loser = _summary(winners), _summary(losers)
    effect = calculate_effect_size(winners, losers)
    return {"sample_count": len(rows), "winner_count": len(winners), "loser_count": len(losers), "winner_mean": winner["mean"], "loser_mean": loser["mean"], "winner_median": winner["median"], "loser_median": loser["median"], "winner_std": winner["std"], "loser_std": loser["std"], "winner_p25": winner["p25"], "winner_p75": winner["p75"], "loser_p25": loser["p25"], "loser_p75": loser["p75"], "mean_difference": _difference(winner["mean"], loser["mean"]), "median_difference": _difference(winner["median"], loser["median"]), "simple_effect_size": effect, "separation_flag": _separation_flag(effect, len(winners), len(losers))}


def _summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {key: None for key in ("mean", "median", "std", "p25", "p75")}
    ordered = sorted(values)
    return {"mean": round(mean(values), 6), "median": round(median(values), 6), "std": round(pstdev(values), 6), "p25": _percentile(ordered, .25), "p75": _percentile(ordered, .75)}


def _percentile(ordered: list[float], fraction: float) -> float:
    point = (len(ordered) - 1) * fraction
    low, high = math.floor(point), math.ceil(point)
    return round(ordered[low] if low == high else ordered[low] + (ordered[high] - ordered[low]) * (point - low), 6)


def _difference(first: float | None, second: float | None) -> float | None:
    return round(first - second, 6) if first is not None and second is not None else None


def _separation_flag(effect: float | None, winners: int, losers: int) -> str:
    if winners < MIN_WINNERS or losers < MIN_LOSERS:
        return "insufficient_data"
    if effect is None or abs(effect) < .2:
        return "no_clear_separation"
    if abs(effect) < .5:
        return "weak_separation"
    if abs(effect) < .8:
        return "moderate_separation"
    return "strong_separation"


def _rank_cohorts(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    ordered = sorted(enumerate(rows), key=lambda item: (item[1][field], item[0]))
    count = len(ordered) // 4
    groups = {"bottom_25": ordered[:count], "middle_50": ordered[count:len(ordered)-count], "top_25": ordered[len(ordered)-count:]}
    return {name: cohort_metrics([row for _, row in group]) for name, group in groups.items()}


def _fixed_bins(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    if field == "reward_to_risk_planned":
        bins = {"lt_1": lambda x: x < 1, "1_to_lt_1_5": lambda x: 1 <= x < 1.5, "1_5_to_lt_2": lambda x: 1.5 <= x < 2, "gte_2": lambda x: x >= 2}
    elif "_over_" in field:
        bins = {"lte_0_5": lambda x: x <= .5, "gt_0_5_to_lte_1": lambda x: .5 < x <= 1, "gt_1_to_lte_2": lambda x: 1 < x <= 2, "gt_2": lambda x: x > 2}
    else:
        return {}
    return {name: cohort_metrics([row for row in rows if predicate(row[field])]) for name, predicate in bins.items()}


def _calibration(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    midpoint = len(rows) // 2
    calibration, test = rows[:midpoint], rows[midpoint:]
    separation = _separation(calibration, field)
    winner_median, loser_median = separation["winner_median"], separation["loser_median"]
    direction = "higher" if winner_median is not None and loser_median is not None and winner_median > loser_median else "lower" if winner_median is not None and loser_median is not None and winner_median < loser_median else None
    threshold = median([row[field] for row in calibration]) if direction is not None else None
    selected = [row for row in test if threshold is not None and (row[field] >= threshold if direction == "higher" else row[field] <= threshold)]
    metrics = cohort_metrics(selected)
    return {"field": field, "calibration_trade_count": len(calibration), "test_trade_count": len(test), "selected_direction": direction, "threshold_used": threshold, "test_selected_trade_count": len(selected), "test_winner_count": metrics["winner_count"], "test_loser_count": metrics["loser_count"], "test_profit_factor": metrics["profit_factor"], "test_expectancy": metrics["expectancy"], "sample_size_warning": len(selected) < MIN_TEST_SELECTED_TRADES, "interpretation_flag": metrics["interpretation_flag"]}


def _calibrations(slice_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {field: item["calibration"] for field, item in slice_report["candidate_field_results"].items() if item["availability"] == "available"}


def _best_cohorts(slice_report: dict[str, Any]) -> list[dict[str, Any]]:
    entries = []
    for field, item in slice_report["candidate_field_results"].items():
        for kind in ("rank_cohorts", "fixed_bins"):
            for cohort, metrics in item.get(kind, {}).items():
                entries.append({"field": field, "cohort": cohort, **metrics})
    return sorted(entries, key=lambda row: (row["expectancy"], row["profit_factor"] or float("-inf")), reverse=True)


def _sample_warnings(slice_report: dict[str, Any]) -> list[str]:
    return [field for field, item in slice_report["candidate_field_results"].items() if item["availability"] == "unavailable" or item["winner_loser_separation"]["separation_flag"] == "insufficient_data"]


def _aggregate_summary(report: dict[str, Any], successful: list[dict[str, Any]]) -> dict[str, Any]:
    full = report["slices"][FIXED_SLICE_NAMES[0]]
    candidates = full["candidate_field_results"]
    consistency = {field: _consistency(field, successful) for field in candidates}
    strongest = sorted((field for field, item in candidates.items() if item["availability"] == "available"), key=lambda field: abs(candidates[field]["winner_loser_separation"]["simple_effect_size"] or 0), reverse=True)
    return {"diagnostic_only": True, "total_inputs": len(successful), "successful_inputs": len(successful), "skipped_inputs": 0, "total_trades": report["total_trades"], "total_filtered_trades": full["filtered_trade_count"], "total_filtered_winners": full["filtered_winner_count"], "total_filtered_losers": full["filtered_loser_count"], "fields_tested": [field for field, item in candidates.items() if item["availability"] == "available"], "fields_excluded_by_provenance": list(report["strict_field_policy"]["excluded_fields"]), "per_field_consistency": consistency, "strongest_strict_pretrade_fields": strongest, "weakest_strict_pretrade_fields": list(reversed(strongest)), "stable_positive_candidates": [field for field, item in consistency.items() if item == "positive"], "mixed_candidates": [field for field, item in consistency.items() if item == "mixed"], "rejected_candidates": [field for field, item in consistency.items() if item == "negative"], "warnings": _sample_warnings(full), "aggregate_slices": report["slices"]}


def _consistency(field: str, runs: list[dict[str, Any]]) -> str:
    directions = []
    for run in runs:
        result = run["candidate_field_results"].get(field, {})
        separation = result.get("winner_loser_separation", {})
        difference = separation.get("mean_difference")
        if difference is not None:
            directions.append(difference > 0)
    return "mixed" if any(directions) and not all(directions) else "positive" if directions and all(directions) else "negative"


def _decision_flags(slices: dict[str, Any], successful_runs: int) -> list[str]:
    full = slices[FIXED_SLICE_NAMES[0]]
    fields = full["candidate_field_results"]
    flags = ["no_actionable_rule"]
    if full["filtered_trade_count"] < MIN_TOTAL_FILTERED_TRADES or successful_runs < 2:
        flags.append("insufficient_data")
    effects = [item["winner_loser_separation"]["mean_difference"] for item in fields.values() if item["availability"] == "available"]
    if any(value is not None and value > 0 for value in effects) and any(value is not None and value < 0 for value in effects):
        flags.append("mixed")
    calibrations = _calibrations(full).values()
    positive = [item for item in calibrations if (item["test_expectancy"] or 0) > 0 and (item["test_profit_factor"] or 0) > 1]
    if positive and successful_runs >= 2 and full["filtered_trade_count"] >= MIN_TOTAL_FILTERED_TRADES:
        flags.append("promising_but_unconfirmed")
    elif positive:
        flags.append("weak_replicated")
    elif effects:
        flags.append("failed_replication")
    return [flag for flag in DECISION_FLAGS if flag in flags]


def _metadata(rows: list[dict[str, Any]]) -> dict[str, Any]:
    times = sorted(str(row[key]) for row in rows for key in ("timestamp_open", "entry_time", "open_time", "timestamp") if row.get(key) is not None)
    def first(field: str) -> Any:
        return next((row[field] for row in rows if row.get(field) not in (None, "")), None)

    return {"symbol": first("symbol"), "timeframe": first("timeframe"), "date_range": {"start": times[0], "end": times[-1]} if times else None}


def _pnl(row: dict[str, Any]) -> float | None:
    return _number(row.get("pnl"))


def _outcome_count(rows: list[dict[str, Any]]) -> tuple[int, int]:
    return sum((_pnl(row) or 0) > 0 for row in rows), sum((_pnl(row) or 0) < 0 for row in rows)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write a diagnostic-only strict pretrade replication report")
    parser.add_argument("--journal", action="append", type=Path, default=[])
    parser.add_argument("--batch-dir", action="append", type=Path, default=[])
    parser.add_argument("--condition", default=CONDITION_NAME, choices=[CONDITION_NAME])
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    journals = [*args.journal, *discover_batch_journals(args.batch_dir)]
    if not journals:
        parser.error("provide at least one --journal or --batch-dir")
    print(write_strict_pretrade_replication_report(replicate_strict_pretrade(journals, provenance_path=args.provenance), args.out))


if __name__ == "__main__":
    main()
