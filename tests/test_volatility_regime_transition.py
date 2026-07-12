from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from trading_bot.research import volatility_regime_transition as vrt


BASE = datetime(2026, 7, 1, tzinfo=UTC)


def _bar(index: int, *, range_size: float = 1.0, close: float | None = None, symbol: str = "XAUUSD", timeframe: str = "M5") -> dict:
    opening = 100.0 if close is None else close - 0.1
    closing = opening + 0.1 if close is None else close
    return {
        "timestamp_utc": BASE + timedelta(minutes=5 * index),
        "symbol": symbol,
        "timeframe": timeframe,
        "open_bid": opening,
        "high_bid": max(opening, closing) + range_size / 2,
        "low_bid": min(opening, closing) - range_size / 2,
        "close_bid": closing,
        "spread_points": 10.0,
        "point_size": 0.01,
    }


def _bars(*, count: int = 65, expanded_indexes: set[int] | None = None, symbol: str = "XAUUSD", timeframe: str = "M5") -> list[dict]:
    expanded_indexes = expanded_indexes or set()
    return [
        _bar(index, range_size=20.0 if index in expanded_indexes else 1.0, close=100.0 + index * 0.1, symbol=symbol, timeframe=timeframe)
        for index in range(count)
    ]


def test_manifest_conformance_and_registry_are_frozen():
    report = vrt.validate_preregistration_conformance()

    assert report["ok"] is True
    assert report["config"]["threshold"] == 1.2
    assert report["config"]["warmup_bars"] == 64
    assert report["strict_predictors"] == [
        "atr_14_points", "atr_56_points", "atr_ratio_14_56", "atr_ratio_change_8",
        "mean_range_8_points", "mean_range_56_points", "range_ratio_8_56", "efficiency_20",
    ]


def test_manifest_missing_or_changed_parameter_fails_closed(tmp_path):
    manifest = vrt.load_preregistration_manifest()
    manifest["detector"]["threshold"]["value"] = 1.21
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(vrt.ManifestConformanceError, match="threshold"):
        vrt.validate_preregistration_conformance(path)

    path.write_text("{}", encoding="utf-8")
    with pytest.raises(vrt.ManifestConformanceError):
        vrt.validate_preregistration_conformance(path)


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(1.19, vrt.RegimeState.BELOW), (1.20, vrt.RegimeState.ABOVE), (1.21, vrt.RegimeState.ABOVE)],
)
def test_threshold_boundaries_are_frozen(ratio, expected):
    assert vrt.classify_regime(ratio) is expected


def test_no_transition_during_warmup_or_steady_below_regime():
    result = vrt.generate_events(_bars(count=64))

    assert result["events"] == []
    assert result["audit"]["raw_event_count"] == 0


def test_valid_transition_is_confirmed_on_same_completed_bar():
    result = vrt.generate_events(_bars(expanded_indexes={64}))

    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["transition_type"] == "below_to_above"
    assert event["decision_timestamp_utc"] == "2026-07-01T05:20:00Z"
    assert event["direction"] == "long"
    assert event["terminal_category"] == "raw"


def test_initial_above_state_does_not_emit_until_reset_and_rearming():
    state = vrt.RegimeState.ABOVE

    state, transition = vrt.advance_regime_state(state, 1.19)
    assert state is vrt.RegimeState.BELOW
    assert transition is False

    state, transition = vrt.advance_regime_state(state, 1.20)
    assert state is vrt.RegimeState.ABOVE
    assert transition is True


def test_no_cooldown_and_one_event_per_rearmed_crossing():
    state = vrt.RegimeState.BELOW
    state, first = vrt.advance_regime_state(state, 1.20)
    state, duplicate = vrt.advance_regime_state(state, 1.21)
    state, reset = vrt.advance_regime_state(state, 1.19)
    state, second = vrt.advance_regime_state(state, 1.20)

    assert (first, duplicate, reset, second) == (True, False, False, True)


