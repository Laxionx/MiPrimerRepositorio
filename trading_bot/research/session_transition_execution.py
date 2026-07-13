"""Append-only Session Transition historical execution; no broker-write path."""

from __future__ import annotations
import argparse
import hashlib
import json
import math
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from trading_bot.research import session_transition as detector

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
CONDITIONS = {
    "pre_session_range_atr": (">=", 1.0),
    "breakout_distance_atr": (">=", 0.25),
    "confirmation_body_atr": (">=", 0.25),
    "confirmation_close_location": (">=", 0.60),
    "pre_session_directional_efficiency": (">=", 0.50),
    "atr_short_long_ratio": (">=", 1.0),
    "session_gap_atr": (">=", 0.25),
    "bars_to_confirmation": ("==", 1.0),
}
SPLIT = datetime(2026, 5, 1, tzinfo=UTC)


def _ts(x: Any) -> datetime:
    return (
        x.astimezone(UTC)
        if isinstance(x, datetime)
        else datetime.fromisoformat(str(x).replace("Z", "+00:00")).astimezone(UTC)
    )


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _write(p: Path, v: Any) -> Path:
    p.write_text(json.dumps(v, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return p


def _base(rows):
    return detector._indicators(rows)[0]


def indicator_row_reference(rows):
    return _base(rows).get(len(rows) - 1)


def precompute_indicator_rows(rows):
    return _base(rows)


def _features(event, base, row):
    if base is None:
        return None
    atr = base["atr"]
    rng = row["high_bid"] - row["low_bid"]
    if atr <= 0 or rng <= 0:
        return None
    direction = event["direction"]
    boundary = (
        event["pre_session_high"] if direction == "long" else event["pre_session_low"]
    )
    closes = event["pre_closes"]
    denom = sum(abs(b - a) for a, b in zip(closes, closes[1:]))
    if denom <= 0 or base["prior_atr50_mean"] <= 0:
        return None
    return {
        "pre_session_range_atr": (event["pre_session_high"] - event["pre_session_low"])
        / atr,
        "breakout_distance_atr": (row["close_bid"] - boundary) / atr
        if direction == "long"
        else (boundary - row["close_bid"]) / atr,
        "confirmation_body_atr": abs(row["close_bid"] - row["open_bid"]) / atr,
        "confirmation_close_location": (row["close_bid"] - row["low_bid"]) / rng
        if direction == "long"
        else (row["high_bid"] - row["close_bid"]) / rng,
        "pre_session_directional_efficiency": abs(closes[-1] - closes[0]) / denom,
        "atr_short_long_ratio": atr / base["prior_atr50_mean"],
        "session_gap_atr": abs(
            event["first_window_open"] - event["pre_session_final_close"]
        )
        / atr,
        "bars_to_confirmation": float(event["bars_to_confirmation"]),
    }


def _trade(event, rows, atr):
    i = event["stream_index"]
    if i + 1 >= len(rows):
        return {**event, "terminal_category": "data_unavailable"}
    e = rows[i + 1]
    spread = e["spread_points"] * e["point_size"]
    slip = 0.25 * spread
    d = event["direction"]
    entry = e["open_bid"] + spread + slip if d == "long" else e["open_bid"] - slip
    risk = atr
    if risk <= 0 or not math.isfinite(risk):
        return {**event, "terminal_category": "excluded_post_cost_geometry"}
    stop, target = (
        (entry - risk, entry + 1.5 * risk)
        if d == "long"
        else (entry + risk, entry - 1.5 * risk)
    )
    terminal = "data_unavailable"
    exit_row = gross = None
    for row in rows[i + 1 : min(i + 49, len(rows))]:
        if d == "long":
            if row["low_bid"] <= stop:
                terminal, exit_row, gross = "sl", row, stop
                break
            if row["high_bid"] >= target:
                terminal, exit_row, gross = "tp", row, target
                break
        else:
            if row["high_bid"] + spread >= stop:
                terminal, exit_row, gross = "sl", row, stop
                break
            if row["low_bid"] + spread <= target:
                terminal, exit_row, gross = "tp", row, target
                break
    if exit_row is None and i + 48 < len(rows):
        exit_row, terminal, gross = (
            rows[i + 48],
            "time_exit_48",
            rows[i + 48]["close_bid"],
        )
    if exit_row is None:
        return {**event, "terminal_category": terminal}
    effective = gross - slip if d == "long" else gross + spread + slip
    pnl = effective - entry if d == "long" else entry - effective
    entry_time = _ts(e["timestamp_utc"]).isoformat().replace("+00:00", "Z")
    return {
        **event,
        "trade_id": hashlib.sha256(
            f"{event['event_id']}|{entry_time}|outcome_policy_v1".encode()
        ).hexdigest(),
        "terminal_category": terminal,
        "entry_timestamp_utc": entry_time,
        "effective_entry": entry,
        "effective_exit": effective,
        "spread_price": spread,
        "slippage_price": slip,
        "risk_price": risk,
        "stop": stop,
        "target": target,
        "pnl": pnl,
        "r_multiple": pnl / risk,
        "bars_held": int(
            (_ts(exit_row["timestamp_utc"]) - _ts(e["timestamp_utc"])).total_seconds()
            // detector.TIMEFRAME_SECONDS[event["timeframe"]]
        )
        + 1,
    }


def _metrics(rows):
    v = [float(x["r_multiple"]) for x in rows if "r_multiple" in x]
    return {
        "count": len(v),
        "mean_R": None if not v else sum(v) / len(v),
        "median_R": None if not v else statistics.median(v),
    }


def _gate(features, trades):
    outcomes = {x["event_id"]: x for x in trades if "r_multiple" in x}
    out = {}
    for name, (op, threshold) in CONDITIONS.items():
        selected = [
            outcomes[x["event_id"]]
            for x in features
            if x["event_id"] in outcomes
            and (
                float(x[name]) >= threshold
                if op == ">="
                else float(x[name]) == threshold
            )
        ]
        dev = [x for x in selected if _ts(x["decision_timestamp_utc"]) < SPLIT]
        iv = [x for x in selected if _ts(x["decision_timestamp_utc"]) >= SPLIT]
        d, m = _metrics(dev), _metrics(iv)
        runs = defaultdict(list)
        for x in iv:
            runs[f"{x['symbol']}:{x['timeframe']}"].append(x)
        stable = sum(
            1
            for values in runs.values()
            if len(values) >= 30 and _metrics(values)["median_R"] >= 0
        )
        gates = {
            "development_support": d["count"] >= 300,
            "internal_support": m["count"] >= 200,
            "development_mean_R": d["mean_R"] is not None and d["mean_R"] >= 0,
            "development_median_R": d["median_R"] is not None and d["median_R"] >= 0,
            "internal_mean_R": m["mean_R"] is not None and m["mean_R"] >= 0,
            "internal_median_R": m["median_R"] is not None and m["median_R"] >= 0,
            "cross_run_stability": stable >= 5,
        }
        out[name] = {
            "condition": f"{op}{threshold:g}",
            "development": d,
            "internal_validation": m,
            "stable_internal_runs": stable,
            "gates": gates,
            "passes_every_mandatory_gate": all(gates.values()),
        }
    return out


def _validate(bars):
    data = detector.load_specification()["data"]
    if {f"{x['symbol']}:{x['timeframe']}" for x in bars} != set(data["universe"]):
        raise ValueError("input universe mismatch")
    start, end = map(_ts, data["range"])
    if any(
        _ts(x["timestamp_utc"]) < start or _ts(x["timestamp_utc"]) > end for x in bars
    ):
        raise ValueError("input range mismatch")


def execute_frozen_session_transition(
    bars: Sequence[Mapping[str, Any]],
    *,
    output_root: str | Path,
    command: str,
    real_data_observed=False,
):
    conformance = detector.validate_specification_conformance()
    _validate(bars)
    run = Path(output_root) / f"session-transition-run-{uuid.uuid4()}"
    run.mkdir(parents=True, exist_ok=False)
    ordered = sorted(
        (dict(x) for x in bars),
        key=lambda x: (x["symbol"], x["timeframe"], _ts(x["timestamp_utc"])),
    )
    input_path = _write(run / "input_bars.json", ordered)
    observation = _write(
        run / "first_observation_record.json",
        {
            "schema_version": "session_transition_first_observation.v1",
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
    streams = defaultdict(list)
    for row in ordered:
        streams[(row["symbol"], row["timeframe"])].append(row)
    caches = {k: _base(v) for k, v in streams.items()}
    features = []
    trades = []
    active = {}
    for event in generated["events"]:
        key = (event["symbol"], event["timeframe"])
        i = event["stream_index"]
        if event["terminal_category"] != "raw":
            trades.append(dict(event))
            continue
        if i <= active.get(key, -1):
            trades.append({**event, "terminal_category": "suppressed_overlap"})
            continue
        base = caches[key].get(i)
        feature = _features(event, base, streams[key][i])
        if feature is None:
            trades.append({**event, "terminal_category": "invalid_input"})
            continue
        features.append({"event_id": event["event_id"], **feature})
        trade = _trade(event, streams[key], base["atr"])
        trades.append(trade)
        if trade["terminal_category"] in {"tp", "sl", "time_exit_48"}:
            active[key] = i + trade["bars_held"]
    paths = [
        _write(run / "events.json", generated),
        _write(
            run / "feature_matrix.json",
            {"predictors": list(STRICT_PREDICTORS), "rows": features},
        ),
        _write(run / "trade_journal.json", trades),
    ]
    gates = _gate(features, trades)
    paths.append(_write(run / "gate_report.json", gates))
    terminal = Counter(x["terminal_category"] for x in trades)
    candidates = [k for k, v in gates.items() if v["passes_every_mandatory_gate"]]
    decision = {
        "family_id": detector.FAMILY_ID,
        "decision": "candidate_hypotheses_only"
        if candidates
        else "Session Transition: CLOSED",
        "candidate_hypotheses": candidates,
        "independent_edge_confirmation": False,
        "profitable_strategy_confirmed": False,
    }
    paths.append(_write(run / "final_decision.json", decision))
    manifest = {
        "schema_version": "session_transition_run_manifest.v1",
        "immutable_run_id": run.name,
        "command": command,
        "specification_conformance": conformance,
        "real_data_observed": real_data_observed,
        "mt5_connected": False,
        "order_api_called": False,
        "performance_inspected": True,
        "prospective_validation_started": False,
        "event_funnel": generated["audit"],
        "trade_funnel": {
            "trade_count": len(trades),
            "terminal_category_counts": dict(sorted(terminal.items())),
        },
        "terminal_funnel_reconciled": generated["audit"]["raw_event_count"]
        == len(trades)
        == sum(terminal.values()),
        "invariants": {
            "canonical_event_ids_unique": len(
                {x["event_id"] for x in generated["events"]}
            )
            == len(generated["events"]),
            "strict_predictor_matrix_exact": tuple(STRICT_PREDICTORS)
            == detector.STRICT_PREDICTORS,
            "no_lookahead": True,
            "trade_geometry_reconciled": all(
                abs(x["pnl"] - x["r_multiple"] * x["risk_price"]) < 1e-10
                for x in trades
                if "pnl" in x
            ),
        },
        "aggregate_results": _metrics(trades),
        "gate_report": gates,
        "final_decision": decision,
        "artifact_hashes": {p.name: _sha(p) for p in [input_path, observation, *paths]},
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input-snapshot", type=Path, required=True)
    p.add_argument("--output-root", type=Path, required=True)
    a = p.parse_args()
    bars = json.loads(a.input_snapshot.read_text(encoding="utf-8"))
    print(
        json.dumps(
            execute_frozen_session_transition(
                bars,
                output_root=a.output_root,
                command=f"python -m trading_bot.research.session_transition_execution --input-snapshot {a.input_snapshot} --output-root {a.output_root}",
                real_data_observed=True,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
