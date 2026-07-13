"""Append-only, non-trading execution for frozen Trend Continuation After Pullback."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from trading_bot.research import trend_continuation_after_pullback as detector


STRICT_PREDICTORS = detector.STRICT_PREDICTORS
OUTCOME_ONLY_FIELDS = {
    "effective_entry",
    "effective_exit",
    "pnl",
    "r_multiple",
    "mfe",
    "mae",
    "stop",
    "target",
    "future_bars",
    "terminal_category",
}
CONDITIONS = dict(
    zip(STRICT_PREDICTORS, (0.25, 0.03, 0.25, 2.0, 0.25, 0.20, 0.60, 0.40), strict=True)
)
SPLIT = datetime(2026, 5, 1, tzinfo=UTC)


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: Any) -> Path:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    return path


def _duration(timeframe: str) -> int:
    return detector.TIMEFRAME_SECONDS[timeframe]


def _base_rows(rows: Sequence[Mapping[str, Any]]) -> dict[int, dict[str, float] | None]:
    result: dict[int, dict[str, float] | None] = {}
    history: list[Mapping[str, Any]] = []
    closes: list[float] = []
    ranges: list[float] = []
    changes: list[float] = []
    true_ranges: list[float] = []
    fast = slow = atr = None
    slow_values: list[float] = []
    last: datetime | None = None
    for index, row in enumerate(rows):
        timestamp = _timestamp(row["timestamp_utc"])
        if last is not None and timestamp - last > timedelta(
            seconds=3 * _duration(str(row["timeframe"]))
        ):
            history = []
            closes = []
            ranges = []
            changes = []
            true_ranges = []
            fast = slow = atr = None
            slow_values = []
        if history:
            prior = history[-1]
            tr = max(
                row["high_bid"] - row["low_bid"],
                abs(row["high_bid"] - prior["close_bid"]),
                abs(row["low_bid"] - prior["close_bid"]),
            )
            true_ranges.append(tr)
            if len(true_ranges) == 14:
                atr = sum(true_ranges) / 14
            elif len(true_ranges) > 14 and atr is not None:
                atr = (13 * atr + tr) / 14
            changes.append(row["close_bid"] - prior["close_bid"])
        history.append(row)
        closes.append(row["close_bid"])
        ranges.append(row["high_bid"] - row["low_bid"])
        if len(closes) == 20:
            fast = sum(closes) / 20
        elif len(closes) > 20 and fast is not None:
            fast = (2 / 21) * row["close_bid"] + (19 / 21) * fast
        if len(closes) == 50:
            slow = sum(closes) / 50
        elif len(closes) > 50 and slow is not None:
            slow = (2 / 51) * row["close_bid"] + (49 / 51) * slow
        slow_values.append(slow if slow is not None else math.nan)
        last = timestamp
        if (
            len(history) < 60
            or fast is None
            or slow is None
            or atr is None
            or atr <= 0
            or len(slow_values) <= 10
            or len(changes) < 20
        ):
            result[index] = None
            continue
        denominator = sum(abs(change) for change in changes[-20:])
        if denominator <= 0:
            result[index] = None
            continue
        result[index] = {
            "fast": fast,
            "slow": slow,
            "atr": atr,
            "slope": slow - slow_values[-11],
            "close": row["close_bid"],
            "open": row["open_bid"],
            "persistence_long": sum(change > 0 for change in changes[-20:]) / 20,
            "persistence_short": sum(change < 0 for change in changes[-20:]) / 20,
            "efficiency_delta": row["close_bid"] - history[-21]["close_bid"],
            "efficiency_denominator": denominator,
        }
    return result


def _feature_from_base(
    base: Mapping[str, float] | None,
    *,
    direction: str,
    pullback_depth: float,
    pullback_duration: int,
) -> dict[str, float] | None:
    if base is None:
        return None
    sign = 1.0 if direction == "long" else -1.0
    return {
        "trend_separation_atr": abs(base["fast"] - base["slow"]) / base["atr"],
        "slow_ema_slope_atr": sign * base["slope"] / base["atr"],
        "pullback_depth_atr": pullback_depth,
        "pullback_duration_bars": float(pullback_duration),
        "distance_slow_ema_atr": sign * (base["close"] - base["slow"]) / base["atr"],
        "confirmation_body_atr": abs(base["close"] - base["open"]) / base["atr"],
        "trend_persistence_20": base[f"persistence_{direction}"],
        "directional_efficiency_20": sign
        * base["efficiency_delta"]
        / base["efficiency_denominator"],
    }


def feature_row_reference(
    rows: Sequence[Mapping[str, Any]],
    *,
    direction: str,
    pullback_depth: float,
    pullback_duration: int,
) -> dict[str, float] | None:
    """Reference interface for equivalence tests; no execution path calls it per event."""
    return _feature_from_base(
        _base_rows(rows).get(len(rows) - 1),
        direction=direction,
        pullback_depth=pullback_depth,
        pullback_duration=pullback_duration,
    )


def precompute_feature_rows(
    rows: Sequence[Mapping[str, Any]],
) -> dict[int, dict[str, float] | None]:
    return {
        index: _feature_from_base(
            base, direction="long", pullback_depth=0.2, pullback_duration=2
        )
        for index, base in _base_rows(rows).items()
    }


def _trade(
    event: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    features: Mapping[str, float],
    *,
    atr14: float,
) -> dict[str, Any]:
    index = int(event["stream_index"])
    if index + 1 >= len(rows):
        return {**event, "terminal_category": "data_unavailable"}
    entry_bar = rows[index + 1]
    spread = entry_bar["spread_points"] * entry_bar["point_size"]
    slip = 0.25 * spread
    direction = event["direction"]
    entry = (
        entry_bar["open_bid"] + spread + slip
        if direction == "long"
        else entry_bar["open_bid"] - slip
    )
    risk = 1.5 * atr14
    if not math.isfinite(risk) or risk <= 0:
        return {**event, "terminal_category": "excluded_post_cost_geometry"}
    stop, target = (
        (entry - risk, entry + 2 * risk)
        if direction == "long"
        else (entry + risk, entry - 2 * risk)
    )
    terminal = "data_unavailable"
    exit_bar = None
    gross = None
    for row in rows[index + 1 : min(index + 49, len(rows))]:
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
        exit_bar, terminal, gross = (
            rows[index + 48],
            "time_exit_48",
            rows[index + 48]["close_bid"],
        )
    if exit_bar is None or gross is None:
        return {**event, "terminal_category": terminal}
    effective_exit = gross - slip if direction == "long" else gross + spread + slip
    pnl = effective_exit - entry if direction == "long" else entry - effective_exit
    entry_time = (
        _timestamp(entry_bar["timestamp_utc"]).isoformat().replace("+00:00", "Z")
    )
    trade_id = hashlib.sha256(
        f"{event['event_id']}|{entry_time}|outcome_policy_v1".encode()
    ).hexdigest()
    return {
        **event,
        "trade_id": trade_id,
        "terminal_category": terminal,
        "entry_timestamp_utc": entry_time,
        "exit_timestamp_utc": _timestamp(exit_bar["timestamp_utc"])
        .isoformat()
        .replace("+00:00", "Z"),
        "effective_entry": entry,
        "effective_exit": effective_exit,
        "spread_price": spread,
        "slippage_price": slip,
        "risk_price": risk,
        "stop": stop,
        "target": target,
        "pnl": pnl,
        "r_multiple": pnl / risk,
        "bars_held": int(
            (
                _timestamp(exit_bar["timestamp_utc"])
                - _timestamp(entry_bar["timestamp_utc"])
            ).total_seconds()
            // _duration(str(event["timeframe"]))
        )
        + 1,
    }


def _metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    values = [
        float(row["r_multiple"])
        for row in rows
        if isinstance(row.get("r_multiple"), (int, float))
    ]
    return {
        "count": len(values),
        "mean_R": None if not values else sum(values) / len(values),
        "median_R": None if not values else statistics.median(values),
    }


def _gate_report(
    features: Sequence[Mapping[str, Any]], trades: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    outcomes = {row["event_id"]: row for row in trades if "r_multiple" in row}
    report: dict[str, Any] = {}
    for predictor, threshold in CONDITIONS.items():
        selected = [
            outcomes[row["event_id"]]
            for row in features
            if row["event_id"] in outcomes and float(row[predictor]) >= threshold
        ]
        development = [
            row for row in selected if _timestamp(row["decision_timestamp_utc"]) < SPLIT
        ]
        internal = [
            row
            for row in selected
            if _timestamp(row["decision_timestamp_utc"]) >= SPLIT
        ]
        dev, iv = _metrics(development), _metrics(internal)
        per_run = defaultdict(list)
        for row in internal:
            per_run[f"{row['symbol']}:{row['timeframe']}"].append(row)
        stable = sum(
            1
            for values in per_run.values()
            if len(values) >= 30 and _metrics(values)["median_R"] >= 0
        )
        gates = {
            "development_support": dev["count"] >= 300,
            "internal_support": iv["count"] >= 200,
            "development_mean_R": dev["mean_R"] is not None and dev["mean_R"] >= 0,
            "development_median_R": dev["median_R"] is not None
            and dev["median_R"] >= 0,
            "internal_mean_R": iv["mean_R"] is not None and iv["mean_R"] >= 0,
            "internal_median_R": iv["median_R"] is not None and iv["median_R"] >= 0,
            "cross_run_stability": stable >= 5,
        }
        report[predictor] = {
            "condition": f">={threshold:g}",
            "development": dev,
            "internal_validation": iv,
            "stable_internal_runs": stable,
            "gates": gates,
            "passes_every_mandatory_gate": all(gates.values()),
        }
    return report


def execute_frozen_tcp(
    bars: Sequence[Mapping[str, Any]],
    *,
    output_root: str | Path,
    command: str,
    real_data_observed: bool = False,
) -> dict[str, Any]:
    """Run one immutable historical research execution; it has no order API path."""
    conformance = detector.validate_specification_conformance()
    run = Path(output_root) / f"tcp-run-{uuid.uuid4()}"
    run.mkdir(parents=True, exist_ok=False)
    ordered = sorted(
        (dict(row) for row in bars),
        key=lambda row: (
            row["symbol"],
            row["timeframe"],
            _timestamp(row["timestamp_utc"]),
        ),
    )
    input_path = _write(run / "input_bars.json", ordered)
    observation_path = _write(
        run / "first_observation_record.json",
        {
            "schema_version": "tcp_first_observation_record.v1",
            "immutable_run_id": run.name,
            "execution_command": command,
            "input_data_artifact_hashes": {"input_bars.json": _sha(input_path)},
            "output_directory": str(run),
            "observation_started_at_utc": datetime.now(UTC).isoformat(),
            "written_before_results": True,
            "performance_inspected_before_record": False,
        },
    )
    generated = detector.generate_events(ordered)
    streams: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in ordered:
        streams[(row["symbol"], row["timeframe"])].append(row)
    caches = {key: _base_rows(rows) for key, rows in streams.items()}
    features: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    active_until: dict[tuple[str, str], int] = {}
    for event in generated["events"]:
        key = (event["symbol"], event["timeframe"])
        index = int(event["stream_index"])
        if event["terminal_category"] != "raw":
            trades.append(dict(event))
            continue
        if index <= active_until.get(key, -1):
            trades.append({**event, "terminal_category": "suppressed_overlap"})
            continue
        feature = _feature_from_base(
            caches[key].get(index),
            direction=str(event["direction"]),
            pullback_depth=float(event["pullback_depth_atr"]),
            pullback_duration=int(event["pullback_duration_bars"]),
        )
        if feature is None:
            trades.append({**event, "terminal_category": "invalid_input"})
            continue
        features.append({"event_id": event["event_id"], **feature})
        base = caches[key].get(index)
        if base is None:
            trades.append({**event, "terminal_category": "invalid_input"})
            continue
        trade = _trade(event, streams[key], feature, atr14=float(base["atr"]))
        trades.append(trade)
        if trade["terminal_category"] in {"tp", "sl", "time_exit_48"}:
            active_until[key] = index + int(trade["bars_held"])
    event_path = _write(run / "events.json", generated)
    feature_path = _write(
        run / "feature_matrix.json",
        {"predictors": list(STRICT_PREDICTORS), "rows": features},
    )
    trade_path = _write(run / "trade_journal.json", trades)
    gates = _gate_report(features, trades)
    gate_path = _write(run / "gate_report.json", gates)
    terminal = Counter(row["terminal_category"] for row in trades)
    reconciled = (
        generated["audit"]["raw_event_count"] == len(trades) == sum(terminal.values())
    )
    candidates = [
        name for name, result in gates.items() if result["passes_every_mandatory_gate"]
    ]
    decision = {
        "family_id": detector.FAMILY_ID,
        "decision": "candidate_hypotheses_only"
        if candidates
        else "Trend Continuation After Pullback CLOSED",
        "candidate_hypotheses": candidates,
        "independent_edge_confirmation": False,
        "profitable_strategy_confirmed": False,
        "closure_reason": None
        if candidates
        else "one_or_more_mandatory_gates_failed_for_every_predictor",
    }
    decision_path = _write(run / "final_decision.json", decision)
    manifest = {
        "schema_version": "tcp_run_manifest.v1",
        "immutable_run_id": run.name,
        "command": command,
        "specification_conformance": conformance,
        "real_data_observed": real_data_observed,
        "mt5_connected": False,
        "mt5_write_api_called": False,
        "order_api_called": False,
        "performance_inspected": True,
        "prospective_validation_started": False,
        "event_funnel": generated["audit"],
        "trade_funnel": {
            "trade_count": len(trades),
            "terminal_category_counts": dict(sorted(terminal.items())),
        },
        "terminal_funnel_reconciled": reconciled,
        "invariants": {
            "canonical_event_ids_unique": len(
                {row["event_id"] for row in generated["events"]}
            )
            == len(generated["events"]),
            "strict_predictor_matrix_exact": tuple(STRICT_PREDICTORS)
            == detector.STRICT_PREDICTORS,
            "no_lookahead": True,
            "trade_geometry_reconciled": all(
                abs(
                    float(row["pnl"])
                    - float(row["r_multiple"]) * float(row["risk_price"])
                )
                < 1e-10
                for row in trades
                if "pnl" in row
            ),
        },
        "aggregate_results": _metrics(trades),
        "gate_report": gates,
        "final_decision": decision,
        "artifact_hashes": {
            path.name: _sha(path)
            for path in (
                input_path,
                observation_path,
                event_path,
                feature_path,
                trade_path,
                gate_path,
                decision_path,
            )
        },
    }
    manifest_path = _write(run / "run_manifest.json", manifest)
    return {
        "output_directory": str(run),
        "run_manifest_sha256": _sha(manifest_path),
        "event_funnel": manifest["event_funnel"],
        "trade_funnel": manifest["trade_funnel"],
        "aggregate_results": manifest["aggregate_results"],
        "gate_report": gates,
        "final_decision": decision,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run frozen Trend Continuation After Pullback from a read-only MT5 snapshot"
    )
    parser.add_argument("--input-snapshot", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    bars = json.loads(args.input_snapshot.read_text(encoding="utf-8"))
    print(
        json.dumps(
            execute_frozen_tcp(
                bars,
                output_root=args.output_root,
                command=f"python -m trading_bot.research.tcap_execution --input-snapshot {args.input_snapshot} --output-root {args.output_root}",
                real_data_observed=True,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
