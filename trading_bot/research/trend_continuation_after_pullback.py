"""Frozen, completed-bar Trend Continuation After Pullback detector."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence


FAMILY_ID = "trend-continuation-after-pullback-tcp-20260713-v1"
SPECIFICATION_PATH = Path(
    "docs/research_preregistrations/trend_continuation_after_pullback_2026-07-13/specification.json"
)
STRICT_PREDICTORS = (
    "trend_separation_atr",
    "slow_ema_slope_atr",
    "pullback_depth_atr",
    "pullback_duration_bars",
    "distance_slow_ema_atr",
    "confirmation_body_atr",
    "trend_persistence_20",
    "directional_efficiency_20",
)
TIMEFRAME_SECONDS = {"M5": 300, "M15": 900, "H1": 3600}
EXPECTED_DETECTOR = {
    "ema": {
        "fast_period": 20,
        "slow_period": 50,
        "initialization": "arithmetic_mean_first_n_closes",
        "recurrence": "ema_t=alpha*close_t+(1-alpha)*ema_t_minus_1",
    },
    "slow_ema_slope": {
        "lookback_bars": 10,
        "formula": "slow_ema_t-slow_ema_t_minus_10",
    },
    "atr": {
        "period": 14,
        "method": "wilder",
        "true_range": "max(high_t-low_t,abs(high_t-close_t_minus_1),abs(low_t-close_t_minus_1))",
        "initialization": "arithmetic_mean_first_14_true_ranges",
        "recurrence": "(13*atr_t_minus_1+tr_t)/14",
    },
    "warmup": {
        "minimum_contiguous_completed_bars": 60,
        "reason": "slow_ema_50_plus_slope_10",
    },
}
EXPECTED_CONDITIONS = (
    ">=0.25",
    ">=0.03",
    ">=0.25",
    ">=2",
    ">=0.25",
    ">=0.20",
    ">=0.60",
    ">=0.40",
)


class SpecificationConformanceError(ValueError):
    """Raised when the independent frozen specification is not exact."""


@dataclass
class _StreamState:
    history: list[dict[str, Any]] = field(default_factory=list)
    closes: list[float] = field(default_factory=list)
    true_ranges: list[float] = field(default_factory=list)
    fast_ema: float | None = None
    slow_ema: float | None = None
    slow_values: list[float] = field(default_factory=list)
    atr14: float | None = None
    last_timestamp: datetime | None = None
    pullback: dict[str, Any] | None = None
    cooldown_until: int = -1
    operations: int = 0


def load_specification(path: str | Path | None = None) -> dict[str, Any]:
    source = Path(path) if path else Path(__file__).parents[2] / SPECIFICATION_PATH
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecificationConformanceError(f"invalid specification: {source}") from exc
    if not isinstance(value, dict):
        raise SpecificationConformanceError("specification must be an object")
    return value


def validate_specification_conformance(
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Compare an external frozen file with literals, never runtime-generated constants."""
    spec = load_specification(path)
    if spec.get("schema_version") != "trend_continuation_pullback_specification.v1":
        raise SpecificationConformanceError("schema version mismatch")
    family = spec.get("family")
    if not isinstance(family, dict) or family.get("id") != FAMILY_ID:
        raise SpecificationConformanceError("family identifier mismatch")
    if (
        spec.get("order_api_permitted") is not False
        or spec.get("execution_authorized_by_specification") is not True
    ):
        raise SpecificationConformanceError("execution safety mismatch")
    detector = spec.get("detector")
    if not isinstance(detector, dict):
        raise SpecificationConformanceError("detector missing")
    for key, expected in EXPECTED_DETECTOR.items():
        if detector.get(key) != expected:
            raise SpecificationConformanceError(f"detector {key} mismatch")
    if (
        detector.get("completed_bar_policy")
        != "only_completed_bar_t; no_partial_or_future_bar_dependency"
    ):
        raise SpecificationConformanceError("completed-bar policy mismatch")
    predictors = spec.get("strict_predictors")
    if (
        not isinstance(predictors, list)
        or tuple(row.get("name") for row in predictors if isinstance(row, dict))
        != STRICT_PREDICTORS
    ):
        raise SpecificationConformanceError("strict predictor list mismatch")
    if (
        tuple(row.get("candidate_condition") for row in predictors)
        != EXPECTED_CONDITIONS
    ):
        raise SpecificationConformanceError("predictor conditions mismatch")
    for row in predictors:
        if (
            row.get("timing") != "pre_decision"
            or row.get("strict_eligibility") is not True
        ):
            raise SpecificationConformanceError("strict predictor provenance mismatch")
        if row.get("missing_value_policy") != "unavailable_fail_closed_no_imputation":
            raise SpecificationConformanceError(
                "strict predictor missing-value policy mismatch"
            )
    return {
        "family_id": FAMILY_ID,
        "specification_sha256": hashlib.sha256(
            json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must have a timezone")
    return parsed.astimezone(UTC)


def _normalise(raw: Mapping[str, Any]) -> dict[str, Any]:
    required = (
        "timestamp_utc",
        "symbol",
        "timeframe",
        "open_bid",
        "high_bid",
        "low_bid",
        "close_bid",
        "spread_points",
        "point_size",
        "is_completed",
    )
    if not isinstance(raw, Mapping) or any(key not in raw for key in required):
        raise ValueError("required bar field missing")
    if (
        raw["is_completed"] is not True
        or raw["timeframe"] not in TIMEFRAME_SECONDS
        or not isinstance(raw["symbol"], str)
        or not raw["symbol"]
    ):
        raise ValueError("invalid completed bar")
    bar = {key: raw[key] for key in required}
    bar["timestamp_utc"] = _timestamp(bar["timestamp_utc"])
    for key in (
        "open_bid",
        "high_bid",
        "low_bid",
        "close_bid",
        "spread_points",
        "point_size",
    ):
        if isinstance(bar[key], bool):
            raise ValueError(f"invalid {key}")
        bar[key] = float(bar[key])
        if not math.isfinite(bar[key]):
            raise ValueError(f"invalid {key}")
    if (
        bar["high_bid"] < bar["low_bid"]
        or bar["point_size"] <= 0
        or bar["spread_points"] < 0
    ):
        raise ValueError("invalid bar geometry")
    return bar


def _reset(state: _StreamState) -> None:
    state.history.clear()
    state.closes.clear()
    state.true_ranges.clear()
    state.slow_values.clear()
    state.fast_ema = state.slow_ema = state.atr14 = None
    state.last_timestamp = None
    state.pullback = None
    state.cooldown_until = -1


def _direction(state: _StreamState, bar: Mapping[str, Any]) -> str | None:
    if (
        state.fast_ema is None
        or state.slow_ema is None
        or state.atr14 is None
        or len(state.slow_values) <= 10
    ):
        return None
    slope = state.slow_ema - state.slow_values[-11]
    if (
        state.fast_ema > state.slow_ema
        and slope > 0
        and bar["close_bid"] > state.slow_ema
    ):
        return "long"
    if (
        state.fast_ema < state.slow_ema
        and slope < 0
        and bar["close_bid"] < state.slow_ema
    ):
        return "short"
    return None


def _depth(direction: str, bar: Mapping[str, Any], fast: float, atr: float) -> float:
    return (
        max(0.0, fast - bar["low_bid"]) / atr
        if direction == "long"
        else max(0.0, bar["high_bid"] - fast) / atr
    )


def _event_id(event: Mapping[str, Any]) -> str:
    preimage = "|".join(
        (
            FAMILY_ID,
            str(event["symbol"]),
            str(event["timeframe"]),
            str(event["decision_timestamp_utc"]),
            "pullback_continuation",
            str(event["direction"]),
            "ema20",
            "ema50",
            "slope10",
            "atr14",
            "depth1.0",
            "duration6",
            "cooldown8",
        )
    )
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def canonical_event_id(event: Mapping[str, Any]) -> str:
    return _event_id(event)


def event_order_key(event: Mapping[str, Any]) -> tuple[datetime, str, str, str]:
    return (
        _timestamp(event["decision_timestamp_utc"]),
        str(event["symbol"]),
        str(event["timeframe"]),
        str(event["event_id"]),
    )


def _make_event(
    bar: Mapping[str, Any],
    *,
    direction: str,
    source_index: int,
    stream_index: int,
    depth: float,
    duration: int,
) -> dict[str, Any]:
    event = {
        "family_id": FAMILY_ID,
        "symbol": bar["symbol"],
        "timeframe": bar["timeframe"],
        "direction": direction,
        "transition_type": "pullback_continuation",
        "decision_timestamp_utc": (
            bar["timestamp_utc"]
            + timedelta(seconds=TIMEFRAME_SECONDS[bar["timeframe"]])
        )
        .isoformat()
        .replace("+00:00", "Z"),
        "source_index": source_index,
        "stream_index": stream_index,
        "pullback_depth_atr": depth,
        "pullback_duration_bars": duration,
        "terminal_category": "raw",
    }
    event["event_id"] = _event_id(event)
    return event


def generate_events(
    bars: Sequence[Mapping[str, Any]],
    *,
    active_until_by_stream: Mapping[str, int] | None = None,
    specification_path: str | Path | None = None,
) -> dict[str, Any]:
    conformance = validate_specification_conformance(specification_path)
    streams: dict[tuple[str, str], _StreamState] = {}
    raw_events: list[dict[str, Any]] = []
    resets: list[dict[str, Any]] = []
    for source_index, raw in enumerate(bars):
        try:
            bar = _normalise(raw)
        except (TypeError, ValueError) as exc:
            if (
                isinstance(raw, Mapping)
                and isinstance(raw.get("symbol"), str)
                and isinstance(raw.get("timeframe"), str)
                and raw.get("timeframe") in TIMEFRAME_SECONDS
            ):
                _reset(
                    streams.setdefault(
                        (raw["symbol"], raw["timeframe"]), _StreamState()
                    )
                )
            resets.append(
                {
                    "source_index": source_index,
                    "reason": "invalid_input",
                    "detail": str(exc),
                }
            )
            continue
        key = (bar["symbol"], bar["timeframe"])
        state = streams.setdefault(key, _StreamState())
        if state.last_timestamp is not None:
            delta = bar["timestamp_utc"] - state.last_timestamp
            if delta.total_seconds() <= 0:
                _reset(state)
                resets.append(
                    {
                        "source_index": source_index,
                        "reason": "duplicate_timestamp"
                        if delta.total_seconds() == 0
                        else "non_monotonic_timestamp",
                    }
                )
            elif delta > timedelta(seconds=3 * TIMEFRAME_SECONDS[bar["timeframe"]]):
                _reset(state)
                resets.append({"source_index": source_index, "reason": "gap"})
        if state.history:
            prior = state.history[-1]
            tr = max(
                bar["high_bid"] - bar["low_bid"],
                abs(bar["high_bid"] - prior["close_bid"]),
                abs(bar["low_bid"] - prior["close_bid"]),
            )
            state.true_ranges.append(tr)
            if len(state.true_ranges) == 14:
                state.atr14 = sum(state.true_ranges) / 14
            elif len(state.true_ranges) > 14 and state.atr14 is not None:
                state.atr14 = (13 * state.atr14 + tr) / 14
        state.history.append(bar)
        state.closes.append(bar["close_bid"])
        state.last_timestamp = bar["timestamp_utc"]
        state.operations += 1
        if len(state.closes) == 20:
            state.fast_ema = sum(state.closes) / 20
        elif len(state.closes) > 20 and state.fast_ema is not None:
            state.fast_ema = (2 / 21) * bar["close_bid"] + (19 / 21) * state.fast_ema
        if len(state.closes) == 50:
            state.slow_ema = sum(state.closes) / 50
        elif len(state.closes) > 50 and state.slow_ema is not None:
            state.slow_ema = (2 / 51) * bar["close_bid"] + (49 / 51) * state.slow_ema
        state.slow_values.append(
            state.slow_ema if state.slow_ema is not None else math.nan
        )
        stream_index = len(state.history) - 1
        if (
            stream_index < 59
            or state.fast_ema is None
            or state.slow_ema is None
            or state.atr14 is None
            or state.atr14 <= 0
        ):
            continue
        direction = _direction(state, bar)
        if stream_index <= state.cooldown_until:
            continue
        active = state.pullback
        if active is None:
            if direction is not None and (
                (direction == "long" and bar["low_bid"] <= state.fast_ema)
                or (direction == "short" and bar["high_bid"] >= state.fast_ema)
            ):
                depth = _depth(direction, bar, state.fast_ema, state.atr14)
                if depth <= 1.0:
                    state.pullback = {
                        "direction": direction,
                        "start": stream_index,
                        "depth": depth,
                    }
            continue
        if direction != active["direction"]:
            state.pullback = None
            continue
        depth = max(
            float(active["depth"]), _depth(direction, bar, state.fast_ema, state.atr14)
        )
        duration = stream_index - int(active["start"]) + 1
        if depth > 1.0 or duration > 6:
            state.pullback = None
            continue
        prior = state.history[-2]
        confirmed = (
            direction == "long"
            and bar["close_bid"] > state.fast_ema
            and bar["close_bid"] > bar["open_bid"]
            and bar["close_bid"] > prior["high_bid"]
        ) or (
            direction == "short"
            and bar["close_bid"] < state.fast_ema
            and bar["close_bid"] < bar["open_bid"]
            and bar["close_bid"] < prior["low_bid"]
        )
        if confirmed:
            raw_events.append(
                _make_event(
                    bar,
                    direction=direction,
                    source_index=source_index,
                    stream_index=stream_index,
                    depth=depth,
                    duration=duration,
                )
            )
            state.pullback = None
            state.cooldown_until = stream_index + 8
        else:
            active["depth"] = depth
    unique: dict[str, dict[str, Any]] = {}
    duplicate_count = 0
    for event in sorted(
        raw_events, key=lambda row: (row["source_index"], row["event_id"])
    ):
        if event["event_id"] in unique:
            duplicate_count += 1
        else:
            unique[event["event_id"]] = event
    events = list(unique.values())
    for event in events:
        stream = f"{event['symbol']}:{event['timeframe']}"
        if active_until_by_stream and event[
            "stream_index"
        ] <= active_until_by_stream.get(stream, -1):
            event["terminal_category"] = "suppressed_overlap"
    events.sort(key=event_order_key)
    return {
        "schema_version": "tcp_event_stream.v1",
        "conformance": conformance,
        "events": events,
        "audit": {
            "raw_event_count": len(events),
            "duplicate_event_count": duplicate_count,
            "reset_count": len(resets),
            "resets": resets,
            "terminal_category_counts": dict(
                sorted(Counter(event["terminal_category"] for event in events).items())
            ),
            "linear_operations": sum(state.operations for state in streams.values()),
        },
    }
