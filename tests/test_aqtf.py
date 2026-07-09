import pandas as pd

from trading_bot.risk.risk_guard import SimpleRiskGuard
from trading_bot.signals.aqtf import ContextEngine, EntryScorer


def candles(closes: list[float], ranges: list[float] | None = None) -> pd.DataFrame:
    ranges = ranges or [1.0] * len(closes)
    return pd.DataFrame(
        {
            "open": closes,
            "high": [close + width / 2 for close, width in zip(closes, ranges)],
            "low": [close - width / 2 for close, width in zip(closes, ranges)],
            "close": closes,
            "tick_volume": [100] * len(closes),
        }
    )


def sweep_report(direction: str, level: float, price: float) -> dict:
    return {
        "setup": {
            "type": direction,
            "entry_price": price,
            "stop_loss": price - 1 if direction == "LONG" else price + 1,
            "take_profit": price + 2 if direction == "LONG" else price - 2,
        },
        "liquidity": {
            "recent_low": level if direction == "LONG" else level - 5,
            "recent_high": level if direction == "SHORT" else level + 5,
            "low_sweep": direction == "LONG",
            "high_sweep": direction == "SHORT",
        },
    }


def test_rising_h1_context_supports_low_sweep_long():
    context = ContextEngine().evaluate(candles([100 + i for i in range(20)]))
    score = EntryScorer().evaluate(
        sweep_report("LONG", level=118.5, price=119.0),
        candles([118.0] * 19 + [119.0]),
        context,
        {"spread": 5, "volatility": 0.001},
    )
    assert context["market_regime"] == "trend"
    assert context["context_bias"] == "long"
    assert context["context_reason"] == "Trend continuation"
    assert score["blocked_by_context"] is False
    assert score["entry_score"] >= 65


def test_falling_h1_context_supports_high_sweep_short():
    context = ContextEngine().evaluate(candles([120 - i for i in range(20)]))
    score = EntryScorer().evaluate(
        sweep_report("SHORT", level=101.5, price=101.0),
        candles([102.0] * 19 + [101.0]),
        context,
        {"spread": 5, "volatility": 0.001},
    )
    assert context["market_regime"] == "trend"
    assert context["context_bias"] == "short"
    assert score["blocked_by_context"] is False
    assert score["entry_score"] >= 65


def test_flat_overlapping_h1_context_is_range():
    context = ContextEngine().evaluate(candles([100.0] * 20, ranges=[4.0] * 20))

    assert context["market_regime"] == "range"
    assert context["context_bias"] == "neutral"
    assert context["context_reason"] == "Range center"


def test_shrinking_h1_ranges_are_compression():
    context = ContextEngine().evaluate(
        candles([100.0] * 20, ranges=[2.0] * 17 + [0.5] * 3)
    )

    assert context["market_regime"] == "compression"
    assert context["context_reason"].startswith("Compression")


def test_context_score_varies_across_regimes_and_trend_locations():
    continuation = ContextEngine().evaluate(candles([100 + i for i in range(20)]))
    pullback = ContextEngine().evaluate(
        candles([100 + i for i in range(19)] + [116.0])
    )
    ranging = ContextEngine().evaluate(candles([100.0] * 20, ranges=[4.0] * 20))
    compression = ContextEngine().evaluate(
        candles([100.0] * 20, ranges=[2.0] * 17 + [0.5] * 3)
    )

    assert continuation["context_score"] != pullback["context_score"]
    assert len(
        {
            continuation["context_score"],
            ranging["context_score"],
            compression["context_score"],
        }
    ) == 3
    assert continuation["context_score"] >= 60
    assert ranging["context_score"] < 60
    assert compression["context_score"] < 60


def test_context_always_includes_normalized_h1_distances():
    context = ContextEngine().evaluate(candles([100 + i * 0.1 for i in range(20)]))

    assert 0.0 <= context["distance_to_h1_high"] <= 1.0
    assert 0.0 <= context["distance_to_h1_low"] <= 1.0
    assert 0.0 <= context["distance_to_h1_mid"] <= 0.5
    assert context["context_reason"]


def test_setup_is_blocked_below_context_threshold():
    result = EntryScorer(context_score_min=60).evaluate(
        sweep_report("LONG", level=100.0, price=100.2),
        candles([100.0] * 20),
        {
            "market_regime": "range",
            "context_bias": "neutral",
            "context_score": 55,
            "context_reason": "overlapping H1 structure",
        },
        {"spread": 5, "volatility": 0.001},
    )
    assert result["blocked_by_context"] is True


