import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trading_bot.data.mt5_history import (  # noqa: E402
    MT5HistoryError,
    export_from_local_terminal,
    export_paginated_from_local_terminal,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export local MT5 candle history")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", choices=["M5", "M15", "H1", "H4"], default="M5")
    parser.add_argument("--bars", type=int, default=50_000)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--history-mode", choices=["range", "paginated"], default="range")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--page-size", type=int, default=5_000)
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument("--include-current-bar", action="store_true")
    args = parser.parse_args()
    try:
        if args.history_mode == "range":
            output = export_from_local_terminal(
                symbol=args.symbol,
                timeframe=args.timeframe,
                bars=args.bars,
                output=args.output,
            )
        else:
            if not args.start or not args.end or args.manifest_out is None:
                parser.error("paginated mode requires --start, --end, and --manifest-out")
            output = export_paginated_from_local_terminal(
                symbol=args.symbol,
                timeframe=args.timeframe,
                start=args.start,
                end=args.end,
                output=args.output,
                manifest_out=args.manifest_out,
                page_size=args.page_size,
                include_current_bar=args.include_current_bar,
            ).csv_path
    except MT5HistoryError as exc:
        parser.error(str(exc))
    print(output)


if __name__ == "__main__":
    main()
