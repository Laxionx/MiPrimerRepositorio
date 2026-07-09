from trading_bot.analysis.context_diagnostics import (
    analyze_context_diagnostics,
    generate_context_diagnostics_report,
    score_statistics,
)


def test_score_statistics_are_correct():
    stats = score_statistics([60, 70, 70, 80])

    assert stats["min"] == 60
    assert stats["max"] == 80
    assert stats["mean"] == 70
    assert stats["median"] == 70
    assert stats["stddev"] == 7.0710678118654755
    assert stats["most_common_values"] == [{"value": 70, "count": 2}]


def test_regime_counts_are_correct():
    candles = [
        {"market_regime": "trend", "context_score": 75, "context_bias": "long"},
        {"market_regime": "trend", "context_score": 75, "context_bias": "short"},
        {"market_regime": "range", "context_score": 55, "context_bias": "neutral"},
        {
            "market_regime": "compression",
            "context_score": 50,
            "context_bias": "neutral",
        },
        {"market_regime": "unknown", "context_score": 0, "context_bias": "neutral"},
    ]

    analysis = analyze_context_diagnostics(candles, [])

    assert analysis["all_candles"]["market_regime"] == {
        "trend": 2,
        "range": 1,
        "compression": 1,
        "unknown": 1,
    }


def test_empty_inputs_are_handled_and_report_is_generated(tmp_path):
    output = tmp_path / "context_diagnostics.md"

    analysis = analyze_context_diagnostics([], [])
    generate_context_diagnostics_report(analysis, output)

    assert analysis["all_candles"]["context_score_stats"]["count"] == 0
    assert analysis["accepted_trades"]["entry_score_stats"]["count"] == 0
    assert output.exists()
    assert "No candle or accepted-trade data available." in output.read_text()


def test_report_contains_all_required_distributions(tmp_path):
    candles = [
        {"market_regime": "trend", "context_score": 75, "context_bias": "long"}
    ]
    trades = [
        {
            "market_regime": "trend",
            "context_score": 75,
            "context_bias": "long",
            "entry_score": 85,
        }
    ]
    output = tmp_path / "context_diagnostics.md"

    analysis = analyze_context_diagnostics(candles, trades)
    generate_context_diagnostics_report(analysis, output)
    report = output.read_text()

    assert "## All Backtest Candles" in report
    assert "## Accepted Trades" in report
    assert "## Score Statistics" in report
    assert "## Conclusions" in report
