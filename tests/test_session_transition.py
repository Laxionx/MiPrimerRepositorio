from __future__ import annotations

import copy
from datetime import UTC, date, datetime, timedelta

import pytest

from trading_bot.research import session_transition as session


def _bar(index: int, *, timestamp: datetime, close: float, high: float | None = None, low: float | None = None, open_price: float | None = None, symbol: str = "XAUUSD", timeframe: str = "M5") -> dict:
    return {"timestamp_utc": timestamp + timedelta(minutes=5 * index), "symbol": symbol, "timeframe": timeframe, "open_bid": close - 0.02 if open_price is None else open_price, "high_bid": close + 0.08 if high is None else high, "low_bid": close - 0.08 if low is None else low, "close_bid": close, "spread_points": 10.0, "point_size": 0.01, "is_completed": True}


def _london_fixture(*, direction: str = "long", confirmation_bar: int = 1) -> list[dict]:
    start = datetime(2026, 1, 5, tzinfo=UTC)
    rows = [_bar(index, timestamp=start, close=100.0 + 0.01 * index) for index in range(120)]
    pre = rows[84:96]
    if direction == "long":
        boundary = max(row["high_bid"] for row in pre)
        for position in range(confirmation_bar):
            index = 96 + position
            rows[index].update(close_bid=boundary - 0.01, high_bid=boundary, low_bid=boundary - 0.10, open_bid=boundary - 0.02)
        rows[95 + confirmation_bar].update(close_bid=boundary + 0.20, high_bid=boundary + 0.25, low_bid=boundary + 0.02, open_bid=boundary + 0.05)
    else:
        boundary = min(row["low_bid"] for row in pre)
        for position in range(confirmation_bar):
            index = 96 + position
            rows[index].update(close_bid=boundary + 0.01, high_bid=boundary + 0.10, low_bid=boundary, open_bid=boundary + 0.02)
        rows[95 + confirmation_bar].update(close_bid=boundary - 0.20, high_bid=boundary - 0.02, low_bid=boundary - 0.25, open_bid=boundary - 0.05)
    return rows


def test_timezone_calendar_handles_london_and_new_york_dst():
    assert session.session_start_utc("london_open", date(2026, 3, 27)).isoformat() == "2026-03-27T08:00:00+00:00"
    assert session.session_start_utc("london_open", date(2026, 3, 30)).isoformat() == "2026-03-30T07:00:00+00:00"
    assert session.session_start_utc("new_york_cash_open", date(2026, 3, 6)).isoformat() == "2026-03-06T14:30:00+00:00"
    assert session.session_start_utc("new_york_cash_open", date(2026, 3, 9)).isoformat() == "2026-03-09T13:30:00+00:00"


def test_specification_is_independent_and_fail_closed(tmp_path):
    assert session.validate_specification_conformance()["family_id"] == session.FAMILY_ID
    broken = copy.deepcopy(session.load_specification())
    broken["detector"]["confirmation_window_completed_bars"] = 4
    path = tmp_path / "broken.json"
    path.write_text(__import__("json").dumps(broken), encoding="utf-8")
    with pytest.raises(session.SpecificationConformanceError):
        session.validate_specification_conformance(path)


@pytest.mark.parametrize(("direction", "confirmation_bar"), [("long", 1), ("short", 1), ("long", 2), ("long", 3)])
def test_first_breakout_in_three_completed_confirmation_bars_creates_one_event(direction, confirmation_bar):
    result = session.generate_events(_london_fixture(direction=direction, confirmation_bar=confirmation_bar))
    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["direction"] == direction
    assert event["bars_to_confirmation"] == confirmation_bar
    assert event["event_id"] == session.canonical_event_id(event)


def test_no_breakout_warmup_gaps_missing_duplicate_overlap_and_ordering():
    rows = _london_fixture()
    boundary = max(row["high_bid"] for row in rows[84:96])
    for index in range(96, 99):
        rows[index].update(close_bid=boundary - 0.01, high_bid=boundary, low_bid=boundary - 0.10, open_bid=boundary - 0.02)
    assert session.generate_events(rows)["events"] == []
    assert session.generate_events(rows[:59])["events"] == []

    gapped = copy.deepcopy(_london_fixture()); gapped[96]["timestamp_utc"] += timedelta(hours=2)
    assert session.generate_events(gapped)["events"] == []
    missing = copy.deepcopy(_london_fixture()); missing[95]["close_bid"] = None
    assert session.generate_events(missing)["events"] == []
    duplicated = copy.deepcopy(_london_fixture()); duplicated.insert(96, copy.deepcopy(duplicated[95]))
    result = session.generate_events(duplicated, active_until_by_stream={"XAUUSD:M5": 999})
    assert result["audit"]["reset_count"] >= 1
    assert all(row["terminal_category"] == "suppressed_overlap" for row in result["events"])
    assert result["events"] == sorted(result["events"], key=session.event_order_key)


def test_h1_uses_first_open_at_or_after_unaligned_new_york_start_and_future_bars_do_not_change_event():
    start = datetime(2026, 1, 5, tzinfo=UTC)
    rows = [_bar(index, timestamp=start, close=100 + 0.1 * index, timeframe="H1") for index in range(20)]
    for index, row in enumerate(rows): row["timestamp_utc"] = start + timedelta(hours=index)
    result = session.window_start_index(rows, session.session_start_utc("new_york_cash_open", date(2026, 1, 5)))
    assert result == 15
    rows = _london_fixture(); baseline = session.generate_events(rows)["events"][0]
    altered = copy.deepcopy(rows)
    for row in altered[99:]: row["close_bid"] += 1000; row["high_bid"] += 1000; row["low_bid"] += 1000
    assert session.generate_events(altered)["events"][0]["event_id"] == baseline["event_id"]
    assert session.generate_events(rows)["audit"]["linear_operations"] <= len(rows) * 12