def test_setup_is_blocked_below_entry_threshold():
    result = EntryScorer(entry_score_min=90).evaluate(
        sweep_report("LONG", level=100.0, price=100.2),
        candles([100.0] * 20),
        {
            "market_regime": "trend_up",
            "context_bias": "long",
            "context_score": 75,
            "context_reason": "rising H1 structure",
        },
        {"spread": 5, "volatility": 0.001},
    )
    assert result["blocked_by_entry_score"] is True


def test_no_chase_blocks_extended_entry():
    result = EntryScorer(no_chase_max_atr=0.6).evaluate(
        sweep_report("LONG", level=100.0, price=101.0),
        candles([100.0] * 19 + [101.0], ranges=[1.0] * 20),
        {
            "market_regime": "trend_up",
            "context_bias": "long",
            "context_score": 75,
            "context_reason": "rising H1 structure",
        },
        {"spread": 5, "volatility": 0.001},
    )
    assert result["extension_atr"] > 0.6
    assert result["no_chase_blocked"] is True


def test_quality_guard_blocks_high_spread():
    result = EntryScorer(max_spread_points=6).evaluate(
        sweep_report("LONG", level=99.5, price=100.0),
        candles([100.0] * 20),
        {
            "market_regime": "trend",
            "context_bias": "long",
            "context_score": 75,
            "context_reason": "Trend continuation",
        },
        {"spread": 7, "volatility": 0.001},
    )

    assert result["blocked_by_quality_guard"] is True
    assert result["quality_block_reason"] == "spread_exceeds_maximum"
    assert result["spread"] == 7


def test_quality_guard_blocks_excessive_entry_distance():
    result = EntryScorer(max_entry_distance_from_sweep=10).evaluate(
        sweep_report("LONG", level=100.0, price=111.0),
        candles([110.0] * 19 + [111.0]),
        {
            "market_regime": "trend",
            "context_bias": "long",
            "context_score": 75,
            "context_reason": "Trend continuation",
        },
        {"spread": 1, "volatility": 0.001},
    )

    assert result["blocked_by_quality_guard"] is True
    assert result["quality_block_reason"] == "entry_distance_exceeds_maximum"
    assert result["entry_distance_from_sweep"] == 11.0


def test_quality_guard_blocks_low_planned_rr():
    report = sweep_report("LONG", level=99.5, price=100.0)
    report["setup"]["take_profit"] = 100.5

    result = EntryScorer(min_planned_rr=1.0).evaluate(
        report,
        candles([100.0] * 20),
        {
            "market_regime": "trend",
            "context_bias": "long",
            "context_score": 75,
            "context_reason": "Trend continuation",
        },
        {"spread": 1, "volatility": 0.001},
    )

    assert result["blocked_by_quality_guard"] is True
    assert result["quality_block_reason"] == "planned_rr_below_minimum"
    assert result["planned_rr"] == 0.5


def test_quality_guard_allows_good_setup_and_exposes_json_fields():
    result = EntryScorer().evaluate(
        sweep_report("LONG", level=99.5, price=100.0),
        candles([100.0] * 20),
        {
            "market_regime": "trend",
            "context_bias": "long",
            "context_score": 75,
            "context_reason": "Trend continuation",
        },
        {"spread": 5, "volatility": 0.001},
    )

    assert result["blocked_by_quality_guard"] is False
    assert result["quality_block_reason"] is None
    assert result["spread"] == 5
    assert result["entry_distance_from_sweep"] == 0.5
    assert result["planned_rr"] == 2.0


def test_entry_score_varies_for_weak_and_strong_accepted_sweeps():
    context = ContextEngine().evaluate(candles([100 + i for i in range(20)]))
    report = sweep_report("LONG", level=118.5, price=119.0)
    data = candles([118.0] * 19 + [119.0], ranges=[2.0] * 20)
    scorer = EntryScorer()

    weak = scorer.evaluate(
        report,
        data,
        context,
        {"spread": 19, "volatility": 0.0045},
    )
    strong = scorer.evaluate(
        report,
        data,
        context,
        {"spread": 1, "volatility": 0.0001},
    )

    assert weak["entry_score"] != strong["entry_score"]
    assert weak["blocked_by_entry_score"] is False
    assert strong["blocked_by_entry_score"] is False


def test_risk_guard_blocks_aqtf_rejection():
    report = sweep_report("LONG", level=100.0, price=100.2)
    report["blocked_by_context"] = True
    report["blocked_by_entry_score"] = False
    report["no_chase_blocked"] = False
    result = SimpleRiskGuard().validate_setup(
        report,
        {"connected": True, "spread": 5, "volatility": 0.001},
    )
    assert result["allowed"] is False
    assert "AQTF" in result["reason"]
