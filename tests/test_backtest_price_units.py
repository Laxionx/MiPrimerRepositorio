import json

import pandas as pd
import pytest

from trading_bot.backtest.price_units import PriceUnitContract
from trading_bot.backtest.runner import BacktestRunner, load_historical_csv
from trading_bot.journal.paper_forward import PaperForwardJournal


class OneSignal:
    def __init__(self, direction: str, *, stop: float, target: float):
        self.direction = direction
        self.stop = stop
        self.target = target
        self.emitted = False

    def detect_signals(self, data):
        if self.emitted:
            return {"setup": None, "liquidity": {}}
        self.emitted = True
        return {
            "setup": {
                "type": self.direction,
                "entry_price": float(data.iloc[-1]["close"]),
                "stop_loss": self.stop,
                "take_profit": self.target,
            },
            "liquidity": {"recent_low": self.stop, "recent_high": self.target},
        }


class AcceptedContext:
    def evaluate(self, _data):
        return {
            "market_regime": "test",
            "context_bias": "neutral",
            "context_score": 100,
            "context_reason": "test",
            "distance_to_h1_high": 0.0,
            "distance_to_h1_low": 0.0,
            "distance_to_h1_mid": 0.0,
        }


class AcceptedEntry:
    def evaluate(self, *_args):
        return {
            "entry_score": 100,
            "entry_reason": "test",
            "blocked_by_context": False,
            "blocked_by_entry_score": False,
            "no_chase_blocked": False,
            "no_chase_reason": "test",
            "extension_atr": 0.0,
        }


def bars(*, point_size: float, spread_points: float, opens: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=len(opens), freq="5min", tz="UTC"),
            "open": opens,
            "high": [value + 0.01 for value in opens],
            "low": [value - 0.01 for value in opens],
            "close": opens,
            "tick_volume": [100] * len(opens),
            "spread_points": [spread_points] * len(opens),
            "point_size": [point_size] * len(opens),
            "tick_size": [point_size * 10] * len(opens),
            "spread_price": [spread_points * point_size] * len(opens),
        }
    )


def make_runner(tmp_path, *, direction: str, stop: float, target: float, contract, slippage_points=0):
    return BacktestRunner(
        symbol="TEST",
        timeframe="M5",
        journal=PaperForwardJournal(tmp_path),
        signal_detector=OneSignal(direction, stop=stop, target=target),
        context_engine=AcceptedContext(),
        entry_scorer=AcceptedEntry(),
        price_units=contract,
        slippage_points=slippage_points,
        warmup_bars=1,
    )


def records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_contract_preserves_point_and_tick_size_and_normalizes_points():
    contract = PriceUnitContract(point_size=0.00001, tick_size=0.0001)

    assert contract.spread_price(20) == pytest.approx(0.00020)
    assert contract.slippage_price(3) == pytest.approx(0.00003)
    assert contract.tick_size == pytest.approx(0.0001)


def test_xau_style_spread_normalizes_to_price():
    contract = PriceUnitContract(point_size=0.01, tick_size=0.1)

    assert contract.spread_price(50) == pytest.approx(0.50)


def test_long_entry_uses_normalized_spread_and_slippage(tmp_path):
    contract = PriceUnitContract(point_size=0.00001, tick_size=0.0001)
    data = bars(point_size=0.00001, spread_points=20, opens=[1.10000, 1.10000, 1.10200])
    data.loc[1, "high"] = 1.10050
    data.loc[1, "low"] = 1.10000
    data.loc[2, "high"] = 1.10300
    data.loc[2, "low"] = 1.10100
    runner = make_runner(tmp_path, direction="LONG", stop=1.09900, target=1.10200, contract=contract, slippage_points=3)

    runner.run(data)

    trade = records(tmp_path / "trades.jsonl")[0]
    assert trade["entry"] == pytest.approx(1.10023)
    assert trade["spread_points"] == 20
    assert trade["spread_price"] == pytest.approx(0.00020)
    assert trade["slippage_price"] == pytest.approx(0.00003)
    assert trade["stop_loss"] < trade["entry"] < trade["take_profit"]
    assert trade["pnl"] > 0 and trade["r_multiple"] > 0 and trade["outcome"] == "win"


