"""Diagnostic robustness checks for the preselected Edge V2 raw signal."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from trading_bot.research.edge_v2_cohort_report import (
    cohort_metrics,
    select_fixed_cohort_records,
)
from trading_bot.research.edge_v2_cohort_replication import discover_batch_journals
from trading_bot.research.edge_v2_feature_separation import load_journal_records


SIGNAL_NAME = "lower_quartile_closes"
MIN_TOTAL_TRADES = 100
MIN_GROUP_TRADES = 20
MIN_GROUP_WINNERS = 5
MIN_GROUP_LOSERS = 5
MIN_TEST_TRADES = 20
CUMULATIVE_GROUPS = (
    ("lower_quartile_closes_eq_0", lambda value: value == 0),
    ("lower_quartile_closes_lte_1", lambda value: value <= 1),
    ("lower_quartile_closes_lte_2", lambda value: value <= 2),
    ("lower_quartile_closes_gte_3", lambda value: value >= 3),
    ("lower_quartile_closes_gte_4", lambda value: value >= 4),
)


def build_fixed_signal_robustness_report(
    journal_paths: list[str | Path],
) -> dict[str, Any]:
    """Assess predefined raw, rank, temporal, and calibration diagnostics only."""
    per_input_results: list[dict[str, Any]] = []
    warnings: list[str] = ["rank_partition_may_not_be_directly_tradable"]
    successful_records: list[list[dict[str, Any]]] = []
    seen_hashes: set[str] = set()

    for source in journal_paths:
        path = Path(source)
        try:
            content_hash = _file_hash(path)
            records = load_journal_records(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            per_input_results.append(_failed_input(path, "invalid_or_missing", str(exc)))
            continue
        if content_hash in seen_hashes:
            per_input_results.append(_failed_input(path, "duplicate_input", "duplicate journal content"))
            continue
        seen_hashes.add(content_hash)
        result = _analyze_input(path, records)
        per_input_results.append(result)
        successful_records.append(records)
        warnings.extend(result["warnings"])

    combined = [record for records in successful_records for record in records]
    raw_summary = _raw_value_summary(combined)
    cumulative_summary = _cumulative_group_summary(combined)
    rank_summary = cohort_metrics(
        [
            record
            for records in successful_records
            for record in select_fixed_cohort_records(records, SIGNAL_NAME, "bottom_25")
        ]
    )
    comparison = _rank_vs_raw_comparison(rank_summary, raw_summary, cumulative_summary)
    temporal_summary = {
        result["journal_path"]: result["temporal_splits"]
        for result in per_input_results
        if result["status"] == "success"
    }
    calibration_summary = [
        result["calibration_test"]
        for result in per_input_results
        if result["status"] == "success"
    ]
    total_metrics = cohort_metrics(combined)
    warnings.extend(_aggregate_warnings(total_metrics, raw_summary, cumulative_summary, calibration_summary))
    warnings = sorted(set(warnings))
    return {
        "schema_version": "aqtf_edge_v2_fixed_signal_robustness.v1",
        "diagnostic_only": True,
        "signal_name": SIGNAL_NAME,
        "input_count": len(journal_paths),
        "successful_inputs": len(successful_records),
        "failed_or_skipped_inputs": len(journal_paths) - len(successful_records),
        "total_trades": total_metrics["trade_count"],
        "total_winners": total_metrics["winner_count"],
        "total_losers": total_metrics["loser_count"],
        "total_breakeven": total_metrics["breakeven_count"],
        "raw_value_summary": raw_summary,
        "cumulative_group_summary": cumulative_summary,
        "rank_partition_summary": {"bottom_25": rank_summary},
        "rank_vs_raw_comparison": comparison,
        "temporal_split_summary": temporal_summary,
        "calibration_test_summary": calibration_summary,
        "per_input_results": per_input_results,
        "robustness_flags": _robustness_flags(
            total_metrics, rank_summary, raw_summary, cumulative_summary
        ),
        "warnings": warnings,
        "disclaimer": (
            "Diagnostic only; rank buckets are not directly tradable thresholds, and "
            "one calibration/test split does not confirm an edge or strategy rule."
        ),
    }


def write_fixed_signal_robustness_report(
    report: dict[str, Any], output: str | Path
) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def _analyze_input(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    raw_summary = _raw_value_summary(records)
    cumulative_summary = _cumulative_group_summary(records)
    rank_summary = cohort_metrics(
        select_fixed_cohort_records(records, SIGNAL_NAME, "bottom_25")
    )
    temporal_splits = _temporal_splits(records)
    calibration = _calibration_test(records)
    warnings = _input_warnings(
        records, raw_summary, cumulative_summary, temporal_splits, calibration
    )
    return {
        **_metadata(path, records),
        "status": "success",
        "raw_value_summary": raw_summary,
        "cumulative_group_summary": cumulative_summary,
        "rank_partition_summary": {"bottom_25": rank_summary},
        "rank_vs_raw_comparison": _rank_vs_raw_comparison(
            rank_summary, raw_summary, cumulative_summary
        ),
        "temporal_splits": temporal_splits,
        "calibration_test": calibration,
        "warnings": warnings,
    }


def _raw_value_summary(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[float, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        value = _value(record)
        if value is not None:
            groups[value].append(record)
    return {
        _value_key(value): cohort_metrics(rows)
        for value, rows in sorted(groups.items())
    }


def _cumulative_group_summary(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    values = [(record, _value(record)) for record in records]
    return {
        name: cohort_metrics([record for record, value in values if value is not None and predicate(value)])
        for name, predicate in CUMULATIVE_GROUPS
    }


def _rank_vs_raw_comparison(
    rank_metrics: dict[str, Any],
    raw_summary: dict[str, dict[str, Any]],
    cumulative_summary: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    compared = {
        "rank_bottom_25": rank_metrics,
        "raw_value_eq_0": raw_summary.get("0", cohort_metrics([])),
        "raw_value_lte_1": cumulative_summary["lower_quartile_closes_lte_1"],
        "raw_value_lte_2": cumulative_summary["lower_quartile_closes_lte_2"],
    }
    directions = {
        _direction(metrics["expectancy"])
        for metrics in compared.values()
        if not metrics["sample_size_warning"]
    }
    return {
        **compared,
        "comparison": "agree" if len(directions) <= 1 else "diverge",
        "diagnostic_only": True,
    }


def _temporal_splits(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    ordered = _chronological(records)
    half = len(ordered) // 2
    groups = {"first_half": ordered[:half], "second_half": ordered[half:]}
    if len(ordered) >= 30:
        third = len(ordered) // 3
        groups.update(
            {
                "first_third": ordered[:third],
                "second_third": ordered[third : third * 2],
                "third_third": ordered[third * 2 :],
            }
        )
    return {
        name: _split_metrics(rows)
        for name, rows in groups.items()
    }


def _split_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    raw = _raw_value_summary(records)
    cumulative = _cumulative_group_summary(records)
    rank = cohort_metrics(select_fixed_cohort_records(records, SIGNAL_NAME, "bottom_25"))
    groups = {
        "rank_bottom_25": rank,
        "raw_value_eq_0": raw.get("0", cohort_metrics([])),
        "raw_value_lte_1": cumulative["lower_quartile_closes_lte_1"],
    }
    return {
        "trade_count": len(records),
        "groups": groups,
        "sample_size_warning": any(
            metric["sample_size_warning"] for metric in groups.values()
        ),
    }


def _calibration_test(records: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = _chronological(records)
    midpoint = len(ordered) // 2
    calibration = ordered[:midpoint]
    test = ordered[midpoint:]
    calibration_values = sorted(
        value for record in calibration if (value := _value(record)) is not None
    )
    threshold = _calibration_q25_threshold(calibration_values)
    selected = [
        record
        for record in test
        if threshold is not None
        and (value := _value(record)) is not None
        and value <= threshold
    ]
    metrics = cohort_metrics(selected)
    warning = (
        threshold is None
        or len(test) < MIN_TEST_TRADES
        or metrics["trade_count"] < MIN_TEST_TRADES
        or metrics["winner_count"] < MIN_GROUP_WINNERS
        or metrics["loser_count"] < MIN_GROUP_LOSERS
    )
    return {
        "calibration_trade_count": len(calibration),
        "test_trade_count": len(test),
        "calibrated_q25_threshold": threshold,
        "test_selected_trade_count": metrics["trade_count"],
        "test_winner_count": metrics["winner_count"],
        "test_loser_count": metrics["loser_count"],
        "test_profit_factor": metrics["profit_factor"],
        "test_expectancy": metrics["expectancy"],
        "test_interpretation_flag": metrics["interpretation_flag"],
        "sample_size_warning": warning,
    }


def _metadata(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    first = records[0] if records else {}
    timestamps = [
        str(record["timestamp_open"])
        for record in records
        if record.get("timestamp_open") is not None
    ]
    return {
        "journal_path": str(path),
        "symbol": first.get("symbol"),
        "timeframe": first.get("timeframe"),
        "date_range": {
            "start": min(timestamps) if timestamps else None,
            "end": max(timestamps) if timestamps else None,
        },
        "total_trades": len(records),
    }


def _input_warnings(
    records: list[dict[str, Any]],
    raw: dict[str, dict[str, Any]],
    cumulative: dict[str, dict[str, Any]],
    splits: dict[str, dict[str, Any]],
    calibration: dict[str, Any],
) -> list[str]:
    warnings = []
    if not any(_value(record) is not None for record in records):
        warnings.append("lower_quartile_closes_unavailable")
    if len(records) < MIN_TOTAL_TRADES:
        warnings.append("low_total_trade_count")
    if len(raw) < 4 and raw:
        warnings.append("too_few_unique_values")
    if any(metric["sample_size_warning"] for metric in raw.values()) or any(
        metric["sample_size_warning"] for metric in cumulative.values()
    ):
        warnings.append("raw_value_group_insufficient_sample")
    if any(split["sample_size_warning"] for split in splits.values()):
        warnings.append("split_samples_too_small")
    if calibration["sample_size_warning"]:
        warnings.append("calibrated_threshold_test_insufficient_sample")
    return warnings


def _aggregate_warnings(
    total: dict[str, Any],
    raw: dict[str, dict[str, Any]],
    cumulative: dict[str, dict[str, Any]],
    calibration: list[dict[str, Any]],
) -> list[str]:
    warnings = []
    if total["trade_count"] < MIN_TOTAL_TRADES:
        warnings.append("low_total_trade_count")
    if total["winner_count"] < MIN_GROUP_WINNERS:
        warnings.append("low_winner_count")
    if total["loser_count"] < MIN_GROUP_LOSERS:
        warnings.append("low_loser_count")
    if raw and len(raw) < 4:
        warnings.append("too_few_unique_values")
    if any(metric["sample_size_warning"] for metric in raw.values()) or any(
        metric["sample_size_warning"] for metric in cumulative.values()
    ):
        warnings.append("raw_value_group_insufficient_sample")
    if any(item["sample_size_warning"] for item in calibration):
        warnings.append("calibrated_threshold_test_insufficient_sample")
    return warnings


def _robustness_flags(
    total: dict[str, Any],
    rank: dict[str, Any],
    raw: dict[str, dict[str, Any]],
    cumulative: dict[str, dict[str, Any]],
) -> list[str]:
    flags = []
    if total["trade_count"] < MIN_TOTAL_TRADES:
        flags.append("insufficient_data")
    compared = [
        rank,
        raw.get("0", cohort_metrics([])),
        cumulative["lower_quartile_closes_lte_1"],
    ]
    directions = {_direction(metric["expectancy"]) for metric in compared}
    if len(directions) > 1:
        flags.append("mixed")
    elif all(direction == "positive" for direction in directions):
        flags.append("weak_promising" if any(metric["sample_size_warning"] for metric in compared) else "promising_but_unconfirmed")
    else:
        flags.append("not_robust")
    return flags


def _failed_input(path: Path, status: str, reason: str) -> dict[str, Any]:
    return {
        "journal_path": str(path),
        "status": status,
        "reason": reason,
        "warnings": [status],
    }


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _chronological(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda record: str(record.get("timestamp_open", "")))


def _value(record: dict[str, Any]) -> float | None:
    try:
        value = float(record.get(SIGNAL_NAME))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _value_key(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _calibration_q25_threshold(values: list[float]) -> float | None:
    if not values:
        return None
    return values[max(0, len(values) // 4 - 1)]


def _direction(expectancy: float | None) -> str:
    if expectancy is None or abs(expectancy) < 0.01:
        return "neutral"
    return "positive" if expectancy > 0 else "negative"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate diagnostic-only Edge V2 fixed signal robustness report"
    )
    parser.add_argument("--journal", action="append", type=Path, default=[])
    parser.add_argument("--batch-dir", action="append", type=Path, default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    journals = [*args.journal, *discover_batch_journals(args.batch_dir)]
    if not journals:
        parser.error("provide at least one --journal or --batch-dir")
    report = build_fixed_signal_robustness_report(journals)
    print(write_fixed_signal_robustness_report(report, args.out))


if __name__ == "__main__":
    main()
