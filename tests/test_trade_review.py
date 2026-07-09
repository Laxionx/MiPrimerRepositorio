import csv

from trading_bot.analysis.trade_review import (
    analyze_trade_review,
    export_trade_groups,
    generate_trade_review_report,
    select_trade_groups,
)


def trade(trade_id: str, pnl: float, r_multiple: float) -> dict:
    return {
        "trade_id": trade_id,
        "pnl": pnl,
        "r_multiple": r_multiple,
        "context_score": 75,
        "entry_score": 82,
        "market_regime": "trend",
        "context_bias": "long",
        "direction": "LONG",
        "distance_to_h1_high": 0.2,
        "distance_to_h1_low": 0.8,
        "distance_to_h1_mid": 0.3,
    }


def test_winners_and_losers_are_selected_in_correct_order():
    trades = [
        trade("w1", 1, 0.1),
        trade("w5", 5, 0.5),
        trade("w3", 3, 0.3),
        trade("l1", -1, -0.1),
        trade("l6", -6, -0.6),
        trade("l2", -2, -0.2),
    ]

    winners, losers = select_trade_groups(trades, limit=2)

    assert [row["trade_id"] for row in winners] == ["w5", "w3"]
    assert [row["trade_id"] for row in losers] == ["l6", "l2"]


def test_empty_journal_is_handled_and_outputs_are_generated(tmp_path):
    analysis = analyze_trade_review([])
    report = tmp_path / "review.md"
    winners_csv = tmp_path / "winners.csv"
    losers_csv = tmp_path / "losers.csv"

    generate_trade_review_report(analysis, report)
    export_trade_groups(analysis, winners_csv, losers_csv)

    assert analysis["winners"]["trades"] == 0
    assert analysis["losers"]["trades"] == 0
    assert report.exists()
    assert winners_csv.exists()
    assert losers_csv.exists()


def test_report_and_csv_exports_match_selected_group_totals(tmp_path):
    trades = [trade(f"w{i}", i, i / 10) for i in range(1, 6)]
    trades += [trade(f"l{i}", -i, -i / 10) for i in range(1, 5)]
    analysis = analyze_trade_review(trades, limit=3)
    report = tmp_path / "review.md"
    winners_csv = tmp_path / "winners.csv"
    losers_csv = tmp_path / "losers.csv"

    generate_trade_review_report(analysis, report)
    export_trade_groups(analysis, winners_csv, losers_csv)

    with winners_csv.open(newline="") as stream:
        exported_winners = list(csv.DictReader(stream))
    with losers_csv.open(newline="") as stream:
        exported_losers = list(csv.DictReader(stream))

    assert analysis["winners"]["trades"] == 3
    assert analysis["losers"]["trades"] == 3
    assert len(exported_winners) == 3
    assert len(exported_losers) == 3
    contents = report.read_text()
    assert "## Top Winners Summary" in contents
    assert "## Worst Losers Summary" in contents
    assert "## Key Differences" in contents
    assert "## Possible Edge V2 Clues" in contents
    assert "average atr" in contents
    assert "average bars_held" in contents
    assert "most common exit_reason" in contents
