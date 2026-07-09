import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_bot.analysis.context_diagnostics import (  # noqa: E402
    analyze_context_diagnostics,
    evaluate_candle_contexts,
    generate_context_diagnostics_report,
)
from trading_bot.analysis.trade_segmentation import load_trade_journal  # noqa: E402
from trading_bot.backtest.runner import load_historical_csv  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose AQTF context distributions")
    parser.add_argument(
        "--candles",
        type=Path,
        default=Path("data/xauusd_m5.csv"),
    )
    parser.add_argument(
        "--trades",
        type=Path,
        default=Path("logs/xauusd_m5/trades.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/context_diagnostics.md"),
    )
    args = parser.parse_args()
    candles = load_historical_csv(args.candles)
    contexts = evaluate_candle_contexts(candles)
    trades = load_trade_journal(args.trades)
    analysis = analyze_context_diagnostics(contexts, trades)
    output = generate_context_diagnostics_report(analysis, args.output)
    print(output)


if __name__ == "__main__":
    main()
