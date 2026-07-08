import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_bot.backtest.mt5_pipeline import run_mt5_backtest  # noqa: E402
from trading_bot.data.mt5_history import MT5HistoryError  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Export MT5 history and backtest it")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", choices=["M5", "M15", "H1", "H4"], default="M5")
    parser.add_argument("--bars", type=int, default=50_000)
    parser.add_argument("--default-spread", type=float, default=0.0)
    parser.add_argument("--slippage-points", type=float, default=0.0)
    args = parser.parse_args()

    stem = f"{args.symbol.lower()}_{args.timeframe.lower()}"
    try:
        metrics = run_mt5_backtest(
            symbol=args.symbol,
            timeframe=args.timeframe,
            bars=args.bars,
            output=Path("data") / f"{stem}.csv",
            logs_dir=Path("logs") / stem,
            default_spread=args.default_spread,
            slippage_points=args.slippage_points,
        )
    except MT5HistoryError as exc:
        parser.error(str(exc))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
