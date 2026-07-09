import json

from trading_bot.journal.paper_forward import PaperForwardJournal


def trade_record(trade_id: str, pnl: float, r_multiple: float) -> dict:
    return {
        "trade_id": trade_id,
        "timestamp_open": "2026-07-08T10:00:00+00:00",
        "timestamp_close": "2026-07-08T11:00:00+00:00",
        "symbol": "XAUUSD",
        "timeframe": "TIMEFRAME_M5",
        "direction": "LONG",
        "entry": 2350.0,
        "stop_loss": 2345.0,
        "take_profit": 2360.0,
        "exit_price": 2360.0 if pnl > 0 else 2345.0,
        "pnl": pnl,
        "r_multiple": r_multiple,
        "outcome": "win" if pnl > 0 else "loss",
        "market_regime": "trend",
        "context_bias": "long",
        "context_score": 75,
        "context_reason": "Trend continuation",
        "entry_score": 85,
        "distance_to_h1_high": 0.1,
        "distance_to_h1_low": 0.9,
        "distance_to_h1_mid": 0.4,
    }


def setup_record(*, blocked: bool) -> dict:
    return {
        "generated_at": "2026-07-08T09:00:00+00:00",
        "symbol": "XAUUSD",
        "setup": {"type": "LONG"},
        "market_regime": "range",
        "context_score": 55 if blocked else 75,
        "entry_score": 60 if blocked else 80,
        "blocked_by_context": blocked,
        "blocked_by_entry_score": False,
        "no_chase_blocked": False,
        "no_chase_reason": "entry remains within no-chase limit",
    }


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_completed_trade_is_logged_with_required_context(tmp_path):
    journal = PaperForwardJournal(tmp_path)
    record = trade_record("trade-1", 100.0, 2.0)
    record.update(
        {
            "extension_atr": 0.25,
            "spread": 18.0,
            "volatility": 0.001,
            "atr": 4.0,
            "candle_range": 5.0,
            "risk_points": 5.0,
            "reward_points": 10.0,
            "planned_rr": 2.0,
            "entry_distance_from_sweep": 1.0,
            "bars_held": 3,
            "exit_reason": "take_profit",
        }
    )

    journal.record_completed_trade(record)

    records = read_jsonl(tmp_path / "trades.jsonl")
    assert len(records) == 1
    assert records[0]["trade_id"] == "trade-1"
    assert records[0]["market_regime"] == "trend"
    assert records[0]["r_multiple"] == 2.0
    assert records[0]["extension_atr"] == 0.25
    assert records[0]["bars_held"] == 3
    assert records[0]["exit_reason"] == "take_profit"


def test_blocked_aqtf_setup_is_logged(tmp_path):
    journal = PaperForwardJournal(tmp_path)

    journal.record_setup(setup_record(blocked=True))

    records = read_jsonl(tmp_path / "blocked_setups.jsonl")
    assert records == [
        {
            "timestamp": "2026-07-08T09:00:00+00:00",
            "symbol": "XAUUSD",
            "market_regime": "range",
            "context_score": 55,
            "entry_score": 60,
            "block_reason": "context_score_below_threshold",
            "no_chase_blocked": False,
        }
    ]


def test_daily_summary_combines_setups_and_completed_trades(tmp_path):
    journal = PaperForwardJournal(tmp_path)
    journal.record_setup(setup_record(blocked=False))
    journal.record_setup(setup_record(blocked=True))
    journal.record_completed_trade(trade_record("trade-1", 100.0, 2.0))
    journal.record_completed_trade(trade_record("trade-2", -50.0, -1.0))

    summary = journal.write_daily_summary("2026-07-08")

    assert summary["total_setups"] == 2
    assert summary["accepted_setups"] == 1
    assert summary["blocked_setups"] == 1
    assert summary["executed_trades"] == 2
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["win_rate"] == 0.5
    assert summary["expectancy"] == 25.0
    assert summary["profit_factor"] == 2.0
    assert json.loads((tmp_path / "daily_summary.json").read_text()) == summary


def test_empty_journals_generate_zero_summary(tmp_path):
    summary = PaperForwardJournal(tmp_path).write_daily_summary("2026-07-08")

    assert summary["total_setups"] == 0
    assert summary["executed_trades"] == 0
    assert summary["win_rate"] == 0.0
    assert summary["profit_factor"] is None