def test_short_entry_uses_normalized_spread(tmp_path):
    contract = PriceUnitContract(point_size=0.01, tick_size=0.1)
    data = bars(point_size=0.01, spread_points=50, opens=[2000.0, 2000.0, 1998.0])
    data.loc[2, "low"] = 1997.0
    runner = make_runner(tmp_path, direction="SHORT", stop=2001.0, target=1998.0, contract=contract)

    runner.run(data)

    trade = records(tmp_path / "trades.jsonl")[0]
    assert trade["entry"] == pytest.approx(1999.5)
    assert trade["take_profit"] < trade["entry"] < trade["stop_loss"]


def test_positive_spread_without_contract_fails_closed(tmp_path):
    data = bars(point_size=0.00001, spread_points=20, opens=[1.1, 1.1, 1.1])
    data = data.drop(columns=["point_size", "tick_size", "spread_price"])
    runner = make_runner(tmp_path, direction="LONG", stop=1.09, target=1.12, contract=None)

    with pytest.raises(ValueError, match="point_size"):
        runner.run(data)


def test_slippage_points_without_point_size_fails_closed(tmp_path):
    data = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=3, freq="5min", tz="UTC"),
            "open": [1.1, 1.1, 1.1], "high": [1.11] * 3, "low": [1.09] * 3,
            "close": [1.1] * 3, "tick_volume": [100] * 3,
        }
    )
    runner = make_runner(tmp_path, direction="LONG", stop=1.09, target=1.12, contract=None, slippage_points=1)

    with pytest.raises(ValueError, match="slippage_points"):
        runner.run(data)


def test_legacy_positive_raw_spread_csv_fails_closed(tmp_path):
    path = tmp_path / "legacy.csv"
    pd.DataFrame(
        {
            "timestamp": ["2026-01-01T00:00:00Z"], "open": [1.1], "high": [1.2],
            "low": [1.0], "close": [1.1], "volume": [100], "spread": [20],
        }
    ).to_csv(path, index=False)

    with pytest.raises(ValueError, match="ambiguous legacy spread"):
        load_historical_csv(path)


@pytest.mark.parametrize(
    ("direction", "stop", "target", "opens"),
    [
        ("LONG", 1.0990, 1.1001, [1.1000, 1.1000, 1.1000]),
        ("SHORT", 1.1010, 1.0999, [1.1000, 1.1000, 1.1000]),
    ],
)
def test_invalid_post_cost_geometry_is_journaled_and_not_opened(tmp_path, direction, stop, target, opens):
    contract = PriceUnitContract(point_size=0.00001, tick_size=0.0001)
    data = bars(point_size=0.00001, spread_points=20, opens=opens)
    runner = make_runner(tmp_path, direction=direction, stop=stop, target=target, contract=contract)

    metrics = runner.run(data)

    assert metrics["total_trades"] == 0
    blocked = records(tmp_path / "post_cost_blocks.jsonl")[0]
    assert blocked["block_reason"] == "invalid_post_cost_trade_geometry"
    assert blocked["spread_points"] == 20
    assert blocked["point_size"] == pytest.approx(0.00001)
    assert blocked["spread_price"] == pytest.approx(0.00020)


def test_trade_id_includes_timeframe_for_same_symbol_and_timestamp(tmp_path):
    contract = PriceUnitContract(point_size=0.00001, tick_size=0.0001)
    data = bars(point_size=0.00001, spread_points=0, opens=[1.1, 1.1, 1.102])
    data.loc[2, "high"] = 1.103
    m5 = make_runner(tmp_path / "m5", direction="LONG", stop=1.099, target=1.102, contract=contract)
    m15 = BacktestRunner(
        symbol="TEST", timeframe="M15", journal=PaperForwardJournal(tmp_path / "m15"),
        signal_detector=OneSignal("LONG", stop=1.099, target=1.102), context_engine=AcceptedContext(),
        entry_scorer=AcceptedEntry(), price_units=contract, warmup_bars=1,
    )

    m5.run(data)
    m15.run(data)

    assert records(tmp_path / "m5" / "trades.jsonl")[0]["trade_id"] != records(tmp_path / "m15" / "trades.jsonl")[0]["trade_id"]
