import csv
import hashlib
import inspect
import json

from collections import Counter

import pytest

from trading_bot.research import edge_v4_setup_failure_audit
from trading_bot.research.edge_v4_setup_failure_metrics import outcome_distribution
from trading_bot.signals.liquidity_sweep import LiquiditySweepDetector


def _trade(*, direction="LONG", opened="2026-01-01T00:00:00Z", closed="2026-01-01T00:10:00Z"):
    if direction == "LONG":
        stop_loss, take_profit = 98.0, 104.0
    else:
        stop_loss, take_profit = 102.0, 96.0
    return {
        "trade_id": f"trade-{direction}",
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "direction": direction,
        "timestamp_open": opened,
        "timestamp_close": closed,
        "entry": 100.0,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "exit_price": take_profit,
        "risk_points": 2.0,
        "reward_points": 4.0,
        "pnl": 4.0,
        "r_multiple": 2.0,
        "outcome": "win",
        "exit_reason": "take_profit",
        "bars_held": 3,
    }


def _rows(*values):
    return [
        {
            "timestamp": timestamp,
            "open": 100.0,
            "high": high,
            "low": low,
            "close": close,
            "volume": 100,
            "spread": 0,
        }
        for timestamp, high, low, close in values
    ]


def _loss_trade():
    trade = _trade()
    trade.update(
        exit_price=98.0,
        pnl=-2.0,
        r_multiple=-1.0,
        outcome="loss",
        exit_reason="stop_loss",
    )
    return trade


def _write_run(tmp_path, rows, trades, *, manifest_status="complete", checksum=None):
    run_dir = tmp_path / "run_001_xauusd_m5"
    journal_dir = run_dir / "journal"
    journal_dir.mkdir(parents=True)
    csv_path = run_dir / "mt5_history.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    manifest = {
        "status": manifest_status,
        "csv_sha256": checksum or digest,
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "obtained_start": rows[0]["timestamp"],
        "obtained_end": rows[-1]["timestamp"],
        "filtered_bars": len(rows),
        "duplicate_bars": 0,
        "conflicting_duplicates": 0,
        "gaps": [],
    }
    (run_dir / "mt5_history_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (journal_dir / "trades.jsonl").write_text(
        "".join(json.dumps(trade) + "\n" for trade in trades), encoding="utf-8"
    )
    return run_dir


def test_reconstructs_long_mfe_mae_and_timing(tmp_path):
    rows = _rows(
        ("2026-01-01T00:00:00Z", 101.0, 99.0, 100.0),
        ("2026-01-01T00:05:00Z", 103.0, 99.5, 102.0),
        ("2026-01-01T00:10:00Z", 105.0, 99.2, 104.0),
    )
    _write_run(tmp_path, rows, [_trade()])

    report = edge_v4_setup_failure_audit.run_setup_failure_audit(tmp_path)
    excursion = report["runs"][0]["trade_excursions"][0]

    assert excursion["mfe"] == 5.0
    assert excursion["mae"] == 1.0
    assert excursion["mfe_r"] == 2.5
    assert excursion["mae_r"] == 0.5
    assert excursion["bars_to_mfe"] == 2
    assert excursion["timestamp_mfe"] == "2026-01-01T00:10:00+00:00"


def test_reconstructs_short_mfe_mae(tmp_path):
    rows = _rows(
        ("2026-01-01T00:00:00Z", 101.0, 99.0, 100.0),
        ("2026-01-01T00:05:00Z", 101.0, 97.0, 98.0),
        ("2026-01-01T00:10:00Z", 100.5, 95.0, 96.0),
    )
    _write_run(tmp_path, rows, [_trade(direction="SHORT")])

    report = edge_v4_setup_failure_audit.run_setup_failure_audit(tmp_path)
    excursion = report["runs"][0]["trade_excursions"][0]

    assert excursion["mfe"] == 5.0
    assert excursion["mae"] == 1.0
    assert excursion["bars_to_mae"] == 0
    assert excursion["timestamp_mae"] == "2026-01-01T00:00:00+00:00"


def test_marks_same_bar_tp_and_sl_as_ambiguous(tmp_path):
    rows = _rows(
        ("2026-01-01T00:00:00Z", 101.0, 99.0, 100.0),
        ("2026-01-01T00:05:00Z", 105.0, 97.0, 101.0),
        ("2026-01-01T00:10:00Z", 103.0, 99.0, 102.0),
    )
    _write_run(tmp_path, rows, [_trade()])

    report = edge_v4_setup_failure_audit.run_setup_failure_audit(tmp_path)
    excursion = report["runs"][0]["trade_excursions"][0]

    assert excursion["tp_touched"] is True
    assert excursion["sl_touched"] is True
    assert excursion["ambiguous_both_levels"] is True


