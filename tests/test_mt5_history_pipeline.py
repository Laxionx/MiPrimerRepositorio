import inspect
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from trading_bot.data.mt5_history import (
    MT5HistoryError,
    export_from_local_terminal,
    export_mt5_history,
    export_mt5_history_paginated,
    export_mt5_history_range,
    export_paginated_from_local_terminal,
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

    def copy_rates_range(self, symbol, timeframe, start, end):
        return self.copy_rates_from_pos(symbol, timeframe, 0, 1)


def rate(timestamp, *, high=2001.0):
    return {
        "time": timestamp,
        "open": 2000.0,
        "high": high,
        "low": 1999.0,
        "close": 2000.5,
        "tick_volume": 120,
        "real_volume": 0,
        "spread": 18,
    }


class PagedMT5(FakeMT5):
    def __init__(self, pages, *, error=(1, "Success")):
        super().__init__()
        self.pages = pages
        self.error = error
        self.position_calls = []
        self.range_calls = 0

    def copy_rates_from_pos(self, symbol, timeframe, start, bars):
        self.position_calls.append((symbol, timeframe, start, bars))
        return self.pages.get(start)

    def copy_rates_range(self, symbol, timeframe, start, end):
        self.range_calls += 1
        raise AssertionError("paginated export must not call copy_rates_range")

    def last_error(self):
        return self.error


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


def test_range_exported_csv_has_backtest_columns(tmp_path):
    output = tmp_path / "xauusd_m5_range.csv"

    export_mt5_history_range(
        FakeMT5(),
        symbol="XAUUSD",
        timeframe="M5",
        start="2025-01-01",
        end="2025-01-02",
        output=output,
    )

    assert pd.read_csv(output).iloc[0]["close"] == 2000.5


def test_paginated_export_sorts_pages_uses_closed_bar_and_writes_manifest(tmp_path):
    gateway = PagedMT5(
        {
            1: [rate(600), rate(900)],
            3: [rate(0), rate(300)],
        }
    )
    output = tmp_path / "history.csv"
    manifest_path = tmp_path / "manifest.json"

    result = export_mt5_history_paginated(
        gateway,
        symbol="XAUUSD",
        timeframe="M5",
        start="1970-01-01T00:00:00+00:00",
        end="1970-01-01T00:20:00+00:00",
        output=output,
        manifest_out=manifest_path,
        page_size=2,
    )

    assert [call[2] for call in gateway.position_calls] == [1, 3]
    assert gateway.range_calls == 0
    assert pd.read_csv(result.csv_path)["timestamp"].tolist() == [
        "1970-01-01 00:00:00+00:00",
        "1970-01-01 00:05:00+00:00",
        "1970-01-01 00:10:00+00:00",
        "1970-01-01 00:15:00+00:00",
    ]
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["status"] == "complete"


def test_paginated_export_deduplicates_identical_rows_and_records_gaps(tmp_path):
    gateway = PagedMT5(
        {
            1: [rate(600), rate(900)],
            3: [rate(0), rate(600)],
        }
    )
    manifest_path = tmp_path / "manifest.json"

    export_mt5_history_paginated(
        gateway,
        symbol="XAUUSD",
        timeframe="M5",
        start="1970-01-01T00:00:00+00:00",
        end="1970-01-01T00:20:00+00:00",
        output=tmp_path / "history.csv",
        manifest_out=manifest_path,
        page_size=2,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["duplicate_bars"] == 1
    assert manifest["gap_count"] == 1
    assert manifest["gaps"][0]["classification"] == "unclassified_gap"


def test_paginated_export_rejects_conflicting_duplicates_without_csv(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    with pytest.raises(MT5HistoryError, match="conflicting duplicate"):
        export_mt5_history_paginated(
            PagedMT5({1: [rate(600), rate(900)], 3: [rate(0), rate(600, high=2002.0)]}),
            symbol="XAUUSD",
            timeframe="M5",
            start="1970-01-01T00:00:00+00:00",
            end="1970-01-01T00:20:00+00:00",
            output=tmp_path / "history.csv",
            manifest_out=manifest_path,
            page_size=2,
        )

    assert json.loads(manifest_path.read_text(encoding="utf-8"))["status"] == "integrity_failed"
    assert not (tmp_path / "history.csv").exists()


def test_paginated_export_records_partial_boundary_and_mt5_error(tmp_path):
    partial_manifest = tmp_path / "partial.json"
    with pytest.raises(MT5HistoryError, match="partial"):
        export_mt5_history_paginated(
            PagedMT5({1: [rate(900)]}),
            symbol="XAUUSD",
            timeframe="M5",
            start="1970-01-01T00:00:00+00:00",
            end="1970-01-01T00:20:00+00:00",
            output=tmp_path / "partial.csv",
            manifest_out=partial_manifest,
            page_size=2,
        )
    assert json.loads(partial_manifest.read_text(encoding="utf-8"))["status"] == "partial_history_boundary"

    error_manifest = tmp_path / "error.json"
    with pytest.raises(MT5HistoryError, match="MT5 page request failed"):
        export_mt5_history_paginated(
            PagedMT5({1: None}, error=(-2, "Invalid params")),
            symbol="XAUUSD",
            timeframe="M5",
            start="1970-01-01T00:00:00+00:00",
            end="1970-01-01T00:20:00+00:00",
            output=tmp_path / "error.csv",
            manifest_out=error_manifest,
            page_size=2,
        )
    manifest = json.loads(error_manifest.read_text(encoding="utf-8"))
    assert manifest["status"] == "environment_blocked"
    assert manifest["pages"][0]["last_error"] == [-2, "Invalid params"]


@pytest.mark.parametrize("broken", ["spread", "real_volume"])
def test_paginated_export_rejects_missing_required_columns(tmp_path, broken):
    source = rate(0)
    source.pop(broken)
    manifest_path = tmp_path / "manifest.json"

    with pytest.raises(MT5HistoryError, match="missing fields"):
        export_mt5_history_paginated(
            PagedMT5({1: [source]}),
            symbol="XAUUSD",
            timeframe="M5",
            start="1970-01-01T00:00:00+00:00",
            end="1970-01-01T00:00:00+00:00",
            output=tmp_path / "history.csv",
            manifest_out=manifest_path,
        )

    assert json.loads(manifest_path.read_text(encoding="utf-8"))["status"] == "integrity_failed"


def test_paginated_export_rejects_timestamp_not_aligned_to_timeframe(tmp_path):
    manifest_path = tmp_path / "manifest.json"

    with pytest.raises(MT5HistoryError, match="not aligned"):
        export_mt5_history_paginated(
            PagedMT5({1: [rate(1)]}),
            symbol="XAUUSD",
            timeframe="M5",
            start="1970-01-01T00:00:01+00:00",
            end="1970-01-01T00:00:01+00:00",
            output=tmp_path / "history.csv",
            manifest_out=manifest_path,
        )

    assert json.loads(manifest_path.read_text(encoding="utf-8"))["status"] == "integrity_failed"


def test_local_paginated_export_initializes_and_records_terminal_block(tmp_path):
    output = tmp_path / "history.csv"
    manifest_path = tmp_path / "manifest.json"
    gateway = PagedMT5({1: [rate(0)]})

    result = export_paginated_from_local_terminal(
        symbol="XAUUSD",
        timeframe="M5",
        start="1970-01-01T00:00:00+00:00",
        end="1970-01-01T00:00:00+00:00",
        output=output,
        manifest_out=manifest_path,
        gateway=gateway,
    )

    assert result.csv_path == output
    assert gateway.shutdown_called is True

    blocked = PagedMT5({})
    blocked.initialize_result = False
    blocked_manifest = tmp_path / "blocked.json"
    with pytest.raises(MT5HistoryError, match="terminal is unavailable"):
        export_paginated_from_local_terminal(
            symbol="XAUUSD",
            timeframe="M5",
            start="1970-01-01T00:00:00+00:00",
            end="1970-01-01T00:00:00+00:00",
            output=tmp_path / "blocked.csv",
            manifest_out=blocked_manifest,
            gateway=blocked,
        )
    assert json.loads(blocked_manifest.read_text(encoding="utf-8"))["status"] == "environment_blocked"


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
