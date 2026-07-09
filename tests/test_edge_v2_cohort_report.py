import inspect

from trading_bot.research import edge_v2_cohort_report as cohort


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
    assert "order_send" not in source
    assert "submit_allowed=True" not in source