def test_marks_trade_unavailable_when_its_candle_window_has_a_gap(tmp_path):
    rows = _rows(
        ("2026-01-01T00:00:00Z", 101.0, 99.0, 100.0),
        ("2026-01-01T00:10:00Z", 105.0, 99.0, 104.0),
    )
    _write_run(tmp_path, rows, [_trade()])

    report = edge_v4_setup_failure_audit.run_setup_failure_audit(tmp_path)
    excursion = report["runs"][0]["trade_excursions"][0]

    assert excursion["data_quality_status"] == "data_unavailable"
    assert excursion["data_quality_reason"] == "gap_in_trade_window"


def test_marks_trade_unavailable_when_it_does_not_match_its_run_segment(tmp_path):
    rows = _rows(
        ("2026-01-01T00:00:00Z", 101.0, 99.0, 100.0),
        ("2026-01-01T00:05:00Z", 103.0, 99.0, 102.0),
        ("2026-01-01T00:10:00Z", 105.0, 99.0, 104.0),
    )
    trade = _trade()
    trade["symbol"] = "EURUSD"
    _write_run(tmp_path, rows, [trade])

    report = edge_v4_setup_failure_audit.run_setup_failure_audit(tmp_path)
    excursion = report["runs"][0]["trade_excursions"][0]

    assert excursion["data_quality_status"] == "data_unavailable"
    assert excursion["data_quality_reason"] == "trade_segment_mismatch"


@pytest.mark.parametrize(
    ("manifest_status", "checksum", "message"),
    [
        ("partial", None, "manifest_not_complete"),
        ("complete", "not-the-csv-hash", "manifest_csv_hash_mismatch"),
    ],
)
def test_rejects_incomplete_or_inconsistent_manifest(tmp_path, manifest_status, checksum, message):
    rows = _rows(
        ("2026-01-01T00:00:00Z", 101.0, 99.0, 100.0),
        ("2026-01-01T00:05:00Z", 103.0, 99.0, 102.0),
        ("2026-01-01T00:10:00Z", 105.0, 99.0, 104.0),
    )
    _write_run(tmp_path, rows, [_trade()], manifest_status=manifest_status, checksum=checksum)

    with pytest.raises(ValueError, match=message):
        edge_v4_setup_failure_audit.run_setup_failure_audit(tmp_path)


def test_funnel_replay_matches_detector_and_preserves_short_priority():
    rows = _rows(
        *[
            (f"2026-01-01T{hour:02d}:00:00Z", 100.0, 80.0, 85.0)
            for hour in range(20)
        ],
        ("2026-01-01T20:00:00Z", 101.0, 79.0, 90.0),
        ("2026-01-01T21:00:00Z", 100.0, 80.0, 85.0),
    )

    candles = edge_v4_setup_failure_audit.load_audit_candles(rows)
    funnel = edge_v4_setup_failure_audit.build_detector_funnel(candles)
    detector_report = LiquiditySweepDetector().detect_signals(candles.iloc[:21])

    assert funnel["high_sweep_observations"] == 1
    assert funnel["low_sweep_observations"] == 1
    assert funnel["generated_short_setups"] == 1
    assert funnel["generated_long_setups"] == 0
    assert detector_report["setup"]["type"] == "SHORT"


def test_aggregated_json_is_deterministic_and_writes_requested_outputs(tmp_path):
    rows = _rows(
        ("2026-01-01T00:00:00Z", 101.0, 99.0, 100.0),
        ("2026-01-01T00:05:00Z", 103.0, 99.0, 102.0),
        ("2026-01-01T00:10:00Z", 105.0, 99.0, 104.0),
    )
    _write_run(tmp_path, rows, [_trade()])
    out = tmp_path / "audit.json"
    detail = tmp_path / "detail.jsonl"

    first = edge_v4_setup_failure_audit.run_setup_failure_audit(tmp_path, out=out, detail_out=detail)
    second = edge_v4_setup_failure_audit.run_setup_failure_audit(tmp_path)

    assert first == second
    assert json.loads(out.read_text(encoding="utf-8"))["conclusion"]["trading_rule_generated"] is False
    assert len(detail.read_text(encoding="utf-8").splitlines()) == 1
    assert first["outcome_distribution"]["bars_held_distribution"]["count"] == 1
    assert first["early_movement_by_bar"][0]["mean_cumulative_mfe_r"] == 0.5


def test_outcome_distribution_marks_no_winners_without_throwing():
    result = outcome_distribution([_loss_trade()])

    assert result["mean_win_r"] is None
    assert result["payoff_ratio_r"] is None
    assert "no_winners" in result["payoff_ratio_flags"]


