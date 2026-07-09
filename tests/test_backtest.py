import inspect
import json

import pandas as pd

from trading_bot.backtest.runner import BacktestRunner, load_historical_csv
from trading_bot.journal.paper_forward import PaperForwardJournal


class OneLongSignal:
    def __init__(self):
        self.seen_timestamps = []
        self.emitted = False

    def detect_signals(self, data):
        self.seen_timestamps.append(list(data["time"]))
        if self.emitted:
            return {"setup": None, "liquidity": {}}
        self.emitted = True
        return {
            "setup": {
                "type": "LONG",
                "entry_price": float(data.iloc[-1]["close"]),
                "stop_loss": 9.0,
                "take_profit": 11.0,
            },
            "liquidity": {"recent_low": 9.5, "recent_high": 11.0},
        }


class AcceptedContext:
    def evaluate(self, data):
        return {
            "market_regime": "trend",
            "context_bias": "long",
            "context_score": 75,
            "context_reason": "Trend continuation",
            "distance_to_h1_high": 0.1,
            "distance_to_h1_low": 0.9,
            "distance_to_h1_mid": 0.4,
        }


class AcceptedEntry:
    def evaluate(self, signal_report, m5_data, context, market_state):
        return {
            "entry_score": 80,
            "entry_reason": "accepted",
            "blocked_by_context": False,
            "blocked_by_entry_score": False,
            "no_chase_blocked": False,
            "no_chase_reason": "within limit",
            "extension_atr": 0.1,
        }


class BlockedEntry(AcceptedEntry):
    def evaluate(self, signal_report, m5_data, context, market_state):
        result = super().evaluate(signal_report, m5_data, context, market_state)
        result["blocked_by_entry_score"] = True
        result["entry_score"] = 50
        return result


def candles() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": pd.to_datetime(
                [
                    "2026-07-08T10:00:00Z",
                    "2026-07-08T10:05:00Z",
                    "2026-07-08T10:10:00Z",
                ]
            ),
            "open": [10.0, 10.0, 10.0],
            "high": [10.5, 12.0, 10.5],
            "low": [9.5, 8.0, 9.5],
            "close": [10.0, 10.0, 10.0],
            "tick_volume": [100, 100, 100],
        }
    )


def runner(tmp_path, *, spread=0.0, entry_scorer=None, detector=None):
    return BacktestRunner(
        symbol="XAUUSD",
        timeframe="M5",
        journal=PaperForwardJournal(tmp_path),
        signal_detector=detector or OneLongSignal(),
        context_engine=AcceptedContext(),
        entry_scorer=entry_scorer or AcceptedEntry(),
        default_spread=spread,
        warmup_bars=1,
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_empty_csv_does_not_crash_and_generates_summary(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("timestamp,open,high,low,close,volume\n")

    data = load_historical_csv(csv_path)
    metrics = runner(tmp_path / "logs").run(data)

    assert metrics["total_trades"] == 0
    assert (tmp_path / "logs" / "daily_summary.json").exists()


def test_sample_run_writes_trade_and_summary_files(tmp_path):
    csv_path = tmp_path / "xauusd_m5.csv"
    candles().rename(
        columns={"time": "timestamp", "tick_volume": "volume"}
    ).to_csv(csv_path, index=False)

    metrics = runner(tmp_path / "logs").run(load_historical_csv(csv_path))

    assert metrics["total_trades"] == 1
    assert (tmp_path / "logs" / "trades.jsonl").exists()
    assert (tmp_path / "logs" / "daily_summary.json").exists()


def test_replay_never_sends_future_candles_to_signal_detector(tmp_path):
    detector = OneLongSignal()
    data = candles()

    runner(tmp_path, detector=detector).run(data)

    for call_index, timestamps in enumerate(detector.seen_timestamps):
        assert max(timestamps) <= data.iloc[call_index]["time"]


def test_same_candle_stop_and_target_uses_stop_first(tmp_path):
    runner(tmp_path).run(candles())

    trade = read_jsonl(tmp_path / "trades.jsonl")[0]
    assert trade["exit_price"] == 9.0
    assert trade["outcome"] == "loss"
    assert trade["extension_atr"] == 0.1
    assert trade["spread"] == 0.0
    assert trade["volatility"] == 0.0
    assert trade["atr"] == 1.0
    assert trade["candle_range"] == 1.0
    assert trade["risk_points"] == 1.0
    assert trade["reward_points"] == 1.0
    assert trade["planned_rr"] == 1.0
    assert trade["entry_distance_from_sweep"] == 0.5
    assert trade["bars_held"] == 1
    assert trade["exit_reason"] == "stop_loss"


def test_missing_spread_uses_configured_default(tmp_path):
    runner(tmp_path, spread=0.2).run(candles())

    trade = read_jsonl(tmp_path / "trades.jsonl")[0]
    assert trade["entry"] == 10.2


def test_blocked_setup_is_written_without_trade(tmp_path):
    metrics = runner(tmp_path, entry_scorer=BlockedEntry()).run(candles())

    assert metrics["total_trades"] == 0
    assert (tmp_path / "blocked_setups.jsonl").exists()
    blocked = read_jsonl(tmp_path / "blocked_setups.jsonl")[0]
    assert blocked["extension_atr"] == 0.1
    assert blocked["spread"] == 0.0
    assert blocked["volatility"] == 0.0
    assert blocked["atr"] == 1.0
    assert blocked["candle_range"] == 1.0


def test_backtest_module_has_no_order_send_path():
    import trading_bot.backtest.runner as backtest_module

    assert "order_send" not in inspect.getsource(backtest_module)
