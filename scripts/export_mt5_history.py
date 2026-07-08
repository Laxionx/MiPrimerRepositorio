import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_bot.data.mt5_history import (  # noqa: E402
    MT5HistoryError,
    export_from_local_terminal,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export local MT5 candle history")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", choices=["M5", "M15", "H1", "H4"], default="M5")
    parser.add_argument("--bars", type=int, default=50_000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = export_from_local_terminal(
            symbol=args.symbol,
            timeframe=args.timeframe,
            bars=args.bars,
            output=args.output,
        )
    except MT5HistoryError as exc:
        parser.error(str(exc))
    print(output)


if __name__ == "__main__":
    main()
