import inspect
import json
import sys

from trading_bot.data.mt5_history import MT5HistoryError
from trading_bot.research import edge_v2_mt5_batch


def plan_item(timeframe="M5"):
    return {
        "symbol": "XAUUSD",
        "timeframe": timeframe,
        "start": "2026-05-18T19:10:00+00:00",
        "end": "2026-07-10T01:40:00+00:00",
    }


def report(effect=0.4):
    return {
        "candle_count": 1000,
        "trade_count": 60,
        "winner_count": 25,
        "loser_count": 30,
        "breakeven_count": 5,
        "features": {"compression_score": {"sample_count": 60, "simple_effect_size": effect}},
        "diagnostic_only": True,
        "submit_allowed": False,
        "broker_api_called": False,
    }


def test_batch_plan_parses_json(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps([plan_item(), plan_item("M15")]))

    assert edge_v2_mt5_batch.load_batch_plan(path) == [plan_item(), plan_item("M15")]


def test_batch_continues_after_blocked_run_and_aggregates(tmp_path, monkeypatch):
    calls = []

    def fake_pipeline(**kwargs):
        calls.append(kwargs["timeframe"])
        if kwargs["timeframe"] == "M15":
            raise MT5HistoryError("no M15 history")
        return {"report": report(), "report_path": kwargs["out_dir"] / "report.json"}

    monkeypatch.setattr(edge_v2_mt5_batch, "run_edge_v2_mt5_research", fake_pipeline)
    summary = edge_v2_mt5_batch.run_edge_v2_mt5_batch(
        [plan_item(), plan_item("M15")],
        out_dir=tmp_path,
    )

    assert calls == ["M5", "M15"]
    assert summary["successful_runs"] == 1
    assert summary["failed_or_blocked_runs"] == 1
    assert summary["total_candles"] == 1000
    assert summary["per_run_summary"][1]["status"] == "environment_blocked"
    assert summary["submit_allowed"] is False


def test_batch_forwards_explicit_pagination_options(tmp_path, monkeypatch):
    calls = []

    def fake_pipeline(**kwargs):
        calls.append(kwargs)
        return {"report": report(), "report_path": kwargs["out_dir"] / "report.json"}

    monkeypatch.setattr(edge_v2_mt5_batch, "run_edge_v2_mt5_research", fake_pipeline)
    edge_v2_mt5_batch.run_edge_v2_mt5_batch(
        [plan_item()], out_dir=tmp_path, history_mode="paginated", page_size=2
    )

    assert calls[0]["history_mode"] == "paginated"
    assert calls[0]["page_size"] == 2


def test_batch_cli_forwards_paginated_options(tmp_path, monkeypatch):
    captured = {}
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps([plan_item()]), encoding="utf-8")

    def fake_batch(plan_data, **kwargs):
        captured["plan"] = plan_data
        captured.update(kwargs)

    monkeypatch.setattr(edge_v2_mt5_batch, "run_edge_v2_mt5_batch", fake_batch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "edge_v2_mt5_batch", "--plan", str(plan), "--out-dir", str(tmp_path),
            "--history-mode", "paginated", "--page-size", "2", "--include-current-bar",
            "--allow-partial-history",
        ],
    )

    edge_v2_mt5_batch.main()

    assert captured["history_mode"] == "paginated"
    assert captured["page_size"] == 2
    assert captured["include_current_bar"] is True
    assert captured["require_complete"] is False


def test_aggregate_reports_direction_consistency_and_stability():
    aggregate = edge_v2_mt5_batch.aggregate_feature_summaries(
        [
            {"run_id": "a", "features": report(0.4)["features"]},
            {"run_id": "b", "features": report(0.6)["features"]},
            {"run_id": "c", "features": report(-0.5)["features"]},
        ]
    )["compression_score"]

    assert aggregate["runs_available"] == 3
    assert aggregate["positive_direction_count"] == 2
    assert aggregate["negative_direction_count"] == 1
    assert aggregate["direction_consistency"] is False
    assert aggregate["stability_flag"] == "unstable"


def test_batch_code_has_no_order_send_or_submit_activation():
    source = inspect.getsource(edge_v2_mt5_batch)
    assert "order_send" not in source
    assert "submit_allowed=True" not in source
