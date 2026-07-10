"""Deterministic temporal validation for Edge V3 descriptive cohorts."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from trading_bot.research.edge_v3_full_pretrade_discriminator_discovery import (
    _feature_report,
    _value,
    assign_cohorts,
    cohort_definitions,
)


MIN_COHORT_TRADES = 30
MIN_WINNERS = 10
MIN_LOSERS = 10


def audit_temporal_train_test(matrix: dict[str, Any], discovery: dict[str, Any]) -> dict[str, Any]:
    records = list(matrix.get("records", []))
    predictors = [feature for feature in discovery.get("features", {}) if feature != "lower_quartile_closes"]
    segments = {
        "global": [("all", records)],
        **_segmented_records(records),
    }
    return {
        "schema_version": "aqtf_edge_v3_temporal_train_test.v1",
        "diagnostic_only": True,
        "lqc_excluded": True,
        "segments": {
            kind: [_segment_report(name, rows, predictors) for name, rows in entries]
            for kind, entries in segments.items()
        },
        "disclaimer": "Cohort definitions are set in train and applied unchanged in test; no rule is promoted.",
    }


def _segment_report(name: str, rows: list[dict[str, Any]], predictors: list[str]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (str(row.get("segment", {}).get("timestamp_open", "")), row["record_id"]))
    midpoint = len(ordered) // 2
    train, test = ordered[:midpoint], ordered[midpoint:]
    return {
        "segment": name, "total_trade_count": len(ordered),
        "features": {feature: _feature_audit(train, test, feature) for feature in predictors},
    }


def _feature_audit(train: list[dict[str, Any]], test: list[dict[str, Any]], feature: str) -> dict[str, Any]:
    train_rows = [row for row in train if _value(row, feature) is not None]
    test_rows = [row for row in test if _value(row, feature) is not None]
    ordered_train = sorted(((row, _value(row, feature)) for row in train_rows), key=lambda item: (item[1], item[0]["record_id"]))
    ordered_test = sorted(((row, _value(row, feature)) for row in test_rows), key=lambda item: (item[1], item[0]["record_id"]))
    definitions = _train_definitions([value for _, value in ordered_train], feature)
    train_cohorts = assign_cohorts(ordered_train, feature, definitions, include_record_ids=False)
    test_cohorts = assign_cohorts(ordered_test, feature, definitions, include_record_ids=False)
    cohorts = {
        name: _cohort_audit(train_cohorts[name], test_cohorts[name])
        for name in definitions
    }
    return {
        "train_trade_count": len(train_rows), "test_trade_count": len(test_rows),
        "cohort_definitions": definitions,
        "train": _distribution_report(train_rows, feature),
        "test": _distribution_report(test_rows, feature),
        "cohorts": cohorts,
    }


def _cohort_audit(train: dict[str, Any], test: dict[str, Any]) -> dict[str, Any]:
    warning = any(
        item["trade_count"] < MIN_COHORT_TRADES
        or item["winner_count"] < MIN_WINNERS
        or item["loser_count"] < MIN_LOSERS
        for item in (train, test)
    )
    return {"train": train, "test": test, "sample_size_warning": warning}


def _train_definitions(values: list[float], feature: str) -> dict[str, dict[str, Any]]:
    base = cohort_definitions(values, feature)
    if not base or next(iter(base.values()))["kind"] == "fixed":
        return base
    ordered = sorted(values)
    bottom_end, top_start = len(ordered) // 4, len(ordered) - len(ordered) // 4
    if bottom_end == 0 or top_start >= len(ordered):
        return {"all_values": {"kind": "fixed", "lower": None, "upper": None}}
    return {
        "bottom_25": {"kind": "fixed", "lower": None, "upper": ordered[bottom_end - 1]},
        "middle_50": {"kind": "fixed", "lower": ordered[bottom_end - 1], "upper": ordered[top_start - 1]},
        "top_25": {"kind": "fixed", "lower": ordered[top_start - 1], "upper": None},
    }


def _distribution_report(rows: list[dict[str, Any]], feature: str) -> dict[str, Any]:
    report = _feature_report(rows, feature, include_record_ids=False)
    report.pop("cohort_definitions", None)
    report.pop("cohorts", None)
    return report


def _segmented_records(records: list[dict[str, Any]]) -> dict[str, list[tuple[str, list[dict[str, Any]]]]]:
    groups = {"symbol": defaultdict(list), "timeframe": defaultdict(list), "direction": defaultdict(list), "symbol_timeframe": defaultdict(list)}
    for row in records:
        segment = row.get("segment", {})
        for kind, value in (("symbol", segment.get("symbol")), ("timeframe", segment.get("timeframe")), ("direction", segment.get("direction"))):
            if value is not None:
                groups[kind][str(value)].append(row)
        if segment.get("symbol") is not None and segment.get("timeframe") is not None:
            groups["symbol_timeframe"][f"{segment['symbol']}/{segment['timeframe']}"].append(row)
    return {kind: sorted(values.items()) for kind, values in groups.items()}


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(value: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run Edge V3 deterministic temporal train/test diagnostics")
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--discovery", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    _write_json(audit_temporal_train_test(_read_json(args.matrix), _read_json(args.discovery)), args.out)
    print(args.out)


if __name__ == "__main__":
    main()
