"""Read-only audit of setup generation and completed-trade excursions."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from trading_bot.data.mt5_history import TIMEFRAME_SECONDS
from trading_bot.research.edge_v4_setup_failure_metrics import (
    ambiguity_summary,
    data_quality,
    early_movement_by_bar,
    exit_reason_excursions,
    loss_streaks,
    mfe_mae_summary,
    outcome_distribution,
    stop_efficiency,
    take_profit_efficiency,
)
from trading_bot.signals.liquidity_sweep import LiquiditySweepDetector


REQUIRED_CANDLE_COLUMNS = {
    "timestamp", "open", "high", "low", "close", "volume"
}
EXCURSION_FIELDS = (
    "mfe",
    "mae",
    "mfe_r",
    "mae_r",
    "bars_to_mfe",
    "bars_to_mae",
    "timestamp_mfe",
    "timestamp_mae",
    "min_distance_to_tp",
    "min_distance_to_sl",
    "max_favorable_before_close",
    "max_adverse_before_close",
    "tp_touched",
    "sl_touched",
    "ambiguous_both_levels",
)


def load_audit_candles(source: Path | list[dict[str, Any]]) -> pd.DataFrame:
    """Load UTC-normalized, chronological candles used only by this audit."""
    candles = pd.DataFrame(source) if isinstance(source, list) else pd.read_csv(source)
    missing = REQUIRED_CANDLE_COLUMNS.difference(candles.columns)
    if missing:
        raise ValueError(f"missing_candle_columns: {', '.join(sorted(missing))}")
    candles = candles.copy()
    candles["time"] = pd.to_datetime(candles["timestamp"], utc=True, errors="raise")
    numeric = ["open", "high", "low", "close", "volume"]
    numeric.extend(
        column for column in ("spread_points", "spread_price", "point_size", "tick_size")
        if column in candles.columns
    )
    candles[numeric] = candles[numeric].apply(pd.to_numeric, errors="raise")
    candles["tick_volume"] = candles["volume"]
    if candles["time"].duplicated().any():
        raise ValueError("duplicate_candle_timestamps")
    return candles.sort_values("time").reset_index(drop=True)


def build_detector_funnel(
    candles: pd.DataFrame,
    *,
    detector: LiquiditySweepDetector | None = None,
    warmup_bars: int = 21,
) -> dict[str, int]:
    """Replay existing detector predicates without submitting or changing a setup."""
    counters, _ = _detector_funnel_events(candles, detector=detector, warmup_bars=warmup_bars)
    keys = (
        "eligible_bars",
        "high_sweep_observations",
        "low_sweep_observations",
        "high_sweeps_not_reclaimed",
        "low_sweeps_not_reclaimed",
        "high_reclaims_failing_vwap",
        "low_reclaims_failing_vwap",
        "generated_setups",
        "generated_long_setups",
        "generated_short_setups",
    )
    return {key: int(counters[key]) for key in keys}


def _detector_funnel_events(
    candles: pd.DataFrame,
    *,
    detector: LiquiditySweepDetector | None = None,
    warmup_bars: int = 21,
) -> tuple[Counter, list[str]]:
    active_detector = detector or LiquiditySweepDetector()
    counters = Counter()
    candidate_timestamps = []
    for index in range(warmup_bars - 1, max(len(candles) - 1, 0)):
        history = candles.iloc[: index + 1]
        report = active_detector.detect_signals(history)
        liquidity = report.get("liquidity", {})
        if not liquidity:
            continue
        counters["eligible_bars"] += 1
        current = history.iloc[-1]
        high_sweep = bool(liquidity.get("high_sweep"))
        low_sweep = bool(liquidity.get("low_sweep"))
        recent_high = float(liquidity["recent_high"])
        recent_low = float(liquidity["recent_low"])
        vwap = float(report["vwap"]["value"])
        close = float(current["close"])
        if high_sweep:
            counters["high_sweep_observations"] += 1
            if close >= recent_high:
                counters["high_sweeps_not_reclaimed"] += 1
            elif close <= vwap:
                counters["high_reclaims_failing_vwap"] += 1
        if low_sweep:
            counters["low_sweep_observations"] += 1
            if close <= recent_low:
                counters["low_sweeps_not_reclaimed"] += 1
            elif close >= vwap:
                counters["low_reclaims_failing_vwap"] += 1
        setup = report.get("setup")
        if setup:
            counters["generated_setups"] += 1
            candidate_timestamps.append(current["time"].isoformat())
            counters[
                "generated_long_setups"
                if setup.get("type") == "LONG"
                else "generated_short_setups"
            ] += 1
    return counters, candidate_timestamps


def reconstruct_trade_excursion(
    trade: dict[str, Any], candles: pd.DataFrame
) -> dict[str, Any]:
    """Calculate OHLC excursion bounds, retaining indeterminate intrabar order."""
    base = _excursion_base(trade)
    try:
        opened = pd.to_datetime(trade["timestamp_open"], utc=True, errors="raise")
        closed = pd.to_datetime(trade["timestamp_close"], utc=True, errors="raise")
        direction = str(trade["direction"])
        entry = float(trade["entry"])
        stop = float(trade["stop_loss"])
        target = float(trade["take_profit"])
        risk = float(trade.get("risk_points", abs(entry - stop)))
    except (KeyError, TypeError, ValueError):
        return _unavailable(base, "invalid_trade_record")
    if closed < opened or direction not in {"LONG", "SHORT"} or risk <= 0:
        return _unavailable(base, "invalid_trade_record")
    timeframe = str(trade.get("timeframe", "")).upper()
    expected_seconds = TIMEFRAME_SECONDS.get(timeframe)
    if expected_seconds is None:
        return _unavailable(base, "unsupported_timeframe")
    window = candles.loc[(candles["time"] >= opened) & (candles["time"] <= closed)]
    if (
        window.empty
        or window.iloc[0]["time"] != opened
        or window.iloc[-1]["time"] != closed
    ):
        return _unavailable(base, "trade_timestamps_not_covered")
    deltas = window["time"].diff().dropna().dt.total_seconds()
    if bool((deltas > expected_seconds).any()):
        return _unavailable(base, "gap_in_trade_window")

    highs = window["high"].astype(float).reset_index(drop=True)
    lows = window["low"].astype(float).reset_index(drop=True)
    if direction == "LONG":
        favorable = highs - entry
        adverse = entry - lows
        tp_touched = highs.ge(target)
        sl_touched = lows.le(stop)
        distance_to_tp = (target - highs).clip(lower=0)
        distance_to_sl = (lows - stop).clip(lower=0)
    else:
        favorable = entry - lows
        adverse = highs - entry
        tp_touched = lows.le(target)
        sl_touched = highs.ge(stop)
        distance_to_tp = (lows - target).clip(lower=0)
        distance_to_sl = (stop - highs).clip(lower=0)
    mfe_index = int(favorable.idxmax())
    mae_index = int(adverse.idxmax())
    ambiguous = bool((tp_touched & sl_touched).any())
    base.update(
        {
            "mfe": max(0.0, float(favorable.iloc[mfe_index])),
            "mae": max(0.0, float(adverse.iloc[mae_index])),
            "bars_to_mfe": mfe_index,
            "bars_to_mae": mae_index,
            "timestamp_mfe": window.iloc[mfe_index]["time"].isoformat(),
            "timestamp_mae": window.iloc[mae_index]["time"].isoformat(),
            "min_distance_to_tp": float(distance_to_tp.min()),
            "min_distance_to_sl": float(distance_to_sl.min()),
            "tp_touched": bool(tp_touched.any()),
            "sl_touched": bool(sl_touched.any()),
            "ambiguous_both_levels": ambiguous,
            "data_quality_status": "complete",
            "data_quality_reason": None,
        }
    )
    base["mfe_r"] = base["mfe"] / risk
    base["mae_r"] = base["mae"] / risk
    base["max_favorable_before_close"] = base["mfe"]
    base["max_adverse_before_close"] = base["mae"]
    base["_favorable_path_r"] = [
        max(0.0, float(favorable.iloc[: position + 1].max())) / risk
        for position in range(len(window))
    ]
    base["_adverse_path_r"] = [
        max(0.0, float(adverse.iloc[: position + 1].max())) / risk
        for position in range(len(window))
    ]
    return base


def run_setup_failure_audit(
    batch_dir: str | Path,
    *,
    out: str | Path | None = None,
    detail_out: str | Path | None = None,
) -> dict[str, Any]:
    """Audit a paginated research batch without accessing MT5 or execution code."""
    root = Path(batch_dir)
    manifests = sorted(root.rglob("mt5_history_manifest.json"))
    if not manifests:
        raise ValueError("no_paginated_history_manifests")
    runs = []
    all_excursions: list[dict[str, Any]] = []
    canonical_ids: set[str] = set()
    for manifest_path in manifests:
        run_dir = manifest_path.parent
        manifest = _read_json(manifest_path)
        csv_path = run_dir / "mt5_history.csv"
        _validate_manifest(manifest, csv_path)
        candles = load_audit_candles(csv_path)
        _validate_manifest_range(manifest, candles)
        trades = _read_jsonl(run_dir / "journal" / "trades.jsonl")
        setups = _read_jsonl(run_dir / "journal" / "setups.jsonl")
        blocked = _read_jsonl(run_dir / "journal" / "blocked_setups.jsonl")
        post_cost_blocks = _read_jsonl(run_dir / "journal" / "post_cost_blocks.jsonl")
        excursions = [
            reconstruct_trade_excursion(trade, candles)
            if _trade_matches_run(trade, manifest)
            else _unavailable(_excursion_base(trade), "trade_segment_mismatch")
            for trade in trades
        ]
        all_excursions.extend(excursions)
        for excursion in excursions:
            if excursion["trade_id"] in canonical_ids:
                raise ValueError(f"canonical_trade_id_collision: {excursion['trade_id']}")
            canonical_ids.add(excursion["trade_id"])
        runs.append(
            {
                "run_id": run_dir.name,
                "symbol": manifest.get("symbol"),
                "timeframe": manifest.get("timeframe"),
                "candle_count": len(candles),
                "trade_count": len(trades),
                "funnel": _run_funnel(candles, setups, blocked, post_cost_blocks, trades),
                "outcome_distribution": outcome_distribution(excursions),
                "loss_streaks": loss_streaks(excursions),
                "early_movement_by_bar": early_movement_by_bar(excursions),
                "exit_reason_excursions": exit_reason_excursions(excursions),
                "trade_excursions": excursions,
            }
        )
    early_movement = early_movement_by_bar(all_excursions)
    for excursion in all_excursions:
        excursion.pop("_favorable_path_r", None)
        excursion.pop("_adverse_path_r", None)
    report = {
        "schema_version": "aqtf_edge_v4_setup_failure_audit.v2",
        "metadata": {
            "diagnostic_only": True,
            "data_provider": "batch_artifacts",
            "broker_api_called": False,
            "intrabar_order": "not_inferred; historical backtest convention is stop_first",
        },
        "batch_summary": {
            "run_count": len(runs),
            "total_candles": sum(run["candle_count"] for run in runs),
            "total_trades": len(all_excursions),
        },
        "runs": runs,
        "funnel": _aggregate_funnel(runs),
        "outcome_distribution": outcome_distribution(all_excursions),
        "mfe_mae_summary": mfe_mae_summary(all_excursions),
        "early_movement_by_bar": early_movement,
        "loss_streaks": loss_streaks(all_excursions),
        "exit_reason_excursions": exit_reason_excursions(all_excursions),
        "stop_efficiency": stop_efficiency(all_excursions),
        "take_profit_efficiency": take_profit_efficiency(all_excursions),
        "ambiguity_summary": ambiguity_summary(all_excursions),
        "data_quality": data_quality(all_excursions),
        "interpretation_flags": [
            "diagnostic_only",
            "intrabar_order_not_observable_from_ohlc",
            "no_parameter_optimization",
        ],
        "conclusion": {
            "trading_rule_generated": False,
            "edge_confirmation": False,
        },
    }
    if out is not None:
        _write_json(report, Path(out))
    if detail_out is not None:
        _write_jsonl(all_excursions, Path(detail_out))
    return report


def _excursion_base(trade: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "trade_id", "symbol", "timeframe", "direction", "timestamp_open",
        "timestamp_close", "entry", "stop_loss", "take_profit", "risk_points",
        "reward_points", "pnl", "r_multiple", "outcome", "exit_reason", "bars_held",
    )
    base = {field: trade.get(field) for field in fields}
    base["source_trade_id"] = base["trade_id"]
    base["trade_id"] = canonical_trade_id(trade)
    base.update({field: None for field in EXCURSION_FIELDS})
    base["data_quality_status"] = "data_unavailable"
    base["data_quality_reason"] = None
    return base


def _unavailable(base: dict[str, Any], reason: str) -> dict[str, Any]:
    base["data_quality_reason"] = reason
    return base


def _validate_manifest(manifest: dict[str, Any], csv_path: Path) -> None:
    if manifest.get("status") != "complete":
        raise ValueError("manifest_not_complete")
    if not csv_path.exists():
        raise ValueError("manifest_csv_missing")
    expected_hash = manifest.get("csv_sha256")
    actual_hash = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    if not isinstance(expected_hash, str) or expected_hash != actual_hash:
        raise ValueError("manifest_csv_hash_mismatch")
    if int(manifest.get("conflicting_duplicates", 0)) != 0:
        raise ValueError("manifest_conflicting_duplicates")


def _validate_manifest_range(manifest: dict[str, Any], candles: pd.DataFrame) -> None:
    if candles.empty:
        raise ValueError("manifest_empty_csv")
    try:
        obtained_start = pd.to_datetime(manifest["obtained_start"], utc=True, errors="raise")
        obtained_end = pd.to_datetime(manifest["obtained_end"], utc=True, errors="raise")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("manifest_obtained_range_invalid") from exc
    if candles.iloc[0]["time"] != obtained_start or candles.iloc[-1]["time"] != obtained_end:
        raise ValueError("manifest_obtained_range_mismatch")
    if int(manifest.get("filtered_bars", len(candles))) != len(candles):
        raise ValueError("manifest_filtered_bar_count_mismatch")


def _trade_matches_run(trade: dict[str, Any], manifest: dict[str, Any]) -> bool:
    return (
        str(trade.get("symbol", "")) == str(manifest.get("symbol", ""))
        and str(trade.get("timeframe", "")).upper()
        == str(manifest.get("timeframe", "")).upper()
    )


def canonical_trade_id(trade: dict[str, Any]) -> str:
    """Create an unambiguous identifier for new and legacy journal records."""
    source = str(trade.get("trade_id", ""))
    symbol = str(trade.get("symbol", ""))
    timeframe = str(trade.get("timeframe", "")).upper()
    timestamp = str(trade.get("timestamp_open", ""))
    direction = str(trade.get("direction", ""))
    if not all((symbol, timeframe, timestamp, direction)):
        raise ValueError("trade identifier requires symbol, timeframe, timestamp_open, and direction")
    prefix = f"{symbol}-{timeframe}-"
    if source.startswith(prefix):
        return source
    return "legacy::" + "::".join((source, symbol, timeframe, timestamp, direction))


def _run_funnel(
    candles: pd.DataFrame,
    setups: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
    post_cost_blocks: list[dict[str, Any]],
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    detector, candidate_timestamps = _detector_funnel_events(candles)
    exits = Counter(str(trade.get("exit_reason")) for trade in trades)
    reasons = Counter(str(item.get("block_reason")) for item in blocked)
    setup_timestamps = Counter(str(item.get("timestamp")) for item in setups)
    detector_timestamps = Counter(candidate_timestamps)
    suppressed = list((detector_timestamps - setup_timestamps).elements())
    journal_only = list((setup_timestamps - detector_timestamps).elements())
    legacy_incomplete_journal = not setups and not blocked and not post_cost_blocks and bool(trades)
    if journal_only:
        raise ValueError("journal setup does not match detector candidate")
    suppressed_active = _suppressed_while_position_open(suppressed, trades)
    if not legacy_incomplete_journal and suppressed_active != len(suppressed):
        raise ValueError("detector candidate missing without an active position")
    accepted = sum(bool(item.get("accepted")) for item in setups)
    if not legacy_incomplete_journal and len(setups) != len(blocked) + accepted:
        raise ValueError("runner evaluable setup funnel does not reconcile")
    if not legacy_incomplete_journal and accepted != len(post_cost_blocks) + len(trades):
        raise ValueError("accepted setup funnel does not reconcile to post-cost blocks and opened trades")
    return {
        **{key: int(value) for key, value in detector.items()},
        "detector_candidates_total": len(candidate_timestamps),
        "candidates_suppressed_while_position_open": len(suppressed),
        "runner_evaluable_setups": len(setups),
        "journal_setups_generated": len(setups),
        "journal_setups_blocked": len(blocked),
        "journal_setups_accepted": accepted,
        "post_cost_geometry_blocks": len(post_cost_blocks),
        "accepted_not_opened": 0 if legacy_incomplete_journal else accepted - len(trades),
        "funnel_reconciliation_status": "legacy_incomplete_journal" if legacy_incomplete_journal else "complete",
        "blocked_by_reason": dict(sorted(reasons.items())),
        "trades_opened": len(trades),
        "trades_closed_stop_loss": exits["stop_loss"],
        "trades_closed_take_profit": exits["take_profit"],
        "trades_closed_end_of_data": exits["end_of_data"],
    }


def _suppressed_while_position_open(candidate_timestamps: list[str], trades: list[dict[str, Any]]) -> int:
    intervals = [
        (
            pd.to_datetime(trade["timestamp_open"], utc=True, errors="raise"),
            pd.to_datetime(trade["timestamp_close"], utc=True, errors="raise"),
        )
        for trade in trades
    ]
    return sum(
        any(opened <= pd.to_datetime(timestamp, utc=True, errors="raise") < closed for opened, closed in intervals)
        for timestamp in candidate_timestamps
    )


def _aggregate_funnel(runs: list[dict[str, Any]]) -> dict[str, Any]:
    totals = Counter()
    reasons = Counter()
    for run in runs:
        for key, value in run["funnel"].items():
            if key == "blocked_by_reason":
                reasons.update(value)
            elif isinstance(value, int):
                totals[key] += value
    result = {key: int(value) for key, value in sorted(totals.items())}
    result["blocked_by_reason"] = dict(sorted(reasons.items()))
    return result


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_manifest_json") from exc
    if not isinstance(value, dict):
        raise ValueError("invalid_manifest_json")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"invalid_jsonl_record: {path}")
            records.append(value)
    return records


def _write_json(value: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Audit setup failures from paginated research artifacts")
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--detail-out", type=Path, required=True)
    args = parser.parse_args(argv)
    run_setup_failure_audit(args.batch_dir, out=args.out, detail_out=args.detail_out)
    print(args.out)


if __name__ == "__main__":
    main()
