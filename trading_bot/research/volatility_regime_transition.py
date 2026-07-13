"""Synthetic-only Volatility Regime Transition detector frozen by PR #28."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


FAMILY_ID = "volatility-regime-transition-vrt-20260712-v1"
MANIFEST_RELATIVE_PATH = Path(
    "docs/research_preregistrations/next_family_selection_2026-07-12/"
    "preregistration_manifest.json"
)
STRICT_PREDICTORS = (
    "atr_14_points",
    "atr_56_points",
    "atr_ratio_14_56",
    "atr_ratio_change_8",
    "mean_range_8_points",
    "mean_range_56_points",
    "range_ratio_8_56",
    "efficiency_20",
)
EXPECTED_CONFIG = {
    "threshold": 1.2,
    "warmup_bars": 64,
    "fast_period": 14,
    "slow_period": 56,
    "persistence_bars": 1,
    "cooldown_bars": 0,
    "gap_multiplier": 3,
}
EXPECTED_DETECTOR_SEMANTICS = {
    "decision_timestamp": "utc_close_timestamp_of_completed_bar_t",
    "ratio": "atr_14_points/atr_56_points",
    "true_range": "max(high_t-low_t,abs(high_t-close_t_minus_1),abs(low_t-close_t_minus_1))",
    "initial_state": "after_64_contiguous_valid_completed_bars_initialize_to_below_or_above_without_event",
    "states": {
        "above": "ratio_gte_1_20",
        "below": "ratio_lt_1_20",
        "unavailable": "invalid_missing_duplicate_nonmonotonic_or_gapped_stream_or_warmup",
    },
    "gap_rule": "timestamp_delta_gt_three_nominal_timeframe_durations_resets_to_unavailable",
    "transition_start_and_confirmation": "same_completed_bar_prior_state_below_and_ratio_gte_1_20",
    "transition_end_reset_rearm": "first_subsequent_eligible_ratio_lt_1_20_sets_below_and_rearms",
    "duplicate_suppression": "retain_first_canonical_id_in_ascending_source_row_order",
    "overlap_policy": "raw_event_stream_retained; outcome_can_mark_suppressed_overlap",
    "stream_isolation": "independent_per_symbol_and_timeframe",
    "ordering": ["decision_timestamp_utc", "symbol", "timeframe", "event_id"],
    "direction": {
        "long": "close_t_gt_close_t_minus_8",
        "short": "close_t_lt_close_t_minus_8",
        "equality": "raw_event_direction_none_terminal_no_direction",
    },
    "event_identity": {
        "preimage": "family_id|preregistration_version|symbol|timeframe|decision_timestamp_utc|below_to_above|direction|atr14=14|atr56=56|threshold=1.20|warmup=64",
        "algorithm": "sha256_utf8_lowercase_hex",
    },
}
EXPECTED_STRICT_FEATURES = {
    "atr_14_points": ("detector_input_and_discovery_predictor", "float64", True, "pre_decision", ("true_range_points",), "price"),
    "atr_56_points": ("detector_input_and_discovery_predictor", "float64", True, "pre_decision", ("true_range_points",), "price"),
    "atr_ratio_14_56": ("detector_input_and_discovery_predictor", "float64", True, "pre_decision", ("atr_14_points", "atr_56_points"), "dimensionless"),
    "atr_ratio_change_8": ("discovery_predictor", "float64", True, "pre_decision", ("atr_ratio_14_56",), "dimensionless"),
    "mean_range_8_points": ("discovery_predictor", "float64", True, "pre_decision", ("high_bid", "low_bid"), "price"),
    "mean_range_56_points": ("discovery_predictor", "float64", True, "pre_decision", ("high_bid", "low_bid"), "price"),
    "range_ratio_8_56": ("discovery_predictor", "float64", True, "pre_decision", ("mean_range_8_points", "mean_range_56_points"), "dimensionless"),
    "efficiency_20": ("discovery_predictor", "float64", True, "pre_decision", ("close_bid",), "ratio_0_to_1"),
}


class ManifestConformanceError(ValueError):
    """Raised when the merged preregistration cannot be used unchanged."""


class ProvenanceContractError(ValueError):
    """Raised when a strict feature has incomplete or late provenance."""


class RegimeState(str, Enum):
    UNAVAILABLE = "unavailable"
    BELOW = "below"
    ABOVE = "above"


@dataclass
class _StreamState:
    history: list[dict[str, Any]] = field(default_factory=list)
    regime: RegimeState = RegimeState.UNAVAILABLE
    last_timestamp: datetime | None = None
    true_ranges: list[float] = field(default_factory=list)
    fast_atr: float | None = None
    slow_atr: float | None = None


def _default_manifest_path() -> Path:
    return Path(__file__).resolve().parents[2] / MANIFEST_RELATIVE_PATH


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_preregistration_manifest(path: str | Path | None = None) -> dict[str, Any]:
    """Load the frozen manifest without permitting fallback defaults."""
    source = Path(path) if path is not None else _default_manifest_path()
    try:
        parsed = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestConformanceError(f"invalid preregistration manifest: {source}") from exc
    if not isinstance(parsed, dict):
        raise ManifestConformanceError("preregistration manifest must be an object")
    return parsed


def _require(mapping: Mapping[str, Any], key: str, context: str) -> Any:
    if key not in mapping:
        raise ManifestConformanceError(f"{context} is missing required key: {key}")
    return mapping[key]


def validate_preregistration_conformance(path: str | Path | None = None) -> dict[str, Any]:
    """Fail closed unless implementation constants exactly match PR #28."""
    manifest_path = Path(path) if path is not None else _default_manifest_path()
    manifest = load_preregistration_manifest(manifest_path)
    if manifest.get("schema_version") != "next_family_preregistration.v2":
        raise ManifestConformanceError("unsupported preregistration manifest schema")
    family = _require(manifest, "family", "manifest")
    if not isinstance(family, dict) or family.get("id") != FAMILY_ID:
        raise ManifestConformanceError("family ID does not match frozen implementation")
    detector = _require(manifest, "detector", "manifest")
    if not isinstance(detector, dict):
        raise ManifestConformanceError("detector must be an object")
    threshold = _require(detector, "threshold", "detector")
    atr = _require(detector, "atr", "detector")
    actual = {
        "threshold": threshold.get("value") if isinstance(threshold, dict) else None,
        "warmup_bars": detector.get("minimum_contiguous_valid_completed_bars"),
        "fast_period": atr.get("fast_period") if isinstance(atr, dict) else None,
        "slow_period": atr.get("slow_period") if isinstance(atr, dict) else None,
        "persistence_bars": detector.get("persistence_completed_bars"),
        "cooldown_bars": detector.get("cooldown_completed_bars"),
        "gap_multiplier": 3,
    }
    for name, expected in EXPECTED_CONFIG.items():
        if actual[name] != expected:
            raise ManifestConformanceError(
                f"frozen implementation {name}={expected!r} differs from manifest {actual[name]!r}"
            )
    for name, expected in EXPECTED_DETECTOR_SEMANTICS.items():
        if detector.get(name) != expected:
            raise ManifestConformanceError(f"{name} semantics differ from frozen implementation")
    if detector.get("threshold") != {"value": 1.2, "unit": "dimensionless", "above_operator": ">=", "below_operator": "<"}:
        raise ManifestConformanceError("threshold semantics differ from frozen implementation")
    if detector.get("atr") != {
        "fast_period": 14, "slow_period": 56, "method": "wilder",
        "initialization": "arithmetic_mean_of_first_n_true_ranges",
        "recurrence": "((n-1)*atr_previous+tr_current)/n",
    }:
        raise ManifestConformanceError("ATR semantics differ from frozen implementation")
    if detector.get("input_fields") != [
        "timestamp_utc", "symbol", "timeframe", "open_bid", "high_bid", "low_bid", "close_bid", "spread_points", "point_size",
    ]:
        raise ManifestConformanceError("detector input fields differ from frozen implementation")
    feature_registry = _require(manifest, "feature_registry", "manifest")
    if not isinstance(feature_registry, dict):
        raise ManifestConformanceError("feature_registry must be an object")
    if feature_registry.get("common_missing_policy") != "unavailable_fail_closed_no_imputation":
        raise ManifestConformanceError("missing-value policy differs from frozen implementation")
    derived = {item.get("name"): item for item in feature_registry.get("derived", []) if isinstance(item, dict)}
    for name, expected in EXPECTED_STRICT_FEATURES.items():
        entry = derived.get(name)
        actual_feature = None if entry is None else (
            entry.get("role"), entry.get("type"), entry.get("nullable"), entry.get("timing"),
            tuple(entry.get("depends_on_fields", ())), entry.get("unit"),
        )
        if actual_feature != expected or entry.get("strict_eligibility") is not True:
            raise ManifestConformanceError(f"strict predictor {name} differs from frozen implementation")
    registry = build_feature_registry(manifest)
    strict = validate_strict_eligibility(registry, manifest)
    source_bytes = manifest_path.read_bytes()
    return {
        "ok": True,
        "manifest_sha256": _sha256_bytes(source_bytes),
        "config": actual,
        "strict_predictors": strict,
        "semantic_diff": [],
        "execution_disabled": True,
        "broker_api_called": False,
    }


