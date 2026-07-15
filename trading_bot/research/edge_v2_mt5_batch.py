from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Any

from trading_bot.data.mt5_history import MT5HistoryError
from trading_bot.research.edge_v2_mt5_pipeline import run_edge_v2_mt5_research


MIN_TRADES = 50
MIN_WINNERS = 20
MIN_LOSERS = 20


def load_batch_plan(path: str | Path) -> list[dict[str, str]]:
    parsed = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        raise ValueError("batch plan must be a JSON array")
    required = {"symbol", "timeframe", "start", "end"}
    for item in parsed:
        if not isinstance(item, dict) or required.difference(item):
            raise ValueError("each batch run requires symbol, timeframe, start, and end")
    return [{key: str(item[key]) for key in required} for item in parsed]


def run_edge_v2_mt5_batch(
    plan: list[dict[str, str]],
    *,
    out_dir: str | Path,
    strict: bool = False,
    history_mode: str = "range",
    page_size: int = 5_000,
    include_current_bar: bool = False,
    require_complete: bool = True,
) -> dict[str, Any]:
    root = Path(out_dir)
    successful: list[dict[str, Any]] = []
    per_run = []
    for index, item in enumerate(plan, start=1):
        run_id = f"run_{index:03d}_{item['symbol'].lower()}_{item['timeframe'].lower()}"
        try:
            result = run_edge_v2_mt5_research(
                **item,
                out_dir=root / run_id,
                history_mode=history_mode,
                page_size=page_size,
                include_current_bar=include_current_bar,
                require_complete=require_complete,
            )
            report = result["report"]
            successful.append({"run_id": run_id, "features": report["features"]})
            per_run.append({"run_id": run_id, "status": "success", **item, **_counts(report)})
        except MT5HistoryError as exc:
            per_run.append({"run_id": run_id, "status": "environment_blocked", "reason": str(exc), **item})
            if strict:
                raise

    aggregate = aggregate_feature_summaries(successful)
    summary = {
        "schema_version": "aqtf_edge_v2_mt5_batch.v1",
        "diagnostic_only": True,
        "data_provider": "mt5",
        "submit_allowed": False,
        "broker_api_called": False,
        "total_configured_runs": len(plan),
        "successful_runs": len(successful),
        "failed_or_blocked_runs": len(plan) - len(successful),
        "total_candles": sum(item.get("candle_count", 0) for item in per_run),
        "total_trades": sum(item.get("trade_count", 0) for item in per_run),
        "total_winners": sum(item.get("winner_count", 0) for item in per_run),
        "total_losers": sum(item.get("loser_count", 0) for item in per_run),
        "total_breakeven": sum(item.get("breakeven_count", 0) for item in per_run),
        "per_run_summary": per_run,
        "per_feature_aggregate_summary": aggregate,
        "strongest_features_by_abs_effect_size": _rank_features(aggregate, reverse=True),
        "most_consistent_features": _consistent_features(aggregate),
        "weakest_features": _rank_features(aggregate, reverse=False),
        "unstable_features": [key for key, value in aggregate.items() if value["stability_flag"] == "unstable"],
        "warnings": _warnings(per_run, aggregate),
        "disclaimer": "Diagnostic only; no profitability or strategy-change claim is made.",
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "edge_v2_batch_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def aggregate_feature_summaries(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    values: dict[str, list[tuple[str, float, int]]] = {}
    for run in runs:
        for feature, result in run["features"].items():
            effect = result.get("simple_effect_size")
            if effect is not None:
                values.setdefault(feature, []).append((run["run_id"], float(effect), int(result.get("sample_count", 0))))
    aggregate = {}
    for feature, entries in values.items():
        effects = [entry[1] for entry in entries]
        weights = [max(entry[2], 1) for entry in entries]
        positive = sum(effect > 0 for effect in effects)
        negative = sum(effect < 0 for effect in effects)
        consistent = not (positive and negative)
        weighted = sum(effect * weight for effect, weight in zip(effects, weights)) / sum(weights)
        strongest = max(entries, key=lambda entry: abs(entry[1]))
        weakest = min(entries, key=lambda entry: abs(entry[1]))
        aggregate[feature] = {
            "runs_available": len(entries),
            "total_sample_count": sum(weights),
            "weighted_average_effect_size": round(weighted, 6),
            "median_effect_size_across_runs": round(median(effects), 6),
            "max_abs_effect_size": round(max(abs(effect) for effect in effects), 6),
            "min_abs_effect_size": round(min(abs(effect) for effect in effects), 6),
            "direction_consistency": consistent,
            "positive_direction_count": positive,
            "negative_direction_count": negative,
            "no_clear_direction_count": sum(effect == 0 for effect in effects),
            "strongest_run": strongest[0],
            "weakest_run": weakest[0],
            "stability_flag": _stability(entries, consistent, weighted),
        }
    return aggregate


def _stability(entries: list[tuple[str, float, int]], consistent: bool, weighted: float) -> str:
    if len(entries) < 2:
        return "insufficient_data"
    if not consistent:
        return "unstable"
    magnitude = abs(weighted)
    if magnitude >= 0.8:
        return "strong_consistent"
    if magnitude >= 0.5:
        return "moderate_consistent"
    return "weak_but_consistent"


def _counts(report: dict[str, Any]) -> dict[str, int]:
    return {key: int(report.get(key, 0)) for key in ("candle_count", "trade_count", "winner_count", "loser_count", "breakeven_count")}


def _rank_features(aggregate: dict[str, dict[str, Any]], *, reverse: bool) -> list[str]:
    return [key for key, _ in sorted(aggregate.items(), key=lambda item: abs(item[1]["weighted_average_effect_size"]), reverse=reverse)]


def _consistent_features(aggregate: dict[str, dict[str, Any]]) -> list[str]:
    return [key for key, value in aggregate.items() if value["stability_flag"] not in {"insufficient_data", "unstable"}]


def _warnings(runs: list[dict[str, Any]], aggregate: dict[str, dict[str, Any]]) -> list[str]:
    warnings = []
    for run in runs:
        if run.get("status") == "success" and (run["trade_count"] < MIN_TRADES or run["winner_count"] < MIN_WINNERS or run["loser_count"] < MIN_LOSERS):
            warnings.append(f"{run['run_id']}: sample_size_below_default_minimum")
    warnings.extend(f"{feature}: appears_in_only_one_run" for feature, value in aggregate.items() if value["runs_available"] == 1)
    warnings.extend(f"{feature}: direction_flips_between_runs" for feature, value in aggregate.items() if not value["direction_consistency"])
    return warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run diagnostic-only Edge V2 MT5 batch research")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--history-mode", choices=["range", "paginated"], default="range")
    parser.add_argument("--page-size", type=int, default=5_000)
    parser.add_argument("--include-current-bar", action="store_true")
    parser.add_argument("--allow-partial-history", action="store_true")
    args = parser.parse_args()
    run_edge_v2_mt5_batch(
        load_batch_plan(args.plan),
        out_dir=args.out_dir,
        strict=args.strict,
        history_mode=args.history_mode,
        page_size=args.page_size,
        include_current_bar=args.include_current_bar,
        require_complete=not args.allow_partial_history,
    )
    print(args.out_dir / "edge_v2_batch_summary.json")


if __name__ == "__main__":
    main()
