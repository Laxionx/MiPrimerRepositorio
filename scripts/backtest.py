import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_bot.backtest.runner import BacktestRunner, load_historical_csv  # noqa: E402
from trading_bot.journal.paper_forward import PaperForwardJournal  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run sequential AQTF backtest")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="M5")
    parser.add_argument("--logs-dir", type=Path, default=Path("logs/backtest"))
    parser.add_argument("--default-spread", type=float, default=0.0)
    parser.add_argument("--slippage-points", type=float, default=0.0)
    args = parser.parse_args()

    runner = BacktestRunner(
        symbol=args.symbol,
        timeframe=args.timeframe,
        journal=PaperForwardJournal(args.logs_dir),
        default_spread=args.default_spread,
        slippage_points=args.slippage_points,
    )
    metrics = runner.run(load_historical_csv(args.input))
    selected = {
        key: metrics[key]
        for key in (
            "total_trades",
            "win_rate",
            "expectancy",
            "profit_factor",
            "max_drawdown",
            "average_r",
        )
    }
    print(json.dumps(selected, indent=2))


if __name__ == "__main__":
    main()
