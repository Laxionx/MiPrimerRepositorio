"""Frozen timezone-aware Session Transition detector."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

FAMILY_ID = "session-transition-st-20260713-v1"
SPECIFICATION_PATH = Path(
    "docs/research_preregistrations/session_transition_2026-07-13/specification.json"
)
STRICT_PREDICTORS = (
    "pre_session_range_atr",
    "breakout_distance_atr",
    "confirmation_body_atr",
    "confirmation_close_location",
    "pre_session_directional_efficiency",
    "atr_short_long_ratio",
    "session_gap_atr",
    "bars_to_confirmation",
)
TIMEFRAME_SECONDS = {"M5": 300, "M15": 900, "H1": 3600}
SESSIONS = {
    "london_open": ("Europe/London", time(8)),
    "new_york_cash_open": ("America/New_York", time(9, 30)),
}
CONDITIONS = (">=1.0", ">=0.25", ">=0.25", ">=0.60", ">=0.50", ">=1.0", ">=0.25", "==1")


class SpecificationConformanceError(ValueError):
    pass


def load_specification(path: str | Path | None = None) -> dict[str, Any]:
    source = Path(path) if path else Path(__file__).parents[2] / SPECIFICATION_PATH
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecificationConformanceError("invalid specification") from exc
    if not isinstance(value, dict):
        raise SpecificationConformanceError("specification must be object")
    return value


def validate_specification_conformance(
    path: str | Path | None = None,
) -> dict[str, Any]:
    spec = load_specification(path)
    detector = spec.get("detector", {})
    if (
        spec.get("schema_version") != "session_transition_specification.v1"
        or spec.get("family", {}).get("id") != FAMILY_ID
    ):
        raise SpecificationConformanceError("family mismatch")
    expected = {
        "weekdays_only": True,
        "pre_session_completed_bars": 12,
        "pre_session_alignment": "12_contiguous_bars_with_close_timestamp_lte_session_start",
        "confirmation_window_completed_bars": 3,
        "unaligned_timeframe_policy": "first_bar_open_timestamp_gte_timezone_converted_session_start",
        "decision_timestamp": "utc_close_timestamp_of_completed_confirmation_bar_t",
    }
    if any(detector.get(key) != value for key, value in expected.items()):
        raise SpecificationConformanceError("detector mismatch")
    if detector.get("sessions") != [
        {"type": "london_open", "timezone": "Europe/London", "local_time": "08:00"},
        {
            "type": "new_york_cash_open",
            "timezone": "America/New_York",
            "local_time": "09:30",
        },
    ]:
        raise SpecificationConformanceError("sessions mismatch")
    if (
        detector.get("atr", {}).get("period") != 14
        or detector.get("warmup", {}).get("minimum_contiguous_completed_bars") != 60
    ):
        raise SpecificationConformanceError("indicator mismatch")
    predictors = spec.get("strict_predictors")
    if (
        not isinstance(predictors, list)
        or tuple(x.get("name") for x in predictors) != STRICT_PREDICTORS
        or tuple(x.get("candidate_condition") for x in predictors) != CONDITIONS
    ):
        raise SpecificationConformanceError("predictor mismatch")
    if any(
        x.get("timing") != "pre_decision"
        or x.get("missing_value_policy") != "unavailable_fail_closed_no_imputation"
        or x.get("strict_eligibility") is not True
        for x in predictors
    ):
        raise SpecificationConformanceError("provenance mismatch")
    if spec.get("order_api_permitted") is not False:
        raise SpecificationConformanceError("safety mismatch")
    return {
        "family_id": FAMILY_ID,
        "specification_sha256": hashlib.sha256(
            json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(UTC)


def session_start_utc(session_type: str, local_date: date) -> datetime:
    zone, local_time = SESSIONS[session_type]
    return datetime.combine(local_date, local_time, ZoneInfo(zone)).astimezone(UTC)


def window_start_index(
    rows: Sequence[Mapping[str, Any]], start: datetime
) -> int | None:
    return next(
        (i for i, row in enumerate(rows) if _ts(row["timestamp_utc"]) >= start), None
    )


def _bar(raw: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
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
    if (
        not isinstance(raw, Mapping)
        or any(k not in raw for k in keys)
        or raw["is_completed"] is not True
        or raw["timeframe"] not in TIMEFRAME_SECONDS
    ):
        raise ValueError("invalid input")
    row = {k: raw[k] for k in keys}
    row["timestamp_utc"] = _ts(row["timestamp_utc"])
    for key in keys[3:9]:
        row[key] = float(row[key])
        if not math.isfinite(row[key]):
            raise ValueError("invalid number")
    if (
        row["high_bid"] < row["low_bid"]
        or row["point_size"] <= 0
        or row["spread_points"] < 0
    ):
        raise ValueError("invalid geometry")
    return row


def _indicators(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[int, dict[str, Any] | None], list[dict[str, Any]]]:
    result = {}
    resets = []
    history = []
    trs = []
    eligible = []
    atr = None
    last = None
    segment = 0
    for index, row in enumerate(rows):
        timestamp = _ts(row["timestamp_utc"])
        if last is not None and timestamp <= last:
            history = []
            trs = []
            eligible = []
            atr = None
            segment += 1
            resets.append({"source_index": index, "reason": "duplicate_timestamp"})
            result[index] = None
            continue
        if last is not None and timestamp - last > timedelta(
            seconds=3 * TIMEFRAME_SECONDS[row["timeframe"]]
        ):
            history = []
            trs = []
            eligible = []
            atr = None
            segment += 1
            resets.append({"source_index": index, "reason": "gap"})
        if history:
            prior = history[-1]
            tr = max(
                row["high_bid"] - row["low_bid"],
                abs(row["high_bid"] - prior["close_bid"]),
                abs(row["low_bid"] - prior["close_bid"]),
            )
            trs.append(tr)
            if len(trs) == 14:
                atr = sum(trs) / 14
            elif len(trs) > 14 and atr is not None:
                atr = (13 * atr + tr) / 14
        prior_mean = sum(eligible[-50:]) / 50 if len(eligible) >= 50 else None
        history.append(row)
        last = timestamp
        if atr is not None and atr > 0:
            eligible.append(atr)
        result[index] = (
            None
            if len(history) < 60 or atr is None or atr <= 0 or prior_mean is None
            else {"atr": atr, "prior_atr50_mean": prior_mean, "segment": segment}
        )
    return result, resets


def _event_id(event: Mapping[str, Any]) -> str:
    value = "|".join(
        (
            FAMILY_ID,
            str(event["symbol"]),
            str(event["timeframe"]),
            str(event["session_type"]),
            str(event["local_session_date"]),
            str(event["decision_timestamp_utc"]),
            str(event["direction"]),
            "st_detector_v1",
        )
    )
    return hashlib.sha256(value.encode()).hexdigest()


def canonical_event_id(event: Mapping[str, Any]) -> str:
    return _event_id(event)


def event_order_key(event: Mapping[str, Any]) -> tuple[datetime, str, str, str]:
    return (
        _ts(event["decision_timestamp_utc"]),
        str(event["symbol"]),
        str(event["timeframe"]),
        str(event["event_id"]),
    )


def _dates(rows: Sequence[Mapping[str, Any]], session_type: str) -> list[date]:
    zone = ZoneInfo(SESSIONS[session_type][0])
    return sorted(
        {
            _ts(row["timestamp_utc"]).astimezone(zone).date()
            for row in rows
            if _ts(row["timestamp_utc"]).astimezone(zone).weekday() < 5
        }
    )


def _stream_events(
    rows: list[dict[str, Any]], source_indices: list[int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    indicators, resets = _indicators(rows)
    events = []
    for session_type in SESSIONS:
        for local_date in _dates(rows, session_type):
            start = session_start_utc(session_type, local_date)
            first = window_start_index(rows, start)
            if first is None:
                continue
            duration = timedelta(seconds=TIMEFRAME_SECONDS[rows[0]["timeframe"]])
            pre_end = next(
                (
                    i
                    for i in range(first - 1, -1, -1)
                    if _ts(rows[i]["timestamp_utc"]) + duration <= start
                ),
                None,
            )
            if pre_end is None or pre_end < 11:
                continue
            pre = list(range(pre_end - 11, pre_end + 1))
            segment = (
                indicators[first].get("segment") if indicators.get(first) else None
            )
            if segment is None or any(
                indicators.get(i) is None or indicators[i]["segment"] != segment
                for i in pre
            ):
                continue
            high = max(rows[i]["high_bid"] for i in pre)
            low = min(rows[i]["low_bid"] for i in pre)
            closes = [rows[i]["close_bid"] for i in pre]
            denom = sum(abs(b - a) for a, b in zip(closes, closes[1:]))
            for position, index in enumerate(
                range(first, min(first + 3, len(rows))), 1
            ):
                base = indicators.get(index)
                if base is None or base["segment"] != segment:
                    break
                row = rows[index]
                direction = (
                    "long"
                    if row["close_bid"] > high and row["close_bid"] > row["open_bid"]
                    else "short"
                    if row["close_bid"] < low and row["close_bid"] < row["open_bid"]
                    else None
                )
                if direction is None:
                    continue
                rng = row["high_bid"] - row["low_bid"]
                if rng <= 0 or denom <= 0:
                    break
                event = {
                    "family_id": FAMILY_ID,
                    "symbol": row["symbol"],
                    "timeframe": row["timeframe"],
                    "session_type": session_type,
                    "local_session_date": local_date.isoformat(),
                    "direction": direction,
                    "decision_timestamp_utc": (row["timestamp_utc"] + duration)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "source_index": source_indices[index],
                    "stream_index": index,
                    "bars_to_confirmation": position,
                    "pre_session_high": high,
                    "pre_session_low": low,
                    "pre_closes": closes,
                    "first_window_open": rows[first]["open_bid"],
                    "pre_session_final_close": rows[pre[-1]]["close_bid"],
                    "terminal_category": "raw",
                }
                event["event_id"] = _event_id(event)
                events.append(event)
                break
    return events, resets, len(rows)


def generate_events(
    bars: Sequence[Mapping[str, Any]],
    *,
    active_until_by_stream: Mapping[str, int] | None = None,
    specification_path: str | Path | None = None,
) -> dict[str, Any]:
    conformance = validate_specification_conformance(specification_path)
    streams = {}
    invalid_sources: dict[tuple[str, str], list[int]] = {}
    resets = []
    for source_index, raw in enumerate(bars):
        try:
            row = _bar(raw)
        except (TypeError, ValueError) as exc:
            if (
                isinstance(raw, Mapping)
                and isinstance(raw.get("symbol"), str)
                and raw.get("timeframe") in TIMEFRAME_SECONDS
            ):
                invalid_sources.setdefault(
                    (raw["symbol"], raw["timeframe"]), []
                ).append(source_index)
            resets.append(
                {
                    "source_index": source_index,
                    "reason": "invalid_input",
                    "detail": str(exc),
                }
            )
            continue
        streams.setdefault((row["symbol"], row["timeframe"]), []).append(
            (source_index, row)
        )
    raw_events = []
    operations = 0
    for key, entries in streams.items():
        entries.sort(key=lambda pair: pair[1]["timestamp_utc"])
        events, local_resets, count = _stream_events(
            [row for _, row in entries], [index for index, _ in entries]
        )
        raw_events.extend(
            event
            for event in events
            if not any(
                event["source_index"] - 15 <= invalid <= event["source_index"]
                for invalid in invalid_sources.get(key, [])
            )
        )
        resets.extend(local_resets)
        operations += count
    unique = {}
    for event in sorted(
        raw_events, key=lambda row: (row["source_index"], row["event_id"])
    ):
        unique.setdefault(event["event_id"], event)
    events = list(unique.values())
    for event in events:
        if active_until_by_stream and event[
            "stream_index"
        ] <= active_until_by_stream.get(f"{event['symbol']}:{event['timeframe']}", -1):
            event["terminal_category"] = "suppressed_overlap"
    events.sort(key=event_order_key)
    return {
        "schema_version": "session_transition_event_stream.v1",
        "conformance": conformance,
        "events": events,
        "audit": {
            "raw_event_count": len(events),
            "duplicate_event_count": len(raw_events) - len(events),
            "reset_count": len(resets),
            "resets": resets,
            "terminal_category_counts": dict(
                sorted(Counter(e["terminal_category"] for e in events).items())
            ),
            "linear_operations": operations,
        },
    }