def test_outcome_distribution_marks_no_losers_without_throwing():
    result = outcome_distribution([_trade()])

    assert result["mean_loss_r"] is None
    assert result["payoff_ratio_r"] is None
    assert "no_losers" in result["payoff_ratio_flags"]


def test_outcome_distribution_marks_empty_segment_as_undefined():
    result = outcome_distribution([])

    assert result["expectancy_r"] is None
    assert result["payoff_ratio_r"] is None
    assert "empty_or_no_resolved_outcomes" in result["payoff_ratio_flags"]


def test_outcome_distribution_preserves_payoff_for_resolved_segment():
    result = outcome_distribution([_trade(), _loss_trade()])

    assert result["mean_win_r"] == 2.0
    assert result["mean_loss_r"] == 1.0
    assert result["payoff_ratio_r"] == 2.0
    assert result["expectancy_r"] == result["weighted_expectancy_r"]
    assert result["payoff_ratio_flags"] == []


def test_outcome_distribution_uses_r_not_cross_instrument_price_pnl():
    eur = _trade()
    eur.update(symbol="EURUSD", pnl=0.0004, r_multiple=2.0)
    xau = _loss_trade()
    xau.update(symbol="XAUUSD", pnl=-50.0, r_multiple=-1.0)

    result = outcome_distribution([eur, xau])

    assert result["mean_win_r"] == 2.0
    assert result["mean_loss_r"] == 1.0
    assert result["payoff_ratio_r"] == 2.0
    assert "mean_win" not in result and "payoff_ratio" not in result


def test_audit_writes_outputs_for_a_zero_winner_run(tmp_path):
    rows = _rows(
        ("2026-01-01T00:00:00Z", 101.0, 99.0, 100.0),
        ("2026-01-01T00:05:00Z", 103.0, 97.0, 98.0),
        ("2026-01-01T00:10:00Z", 103.0, 99.0, 100.0),
    )
    _write_run(tmp_path, rows, [_loss_trade()])
    out = tmp_path / "audit.json"
    detail = tmp_path / "detail.jsonl"

    report = edge_v4_setup_failure_audit.run_setup_failure_audit(
        tmp_path, out=out, detail_out=detail
    )

    assert report["runs"][0]["outcome_distribution"]["payoff_ratio_r"] is None
    assert "no_winners" in report["outcome_distribution"]["payoff_ratio_flags"]
    assert out.exists()
    assert detail.exists()


def test_funnel_explicitly_accounts_for_candidates_suppressed_while_open(monkeypatch):
    candles = edge_v4_setup_failure_audit.load_audit_candles(
        _rows(
            ("2026-01-01T00:00:00Z", 101.0, 99.0, 100.0),
            ("2026-01-01T00:05:00Z", 101.0, 99.0, 100.0),
            ("2026-01-01T00:10:00Z", 101.0, 99.0, 100.0),
        )
    )
    monkeypatch.setattr(
        edge_v4_setup_failure_audit,
        "_detector_funnel_events",
        lambda *_args, **_kwargs: (Counter({"generated_setups": 2}), ["2026-01-01T00:05:00+00:00", "2026-01-01T00:10:00+00:00"]),
    )
    trade = _trade(opened="2026-01-01T00:00:00+00:00", closed="2026-01-01T00:10:00+00:00")
    setup = {"timestamp": "2026-01-01T00:10:00+00:00", "accepted": True}

    funnel = edge_v4_setup_failure_audit._run_funnel(candles, [setup], [], [], [trade])

    assert funnel["detector_candidates_total"] == 2
    assert funnel["candidates_suppressed_while_position_open"] == 1
    assert funnel["runner_evaluable_setups"] == funnel["journal_setups_blocked"] + funnel["journal_setups_accepted"]
    assert funnel["journal_setups_accepted"] == funnel["post_cost_geometry_blocks"] + funnel["trades_opened"]


def test_canonical_trade_id_makes_legacy_timeframes_distinct():
    m5 = _trade(opened="2026-01-01T00:00:00Z")
    m15 = _trade(opened="2026-01-01T00:00:00Z")
    m15["timeframe"] = "M15"

    assert edge_v4_setup_failure_audit.canonical_trade_id(m5) != edge_v4_setup_failure_audit.canonical_trade_id(m15)


def test_module_has_no_execution_or_excluded_feature_path():
    from trading_bot.research import edge_v4_setup_failure_metrics

    source = (
        inspect.getsource(edge_v4_setup_failure_audit)
        + inspect.getsource(edge_v4_setup_failure_metrics)
    )

    assert "order_send" not in source
    assert "lower_quartile_closes" not in source
    assert "candidate_rule" not in source
