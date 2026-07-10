import inspect
import json

from trading_bot.research import edge_v2_cohort_report as cohort
from trading_bot.research import edge_v2_cohort_replication as replication


def records():
    rows = []
    for index in range(40):
        pnl = 10 if index >= 30 else -5 if index < 10 else 1
        rows.append({"trade_id": str(index), "pnl": pnl, "price_position_in_range": index / 39, "pressure_score": index, "lower_quartile_closes": 40 - index})
    return rows


def test_quantile_cohorts_and_pairwise_metrics():
    report = cohort.analyze_cohorts(records())
    single = report["single_feature_cohorts"]["price_position_in_range"]["top_25"]
    assert single["trade_count"] == 10
    assert single["diagnostic_only"] is True
    assert "price_position_in_range_top_25__pressure_score_top_25" in report["pairwise_cohorts"]


def test_missing_and_empty_journals_are_safe():
    assert cohort.analyze_cohorts([])["single_feature_cohorts"] == {}
    report = cohort.analyze_cohorts([{"pnl": 1}])
    assert report["unavailable_features"]


def test_sample_guards_and_flags():
    result = cohort.cohort_metrics([{"pnl": 1}, {"pnl": -1}])
    assert result["interpretation"] == "insufficient_data"
    assert result["sample_size_warning"] is True


def test_no_execution_path():
    source = inspect.getsource(cohort)
    replication_source = inspect.getsource(replication)
    assert "order_send" not in source
    assert "order_send" not in replication_source
    assert "submit_allowed=True" not in source
    assert "submit_allowed=True" not in replication_source


def test_quantile_assignment_is_a_mutually_exclusive_rank_partition():
    diagnostics = cohort.analyze_cohorts(records())["cohort_assignment_diagnostics"]
    assignment = diagnostics["price_position_in_range"]
    assert assignment["assignment_method"] == "stable_rank_partition"
    assert assignment["bucket_counts"] == {
        "bottom_25": 10,
        "middle_50": 20,
        "top_25": 10,
    }
    assert assignment["overlap_diagnostics"]["overlap_count_between_buckets"] == 0
    assert assignment["overlap_diagnostics"]["buckets_are_mutually_exclusive"] is True


def test_duplicate_and_constant_values_are_partitioned_and_diagnosed():
    rows = [{"pnl": 1, "pressure_score": 0} for _ in range(71)]
    rows.extend({"pnl": -1, "pressure_score": value} for value in range(1, 15))
    report = cohort.analyze_cohorts(rows)
    pressure = report["cohort_assignment_diagnostics"]["pressure_score"]
    assert pressure["bucket_counts"] == {
        "bottom_25": 21,
        "middle_50": 43,
        "top_25": 21,
    }
    assert pressure["overlap_diagnostics"]["overlap_count_between_buckets"] == 0
    assert pressure["threshold_ties_caused_inflated_cohort_size"] is False
    assert pressure["legacy_threshold_groups_would_be_inflated"] is True
    assert "threshold_ties_would_inflate_legacy_threshold_groups" in pressure["warnings"]

    constant = cohort.analyze_cohorts([{"pnl": 1, "compression_score": 7} for _ in range(12)])
    diagnostic = constant["cohort_assignment_diagnostics"]["compression_score"]
    assert diagnostic["bucket_counts"] == {
        "bottom_25": 3,
        "middle_50": 6,
        "top_25": 3,
    }
    assert diagnostic["degenerate_distribution"] is True
    assert "degenerate_feature_distribution" in diagnostic["warnings"]


def test_null_values_are_skipped_without_breaking_bucket_coverage():
    report = cohort.analyze_cohorts(
        [
            {"pnl": 1, "lower_quartile_closes": 0},
            {"pnl": -1, "lower_quartile_closes": 1},
            {"pnl": 1, "lower_quartile_closes": 2},
            {"pnl": -1, "lower_quartile_closes": 3},
            {"pnl": 1, "lower_quartile_closes": None},
            {"pnl": -1},
            {"pnl": 1, "lower_quartile_closes": "NaN"},
        ]
    )
    diagnostic = report["cohort_assignment_diagnostics"]["lower_quartile_closes"]
    assert diagnostic["null_count"] == 3
    assert diagnostic["non_null_count"] == 4
    assert sum(diagnostic["bucket_counts"].values()) == 4


def _write_journal(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_fixed_cohort_replication_for_one_and_multiple_journals(tmp_path):
    first = tmp_path / "xauusd_m5.jsonl"
    second = tmp_path / "xauusd_m15.jsonl"
    first_rows = [
        {
            **row,
            "symbol": "XAUUSD",
            "timeframe": "M5",
            "timestamp_open": f"2026-01-01T00:{index:02d}:00+00:00",
        }
        for index, row in enumerate(records())
    ]
    _write_journal(first, first_rows)
    _write_journal(second, [{**row, "timeframe": "M15"} for row in first_rows])

    one = replication.replicate_fixed_cohorts([first])
    assert one["diagnostic_only"] is True
    assert one["fixed_cohorts_tested"] == [{"feature": "lower_quartile_closes", "bucket": "bottom_25"}]
    assert one["per_run_results"][0]["cohorts"]["lower_quartile_closes_bottom_25"]["cohort_trade_count"] == 10
    assert one["per_run_results"][0]["date_range"]["start"] == "2026-01-01T00:00:00+00:00"

    multiple = replication.replicate_fixed_cohorts([first, second])
    aggregate = multiple["aggregate_results"]["lower_quartile_closes_bottom_25"]
    assert aggregate["runs_available"] == 2
    assert aggregate["total_cohort_trades"] == 20
    assert "stability_flag" in aggregate


def test_replication_handles_missing_journal_safely(tmp_path):
    report = replication.replicate_fixed_cohorts([tmp_path / "missing.jsonl"])
    assert report["per_run_results"][0]["status"] == "invalid_or_missing"
    assert report["sample_size_warnings"]
