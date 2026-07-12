import json

import pytest

from trading_bot.research import edge_v3_full_pretrade_discriminator_discovery as discovery
from trading_bot.research import edge_v3_pretrade_feature_matrix as matrix
from trading_bot.research import edge_v3_robustness_scorecard as scorecard
from trading_bot.research import edge_v3_temporal_train_test_audit as temporal
from trading_bot.research.edge_v2_feature_timing_provenance import (
    build_feature_timing_provenance_report,
)


def _provenance():
    return build_feature_timing_provenance_report()["registry"]


def _trade(index, pnl, *, symbol="XAUUSD", timeframe="M5", **extra):
    return {
        "trade_id": f"trade-{index}",
        "timestamp_open": f"2026-01-{(index % 28) + 1:02d}T00:00:00+00:00",
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": "LONG" if index % 2 else "SHORT",
        "pnl": pnl,
        "outcome": "win" if pnl > 0 else "loss",
        "r_multiple": pnl / 2,
        "exit_price": 100 + pnl,
        "timestamp_close": "2026-02-01T00:00:00+00:00",
        "bars_held": 3,
        "lower_quartile_closes": 0,
        "candle_range": 4,
        "risk_points": 2 if pnl > 0 else 8,
        "reward_points": 8 if pnl > 0 else 4,
        "prior_range_points": 10,
        "atr": 2,
        "pressure_score": 70 if pnl > 0 else 30,
        "price_position_in_range": 0.8 if pnl > 0 else 0.2,
        "compression_score": 60 if pnl > 0 else 20,
        "range_duration_bars": 4,
        "atr_contraction_pct": 25.0,
        "recent_range_points": 8.0,
        "upper_quartile_closes": 4,
        "average_pullback_depth": 0.2,
        "is_compressing": True,
        "pressure_direction": "long",
        "market_regime": "trend",
        "context_bias": "long",
        "context_reason": "fixture-only context",
        "spread": 0.2,
        "entry": 100.0,
        "entry_distance_from_sweep": 0.5,
        **extra,
    }


def _write_journal(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in records), encoding="utf-8")


