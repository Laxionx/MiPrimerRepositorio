"""Research-only, provenance-gated Edge V3 pre-trade feature matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from trading_bot.research.edge_v2_feature_separation import load_journal_records
from trading_bot.research.edge_v2_feature_timing_provenance import (
    combine_source_provenance,
    get_field_provenance,
    load_provenance_file,
)


REQUIRED_JOURNAL_FIELDS = ("timestamp_open", "pnl", "symbol", "timeframe")
OUTCOME_FIELDS = {
    "pnl", "r_multiple", "outcome", "exit_price", "timestamp_close", "bars_held",
    "exit_reason", "entry_price", "exit_time",
}
METADATA_FIELDS = {"trade_id", "symbol", "timeframe", "timestamp_open", "direction"}
EXCLUDED_PREDICTORS = OUTCOME_FIELDS | {
    "lower_quartile_closes", "candle_range", "candle_range_over_atr",
    "candle_range_over_prior_range_points", "risk_points_over_candle_range",
    "reward_points_over_candle_range", "entry", "stop_loss", "take_profit",
    "planned_rr",
}
DERIVED_SOURCES = {
    "reward_to_risk_planned": ("reward_points", "risk_points"),
    "risk_points_over_prior_range_points": ("risk_points", "prior_range_points"),
    "reward_points_over_prior_range_points": ("reward_points", "prior_range_points"),
    "risk_points_over_atr": ("risk_points", "atr"),
    "reward_points_over_atr": ("reward_points", "atr"),
}


def discover_batch_journals(batch_dirs: list[str | Path]) -> list[Path]:
    paths: set[Path] = set()
    for value in batch_dirs:
        source = Path(value)
        if source.is_file() and source.name == "trades.jsonl":
            paths.add(source)
        elif source.exists():
            paths.update(source.rglob("trades.jsonl"))
    return sorted(paths, key=lambda path: str(path).lower())


def build_pretrade_feature_matrix(
    batch_dirs: list[str | Path], *, provenance: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    journals = discover_batch_journals(batch_dirs)
    records, manifest = _load_unique_records(journals)
    return _build_matrix(records, manifest, provenance)


def build_matrix_from_records(
    records: list[dict[str, Any]], *, provenance: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    manifest = [{
        "path": "in_memory", "sha256": None, "symbol": _first(records, "symbol"),
        "timeframe": _first(records, "timeframe"), "trades": len(records),
        "timestamp_open_min": _timestamp_bound(records, min),
        "timestamp_open_max": _timestamp_bound(records, max),
        "available_fields": sorted({key for row in records for key in row}),
        "accepted": True, "rejection_reason": None,
    }]
    return _build_matrix(records, manifest, provenance)


def _load_unique_records(journals: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted_rows: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for path in journals:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        try:
            rows = load_journal_records(path)
        except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            manifest.append(_manifest(path, digest, [], False, f"invalid_journal: {exc}"))
            continue
        if digest in seen_hashes:
            manifest.append(_manifest(path, digest, rows, False, "duplicate_sha256"))
            continue
        missing = _missing_required_fields(rows)
        if missing:
            manifest.append(_manifest(path, digest, rows, False, f"missing_required_fields: {', '.join(missing)}"))
            continue
        seen_hashes.add(digest)
        manifest.append(_manifest(path, digest, rows, True, None))
        for index, row in enumerate(rows):
            accepted_rows.append({**row, "_source_journal": str(path), "_source_index": index})
    return accepted_rows, manifest


def _build_matrix(
    records: list[dict[str, Any]], manifest: list[dict[str, Any]], provenance: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    base_predictors = _strict_predictors(records, provenance)
    derived = _strict_derivatives(provenance)
    predictors = sorted([*base_predictors, *derived])
    feature_provenance = {
        feature: _feature_provenance(feature, provenance) for feature in predictors
    }
    matrix_records = [
        _matrix_record(row, index, base_predictors, derived)
        for index, row in enumerate(records)
    ]
    return {
        "schema_version": "aqtf_edge_v3_pretrade_feature_matrix.v1",
        "diagnostic_only": True,
        "lqc_excluded": True,
        "input_manifest": manifest,
        "accepted_journal_count": sum(item["accepted"] for item in manifest),
        "rejected_journal_count": sum(not item["accepted"] for item in manifest),
        "predictors": predictors,
        "labels": ["pnl", "outcome", "r_multiple"],
        "metrics_only_fields": sorted(OUTCOME_FIELDS),
        "excluded_predictors": sorted(EXCLUDED_PREDICTORS),
        "feature_provenance": feature_provenance,
        "records": matrix_records,
        "disclaimer": "Research-only matrix; no strategy, execution, or rule output is produced.",
    }


def _strict_predictors(records: list[dict[str, Any]], provenance: dict[str, dict[str, Any]]) -> list[str]:
    fields = sorted({key for row in records for key in row})
    return [
        field for field in fields
        if field not in EXCLUDED_PREDICTORS | METADATA_FIELDS
        and _is_strict(_feature_provenance(field, provenance))
        and any(_number(row.get(field)) is not None for row in records)
    ]


def _strict_derivatives(provenance: dict[str, dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    return {
        name: sources for name, sources in DERIVED_SOURCES.items()
        if _is_strict(_feature_provenance(name, provenance))
    }


def _feature_provenance(feature: str, provenance: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if feature in DERIVED_SOURCES:
        return combine_source_provenance(
            feature, [get_field_provenance(source, provenance) for source in DERIVED_SOURCES[feature]]
        )
    return get_field_provenance(feature, provenance)


def _is_strict(entry: dict[str, Any]) -> bool:
    return (
        entry.get("source_basis") == "code_verified"
        and entry.get("availability_timing") == "pre_trade"
        and entry.get("leakage_risk") == "low"
    )


def _matrix_record(
    row: dict[str, Any], index: int, base_predictors: list[str], derived: dict[str, tuple[str, ...]]
) -> dict[str, Any]:
    values = {field: _number(row.get(field)) for field in base_predictors}
    values = {field: value for field, value in values.items() if value is not None}
    for name, sources in derived.items():
        numerator, denominator = (_number(row.get(source)) for source in sources)
        if numerator is not None and denominator not in (None, 0):
            values[name] = numerator / denominator
    return {
        "record_id": f"{row.get('_source_journal', 'record')}:{row.get('_source_index', index)}",
        "segment": {
            "symbol": row.get("symbol"), "timeframe": row.get("timeframe"),
            "direction": row.get("direction"), "timestamp_open": row.get("timestamp_open"),
        },
        "predictors": values,
        "labels": {key: row.get(key) for key in ("pnl", "outcome", "r_multiple")},
    }


def _missing_required_fields(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["empty_journal"]
    return [
        field for field in REQUIRED_JOURNAL_FIELDS
        if any(row.get(field) in (None, "") for row in rows)
    ]


def _manifest(path: Path, digest: str, rows: list[dict[str, Any]], accepted: bool, reason: str | None) -> dict[str, Any]:
    return {
        "path": str(path), "sha256": digest, "symbol": _first(rows, "symbol"),
        "timeframe": _first(rows, "timeframe"), "trades": len(rows),
        "timestamp_open_min": _timestamp_bound(rows, min),
        "timestamp_open_max": _timestamp_bound(rows, max),
        "available_fields": sorted({key for row in rows for key in row}),
        "accepted": accepted, "rejection_reason": reason,
    }


def _first(records: list[dict[str, Any]], field: str) -> Any:
    return next((row.get(field) for row in records if row.get(field) not in (None, "")), None)


def _timestamp_bound(records: list[dict[str, Any]], operation: Any) -> str | None:
    values = [str(row["timestamp_open"]) for row in records if row.get("timestamp_open")]
    return operation(values) if values else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _write_json(value: dict[str, Any], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build a strict, research-only Edge V3 feature matrix")
    parser.add_argument("--batch-dir", action="append", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build_pretrade_feature_matrix(args.batch_dir, provenance=load_provenance_file(args.provenance))
    _write_json(report, args.out)
    _write_json({"schema_version": "aqtf_edge_v3_input_manifest.v1", "journals": report["input_manifest"]}, args.manifest_out)
    print(args.out)


if __name__ == "__main__":
    main()
