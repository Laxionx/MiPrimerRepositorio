import inspect
from types import SimpleNamespace

import pandas as pd
import pytest

from trading_bot.data.mt5_history import (
    MT5HistoryError,
    export_from_local_terminal,
    export_mt5_history,
    resolve_timeframe,
)
from trading_bot.backtest import mt5_pipeline


class FakeMT5:
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240

    def __init__(self, *, initialize=True, symbol=True):
        self.initialize_result = initialize
        self.symbol_result = symbol
        self.shutdown_called = False

    def initialize(self):
        return self.initialize_result

    def shutdown(self):
        self.shutdown_called = True

    def last_error(self):
        return (1, "terminal unavailable")

    def symbol_info(self, symbol):
        return SimpleNamespace(name=symbol) if self.symbol_result else None

    def copy_rates_from_pos(self, symbol, timeframe, start, bars):
        return [
            {
                "time": 1_700_000_000,
                "open": 2000.0,
                "high": 2001.0,
                "low": 1999.0,
                "close": 2000.5,
                "tick_volume": 120,
                "real_volume": 0,
                "spread": 18,
            }
        ]


@pytest.mark.parametrize(
    ("label", "expected"),
    [("M5", 5), ("M15", 15), ("H1", 60), ("H4", 240)],
)
def test_supported_timeframe_mapping(label, expected):
    assert resolve_timeframe(FakeMT5(), label) == expected


def test_exported_csv_has_backtest_columns(tmp_path):
    output = tmp_path / "xauusd_m5.csv"

    export_mt5_history(
        FakeMT5(),
        symbol="XAUUSD",
        timeframe="M5",
        bars=100,
        output=output,
    )

    exported = pd.read_csv(output)
    assert list(exported.columns) == [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "spread",
    ]
    assert exported.iloc[0]["volume"] == 120
    assert exported.iloc[0]["spread"] == 18


def test_local_export_fails_cleanly_when_mt5_is_unavailable(tmp_path):
    gateway = FakeMT5(initialize=False)

    with pytest.raises(MT5HistoryError, match="terminal"):
        export_from_local_terminal(
            symbol="XAUUSD",
            timeframe="M5",
            bars=100,
            output=tmp_path / "history.csv",
            gateway=gateway,
        )

    assert gateway.shutdown_called is False


def test_pipeline_exports_then_runs_backtest(tmp_path, monkeypatch):
    calls = []
    output = tmp_path / "xauusd_m5.csv"

    def fake_export(**kwargs):
        calls.append("export")
        pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        ).to_csv(kwargs["output"], index=False)
        return kwargs["output"]

    class FakeRunner:
        def __init__(self, **kwargs):
            calls.append("runner")

        def run(self, data):
            calls.append("backtest")
            return {"total_trades": 0}

    monkeypatch.setattr(mt5_pipeline, "export_from_local_terminal", fake_export)
    monkeypatch.setattr(mt5_pipeline, "BacktestRunner", FakeRunner)

    result = mt5_pipeline.run_mt5_backtest(
        symbol="XAUUSD",
        timeframe="M5",
        bars=100,
        output=output,
        logs_dir=tmp_path / "logs",
    )

    assert calls == ["export", "runner", "backtest"]
    assert result["total_trades"] == 0


def test_export_and_pipeline_have_no_order_send_path():
    import trading_bot.data.mt5_history as history_module

    source = inspect.getsource(history_module) + inspect.getsource(mt5_pipeline)
    assert "order_send" not in source
    assert "account_info" not in source
