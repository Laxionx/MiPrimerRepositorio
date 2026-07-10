import inspect
import json

import pytest

from trading_bot.research import edge_v2_candidate_discriminator_audit as audit


def trade(trade_id, pnl, timestamp, **fields):
    return {
        "trade_id": trade_id,
        "pnl": pnl,
        "timestamp_open": timestamp,
        "lower_quartile_closes": 0,
        "direction": "LONG" if pnl > 0 else "SHORT",
        "timeframe": "M5",
        "risk_points": 2 if pnl > 0 else 8,
        "reward_points": 8 if pnl > 0 else 12,
        "candle_range": 4 if pnl > 0 else 10,
        "prior_range_points": 20,
        "atr": 5,
        **fields,
    }


def records():
    return [
        trade("w1", 8, "2026-01-01T00:00:00+00:00", risk_points=1),
        trade("l1", -5, "2026-01-02T00:00:00+00:00", risk_points=9),
        trade("w2", 6, "2026-01-03T00:00:00+00:00", risk_points=2),
        trade("l2", -4, "2026-01-04T00:00:00+00:00", risk_points=10),
        trade("w3", 7, "2026-01-05T00:00:00+00:00", risk_points=1),
        trade("l3", -6, "2026-01-06T00:00:00+00:00", risk_points=8),
        trade("w4", 5, "2026-01-07T00:00:00+00:00", risk_points=2),
        trade("l4", -3, "2026-01-08T00:00:00+00:00", risk_points=9),
        trade("outside", 99, "2026-01-09T00:00:00+00:00", lower_quartile_closes=1),
    ]


def test_candidate_list_and_leakage_metadata_are_fixed_and_conservative():
    report = audit.analyze_candidate_discriminator_records(records())

    assert report["candidate_list"] == list(audit.CANDIDATES)
    metadata = report["raw_discriminators"]["risk_points"]["leakage_metadata"]
    assert metadata["availability_timing"] == "unknown"
    assert metadata["leakage_risk"] == "unknown"
    assert audit.field_leakage_metadata("r_multiple") == {
        "availability_timing": "post_trade",
        "leakage_risk": "high",
        "reason": "Outcome-derived field is only known after trade completion.",
    }


def test_raw_separation_contains_required_summary_fields():
    separation = audit.analyze_candidate_discriminator_records(records())["raw_discriminators"]["risk_points"]["winner_loser_separation"]

    assert separation["sample_count"] == 8
    assert separation["winner_count"] == 4
    assert separation["loser_count"] == 4
    assert separation["winner_mean"] == 1.5
    assert separation["loser_mean"] == 9.0
    assert separation["winner_p25"] is not None
    assert separation["loser_p75"] is not None
    assert separation["separation_flag"] == "strong_separation"


def test_ratio_normalizations_and_unavailable_features_are_explicit():
    report = audit.analyze_candidate_discriminator_records(records())

    normalized = report["normalized_discriminators"]
    assert normalized["risk_points_over_candle_range"]["available"] is True
    assert normalized["reward_to_risk_planned"]["available"] is True
    assert normalized["candle_range_over_atr"]["available"] is True

    rows = records()
    for row in rows:
        row.pop("atr", None)
    missing = audit.analyze_candidate_discriminator_records(rows)
    assert "candle_range_over_atr" in missing["normalized_features_unavailable"]


def test_fixed_diagnostic_groups_are_not_optimized():
    report = audit.analyze_candidate_discriminator_records(records())

    raw_groups = report["raw_discriminators"]["risk_points"]["diagnostic_groups"]
    assert set(raw_groups) == {"bottom_25", "middle_50", "top_25"}
    ratio_groups = report["normalized_discriminators"]["reward_to_risk_planned"]["diagnostic_groups"]
    assert set(ratio_groups) == {"lt_1", "1_to_lt_1_5", "1_5_to_lt_2", "gte_2"}
    assert report["diagnostic_groups_optimized"] is False


def test_segments_and_calibration_use_first_half_only():
    report = audit.analyze_candidate_discriminator_records(records())

    assert set(report["segment_checks"]) == {
        "all", "LONG", "SHORT", "M5", "M15", "first_half", "second_half"
    }
    calibration = report["calibration_diagnostic"]["risk_points"]
    assert calibration["calibration_trade_count"] == 4
    assert calibration["test_trade_count"] == 4
    assert calibration["selected_direction"] == "lower"
    assert calibration["threshold_used"] == 5.5
    assert calibration["test_selected_trade_count"] == 2


def test_missing_condition_invalid_input_and_no_execution_path(tmp_path):
    with pytest.raises(ValueError, match="Unknown predefined condition"):
        audit.analyze_candidate_discriminator_records(records(), condition="tuned_rule")

    valid = tmp_path / "trades.jsonl"
    valid.write_text("\n".join(json.dumps(row) for row in records()), encoding="utf-8")
    report = audit.analyze_candidate_discriminator_journals([valid, tmp_path / "missing.jsonl"])
    assert report["valid_source_count"] == 1
    assert report["invalid_source_count"] == 1

    source = inspect.getsource(audit)
    assert "order_send" not in source
    assert "submit_allowed=True" not in source
