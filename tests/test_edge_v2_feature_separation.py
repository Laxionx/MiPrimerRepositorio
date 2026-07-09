import json

from trading_bot.research.edge_v2_feature_separation import (
    analyze_feature_separation,
    calculate_effect_size,
    load_journal_records,
    write_feature_separation_report,
)


def trade(trade_id, pnl, **features):
    return {"trade_id": trade_id, "pnl": pnl, **features}


def test_feature_report_calculates_numeric_edge_v2_separation():
    report = analyze_feature_separation(
        [
            trade("w1", 10, compression_score=90, pressure_score=80),
            trade("w2", 8, compression_score=80, pressure_score=70),
            trade("l1", -5, compression_score=40, pressure_score=20),
            trade("l2", -8, compression_score=30, pressure_score=10),
        ],
        top_n=1,
    )

    compression = report["features"]["compression_score"]
    assert report["schema_version"] == "aqtf_edge_v2_feature_separation.v1"
    assert report["diagnostic_only"] is True
    assert compression["sample_count"] == 4
    assert compression["winner_count"] == 2
    assert compression["loser_count"] == 2
    assert compression["winner_mean"] == 85.0
    assert compression["loser_mean"] == 35.0
    assert compression["mean_difference"] == 50.0
    assert compression["separation"] == "strong_separation"
    assert compression["top_vs_worst"]["top_n"] == 1


def test_old_journal_without_edge_v2_fields_is_safe():
    report = analyze_feature_separation(
        [trade("w1", 1, context_score=75), trade("l1", -1, context_score=50)]
    )

    assert report["available_features"] == []
    assert report["features"] == {}
    assert report["diagnostic_only"] is True


def test_empty_journal_is_safe():
    report = analyze_feature_separation([])

    assert report["total_records"] == 0
    assert report["features"] == {}
    assert "does not recommend strategy changes" in report["disclaimer"]


def test_one_sided_outcomes_are_insufficient_data():
    report = analyze_feature_separation(
        [
            trade("w1", 1, compression_score=80),
            trade("w2", 2, compression_score=90),
        ]
    )

    result = report["features"]["compression_score"]
    assert result["winner_count"] == 2
    assert result["loser_count"] == 0
    assert result["separation"] == "insufficient_data"
    assert result["simple_effect_size"] is None


def test_breakeven_records_are_not_counted_as_losers():
    report = analyze_feature_separation(
        [
            trade("w1", 1, compression_score=80),
            trade("b1", 0, compression_score=60),
            trade("l1", -1, compression_score=40),
        ]
    )

    result = report["features"]["compression_score"]
    assert result["sample_count"] == 3
    assert result["winner_count"] == 1
    assert result["loser_count"] == 1


def test_jsonl_and_csv_journals_are_loaded(tmp_path):
    jsonl = tmp_path / "trades.jsonl"
    csv_path = tmp_path / "trades.csv"
    jsonl.write_text(json.dumps(trade("w1", 1, compression_score=80)) + "\n")
    csv_path.write_text("trade_id,pnl,compression_score\nl1,-1,20\n")

    assert load_journal_records(jsonl)[0]["compression_score"] == 80
    assert load_journal_records(csv_path)[0]["compression_score"] == "20"


def test_effect_size_uses_pooled_standard_deviation():
    effect_size = calculate_effect_size([8.0, 10.0], [4.0, 6.0])

    assert effect_size == 4.0


def test_pressure_direction_is_reported_as_categorical_without_numeric_claims():
    report = analyze_feature_separation(
        [
            trade("w1", 1, pressure_direction="long"),
            trade("w2", 2, pressure_direction="long"),
            trade("l1", -1, pressure_direction="short"),
            trade("l2", -2, pressure_direction="neutral"),
        ]
    )

    result = report["features"]["pressure_direction"]
    assert result["feature_type"] == "categorical"
    assert result["winner_distribution"] == {"long": 2}
    assert result["loser_distribution"] == {"neutral": 1, "short": 1}
    assert result["simple_effect_size"] is None


def test_json_report_has_schema_and_serializes(tmp_path):
    output = tmp_path / "edge_v2_feature_separation.json"
    report = analyze_feature_separation(
        [
            trade("w1", 1, is_compressing=True),
            trade("w2", 2, is_compressing=True),
            trade("l1", -1, is_compressing=False),
            trade("l2", -2, is_compressing=False),
        ]
    )

    write_feature_separation_report(report, output)

    saved = json.loads(output.read_text())
    result = saved["features"]["is_compressing"]
    assert saved["schema_version"] == "aqtf_edge_v2_feature_separation.v1"
    assert result["feature_type"] == "numeric"
    assert result["winner_mean"] == 1.0
    assert result["loser_mean"] == 0.0
