import pandas as pd

from trading_bot.analysis.edge_v2 import EdgeV2Diagnostics


def candles(closes, ranges, *, shared_range=None):
    if shared_range is not None:
        return pd.DataFrame(
            {
                "close": closes,
                "high": [shared_range[1]] * len(closes),
                "low": [shared_range[0]] * len(closes),
            }
        )
    return pd.DataFrame(
        {
            "close": closes,
            "high": [close + candle_range / 2 for close, candle_range in zip(closes, ranges)],
            "low": [close - candle_range / 2 for close, candle_range in zip(closes, ranges)],
        }
    )


def test_compression_score_increases_when_recent_ranges_contract():
    result = EdgeV2Diagnostics(window_bars=5).evaluate(
        candles([100.0] * 10, [10.0] * 5 + [2.0] * 5)
    )

    assert result["atr_contraction_pct"] == 80.0
    assert result["compression_score"] >= 60
    assert result["recent_range_points"] < result["prior_range_points"]


def test_clear_contraction_is_marked_as_compressing():
    result = EdgeV2Diagnostics(window_bars=5).evaluate(
        candles([100.0] * 10, [8.0] * 5 + [1.0] * 5)
    )

    assert result["is_compressing"] is True
    assert result["range_duration_bars"] >= 5


def test_pressure_is_long_when_closes_cluster_near_range_high():
    result = EdgeV2Diagnostics(window_bars=5).evaluate(
        candles(
            [50.0] * 5 + [85.0, 88.0, 90.0, 92.0, 95.0],
            [100.0] * 10,
            shared_range=(0.0, 100.0),
        )
    )

    assert result["pressure_direction"] == "long"
    assert result["pressure_score"] >= 60
    assert result["price_position_in_range"] == 0.95
    assert result["upper_quartile_closes"] == 5


def test_pressure_is_short_when_closes_cluster_near_range_low():
    result = EdgeV2Diagnostics(window_bars=5).evaluate(
        candles(
            [50.0] * 5 + [15.0, 12.0, 10.0, 8.0, 5.0],
            [100.0] * 10,
            shared_range=(0.0, 100.0),
        )
    )

    assert result["pressure_direction"] == "short"
    assert result["pressure_score"] >= 60
    assert result["lower_quartile_closes"] == 5


def test_pressure_can_be_neutral():
    result = EdgeV2Diagnostics(window_bars=5).evaluate(
        candles(
            [50.0] * 5 + [50.0, 51.0, 49.0, 50.0, 50.0],
            [100.0] * 10,
            shared_range=(0.0, 100.0),
        )
    )

    assert result["pressure_direction"] == "neutral"
    assert result["pressure_score"] == 0


def test_edge_v2_returns_unknown_fields_when_candles_are_insufficient():
    result = EdgeV2Diagnostics(window_bars=5).evaluate(
        candles([100.0] * 9, [2.0] * 9)
    )

    assert all(value is None for value in result.values())
