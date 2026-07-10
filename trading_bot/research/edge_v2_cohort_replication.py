"""Diagnostic-only replication of fixed Edge V2 cohort definitions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from trading_bot.research.edge_v2_cohort_report import (
    cohort_metrics,
    select_fixed_cohort_records,
    select_fixed_pair_records,
)
from trading_bot.research.edge_v2_feature_separation import load_journal_records


DEFAULT_FIXED_COHORTS = [
    {"feature": "lower_quartile_closes", "bucket": "bottom_25"},
]
OPTIONAL_FIXED_PAIR = {
    "left_feature": "pressure_score",
    "left_bucket": "top_25",
    "right_feature": "lower_quartile_closes",
    "right_bucket": "bottom_25",
}


def replicate_fixed_cohorts(
    journal_paths: list[str | Path], *, include_optional_pair: bool = False
) -> dict[str, Any]:
    """Replicate only predefined cohorts across existing journals."""
    fixed_cohorts = list(DEFAULT_FIXED_COHORTS)
    if include_optional_pair:
        fixed_cohorts.append({"pair": OPTIONAL_FIXED_PAIR})
    per_run_results = []
    warnings = []
    for source in journal_paths:
        path = Path(source)
        try:
            records = load_journal_records(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            per_run_results.append(
                {
                    "journal_path": str(path),
                    "status": "invalid_or_missing",
                    "reason": str(exc),
                    "cohorts": {},
                }
            )
            warnings.append(f"{path}: invalid_or_missing_journal")
            continue
        run = _run_metadata(records, path)
        run["status"] = "success"
        run["cohorts"] = {}
        for definition in fixed_cohorts:
            name, selected = _select_fixed_records(records, definition)
            metrics = cohort_metrics(selected)
            run["cohorts"][name] = {
                "cohort_trade_count": metrics["trade_count"],
                **metrics,
            }
            if metrics["sample_size_warning"]:
                warnings.append(f"{path}: {name}: insufficient_sample")
        per_run_results.append(run)
    aggregate_results = _aggregate_results(per_run_results, fixed_cohorts)
    return {
        "schema_version": "aqtf_edge_v2_fixed_cohort_replication.v1",
        "diagnostic_only": True,
        "fixed_cohorts_tested": fixed_cohorts,
        "per_run_results": per_run_results,
        "aggregate_results": aggregate_results,
        "sample_size_warnings": warnings,
        "consistency_summary": {
            name: {
                "direction_consistency": result["direction_consistency"],
                "stability_flag": result["stability_flag"],
            }
            for name, result in aggregate_results.items()
        },
        "disclaimer": (
            "Diagnostic only; fixed cohorts are not optimized and do not establish "
            "profitability, an edge, or a strategy rule."
        ),
    }


def discover_batch_journals(batch_outputs: list[str | Path]) -> list[Path]:
    """Return deterministic trade-journal paths below existing batch output roots."""
    paths = set()
    for root in batch_outputs:
        source = Path(root)
        if source.is_file() and source.name == "trades.jsonl":
            paths.add(source)
        elif source.exists():
            paths.update(source.rglob("trades.jsonl"))
    return sorted(paths, key=lambda path: str(path).lower())


def write_replication_report(report: dict[str, Any], output: str | Path) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def _run_metadata(records: list[dict[str, Any]], path: Path) -> dict[str, Any]:
    first = records[0] if records else {}
    timestamps = sorted(
        str(record[key])
        for record in records
        for key in (
            "timestamp_open",
            "entry_time",
            "open_time",
            "timestamp",
            "time",
        )
        if record.get(key) is not None
    )
    return {
        "journal_path": str(path),
        "symbol": first.get("symbol"),
        "timeframe": first.get("timeframe"),
        "date_range": {
            "start": timestamps[0] if timestamps else None,
            "end": timestamps[-1] if timestamps else None,
        },
        "total_trades": len(records),
    }


def _select_fixed_records(
    records: list[dict[str, Any]], definition: dict[str, Any]
) -> tuple[str, list[dict[str, Any]]]:
    if "pair" not in definition:
        feature = definition["feature"]
        bucket = definition["bucket"]
        return f"{feature}_{bucket}", select_fixed_cohort_records(records, feature, bucket)
    pair = definition["pair"]
    name = (
        f"{pair['left_feature']}_{pair['left_bucket']}__"
        f"{pair['right_feature']}_{pair['right_bucket']}"
    )
    return name, select_fixed_pair_records(records, **pair)


def _aggregate_results(
    runs: list[dict[str, Any]], fixed_cohorts: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    aggregates = {}
    for definition in fixed_cohorts:
        name, _ = _select_fixed_records([], definition)
        metrics = [
            run["cohorts"][name]
            for run in runs
            if run["status"] == "success" and name in run["cohorts"]
        ]
        aggregates[name] = _aggregate_cohort_metrics(metrics)
    return aggregates


def _aggregate_cohort_metrics(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    total_trades = sum(metric["cohort_trade_count"] for metric in metrics)
    gross_profit = sum(metric["gross_profit"] for metric in metrics)
    gross_loss = sum(metric["gross_loss"] for metric in metrics)
    winners = sum(metric["winner_count"] for metric in metrics)
    losers = sum(metric["loser_count"] for metric in metrics)
    expectancy = (
        sum(metric["expectancy"] * metric["cohort_trade_count"] for metric in metrics)
        / total_trades
        if total_trades
        else None
    )
    profit_factor = gross_profit / gross_loss if gross_loss else None
    positive = sum(metric["expectancy"] > 0 for metric in metrics)
    negative = sum(metric["expectancy"] < 0 for metric in metrics)
    sufficient = sum(not metric["sample_size_warning"] for metric in metrics)
    direction_consistency = not (positive and negative)
    return {
        "runs_available": len(metrics),
        "runs_positive_expectancy": positive,
        "runs_pf_above_1": sum(
            metric["profit_factor"] is not None and metric["profit_factor"] > 1
            for metric in metrics
        ),
        "runs_with_sufficient_sample": sufficient,
        "direction_consistency": direction_consistency,
        "weighted_average_expectancy": expectancy,
        "weighted_average_profit_factor": profit_factor,
        "total_cohort_trades": total_trades,
        "total_cohort_winners": winners,
        "total_cohort_losers": losers,
        "stability_flag": _stability_flag(
            len(metrics), positive, negative, sufficient
        ),
    }


def _stability_flag(
    runs: int, positive: int, negative: int, sufficient: int
) -> str:
    if runs < 2:
        return "insufficient_data"
    if positive == 0:
        return "not_replicated"
    if negative:
        return "mixed"
    if sufficient < 2:
        return "weak_replicated"
    return "promising_but_unconfirmed"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replicate diagnostic-only fixed Edge V2 cohorts"
    )
    parser.add_argument("--journal", action="append", type=Path, default=[])
    parser.add_argument("--batch-output", action="append", type=Path, default=[])
    parser.add_argument("--include-optional-pair", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    journals = [*args.journal, *discover_batch_journals(args.batch_output)]
    if not journals:
        parser.error("provide at least one --journal or --batch-output")
    report = replicate_fixed_cohorts(
        journals, include_optional_pair=args.include_optional_pair
    )
    print(write_replication_report(report, args.out))


if __name__ == "__main__":
    main()
