from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

import pytest

from trading_bot.research import trend_continuation_after_pullback as tcp


def _bar(
    index: int,
    *,
    close: float,
    high: float | None = None,
    low: float | None = None,
    symbol: str = "XAUUSD",
    timeframe: str = "M5",
) -> dict:
    return {
        "timestamp_utc": datetime(2026, 1, 1, tzinfo=UTC)
        + timedelta(minutes=5 * index),
        "symbol": symbol,
        "timeframe": timeframe,
        "open_bid": close - 0.03,
        "high_bid": close + 0.10 if high is None else high,
        "low_bid": close - 0.10 if low is None else low,
        "close_bid": close,
        "spread_points": 10.0,
        "point_size": 0.01,
        "is_completed": True,
    }


def _long_pullback_fixture() -> list[dict]:
    rows = [_bar(index, close=100.0 + 0.10 * index) for index in range(70)]
    rows.append(_bar(70, close=106.45, high=106.55, low=105.95))
    rows.append(_bar(71, close=107.15, high=107.25, low=106.70))
    rows.extend(
        _bar(index, close=107.15 + 0.1 * (index - 71)) for index in range(72, 83)
    )
    return rows


def _short_pullback_fixture() -> list[dict]:
    rows = [
        _bar(index, close=120.0 - 0.10 * index, symbol="EURUSD") for index in range(70)
    ]
    rows.append(_bar(70, close=113.55, high=114.05, low=113.45, symbol="EURUSD"))
    rows.append(_bar(71, close=112.85, high=113.30, low=112.75, symbol="EURUSD"))
    rows[71]["open_bid"] = 112.95
    rows.extend(
        _bar(index, close=112.85 - 0.1 * (index - 71), symbol="EURUSD")
        for index in range(72, 83)
    )
    return rows


def test_frozen_specification_is_independent_and_fail_closed(tmp_path):
    conformance = tcp.validate_specification_conformance()
    assert conformance["family_id"] == tcp.FAMILY_ID
    broken = copy.deepcopy(tcp.load_specification())
    broken["detector"]["ema"]["fast_period"] = 21
    path = tmp_path / "broken.json"
    path.write_text(__import__("json").dumps(broken), encoding="utf-8")
    with pytest.raises(tcp.SpecificationConformanceError):
        tcp.validate_specification_conformance(path)


def test_no_trend_warmup_and_equalities_do_not_create_event():
    flat = [_bar(index, close=100.0) for index in range(80)]
    result = tcp.generate_events(flat)
    assert result["events"] == []
    assert result["audit"]["raw_event_count"] == 0


@pytest.mark.parametrize(
    "fixture,direction",
    [(_long_pullback_fixture, "long"), (_short_pullback_fixture, "short")],
)
def test_completed_confirmation_creates_canonical_event(fixture, direction):
    result = tcp.generate_events(fixture())
    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["direction"] == direction
    assert event["decision_timestamp_utc"].endswith("Z")
    assert event["event_id"] == tcp.canonical_event_id(event)


def test_excessive_pullback_invalidation_duration_cooldown_and_rearm():
    rows = _long_pullback_fixture()
    rows[70]["low_bid"] = 90.0
    assert tcp.generate_events(rows)["events"] == []

    rows = _long_pullback_fixture()
    for index in range(71, 78):
        rows[index]["close_bid"] = 106.2
        rows[index]["high_bid"] = 106.3
        rows[index]["low_bid"] = 106.0
    assert tcp.generate_events(rows[:78])["events"] == []

    rows = _long_pullback_fixture()
    rows.append(_bar(83, close=107.8, high=107.9, low=107.3))
    rows.append(_bar(84, close=108.5, high=108.6, low=108.3))
    assert len(tcp.generate_events(rows)["events"]) == 2


def test_missing_gap_duplicate_and_overlap_are_fail_closed_and_deterministic():
    rows = _long_pullback_fixture()
    missing = copy.deepcopy(rows)
    missing[70]["close_bid"] = None
    assert tcp.generate_events(missing)["events"] == []

    gapped = copy.deepcopy(rows)
    gapped[70]["timestamp_utc"] += timedelta(hours=2)
    assert tcp.generate_events(gapped)["events"] == []

    duplicate = copy.deepcopy(rows)
    duplicate.insert(70, copy.deepcopy(duplicate[69]))
    result = tcp.generate_events(duplicate, active_until_by_stream={"XAUUSD:M5": 999})
    assert result["audit"]["reset_count"] >= 1
    assert all(
        event["terminal_category"] == "suppressed_overlap" for event in result["events"]
    )


def test_event_order_ids_and_linear_operation_count_are_stream_isolated():
    rows = _long_pullback_fixture() + _short_pullback_fixture()
    result = tcp.generate_events(rows)
    assert result["events"] == sorted(result["events"], key=tcp.event_order_key)
    assert len({event["event_id"] for event in result["events"]}) == len(
        result["events"]
    )
    assert result["audit"]["linear_operations"] <= len(rows) * 16
