import inspect
import json

import pytest

from trading_bot.research import edge_v2_candidate_discriminator_audit as audit
from trading_bot.research import edge_v2_feature_timing_provenance as provenance


EXPECTED_FIELDS = {
    "risk_points", "reward_points", "candle_range", "prior_range_points",
    "lower_quartile_closes", "price_position_in_range", "pressure_score",
    "compression_score", "sweep_depth", "reclaim_speed", "r_multiple", "pnl",
    "outcome", "range_duration_bars", "atr_contraction_pct", "recent_range_points",
    "upper_quartile_closes", "average_pullback_depth",
}

EXPANDED_STRICT_FIELDS = {
    "range_duration_bars",
    "atr_contraction_pct",
    "recent_range_points",
    "upper_quartile_closes",
    "average_pullback_depth",
}


def _trade(trade_id, pnl, **values):
    return {
        "trade_id": trade_id,
        "timestamp_open": "2026-01-01T00:00:00+00:00",
        "lower_quartile_closes": 0,
        "pnl": pnl,
        "risk_points": 2 if pnl > 0 else 8,
        "reward_points": 6 if pnl > 0 else 12,
        "candle_range": 4 if pnl > 0 else 10,
        "prior_range_points": 20,
        "atr": 5,
        **values,
    }


def test_registry_contains_complete_explicit_entries():
    registry = provenance.PROVENANCE_REGISTRY

    assert EXPECTED_FIELDS.issubset(registry)
    for field, entry in registry.items():
        assert entry["field_name"] == field
        assert set(provenance.REQUIRED_PROVENANCE_KEYS).issubset(entry)


def test_code_verified_and_unknown_and_outcome_classifications():
    assert provenance.get_field_provenance("risk_points")["availability_timing"] == "pre_trade"
    assert provenance.get_field_provenance("risk_points")["leakage_risk"] == "low"
    assert provenance.get_field_provenance("reward_points")["availability_timing"] == "pre_trade"
    assert provenance.get_field_provenance("atr")["availability_timing"] == "pre_trade"
    assert provenance.get_field_provenance("candle_range")["availability_timing"] == "at_entry"
    assert provenance.get_field_provenance("sweep_depth")["availability_timing"] == "unknown"
    for field in ("pnl", "r_multiple", "outcome", "exit_price"):
        item = provenance.get_field_provenance(field)
        assert item["availability_timing"] == "post_trade"
        assert item["leakage_risk"] == "high"


def test_expanded_edge_v3_fields_are_code_verified_strict_pretrade():
    for field in EXPANDED_STRICT_FIELDS:
        entry = provenance.get_field_provenance(field)

        assert entry["source_basis"] == "code_verified"
        assert entry["availability_timing"] == "pre_trade"
        assert entry["leakage_risk"] == "low"
        assert entry["source_module_or_function"]
        assert entry["depends_on_fields"]


def test_normalized_fields_inherit_worst_source_provenance():
    combined = provenance.combine_source_provenance(
        "example",
        [
            provenance.get_field_provenance("risk_points"),
            provenance.get_field_provenance("pnl"),
        ],
    )

    assert combined["availability_timing"] == "post_trade"
    assert combined["leakage_risk"] == "high"
    assert combined["source_fields"] == ["risk_points", "pnl"]


def test_report_supports_journals_and_exposes_required_lists(tmp_path):
    journal = tmp_path / "trades.jsonl"
    journal.write_text(json.dumps(_trade("w", 1)), encoding="utf-8")
    report = provenance.analyze_feature_timing_provenance_journals([journal])

    assert report["inputs_analyzed"] == 1
    assert "risk_points" in report["fields_seen"]
    assert "risk_points" in report["low_leakage_pre_trade_fields"]
    assert "sweep_depth" in report["unknown_timing_fields"]
    assert "pnl" in report["post_trade_or_high_leakage_fields"]
    assert "risk_points_over_prior_range_points" in report["candidate_discriminator_provenance"]


def test_candidate_audit_stays_conservative_without_file_and_strict_uses_report(tmp_path):
    rows = [_trade("w", 1), _trade("l", -1)]
    default = audit.analyze_candidate_discriminator_records(rows)
    assert default["raw_discriminators"]["risk_points"]["leakage_metadata"]["availability_timing"] == "unknown"

    provenance_path = tmp_path / "provenance.json"
    provenance.write_feature_timing_provenance_report(
        provenance.build_feature_timing_provenance_report(), provenance_path
    )
    strict = audit.analyze_candidate_discriminator_records(
        rows, provenance_path=provenance_path, strict_pretrade_only=True
    )

    allowed = set(strict["strict_pretrade_filter"]["allowed_fields"])
    excluded = {item["field"] for item in strict["strict_pretrade_filter"]["excluded_fields"]}
    assert {"risk_points", "reward_points", "reward_to_risk_planned"}.issubset(allowed)
    assert {"candle_range", "risk_points_over_candle_range"}.issubset(excluded)


def test_missing_provenance_old_journal_and_no_execution_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        audit.analyze_candidate_discriminator_records(
            [_trade("w", 1)], provenance_path=tmp_path / "missing.json"
        )
    report = provenance.analyze_feature_timing_provenance_journals([tmp_path / "missing.jsonl"])
    assert report["inputs_analyzed"] == 0
    assert report["failed_inputs"]

    assert "order_send" not in inspect.getsource(provenance)
    assert "order_send" not in inspect.getsource(audit)
    assert "submit_allowed=True" not in inspect.getsource(audit)
