import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_bot.analysis.trade_review import (  # noqa: E402
    analyze_trade_review,
    export_trade_groups,
    generate_trade_review_report,
)
from trading_bot.analysis.trade_segmentation import load_trade_journal  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Review best and worst AQTF trades")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("logs/xauusd_m5/trades.jsonl"),
    )
    parser.add_argument("--rank-by", choices=["pnl", "r_multiple"], default="pnl")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/best_worst_trade_review.md"),
    )
    args = parser.parse_args()
    analysis = analyze_trade_review(
        load_trade_journal(args.input),
        limit=args.limit,
        rank_by=args.rank_by,
    )
    report = generate_trade_review_report(analysis, args.report)
    export_trade_groups(
        analysis,
        args.report.parent / "top_100_winners.csv",
        args.report.parent / "worst_100_losers.csv",
    )
    print(report)


if __name__ == "__main__":
    main()