def build_feature_registry(manifest: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Return an immutable-by-copy registry backed by the merged manifest."""
    source = manifest if manifest is not None else load_preregistration_manifest()
    feature_registry = _require(source, "feature_registry", "manifest")
    if not isinstance(feature_registry, dict):
        raise ProvenanceContractError("feature_registry must be an object")
    entries = []
    for group in ("primitive", "derived"):
        values = _require(feature_registry, group, "feature_registry")
        if not isinstance(values, list):
            raise ProvenanceContractError(f"feature_registry.{group} must be a list")
        entries.extend(values)
    registry: dict[str, dict[str, Any]] = {}
    required = {"name", "role", "type", "nullable", "timing", "depends_on_fields", "unit"}
    for item in entries:
        if not isinstance(item, dict):
            raise ProvenanceContractError("provenance entry must be an object")
        missing = sorted(required - set(item))
        if missing:
            raise ProvenanceContractError(f"provenance entry is missing: {', '.join(missing)}")
        name = item["name"]
        if not isinstance(name, str) or not name or name in registry:
            raise ProvenanceContractError(f"invalid or duplicate provenance field: {name!r}")
        if not isinstance(item["depends_on_fields"], list):
            raise ProvenanceContractError(f"{name} depends_on_fields must be a list")
        registry[name] = copy.deepcopy(item)
    return registry


def validate_strict_eligibility(
    registry: Mapping[str, Mapping[str, Any]] | None = None,
    manifest: Mapping[str, Any] | None = None,
) -> list[str]:
    """Recursively reject late, unknown, unregistered, or execution-dependent inputs."""
    source_manifest = manifest if manifest is not None else load_preregistration_manifest()
    source_registry = registry if registry is not None else build_feature_registry(source_manifest)
    matrix = _require(_require(source_manifest, "feature_registry", "manifest"), "discovery_matrix", "feature_registry")
    if tuple(matrix) != STRICT_PREDICTORS:
        raise ProvenanceContractError("discovery matrix differs from frozen preregistration")

    def visit(name: str, trail: tuple[str, ...]) -> None:
        if name not in source_registry:
            raise ProvenanceContractError(f"unregistered dependency: {' -> '.join((*trail, name))}")
        entry = source_registry[name]
        if not isinstance(entry, Mapping):
            raise ProvenanceContractError(f"invalid provenance metadata for {name}")
        required = {"role", "type", "nullable", "timing", "depends_on_fields", "unit"}
        missing = sorted(required - set(entry))
        if missing:
            raise ProvenanceContractError(f"incomplete provenance metadata for {name}: {', '.join(missing)}")
        if entry["timing"] != "pre_decision":
            raise ProvenanceContractError(f"late or unknown timing dependency: {' -> '.join((*trail, name))}")
        role = str(entry["role"])
        if "outcome" in role or "audit" in role:
            raise ProvenanceContractError(f"outcome/audit dependency is not strict: {' -> '.join((*trail, name))}")
        if name in trail:
            raise ProvenanceContractError(f"cyclic provenance dependency: {' -> '.join((*trail, name))}")
        for dependency in entry["depends_on_fields"]:
            visit(str(dependency), (*trail, name))

    for predictor in matrix:
        entry = source_registry.get(predictor)
        if entry is None or entry.get("strict_eligibility") is not True:
            raise ProvenanceContractError(f"strict predictor is ineligible: {predictor}")
        visit(predictor, ())
    return list(matrix)


def classify_regime(ratio: float) -> RegimeState:
    if not isinstance(ratio, (int, float)) or isinstance(ratio, bool) or not math.isfinite(ratio):
        return RegimeState.UNAVAILABLE
    return RegimeState.BELOW if ratio < EXPECTED_CONFIG["threshold"] else RegimeState.ABOVE


def advance_regime_state(state: RegimeState, ratio: float) -> tuple[RegimeState, bool]:
    """Apply the frozen same-bar confirmation, reset, and re-arming rule."""
    current = classify_regime(ratio)
    if current is RegimeState.UNAVAILABLE:
        return RegimeState.UNAVAILABLE, False
    if state is RegimeState.UNAVAILABLE:
        return current, False
    if state is RegimeState.BELOW and current is RegimeState.ABOVE:
        return RegimeState.ABOVE, True
    if state is RegimeState.ABOVE and current is RegimeState.BELOW:
        return RegimeState.BELOW, False
    return state, False


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("timestamp_utc must be a timezone-aware datetime or ISO timestamp")
    if parsed.tzinfo is None:
        raise ValueError("timestamp_utc must include UTC offset")
    return parsed.astimezone(UTC)


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _timeframe_duration(timeframe: str) -> timedelta:
    match = re.fullmatch(r"([MH])(\d+)", timeframe)
    if not match:
        raise ValueError(f"unsupported timeframe: {timeframe!r}")
    amount = int(match.group(2))
    return timedelta(minutes=amount) if match.group(1) == "M" else timedelta(hours=amount)


def _normalise_bar(raw: Mapping[str, Any]) -> dict[str, Any]:
    required = ("timestamp_utc", "symbol", "timeframe", "open_bid", "high_bid", "low_bid", "close_bid", "spread_points", "point_size")
    if any(key not in raw for key in required):
        raise ValueError("missing required bar field")
    if raw.get("is_completed") is not True:
        raise ValueError("bar is not confirmed completed")
    timestamp = _timestamp(raw["timestamp_utc"])
    symbol = raw["symbol"]
    timeframe = raw["timeframe"]
    if not isinstance(symbol, str) or not symbol or not isinstance(timeframe, str) or not timeframe:
        raise ValueError("symbol and timeframe must be non-empty strings")
    values = {key: raw[key] for key in ("open_bid", "high_bid", "low_bid", "close_bid", "spread_points", "point_size")}
    for key, value in values.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(f"invalid {key}")
    if any(values[key] <= 0 for key in ("open_bid", "high_bid", "low_bid", "close_bid", "point_size")):
        raise ValueError("price and point_size must be positive")
    if values["spread_points"] < 0 or values["high_bid"] < values["low_bid"]:
        raise ValueError("invalid spread or OHLC range")
    return {"timestamp": timestamp, "symbol": symbol, "timeframe": timeframe, **values}


def _true_ranges(history: Sequence[Mapping[str, Any]]) -> list[float]:
    return [
        max(
            bar["high_bid"] - bar["low_bid"],
            abs(bar["high_bid"] - previous["close_bid"]),
            abs(bar["low_bid"] - previous["close_bid"]),
        )
        for previous, bar in zip(history, history[1:])
    ]


def _wilder_atr(history: Sequence[Mapping[str, Any]], period: int) -> float | None:
    ranges = _true_ranges(history)
    if len(ranges) < period:
        return None
    atr = sum(ranges[:period]) / period
    for true_range in ranges[period:]:
        atr = ((period - 1) * atr + true_range) / period
    return atr


def _ratio(history: Sequence[Mapping[str, Any]]) -> float | None:
    fast = _wilder_atr(history, EXPECTED_CONFIG["fast_period"])
    slow = _wilder_atr(history, EXPECTED_CONFIG["slow_period"])
    if fast is None or slow is None or slow <= 0 or not math.isfinite(fast) or not math.isfinite(slow):
        return None
    return fast / slow


def make_event(*, symbol: str, timeframe: str, decision_timestamp: datetime, direction: str, source_index: int) -> dict[str, Any]:
    if direction not in {"long", "short", "none"}:
        raise ValueError("direction must be long, short, or none")
    timestamp = _timestamp_text(decision_timestamp)
    preimage = "|".join(
        (
            FAMILY_ID,
            FAMILY_ID,
            symbol,
            timeframe,
            timestamp,
            "below_to_above",
            direction,
            "atr14=14",
            "atr56=56",
            "threshold=1.20",
            "warmup=64",
        )
    )
    return {
        "schema_version": "vrt_event.v1",
        "family_id": FAMILY_ID,
        "preregistration_version": FAMILY_ID,
        "symbol": symbol,
        "timeframe": timeframe,
        "decision_timestamp_utc": timestamp,
        "transition_type": "below_to_above",
        "direction": direction,
        "detector_parameter_version": "atr14=14|atr56=56|threshold=1.20|warmup=64",
        "event_id": _sha256_bytes(preimage.encode("utf-8")),
        "source_index": source_index,
        "terminal_category": "no_direction" if direction == "none" else "raw",
    }


def event_order_key(event: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(event["decision_timestamp_utc"]),
        str(event["symbol"]),
        str(event["timeframe"]),
        str(event["event_id"]),
    )


def suppress_duplicate_events(events: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in sorted(events, key=lambda item: int(item["source_index"])):
        copied = dict(event)
        event_id = str(copied.get("event_id", ""))
        if not event_id:
            raise ValueError("event identity is incomplete")
        if event_id in seen:
            copied["terminal_category"] = "duplicate_event"
            suppressed.append(copied)
        else:
            seen.add(event_id)
            kept.append(copied)
    return kept, suppressed


def classify_overlap(events: Sequence[Mapping[str, Any]], active_until_by_stream: Mapping[str, int] | None = None) -> list[dict[str, Any]]:
    """Classify outcome overlap without deleting or changing raw detector events."""
    active = active_until_by_stream or {}
    classified = []
    for event in events:
        copied = dict(event)
        stream = f"{copied['symbol']}:{copied['timeframe']}"
        if copied.get("terminal_category") == "raw" and int(copied["source_index"]) <= active.get(stream, -1):
            copied["terminal_category"] = "suppressed_overlap"
        classified.append(copied)
    return classified


def _audit(events: Sequence[Mapping[str, Any]], suppressed: Sequence[Mapping[str, Any]], resets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    terminal_counts = Counter(str(event["terminal_category"]) for event in [*events, *suppressed])
    return {
        "schema_version": "vrt_detector_audit.v1",
        "family_id": FAMILY_ID,
        "execution_disabled": True,
        "broker_api_called": False,
        "real_data": False,
        "raw_event_count": len(events) + len(suppressed),
        "terminal_category_counts": dict(sorted(terminal_counts.items())),
        "stream_resets": list(resets),
        "terminal_funnel_reconciled": len(events) + len(suppressed) == sum(terminal_counts.values()),
    }


def activation_record_schema() -> dict[str, Any]:
    """Return the future activation-record contract without creating an activation."""
    return {
        "schema_version": "vrt_activation_record.v1",
        "required_fields": [
            "family_id", "preregistration_commit", "implementation_commit",
            "provenance_artifact_sha256", "execution_configuration_sha256",
            "conformance_test_result_reference", "activation_record_commit",
            "activation_timestamp_utc", "symbols_timeframes", "software_versions",
            "schema_versions",
        ],
        "activation_permitted": False,
    }


def observation_record_schema() -> dict[str, Any]:
    """Return the future irreversible-observation contract without observing data."""
    return {
        "schema_version": "vrt_observation_record.v1",
        "required_fields": [
            "preregistration_version", "implementation_commit", "activation_record",
            "input_artifact_hashes", "execution_configuration_hash", "command",
            "start_timestamp_utc", "output_directory", "expected_report_schemas",
        ],
        "observation_permitted": False,
    }


def generate_events_reference(
    bars: Sequence[Mapping[str, Any]],
    *,
    active_until_by_stream: Mapping[str, int] | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Generate the frozen ordered raw event stream from synthetic bars only."""
    conformance = validate_preregistration_conformance(manifest_path)
    streams: dict[tuple[str, str], _StreamState] = {}
    raw_events: list[dict[str, Any]] = []
    resets: list[dict[str, Any]] = []
    for source_index, raw in enumerate(bars):
        try:
            bar = _normalise_bar(raw)
        except (TypeError, ValueError) as exc:
            if isinstance(raw, Mapping):
                symbol = raw.get("symbol")
                timeframe = raw.get("timeframe")
                if isinstance(symbol, str) and symbol and isinstance(timeframe, str) and timeframe:
                    affected = streams.setdefault((symbol, timeframe), _StreamState())
                    affected.history.clear()
                    affected.regime = RegimeState.UNAVAILABLE
                    affected.last_timestamp = None
            resets.append({"source_index": source_index, "reason": "invalid_input", "detail": str(exc)})
            continue
        key = (bar["symbol"], bar["timeframe"])
        state = streams.setdefault(key, _StreamState())
        if state.last_timestamp is not None:
            if bar["timestamp"] == state.last_timestamp:
                state.history.clear()
                state.regime = RegimeState.UNAVAILABLE
                resets.append({"source_index": source_index, "reason": "duplicate_timestamp"})
                continue
            if bar["timestamp"] < state.last_timestamp:
                state.history.clear()
                state.regime = RegimeState.UNAVAILABLE
                resets.append({"source_index": source_index, "reason": "non_monotonic_timestamp"})
                continue
            if bar["timestamp"] - state.last_timestamp > EXPECTED_CONFIG["gap_multiplier"] * _timeframe_duration(bar["timeframe"]):
                state.history.clear()
                state.regime = RegimeState.UNAVAILABLE
                resets.append({"source_index": source_index, "reason": "gap"})
        state.history.append(bar)
        state.last_timestamp = bar["timestamp"]
        if len(state.history) < EXPECTED_CONFIG["warmup_bars"]:
            continue
        ratio = _ratio(state.history)
        if ratio is None:
            state.regime = RegimeState.UNAVAILABLE
            resets.append({"source_index": source_index, "reason": "unavailable_ratio"})
            continue
        if state.regime is RegimeState.UNAVAILABLE:
            state.regime = classify_regime(ratio)
            continue
        state.regime, transition = advance_regime_state(state.regime, ratio)
        if not transition:
            continue
        prior_close = state.history[-9]["close_bid"]
        direction = "long" if bar["close_bid"] > prior_close else "short" if bar["close_bid"] < prior_close else "none"
        raw_events.append(
            make_event(
                symbol=bar["symbol"], timeframe=bar["timeframe"],
                decision_timestamp=bar["timestamp"] + _timeframe_duration(bar["timeframe"]),
                direction=direction, source_index=source_index,
            )
        )
    kept, suppressed = suppress_duplicate_events(raw_events)
    classified = classify_overlap(kept, active_until_by_stream)
    ordered = sorted(classified, key=event_order_key)
    return {
        "schema_version": "vrt_event_stream.v1",
        "conformance": conformance,
        "events": ordered,
        "audit": _audit(ordered, suppressed, resets),
    }


def generate_events(
    bars: Sequence[Mapping[str, Any]], *, active_until_by_stream: Mapping[str, int] | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Linear-time implementation exactly equivalent to ``generate_events_reference``."""
    conformance = validate_preregistration_conformance(manifest_path)
    streams: dict[tuple[str, str], _StreamState] = {}
    raw_events: list[dict[str, Any]] = []
    resets: list[dict[str, Any]] = []

    def reset(state: _StreamState) -> None:
        state.history.clear()
        state.true_ranges.clear()
        state.fast_atr = state.slow_atr = None
        state.regime = RegimeState.UNAVAILABLE

    for source_index, raw in enumerate(bars):
        try:
            bar = _normalise_bar(raw)
        except (TypeError, ValueError) as exc:
            if isinstance(raw, Mapping) and isinstance(raw.get("symbol"), str) and raw.get("symbol") and isinstance(raw.get("timeframe"), str) and raw.get("timeframe"):
                affected = streams.setdefault((raw["symbol"], raw["timeframe"]), _StreamState())
                reset(affected)
                affected.last_timestamp = None
            resets.append({"source_index": source_index, "reason": "invalid_input", "detail": str(exc)})
            continue
        state = streams.setdefault((bar["symbol"], bar["timeframe"]), _StreamState())
        if state.last_timestamp is not None:
            if bar["timestamp"] == state.last_timestamp:
                reset(state)
                resets.append({"source_index": source_index, "reason": "duplicate_timestamp"})
                continue
            if bar["timestamp"] < state.last_timestamp:
                reset(state)
                resets.append({"source_index": source_index, "reason": "non_monotonic_timestamp"})
                continue
            if bar["timestamp"] - state.last_timestamp > EXPECTED_CONFIG["gap_multiplier"] * _timeframe_duration(bar["timeframe"]):
                reset(state)
                resets.append({"source_index": source_index, "reason": "gap"})
        if state.history:
            previous = state.history[-1]
            current_tr = max(bar["high_bid"] - bar["low_bid"], abs(bar["high_bid"] - previous["close_bid"]), abs(bar["low_bid"] - previous["close_bid"]))
            state.true_ranges.append(current_tr)
            count = len(state.true_ranges)
            if count == EXPECTED_CONFIG["fast_period"]:
                state.fast_atr = sum(state.true_ranges) / count
            elif count > EXPECTED_CONFIG["fast_period"] and state.fast_atr is not None:
                state.fast_atr = ((EXPECTED_CONFIG["fast_period"] - 1) * state.fast_atr + current_tr) / EXPECTED_CONFIG["fast_period"]
            if count == EXPECTED_CONFIG["slow_period"]:
                state.slow_atr = sum(state.true_ranges) / count
            elif count > EXPECTED_CONFIG["slow_period"] and state.slow_atr is not None:
                state.slow_atr = ((EXPECTED_CONFIG["slow_period"] - 1) * state.slow_atr + current_tr) / EXPECTED_CONFIG["slow_period"]
        state.history.append(bar)
        state.last_timestamp = bar["timestamp"]
        if len(state.history) < EXPECTED_CONFIG["warmup_bars"]:
            continue
        if state.fast_atr is None or state.slow_atr is None or state.slow_atr <= 0 or not math.isfinite(state.fast_atr) or not math.isfinite(state.slow_atr):
            state.regime = RegimeState.UNAVAILABLE
            resets.append({"source_index": source_index, "reason": "unavailable_ratio"})
            continue
        ratio = state.fast_atr / state.slow_atr
        if state.regime is RegimeState.UNAVAILABLE:
            state.regime = classify_regime(ratio)
            continue
        state.regime, transition = advance_regime_state(state.regime, ratio)
        if not transition:
            continue
        prior_close = state.history[-9]["close_bid"]
        direction = "long" if bar["close_bid"] > prior_close else "short" if bar["close_bid"] < prior_close else "none"
        raw_events.append(make_event(symbol=bar["symbol"], timeframe=bar["timeframe"], decision_timestamp=bar["timestamp"] + _timeframe_duration(bar["timeframe"]), direction=direction, source_index=source_index))
    kept, suppressed = suppress_duplicate_events(raw_events)
    ordered = sorted(classify_overlap(kept, active_until_by_stream), key=event_order_key)
    return {"schema_version": "vrt_event_stream.v1", "conformance": conformance, "events": ordered, "audit": _audit(ordered, suppressed, resets)}
