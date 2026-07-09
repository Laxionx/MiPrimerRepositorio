import inspect
import json

import pandas as pd
import pytest

from trading_bot.data.mt5_history import MT5HistoryError
from trading_bot.research import edge_v2_mt5_pipeline


def historical_candles() -> pd.DataFrame:
    timestamps = pd.date_range("2025-01-01", periods=120, freq="5min", tz="UTC")
    closes = [2000.0 + index * 0.1 for index in range(len(timestamps))]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": [close + 0.5 for close in closes],
            "low": [close - 0.5 for close in closes],
            "close": closes,
            "volume": [100] * len(timestamps),
            "spread": [1.0] * len(timestamps),
        }
    )


def test_pipeline_writes_analysis_only_mt5_report(tmp_path, monkeypatch):
    calls = []

    def fake_export(**kwargs):
        calls.append(kwargs)
        historical_candles().to_csv(kwargs["output"], index=False)
        return kwargs["output"]

    monkeypatch.setattr(
        edge_v2_mt5_pipeline,
        "export_range_from_local_terminal",
        fake_export,
    )

    result = edge_v2_mt5_pipeline.run_edge_v2_mt5_research(
        symbol="XAUUSD",
        timeframe="M5",
        start="2025-01-01",
        end="2025-01-02",
        out_dir=tmp_path,
    )

    report = json.loads(result["report_path"].read_text())
    assert calls[0]["symbol"] == "XAUUSD"
    assert report["data_provider"] == "mt5"
    assert report["symbol"] == "XAUUSD"
    assert report["timeframe"] == "M5"
    assert report["candle_count"] == 120
    assert report["diagnostic_only"] is True
    assert report["submit_allowed"] is False
    assert report["broker_api_called"] is False
    assert result["journal_path"].exists() is False


def test_pipeline_fails_cleanly_without_mt5_data(tmp_path, monkeypatch):
    def unavailable(**kwargs):
        raise MT5HistoryError("MT5 terminal is unavailable: test")

    monkeypatch.setattr(
        edge_v2_mt5_pipeline,
        "export_range_from_local_terminal",
        unavailable,
    )

    with pytest.raises(MT5HistoryError, match="terminal is unavailable"):
        edge_v2_mt5_pipeline.run_edge_v2_mt5_research(
            symbol="XAUUSD",
            timeframe="M5",
            start="2025-01-01",
            end="2025-01-02",
            out_dir=tmp_path,
        )

    assert not (tmp_path / "edge_v2_feature_separation.json").exists()


def test_pipeline_and_range_export_have_no_order_send_path():
    import trading_bot.data.mt5_history as history_module

    source = inspect.getsource(edge_v2_mt5_pipeline) + inspect.getsource(history_module)
    assert "order_send" not in source


def test_report_summarizes_strongest_and_weakest_features():
    features = {
        "compression_score": {"simple_effect_size": 1.2},
        "pressure_score": {"simple_effect_size": 0.3},
        "pressure_direction": {"simple_effect_size": None},
    }

    strongest, weakest = edge_v2_mt5_pipeline.rank_feature_separation(features)

    assert strongest == ["compression_score", "pressure_score"]
    assert weakest == ["pressure_score", "compression_score"]
