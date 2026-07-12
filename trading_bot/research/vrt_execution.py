"""Append-only, non-trading execution of the frozen VRT research contract."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from trading_bot.research import volatility_regime_transition as detector


STRICT_PREDICTORS = detector.STRICT_PREDICTORS


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _duration(timeframe: str) -> int:
    return {"M5": 300, "M15": 900, "H1": 3600}[timeframe]


def _tr(history: Sequence[Mapping[str, Any]]) -> list[float]:
    return [max(b["high_bid"] - b["low_bid"], abs(b["high_bid"] - a["close_bid"]), abs(b["low_bid"] - a["close_bid"])) for a, b in zip(history, history[1:])]


def _atr(history: Sequence[Mapping[str, Any]], period: int) -> float | None:
    values = _tr(history)
    if len(values) < period:
        return None
    value = sum(values[:period]) / period
    for current in values[period:]:
        value = ((period - 1) * value + current) / period
    return value


def _feature_row(history: Sequence[Mapping[str, Any]]) -> dict[str, float] | None:
    if len(history) < 64:
        return None
    fast, slow = _atr(history, 14), _atr(history, 56)
    if fast is None or slow is None or slow <= 0:
        return None
    ratio = fast / slow
    ranges = [row["high_bid"] - row["low_bid"] for row in history]
    if len(ranges) < 56 or len(history) < 21:
        return None
    prior_history = history[:-8]
    prior_fast, prior_slow = _atr(prior_history, 14), _atr(prior_history, 56)
    if prior_fast is None or prior_slow is None or prior_slow <= 0:
        return None
    closes = [row["close_bid"] for row in history]
    denominator = sum(abs(closes[i] - closes[i - 1]) for i in range(len(closes) - 19, len(closes)))
    if denominator <= 0:
        return None
    return {
        "atr_14_points": fast, "atr_56_points": slow, "atr_ratio_14_56": ratio,
        "atr_ratio_change_8": ratio - prior_fast / prior_slow,
        "mean_range_8_points": sum(ranges[-8:]) / 8,
        "mean_range_56_points": sum(ranges[-56:]) / 56,
        "range_ratio_8_56": (sum(ranges[-8:]) / 8) / (sum(ranges[-56:]) / 56),
        "efficiency_20": abs(closes[-1] - closes[-21]) / denominator,
    }


def _trade(event: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], features: Mapping[str, float]) -> dict[str, Any]:
    index = int(event["source_index"])
    if event["direction"] == "none":
        return {**event, "terminal_category": "no_direction"}
    if index + 1 >= len(rows):
        return {**event, "terminal_category": "data_unavailable"}
    entry_bar = rows[index + 1]
    spread = entry_bar["spread_points"] * entry_bar["point_size"]
    slip = 0.25 * spread
    direction = event["direction"]
    entry = entry_bar["open_bid"] + spread + slip if direction == "long" else entry_bar["open_bid"] - slip
    risk = 1.5 * features["atr_14_points"]
    if not math.isfinite(risk) or risk <= 0:
        return {**event, "terminal_category": "excluded_post_cost_geometry"}
    stop, target = (entry - risk, entry + 2 * risk) if direction == "long" else (entry + risk, entry - 2 * risk)
    terminal, exit_bar, gross = "data_unavailable", None, None
    for row in rows[index + 1:min(index + 49, len(rows))]:
        if direction == "long":
            if row["low_bid"] <= stop:
                terminal, exit_bar, gross = "sl", row, stop
                break
            if row["high_bid"] >= target:
                terminal, exit_bar, gross = "tp", row, target
                break
        else:
            if row["high_bid"] + spread >= stop:
                terminal, exit_bar, gross = "sl", row, stop
                break
            if row["low_bid"] + spread <= target:
                terminal, exit_bar, gross = "tp", row, target
                break
    if exit_bar is None and index + 48 < len(rows):
        exit_bar, terminal = rows[index + 48], "time_exit_48"
        gross = exit_bar["close_bid"]
    if exit_bar is None or gross is None:
        return {**event, "terminal_category": terminal}
    effective_exit = gross - slip if direction == "long" else gross + spread + slip
    pnl = (effective_exit - entry) if direction == "long" else (entry - effective_exit)
    return {
        **event, "terminal_category": terminal, "entry_timestamp_utc": _timestamp(entry_bar["timestamp_utc"]).isoformat().replace("+00:00", "Z"),
        "exit_timestamp_utc": _timestamp(exit_bar["timestamp_utc"]).isoformat().replace("+00:00", "Z"),
        "effective_entry": entry, "effective_exit": effective_exit, "spread_price": spread, "slippage_price": slip,
        "risk_price": risk, "stop": stop, "target": target, "pnl": pnl, "r_multiple": pnl / risk,
        "bars_held": int((_timestamp(exit_bar["timestamp_utc"]) - _timestamp(entry_bar["timestamp_utc"])).total_seconds() // _duration(str(event["timeframe"]))) + 1,
    }


def execute_frozen_vrt(
    bars: Sequence[Mapping[str, Any]], *, output_root: str | Path, command: str,
    real_data_observed: bool = False, activation_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new immutable research run; this has no order or broker-write path."""
    run_dir = Path(output_root) / f"vrt-run-{uuid.uuid4()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    ordered = sorted((dict(row) for row in bars), key=lambda row: (row["symbol"], row["timeframe"], _timestamp(row["timestamp_utc"])))
    input_path = _write(run_dir / "input_bars.json", ordered)
    observation = {
        "schema_version": "vrt_first_observation_record.v1", "immutable_run_id": run_dir.name,
        "activation_record": activation_record or {"status": "synthetic_test_only"},
        "activation_record_sha256": None if activation_record is None else hashlib.sha256(json.dumps(activation_record, sort_keys=True).encode()).hexdigest(),
        "input_data_artifact_hashes": {str(input_path.name): _sha(input_path)}, "input_locations": [str(input_path)], "execution_command": command,
        "execution_configuration_hash": None if activation_record is None else activation_record.get("frozen_execution_configuration_sha256"),
        "implementation_commit": None if activation_record is None else activation_record.get("implementation_merge_commit"),
        "preregistration_commit": None if activation_record is None else activation_record.get("preregistration_merge_commit"),
        "provenance_hash": None if activation_record is None else activation_record.get("feature_provenance_sha256"),
        "output_directory": str(run_dir), "expected_report_schemas": ["vrt_run_manifest.v1"],
        "observation_started_at_utc": datetime.now(UTC).isoformat(), "observation_completed_at_utc": None,
        "results_not_inspected_before_record_written": True,
    }
    observation_path = _write(run_dir / "first_observation_record.json", observation)
    generated = detector.generate_events(ordered)
    streams: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in ordered:
        streams[(row["symbol"], row["timeframe"])].append(row)
    features, trades, active_until = [], [], {}
    for event in generated["events"]:
        stream = (event["symbol"], event["timeframe"])
        decision = _timestamp(event["decision_timestamp_utc"])
        source_index = next((index for index, row in enumerate(streams[stream]) if _timestamp(row["timestamp_utc"]) + timedelta(seconds=_duration(event["timeframe"])) == decision), None)
        if source_index is None:
            trades.append({**event, "terminal_category": "invalid_input"})
            continue
        local_event = {**event, "source_index": source_index}
        if source_index <= active_until.get(stream, -1) and event["terminal_category"] == "raw":
            trades.append({**local_event, "terminal_category": "suppressed_overlap"})
            continue
        row_features = _feature_row(streams[stream][:source_index + 1])
        if row_features is None:
            trades.append({**local_event, "terminal_category": "invalid_input"})
            continue
        features.append({"event_id": event["event_id"], **row_features})
        result = _trade(local_event, streams[stream], row_features)
        trades.append(result)
        if result["terminal_category"] in {"tp", "sl", "time_exit_48"}:
            active_until[stream] = source_index + int(result["bars_held"])
    event_path, feature_path, trade_path = _write(run_dir / "events.json", generated), _write(run_dir / "feature_matrix.json", {"predictors": list(STRICT_PREDICTORS), "rows": features}), _write(run_dir / "trade_journal.json", trades)
    terminal = Counter(row["terminal_category"] for row in trades)
    manifest = {
        "schema_version": "vrt_run_manifest.v1", "immutable_run_id": run_dir.name, "command": command,
        "real_data_observed": real_data_observed, "mt5_connected": False, "order_api_called": False,
        "performance_inspected": False, "prospective_validation_started": False,
        "event_funnel": generated["audit"], "trade_funnel": {"trade_count": len(trades), "terminal_category_counts": dict(sorted(terminal.items()))},
        "artifact_hashes": {path.name: _sha(path) for path in (input_path, observation_path, event_path, feature_path, trade_path)},
    }
    manifest_path = _write(run_dir / "run_manifest.json", manifest)
    manifest["artifact_hashes"][manifest_path.name] = _sha(manifest_path)
    _write(run_dir / "run_manifest.json", manifest)
    observation["observation_completed_at_utc"] = datetime.now(UTC).isoformat()
    _write(observation_path, observation)
    return {"output_directory": str(run_dir), "event_funnel": generated["audit"], "trade_funnel": manifest["trade_funnel"], "predictor_matrix": {"predictors": list(STRICT_PREDICTORS)}}