def _matrix_records(count=80):
    return [
        _trade(index, 2 if index % 3 else -1, symbol="XAUUSD" if index < count // 2 else "EURUSD")
        for index in range(count)
    ]


def test_matrix_deduplicates_rejects_invalid_and_excludes_lqc_and_outcomes(tmp_path):
    batch = tmp_path / "batch"
    rows = _matrix_records(8)
    _write_journal(batch / "run_a" / "journal" / "trades.jsonl", rows)
    _write_journal(batch / "run_b" / "journal" / "trades.jsonl", rows)
    invalid = [_trade(99, 1)]
    invalid[0].pop("timestamp_open")
    _write_journal(batch / "run_c" / "journal" / "trades.jsonl", invalid)

    result = matrix.build_pretrade_feature_matrix([batch], provenance=_provenance())

    manifest = result["input_manifest"]
    assert sum(item["accepted"] for item in manifest) == 1
    assert any(item["rejection_reason"] == "duplicate_sha256" for item in manifest)
    assert any("missing_required_fields" in (item["rejection_reason"] or "") for item in manifest)
    assert "lower_quartile_closes" not in result["predictors"]
    assert not {"pnl", "r_multiple", "outcome", "exit_price", "timestamp_close", "bars_held"} & set(result["predictors"])
    assert "candle_range" not in result["predictors"]
    assert result["records"][0]["labels"]["pnl"] in {2, -1}


def test_matrix_adds_only_strict_deterministic_derivatives(tmp_path):
    batch = tmp_path / "batch"
    _write_journal(batch / "run" / "journal" / "trades.jsonl", [_trade(1, 2)])

    result = matrix.build_pretrade_feature_matrix([batch], provenance=_provenance())

    assert "reward_to_risk_planned" not in result["predictors"]
    assert "risk_points_over_atr" not in result["predictors"]
    assert "risk_points_over_candle_range" not in result["predictors"]
    assert result["strict_excluded_features"]["risk_points"]["availability_timing"] == "at_entry"


def test_matrix_contains_exactly_ten_predecision_predictors(tmp_path):
    batch = tmp_path / "batch"
    _write_journal(batch / "run" / "journal" / "trades.jsonl", [_trade(1, 2)])

    result = matrix.build_pretrade_feature_matrix([batch], provenance=_provenance())

    assert result["predictors"] == [
        "atr", "atr_contraction_pct", "average_pullback_depth", "compression_score",
        "pressure_score", "price_position_in_range", "prior_range_points",
        "range_duration_bars", "recent_range_points", "upper_quartile_closes",
    ]
    assert not {"risk_points", "reward_points", "reward_to_risk_planned", "risk_points_over_atr", "reward_points_over_atr", "risk_points_over_prior_range_points", "reward_points_over_prior_range_points"} & set(result["predictors"])


def test_matrix_fails_closed_for_numeric_field_without_provenance():
    records = _matrix_records(2)
    for record in records:
        record["unregistered_numeric"] = 1.0

    try:
        matrix.build_matrix_from_records(records, provenance=_provenance())
    except ValueError as exc:
        assert "unregistered_numeric" in str(exc)
    else:
        raise AssertionError("strict matrix accepted a numeric field without provenance")


def test_matrix_rejects_post_trade_excursion_fields_without_provenance():
    records = _matrix_records(2)
    for record in records:
        record["mfe"] = 1.0
        record["mae"] = -1.0

    try:
        matrix.build_matrix_from_records(records, provenance=_provenance())
    except ValueError as exc:
        assert "mae" in str(exc)
    else:
        raise AssertionError("strict matrix accepted post-trade MFE/MAE fields")


def test_matrix_fails_closed_for_predecision_timing_contradiction():
    provenance = _provenance()
    provenance["atr"] = {
        **provenance["atr"],
        "uses_next_entry_bar": True,
    }

    try:
        matrix.build_matrix_from_records(_matrix_records(2), provenance=provenance)
    except ValueError as exc:
        assert "timing contradiction" in str(exc)
    else:
        raise AssertionError("strict matrix accepted contradictory pre-decision provenance")


def test_matrix_fails_closed_for_predecision_spread_dependency():
    provenance = _provenance()
    provenance["atr"] = {
        **provenance["atr"],
        "uses_spread": True,
        "uses_spread_or_slippage": False,
    }

    try:
        matrix.build_matrix_from_records(_matrix_records(2), provenance=provenance)
    except ValueError as exc:
        assert "timing contradiction" in str(exc)
    else:
        raise AssertionError("strict matrix accepted a spread-dependent pre-decision field")


@pytest.mark.parametrize(
    ("missing", "expected"),
    [
        (("uses_spread",), "uses_spread"),
        (("uses_slippage",), "uses_slippage"),
        (("uses_spread", "uses_slippage"), "uses_slippage, uses_spread"),
        (("source_timestamp",), "source_timestamp"),
    ],
)
def test_matrix_reports_all_missing_strict_provenance_keys(missing, expected):
    provenance = _provenance()
    for key in missing:
        provenance["atr"].pop(key)

    with pytest.raises(
        ValueError,
        match=rf"Feature 'atr' has incomplete strict provenance metadata; missing required keys: {expected}",
    ):
        matrix.build_matrix_from_records(_matrix_records(2), provenance=provenance)


def test_matrix_rejects_non_mapping_strict_provenance():
    provenance = _provenance()
    provenance["atr"] = "invalid"

    with pytest.raises(ValueError, match=r"Feature 'atr' has invalid strict provenance metadata"):
        matrix.build_matrix_from_records(_matrix_records(2), provenance=provenance)


@pytest.mark.parametrize(
    ("field", "value"),
    [("uses_spread", "false"), ("uses_slippage", 0)],
)
def test_matrix_rejects_non_boolean_strict_cost_metadata(field, value):
    provenance = _provenance()
    provenance["atr"] = {**provenance["atr"], field: value}

    with pytest.raises(ValueError, match=rf"Feature 'atr' has invalid strict provenance field '{field}'.*expected boolean"):
        matrix.build_matrix_from_records(_matrix_records(2), provenance=provenance)


@pytest.mark.parametrize("field", ("uses_spread", "uses_slippage"))
def test_matrix_reports_predecision_cost_contradictions(field):
    provenance = _provenance()
    provenance["atr"] = {
        **provenance["atr"],
        field: True,
        "uses_spread_or_slippage": False,
    }

    with pytest.raises(ValueError, match=r"strict discovery timing contradiction for atr"):
        matrix.build_matrix_from_records(_matrix_records(2), provenance=provenance)


def test_matrix_admits_expanded_strict_fields_but_keeps_exclusions(tmp_path):
    batch = tmp_path / "batch"
    _write_journal(batch / "run" / "journal" / "trades.jsonl", [_trade(1, 2)])
    provenance = _provenance()
    for field in ("spread", "entry", "entry_distance_from_sweep"):
        provenance[field] = {
            "field_name": field,
            "category": "execution",
            "availability_timing": "at_entry",
            "leakage_risk": "medium",
            "source_basis": "code_verified",
            "source_module_or_function": "test fixture",
            "depends_on_fields": ["entry bar"],
            "depends_on_exit_price": False,
            "depends_on_pnl": False,
            "depends_on_future_bars": False,
            "depends_on_realized_outcome": False,
            "reason": "Explicitly at-entry for the exclusion check.",
        }
    for field in ("is_compressing", "pressure_direction", "market_regime", "context_bias", "context_reason"):
        provenance[field] = {
            "field_name": field,
            "category": "categorical_or_boolean",
            "availability_timing": "pre_trade",
            "leakage_risk": "low",
            "source_basis": "code_verified",
            "source_module_or_function": "test fixture",
            "depends_on_fields": ["historical bars"],
            "depends_on_exit_price": False,
            "depends_on_pnl": False,
            "depends_on_future_bars": False,
            "depends_on_realized_outcome": False,
            "reason": "The matrix must not coerce categories or booleans to numbers.",
        }

    result = matrix.build_pretrade_feature_matrix([batch], provenance=provenance)

    assert {
        "range_duration_bars",
        "atr_contraction_pct",
        "recent_range_points",
        "upper_quartile_closes",
        "average_pullback_depth",
    }.issubset(result["predictors"])
    assert not {
        "lower_quartile_closes",
        "spread",
        "entry",
        "entry_distance_from_sweep",
        "pnl",
        "outcome",
        "r_multiple",
        "exit_price",
        "timestamp_close",
        "bars_held",
        "is_compressing",
        "pressure_direction",
        "market_regime",
        "context_bias",
        "context_reason",
    } & set(result["predictors"])


def test_discovery_has_non_overlapping_cohorts_and_no_lqc_predictor():
    matrix_data = matrix.build_matrix_from_records(_matrix_records(), provenance=_provenance())

    report = discovery.discover_pretrade_discriminators(matrix_data)

    feature = report["features"]["atr"]
    cohort_ids = [
        set(item["record_ids"])
        for item in feature["global"]["cohorts"].values()
    ]
    assert all(left.isdisjoint(right) for index, left in enumerate(cohort_ids) for right in cohort_ids[index + 1:])
    assert "lower_quartile_closes" not in report["features"]
    assert feature["global"]["outlier_sensitivity"]["available"] is True


def test_temporal_split_is_deterministic_and_warns_for_small_cohorts():
    matrix_data = matrix.build_matrix_from_records(_matrix_records(12), provenance=_provenance())
    discovery_data = discovery.discover_pretrade_discriminators(matrix_data)

    first = temporal.audit_temporal_train_test(matrix_data, discovery_data)
    second = temporal.audit_temporal_train_test(matrix_data, discovery_data)

    first_feature = first["segments"]["global"][0]["features"]["atr"]
    assert first == second
    assert first_feature["train_trade_count"] == 6
    assert first_feature["test_trade_count"] == 6
    assert all(item["kind"] == "fixed" for item in first_feature["cohort_definitions"].values())
    assert "cohorts" not in first_feature["test"]
    assert any(item["sample_size_warning"] for item in first_feature["cohorts"].values())


def test_scorecard_rejects_freezes_and_promotes_by_gates():
    reject = scorecard.score_feature(
        "lower_quartile_closes",
        provenance={"availability_timing": "pre_decision", "leakage_risk": "low", "source_basis": "code_verified"},
        sample={"count": 200, "winner_count": 80, "loser_count": 120},
        sign_summary={"positive": 3, "negative": 0},
        temporal_summary={"sufficient": True, "non_negative": True},
        concentration=0.2,
        outlier_conflict=False,
    )
    frozen = scorecard.score_feature(
        "risk_points",
        provenance={"availability_timing": "at_entry", "leakage_risk": "medium", "source_basis": "code_verified"},
        sample={"count": 200, "winner_count": 80, "loser_count": 120},
        sign_summary={"positive": 2, "negative": 1},
        temporal_summary={"sufficient": True, "non_negative": True},
        concentration=0.2,
        outlier_conflict=False,
    )
    promote = scorecard.score_feature(
        "atr",
        provenance={"availability_timing": "pre_decision", "leakage_risk": "low", "source_basis": "code_verified"},
        sample={"count": 200, "winner_count": 80, "loser_count": 120},
        sign_summary={"positive": 3, "negative": 0},
        temporal_summary={"sufficient": True, "non_negative": True},
        concentration=0.4,
        outlier_conflict=False,
    )
    concentrated = scorecard.score_feature(
        "pressure_score",
        provenance={"availability_timing": "pre_decision", "leakage_risk": "low", "source_basis": "code_verified"},
        sample={"count": 200, "winner_count": 80, "loser_count": 120},
        sign_summary={"positive": 3, "negative": 0},
        temporal_summary={"sufficient": True, "non_negative": True},
        concentration=0.6,
        outlier_conflict=False,
    )

    assert reject["decision"] == "rejected"
    assert frozen["decision"] == "rejected"
    assert promote["decision"] == "candidate_discriminator_hypothesis"
    assert "single_symbol_timeframe_concentration" in concentrated["reasons"]


def test_cli_smoke_writes_diagnostic_outputs(tmp_path):
    batch = tmp_path / "batch"
    _write_journal(batch / "run" / "journal" / "trades.jsonl", _matrix_records(12))
    provenance_path = tmp_path / "provenance.json"
    matrix_path = tmp_path / "matrix.json"
    manifest_path = tmp_path / "manifest.json"
    discovery_path = tmp_path / "discovery.json"
    temporal_path = tmp_path / "temporal.json"
    scorecard_path = tmp_path / "scorecard.json"
    summary_path = tmp_path / "summary.md"
    provenance_path.write_text(json.dumps({"registry": _provenance()}), encoding="utf-8")

    matrix.main(["--batch-dir", str(batch), "--provenance", str(provenance_path), "--out", str(matrix_path), "--manifest-out", str(manifest_path)])
    discovery.main(["--matrix", str(matrix_path), "--out", str(discovery_path)])
    temporal.main(["--matrix", str(matrix_path), "--discovery", str(discovery_path), "--out", str(temporal_path)])
    scorecard.main(["--matrix", str(matrix_path), "--discovery", str(discovery_path), "--train-test", str(temporal_path), "--out", str(scorecard_path), "--summary-out", str(summary_path)])

    assert json.loads(scorecard_path.read_text(encoding="utf-8"))["diagnostic_only"] is True
    assert "interacciones 2D" in summary_path.read_text(encoding="utf-8")


def test_modules_have_no_execution_path():
    for module in (matrix, discovery, temporal, scorecard):
        source = open(module.__file__, encoding="utf-8").read() if module.__file__ else ""
        assert "order_send" not in source
        assert "submit_allowed=True" not in source
