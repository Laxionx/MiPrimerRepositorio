import inspect
import json

from trading_bot.research import edge_v2_fixed_signal_robustness as robustness


def _records(count=40):
    rows = []
    for index in range(count):
        value = index % 5
        rows.append(
            {
                "trade_id": str(index),
                "pnl": 8 if value == 0 else -3 if value >= 3 else 1,
                "lower_quartile_closes": value,
                "symbol": "XAUUSD",
                "timeframe": "M5",
                "timestamp_open": f"2026-01-01T00:{index:02d}:00+00:00",
            }
        )
    return rows


def _write_journal(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_raw_value_and_cumulative_groups_are_diagnostic(tmp_path):
    journal = tmp_path / "trades.jsonl"
    _write_journal(journal, _records())

    report = robustness.build_fixed_signal_robustness_report([journal])

    assert report["diagnostic_only"] is True
    assert report["signal_name"] == "lower_quartile_closes"
    assert report["raw_value_summary"]["0"]["trade_count"] == 8
    assert report["cumulative_group_summary"]["lower_quartile_closes_lte_1"]["trade_count"] == 16
    assert report["rank_partition_summary"]["bottom_25"]["trade_count"] == 10
    assert report["rank_vs_raw_comparison"]["rank_bottom_25"]["diagnostic_only"] is True
    assert report["rank_vs_raw_comparison"]["comparison"] in {"agree", "diverge"}


def test_missing_or_empty_feature_is_safe(tmp_path):
    empty = tmp_path / "empty.jsonl"
    old = tmp_path / "old.jsonl"
    _write_journal(empty, [])
    _write_journal(old, [{"pnl": 1}, {"pnl": -1}])

    report = robustness.build_fixed_signal_robustness_report([empty, old])

    assert report["successful_inputs"] == 2
    assert report["raw_value_summary"] == {}
    assert "lower_quartile_closes_unavailable" in report["warnings"]
    assert "insufficient_data" in report["robustness_flags"]


def test_temporal_and_calibration_threshold_use_only_first_half(tmp_path):
    journal = tmp_path / "chronological.jsonl"
    rows = _records()
    for index, row in enumerate(rows[:20]):
        row["lower_quartile_closes"] = 0 if index < 5 else 4
    for index, row in enumerate(rows[20:]):
        row["lower_quartile_closes"] = 0 if index < 4 else 3
    _write_journal(journal, rows)

    report = robustness.build_fixed_signal_robustness_report([journal])
    run = report["per_input_results"][0]
    calibration = run["calibration_test"]

    assert set(run["temporal_splits"]) >= {"first_half", "second_half", "first_third"}
    assert calibration["calibrated_q25_threshold"] == 0.0
    assert calibration["test_trade_count"] == 20
    assert calibration["test_selected_trade_count"] == 4
    assert calibration["sample_size_warning"] is True


def test_multiple_and_invalid_journals_are_aggregated_without_duplicates(tmp_path):
    first = tmp_path / "first.jsonl"
    duplicate = tmp_path / "duplicate.jsonl"
    second = tmp_path / "second.jsonl"
    rows = _records()
    _write_journal(first, rows)
    _write_journal(duplicate, rows)
    _write_journal(second, _records(20))

    report = robustness.build_fixed_signal_robustness_report(
        [first, duplicate, second, tmp_path / "missing.jsonl"]
    )

    assert report["input_count"] == 4
    assert report["successful_inputs"] == 2
    assert report["failed_or_skipped_inputs"] == 2
    assert report["total_trades"] == 60
    assert any(item["status"] == "duplicate_input" for item in report["per_input_results"])
    assert any(item["status"] == "invalid_or_missing" for item in report["per_input_results"])


def test_no_execution_path():
    source = inspect.getsource(robustness)
    assert "order_send" not in source
    assert "submit_allowed=True" not in source
