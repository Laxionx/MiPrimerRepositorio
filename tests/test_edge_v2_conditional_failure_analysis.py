import json
import inspect

from trading_bot.research import edge_v2_conditional_failure_analysis as analysis


def trade(trade_id, pnl, closes=0, **fields):
    return {
        "trade_id": trade_id,
        "pnl": pnl,
        "lower_quartile_closes": closes,
        **fields,
    }


def records():
    return [
        trade(
            "w1",
            10,
            compression_score=90,
            pressure_score=80,
            symbol="XAUUSD",
            timeframe="M5",
            timestamp_open="2026-01-01T00:00:00+00:00",
        ),
        trade(
            "l1",
            -8,
            compression_score=20,
            pressure_score=10,
            symbol="XAUUSD",
            timeframe="M5",
            timestamp_open="2026-01-02T00:00:00+00:00",
        ),
        trade(
            "w2",
            5,
            compression_score=80,
            pressure_score=70,
            symbol="XAUUSD",
            timeframe="M15",
            timestamp_open="2026-01-03T00:00:00+00:00",
        ),
        trade(
            "l2",
            -4,
            compression_score=30,
            pressure_score=20,
            symbol="XAUUSD",
            timeframe="M15",
            timestamp_open="2026-01-04T00:00:00+00:00",
        ),
        trade("outside", 99, closes=1, compression_score=99),
    ]


def test_eq_zero_condition_reports_subset_metrics_and_numeric_separation():
    rows = records()
    for row in rows:
        row["r_multiple"] = 2 if row["pnl"] > 0 else -1
    report = analysis.analyze_conditional_failure_records(rows)

    assert report["condition"] == "lower_quartile_closes_eq_0"
    assert report["condition_name"] == "lower_quartile_closes_eq_0"
    assert report["total_trades_before_filter"] == 5
    assert report["total_trades_after_filter"] == 4
    assert report["subset_metrics"]["trade_count"] == 4
    assert report["subset_metrics"]["winner_count"] == 2
    assert report["subset_metrics"]["loser_count"] == 2
    separation = report["numeric_feature_separation"]["compression_score"]
    assert separation["winner_count"] == 2
    assert separation["loser_count"] == 2
    assert separation["winner_mean"] == 85.0
    assert separation["loser_mean"] == 25.0
    assert report["numeric_feature_separation"]["r_multiple"]["feature_role"] == "outcome_derived"
    assert all(item["feature"] != "r_multiple" for item in report["strongest_candidate_features"])


def test_report_includes_temporal_breakdowns_and_compact_loser_casebook():
    report = analysis.analyze_conditional_failure_records(records())

    assert report["temporal_splits"]["eligible_trade_count"] == 4
    assert report["temporal_splits"]["first_half"]["trade_count"] == 2
    assert report["temporal_splits"]["second_half"]["trade_count"] == 2
    assert report["breakdowns"]["timeframe"]["M5"]["trade_count"] == 2
    assert [case["trade_id"] for case in report["casebook"]["trades"]] == ["w1", "l1", "w2", "l2"]
    assert "session" in report["segment_breakdowns"]["unavailable_fields"]
    assert report["temporal_splits"]["first_half"]["strongest_separating_features"] == []


def test_alias_and_invalid_records_are_safe():
    report = analysis.analyze_conditional_failure_records(
        [
            trade("good", -1, closes="0", timestamp_open="not-a-time"),
            {"trade_id": "bad", "pnl": "not-a-number", "lower_quartile_closes": 1},
            {"trade_id": "outside", "pnl": -2, "lower_quartile_closes": 2},
            {"trade_id": "later", "pnl": -3, "lower_quartile_closes": 3},
        ],
        condition="lower_quartile_closes_bottom_25",
    )

    assert report["condition"] == "lower_quartile_closes_bottom_25"
    assert report["subset_metrics"]["trade_count"] == 1
    assert report["temporal_splits"]["eligible_trade_count"] == 0
    assert report["casebook"]["trades"][0]["trade_id"] == "good"


def test_multiple_journals_and_invalid_input_are_reported_without_raising(tmp_path):
    valid = tmp_path / "trades.jsonl"
    valid.write_text("\n".join(json.dumps(row) for row in records()), encoding="utf-8")

    report = analysis.analyze_conditional_failure_journals(
        [valid, tmp_path / "missing.jsonl"]
    )

    assert report["source_count"] == 2
    assert report["valid_source_count"] == 1
    assert report["invalid_source_count"] == 1
    assert report["runs"][0]["status"] == "success"
    assert report["runs"][1]["status"] == "invalid_or_missing"


def test_casebook_export_and_no_execution_path(tmp_path):
    output = tmp_path / "failure_analysis.json"
    report = analysis.analyze_conditional_failure_journals([tmp_path / "missing.jsonl"])
    analysis.write_conditional_failure_report(report, output)

    casebook = output.with_name("failure_analysis_casebook.json")
    assert output.exists()
    assert casebook.exists()
    source = inspect.getsource(analysis)
    assert "order_send" not in source
    assert "submit_allowed=True" not in source
