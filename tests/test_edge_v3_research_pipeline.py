import json

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

    assert "reward_to_risk_planned" in result["predictors"]
    assert "risk_points_over_atr" in result["predictors"]
    assert "risk_points_over_candle_range" not in result["predictors"]
    assert result["records"][0]["predictors"]["reward_to_risk_planned"] == 4


def test_discovery_has_non_overlapping_cohorts_and_no_lqc_predictor():
    matrix_data = matrix.build_matrix_from_records(_matrix_records(), provenance=_provenance())

    report = discovery.discover_pretrade_discriminators(matrix_data)

    feature = report["features"]["risk_points"]
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

    first_feature = first["segments"]["global"][0]["features"]["risk_points"]
    assert first == second
    assert first_feature["train_trade_count"] == 6
    assert first_feature["test_trade_count"] == 6
    assert all(item["kind"] == "fixed" for item in first_feature["cohort_definitions"].values())
    assert "cohorts" not in first_feature["test"]
    assert any(item["sample_size_warning"] for item in first_feature["cohorts"].values())


def test_scorecard_rejects_freezes_and_promotes_by_gates():
    reject = scorecard.score_feature(
        "lower_quartile_closes",
        provenance={"availability_timing": "pre_trade", "leakage_risk": "low", "source_basis": "code_verified"},
        sample={"count": 200, "winner_count": 80, "loser_count": 120},
        sign_summary={"positive": 3, "negative": 0},
        temporal_summary={"sufficient": True, "non_negative": True},
        concentration=0.2,
        outlier_conflict=False,
    )
    frozen = scorecard.score_feature(
        "risk_points",
        provenance={"availability_timing": "pre_trade", "leakage_risk": "low", "source_basis": "code_verified"},
        sample={"count": 200, "winner_count": 80, "loser_count": 120},
        sign_summary={"positive": 2, "negative": 1},
        temporal_summary={"sufficient": True, "non_negative": True},
        concentration=0.2,
        outlier_conflict=False,
    )
    promote = scorecard.score_feature(
        "reward_points",
        provenance={"availability_timing": "pre_trade", "leakage_risk": "low", "source_basis": "code_verified"},
        sample={"count": 200, "winner_count": 80, "loser_count": 120},
        sign_summary={"positive": 3, "negative": 0},
        temporal_summary={"sufficient": True, "non_negative": True},
        concentration=0.4,
        outlier_conflict=False,
    )
    concentrated = scorecard.score_feature(
        "pressure_score",
        provenance={"availability_timing": "pre_trade", "leakage_risk": "low", "source_basis": "code_verified"},
        sample={"count": 200, "winner_count": 80, "loser_count": 120},
        sign_summary={"positive": 3, "negative": 0},
        temporal_summary={"sufficient": True, "non_negative": True},
        concentration=0.6,
        outlier_conflict=False,
    )

    assert reject["decision"] == "rejected"
    assert frozen["decision"] == "frozen"
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
