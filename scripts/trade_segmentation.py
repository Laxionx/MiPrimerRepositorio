import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_bot.analysis.trade_segmentation import (  # noqa: E402
    analyze_trade_segments,
    generate_segmentation_report,
    load_trade_journal,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Segment completed AQTF trades")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("logs/xauusd_m5/trades.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/trade_segmentation.md"),
    )
    args = parser.parse_args()
    analysis = analyze_trade_segments(load_trade_journal(args.input))
    output = generate_segmentation_report(analysis, args.output)
    print(output)


if __name__ == "__main__":
    main()
