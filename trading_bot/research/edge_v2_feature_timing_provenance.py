"""Source-backed timing provenance for Edge V2 research fields."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from trading_bot.research.edge_v2_feature_separation import load_journal_records


REQUIRED_PROVENANCE_FIELDS = (
    "risk_points",
    "reward_points",
    "candle_range",
    "prior_range_points",
    "lower_quartile_closes",
    "price_position_in_range",
    "pressure_score",
    "compression_score",
    "sweep_depth",
    "reclaim_speed",
    "r_multiple",
    "pnl",
    "outcome",
)
REQUIRED_PROVENANCE_KEYS = (
    "field_name",
    "category",
    "availability_timing",
    "leakage_risk",
    "source_basis",
    "source_module_or_function",
    "depends_on_fields",
    "depends_on_exit_price",
    "depends_on_pnl",
    "depends_on_future_bars",
    "depends_on_realized_outcome",
    "reason",
)
NORMALIZED_FIELD_SOURCES = {
    "candle_range_over_prior_range_points": ("candle_range", "prior_range_points"),
    "risk_points_over_prior_range_points": ("risk_points", "prior_range_points"),
    "candle_range_over_atr": ("candle_range", "atr"),
}
OUTCOME_FIELDS = {
    "pnl",
    "profit",
    "loss",
    "realized_pnl",
    "r_multiple",
    "outcome",
    "exit_price",
    "exit_time",
    "timestamp_close",
    "duration",
    "bars_held",
    "gross_profit",
    "gross_loss",
}


def _entry(
    field_name: str,
    *,
    category: str,
    timing: str,
    risk: str,
    basis: str,
    source: str | None,
    depends: list[str] | None = None,
    exit_price: bool = False,
    pnl: bool = False,
    future_bars: bool = False,
    realized: bool = False,
    reason: str,
) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "category": category,
        "availability_timing": timing,
        "leakage_risk": risk,
        "source_basis": basis,
        "source_module_or_function": source,
        "depends_on_fields": depends or [],
        "depends_on_exit_price": exit_price,
        "depends_on_pnl": pnl,
        "depends_on_future_bars": future_bars,
        "depends_on_realized_outcome": realized,
        "reason": reason,
    }


PROVENANCE_REGISTRY = {
    "atr": _entry(
        "atr", category="market_context", timing="pre_trade", risk="low",
        basis="code_verified", source="trading_bot/backtest/runner.py:_atr",
        depends=["historical bars"],
        reason="Runner calculates ATR from historical bars before creating the pending trade.",
    ),
    "risk_points": _entry(
        "risk_points", category="risk_reward_construction", timing="pre_trade", risk="low",
        basis="code_verified", source="trading_bot/backtest/runner.py:_close_trade",
        depends=["entry", "stop_loss"],
        reason="Calculated as entry-to-stop distance; both values come from the planned setup.",
    ),
    "reward_points": _entry(
        "reward_points", category="risk_reward_construction", timing="pre_trade", risk="low",
        basis="code_verified", source="trading_bot/backtest/runner.py:_close_trade",
        depends=["entry", "take_profit"],
        reason="Calculated as entry-to-planned-take-profit distance, not realized exit distance.",
    ),
    "candle_range": _entry(
        "candle_range", category="market_context", timing="at_entry", risk="medium",
        basis="code_verified", source="trading_bot/backtest/runner.py:run",
        depends=["bar.high", "bar.low"],
        reason="Runner computes high-low before creating the pending trade; closed-candle provenance is not persisted separately.",
    ),
    "prior_range_points": _entry(
        "prior_range_points", category="market_context", timing="pre_trade", risk="low",
        basis="code_verified", source="trading_bot/analysis/edge_v2.py:EdgeV2Diagnostics.evaluate",
        depends=["prior candle history"],
        reason="Computed from the prior historical window before the runner creates a pending trade.",
    ),
    "lower_quartile_closes": _entry(
        "lower_quartile_closes", category="market_context", timing="pre_trade", risk="low",
        basis="code_verified", source="trading_bot/analysis/edge_v2.py:EdgeV2Diagnostics._pressure",
        depends=["historical closes"],
        reason="Computed from completed history before pending-trade creation.",
    ),
    "price_position_in_range": _entry(
        "price_position_in_range", category="market_context", timing="pre_trade", risk="low",
        basis="code_verified", source="trading_bot/analysis/edge_v2.py:EdgeV2Diagnostics._pressure",
        depends=["historical closes", "historical highs", "historical lows"],
        reason="Computed from the historical pressure window before pending-trade creation.",
    ),
    "pressure_score": _entry(
        "pressure_score", category="market_context", timing="pre_trade", risk="low",
        basis="code_verified", source="trading_bot/analysis/edge_v2.py:EdgeV2Diagnostics._pressure",
        depends=["historical closes"],
        reason="Computed from the historical pressure window before pending-trade creation.",
    ),
    "compression_score": _entry(
        "compression_score", category="market_context", timing="pre_trade", risk="low",
        basis="code_verified", source="trading_bot/analysis/edge_v2.py:EdgeV2Diagnostics.evaluate",
        depends=["recent candle history", "prior candle history"],
        reason="Computed from recent and prior historical windows before pending-trade creation.",
    ),
    "sweep_depth": _entry(
        "sweep_depth", category="unknown", timing="unknown", risk="unknown",
        basis="unknown", source=None, reason="No production definition was verified in the repository.",
    ),
    "reclaim_speed": _entry(
        "reclaim_speed", category="unknown", timing="unknown", risk="unknown",
        basis="unknown", source=None, reason="No production definition was verified in the repository.",
    ),
    "r_multiple": _entry(
        "r_multiple", category="outcome", timing="post_trade", risk="high",
        basis="code_verified", source="trading_bot/backtest/runner.py:_close_trade",
        depends=["pnl", "risk_points"], pnl=True, realized=True,
        reason="Calculated from realized PnL after trade completion.",
    ),
    "pnl": _entry(
        "pnl", category="outcome", timing="post_trade", risk="high",
        basis="code_verified", source="trading_bot/backtest/runner.py:_close_trade",
        depends=["entry", "exit_price"], exit_price=True, realized=True,
        reason="Calculated from the realized exit price after trade completion.",
    ),
    "outcome": _entry(
        "outcome", category="outcome", timing="post_trade", risk="high",
        basis="code_verified", source="trading_bot/backtest/runner.py:_close_trade",
        depends=["pnl"], pnl=True, realized=True,
        reason="Derived from realized PnL after trade completion.",
    ),
}


def get_field_provenance(field: str, overrides: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    if field in OUTCOME_FIELDS:
        return _outcome_provenance(field)
    if overrides and field in overrides:
        return copy.deepcopy(overrides[field])
    if field in PROVENANCE_REGISTRY:
        return copy.deepcopy(PROVENANCE_REGISTRY[field])
    return _entry(
        field, category="unknown", timing="unknown", risk="unknown", basis="unknown", source=None,
        reason="No field-level provenance was supplied or verified.",
    )


def load_provenance_file(path: str | Path) -> dict[str, dict[str, Any]]:
    source = Path(path)
    parsed = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("provenance JSON must contain an object")
    entries = parsed.get("registry", parsed)
    if not isinstance(entries, dict):
        raise ValueError("provenance registry must contain an object")
    overrides = {}
    for field, entry in entries.items():
        if field not in PROVENANCE_REGISTRY or not isinstance(entry, dict):
            continue
        missing = [key for key in REQUIRED_PROVENANCE_KEYS if key not in entry]
        if missing:
            raise ValueError(f"provenance for {field} is missing: {', '.join(missing)}")
        overrides[field] = copy.deepcopy(entry)
    return overrides


def combine_source_provenance(name: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    if not sources:
        return _entry(
            name, category="unknown", timing="unknown", risk="unknown", basis="unknown", source=None,
            reason="Normalization has no verified source fields.",
        ) | {"source_fields": []}
    timing_order = {"pre_trade": 0, "at_entry": 1, "unknown": 2, "post_trade": 3}
    risk_order = {"low": 0, "medium": 1, "unknown": 2, "high": 3}
    timing_source = max(sources, key=lambda item: timing_order.get(item["availability_timing"], 2))
    risk_source = max(sources, key=lambda item: risk_order.get(item["leakage_risk"], 2))
    return _entry(
        name, category="market_context", timing=timing_source["availability_timing"],
        risk=risk_source["leakage_risk"], basis="code_verified" if all(item["source_basis"] == "code_verified" for item in sources) else "unknown",
        source=None, depends=[item["field_name"] for item in sources],
        exit_price=any(item["depends_on_exit_price"] for item in sources),
        pnl=any(item["depends_on_pnl"] for item in sources),
        future_bars=any(item["depends_on_future_bars"] for item in sources),
        realized=any(item["depends_on_realized_outcome"] for item in sources),
        reason="Maximum timing and leakage risk inherited from source fields.",
    ) | {"source_fields": [item["field_name"] for item in sources]}


def is_verified_pretrade_low(entry: dict[str, Any]) -> bool:
    return entry.get("availability_timing") == "pre_trade" and entry.get("leakage_risk") == "low"


def strict_exclusion_reason(entry: dict[str, Any]) -> str:
    return (
        "requires availability_timing=pre_trade and leakage_risk=low; "
        f"got availability_timing={entry.get('availability_timing')} "
        f"and leakage_risk={entry.get('leakage_risk')}"
    )


def build_feature_timing_provenance_report(records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inputs = records or []
    registry = copy.deepcopy(PROVENANCE_REGISTRY)
    normalized = {
        name: combine_source_provenance(name, [get_field_provenance(field) for field in fields])
        for name, fields in NORMALIZED_FIELD_SOURCES.items()
    }
    unknown = [name for name, value in registry.items() if value["availability_timing"] == "unknown"]
    low_pretrade = [name for name, value in registry.items() if is_verified_pretrade_low(value)]
    posttrade = [name for name, value in registry.items() if value["leakage_risk"] == "high"]
    fields_seen = sorted({key for record in inputs for key in record})
    return {
        "schema_version": "aqtf_edge_v2_feature_timing_provenance.v1",
        "diagnostic_only": True,
        "inputs_analyzed": len(inputs),
        "total_fields_seen": len(fields_seen),
        "fields_seen": fields_seen,
        "registry": registry,
        "normalized_field_provenance": normalized,
        "known_fields": [name for name, value in registry.items() if value["source_basis"] == "code_verified"],
        "unknown_fields": unknown,
        "low_leakage_pre_trade_fields": low_pretrade,
        "unknown_timing_fields": unknown,
        "post_trade_or_high_leakage_fields": posttrade,
        "candidate_discriminator_provenance": {
            name: get_field_provenance(name)
            for name in ("risk_points", "candle_range", "reward_points")
        } | {
            name: normalized[name]
            for name in NORMALIZED_FIELD_SOURCES
        },
        "warnings": ["unknown_timing_fields_cannot_support_strategy_rules"] if unknown else [],
    }


def analyze_feature_timing_provenance_journals(journal_paths: list[str | Path]) -> dict[str, Any]:
    records = []
    failures = []
    for source in journal_paths:
        try:
            records.extend(load_journal_records(source))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append({"journal_path": str(source), "reason": str(exc)})
    report = build_feature_timing_provenance_report(records)
    report["input_paths"] = [str(path) for path in journal_paths]
    report["failed_inputs"] = failures
    return report


def discover_batch_journals(batch_dirs: list[str | Path]) -> list[Path]:
    paths: set[Path] = set()
    for item in batch_dirs:
        root = Path(item)
        if root.is_file() and root.name == "trades.jsonl":
            paths.add(root)
        elif root.exists():
            paths.update(root.rglob("trades.jsonl"))
    return sorted(paths, key=lambda path: str(path).lower())


def write_feature_timing_provenance_report(report: dict[str, Any], output: str | Path) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def _outcome_provenance(field: str) -> dict[str, Any]:
    return _entry(
        field, category="outcome", timing="post_trade", risk="high", basis="naming_convention", source=None,
        exit_price=field in {"exit_price", "exit_time", "timestamp_close", "duration", "bars_held"},
        pnl=field in {"outcome", "r_multiple"}, realized=True,
        reason="Outcome-derived field is only known after trade completion.",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Write Edge V2 feature timing provenance JSON")
    parser.add_argument("--journal", action="append", type=Path, default=[])
    parser.add_argument("--batch-dir", action="append", type=Path, default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    journals = [*args.journal, *discover_batch_journals(args.batch_dir)]
    report = analyze_feature_timing_provenance_journals(journals)
    print(write_feature_timing_provenance_report(report, args.out))


if __name__ == "__main__":
    main()
