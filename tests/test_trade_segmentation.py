import json

from trading_bot.analysis.trade_segmentation import (
    analyze_trade_segments,
    generate_segmentation_report,
    load_trade_journal,
)


def trade(
    trade_id: str,
    *,
    regime: str,
    direction: str,
    context_score: int,
    entry_score: int,
    pnl: float,
    r_multiple: float,
) -> dict:
    return {
        "trade_id": trade_id,
        "market_regime": regime,
        "direction": direction,
        "context_score": context_score,
        "entry_score": entry_score,
        "pnl": pnl,
        "r_multiple": r_multiple,
    }


def write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(record) for record in records))


def test_empty_journal_is_handled_and_report_is_generated(tmp_path):
    output = tmp_path / "trade_segmentation.md"

    analysis = analyze_trade_segments(load_trade_journal(tmp_path / "missing.jsonl"))
    generate_segmentation_report(analysis, output)

    assert analysis["overall"]["total_trades"] == 0
    assert output.exists()
    assert "No completed trades available." in output.read_text()


def test_report_is_generated_with_rankings_and_conclusions(tmp_path):
    records = [
        trade(
            "1",
            regime="trend",
            direction="LONG",
            context_score=75,
            entry_score=85,
            pnl=10,
            r_multiple=1,
        ),
        trade(
            "2",
            regime="range",
            direction="SHORT",
            context_score=65,
            entry_score=70,
            pnl=-5,
            r_multiple=-0.5,
        ),
    ]
    output = tmp_path / "trade_segmentation.md"

    analysis = analyze_trade_segments(records)
    generate_segmentation_report(analysis, output)
    report = output.read_text()

    assert "## Top 10 Best Performing Segments" in report
    assert "## Bottom 10 Worst Performing Segments" in report
    assert "## Conclusions" in report


def test_each_segmentation_dimension_matches_overall_trade_count():
    records = [
        trade(
            "1",
            regime="trend",
            direction="LONG",
            context_score=75,
            entry_score=85,
            pnl=10,
            r_multiple=1,
        ),
        trade(
            "2",
            regime="range",
            direction="SHORT",
            context_score=65,
            entry_score=70,
            pnl=-5,
            r_multiple=-0.5,
        ),
        trade(
            "3",
            regime="compression",
            direction="LONG",
            context_score=82,
            entry_score=78,
            pnl=4,
            r_multiple=0.4,
        ),
    ]

    analysis = analyze_trade_segments(records)

    for segments in analysis["dimensions"].values():
        assert sum(segment["trades"] for segment in segments) == 3