def test_missing_and_gap_reset_the_stream_and_require_new_warmup():
    bars = _bars(expanded_indexes={64})
    bars[20]["close_bid"] = None
    bars[64]["timestamp_utc"] = bars[63]["timestamp_utc"] + timedelta(hours=1)

    result = vrt.generate_events(bars)

    assert result["events"] == []
    assert {item["reason"] for item in result["audit"]["stream_resets"]} >= {"invalid_input", "gap"}


def test_missing_value_resets_prior_history_before_a_later_transition():
    bars = _bars(count=66, expanded_indexes={65})
    bars[20]["close_bid"] = None

    result = vrt.generate_events(bars)

    assert result["events"] == []


def test_duplicate_suppression_keeps_first_canonical_event():
    event = {
        "event_id": "same", "source_index": 2, "symbol": "XAUUSD", "timeframe": "M5",
        "decision_timestamp_utc": "2026-07-01T00:00:00Z",
    }
    kept, suppressed = vrt.suppress_duplicate_events([event, {**event, "source_index": 3}])

    assert kept == [event]
    assert suppressed[0]["terminal_category"] == "duplicate_event"


def test_overlap_marks_outcome_without_removing_raw_event():
    event = {
        "event_id": "evt", "source_index": 4, "symbol": "XAUUSD", "timeframe": "M5",
        "decision_timestamp_utc": "2026-07-01T00:20:00Z", "terminal_category": "raw",
    }

    classified = vrt.classify_overlap([event], {"XAUUSD:M5": 4})

    assert classified[0]["terminal_category"] == "suppressed_overlap"
    assert event["terminal_category"] == "raw"


def test_symbol_timeframe_isolation_and_deterministic_ordering():
    bars = _bars(expanded_indexes={64}, symbol="XAUUSD", timeframe="M5")
    bars += _bars(expanded_indexes={64}, symbol="EURUSD", timeframe="M5")
    result = vrt.generate_events(bars)

    assert [event["symbol"] for event in result["events"]] == ["EURUSD", "XAUUSD"]
    assert result["events"] == sorted(result["events"], key=vrt.event_order_key)


def test_event_ids_are_canonical_and_deterministic():
    event = vrt.make_event(
        symbol="XAUUSD", timeframe="M5", decision_timestamp=BASE, direction="long", source_index=0
    )

    assert event["event_id"] == vrt.make_event(
        symbol="XAUUSD", timeframe="M5", decision_timestamp=BASE, direction="long", source_index=99
    )["event_id"]
    assert len(event["event_id"]) == 64
    assert event["event_id"] != vrt.make_event(
        symbol="XAUUSD", timeframe="M5", decision_timestamp=BASE, direction="short", source_index=0
    )["event_id"]


def test_strict_provenance_rejects_late_unknown_or_unregistered_dependencies():
    registry = vrt.build_feature_registry()
    registry["atr_14_points"] = {**registry["atr_14_points"], "timing": "at_entry"}
    with pytest.raises(vrt.ProvenanceContractError, match="atr_14_points"):
        vrt.validate_strict_eligibility(registry)

    registry = vrt.build_feature_registry()
    registry["atr_14_points"] = {**registry["atr_14_points"], "depends_on_fields": ["unknown_field"]}
    with pytest.raises(vrt.ProvenanceContractError, match="unknown_field"):
        vrt.validate_strict_eligibility(registry)


def test_audit_schema_is_execution_disabled_and_has_terminal_reconciliation():
    result = vrt.generate_events(_bars(expanded_indexes={64}))
    audit = result["audit"]

    assert audit["schema_version"] == "vrt_detector_audit.v1"
    assert audit["execution_disabled"] is True
    assert audit["broker_api_called"] is False
    assert audit["raw_event_count"] == audit["terminal_category_counts"]["raw"]


def test_future_activation_and_observation_schemas_match_preregistration_policy():
    activation = vrt.activation_record_schema()
    observation = vrt.observation_record_schema()

    assert activation["schema_version"] == "vrt_activation_record.v1"
    assert "activation_timestamp_utc" in activation["required_fields"]
    assert observation["schema_version"] == "vrt_observation_record.v1"
    assert "input_artifact_hashes" in observation["required_fields"]
