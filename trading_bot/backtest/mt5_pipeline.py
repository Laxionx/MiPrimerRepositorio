from pathlib import Path

from trading_bot.backtest.runner import BacktestRunner, load_historical_csv
from trading_bot.data.mt5_history import export_from_local_terminal
from trading_bot.journal.paper_forward import PaperForwardJournal


def run_mt5_backtest(
    *,
    symbol: str,
    timeframe: str,
    bars: int,
    output: str | Path,
    logs_dir: str | Path,
    default_spread: float = 0.0,
    slippage_points: float = 0.0,
) -> dict[str, int | float | None]:
    csv_path = export_from_local_terminal(
        symbol=symbol,
        timeframe=timeframe,
        bars=bars,
        output=output,
    )
    runner = BacktestRunner(
        symbol=symbol,
        timeframe=timeframe,
        journal=PaperForwardJournal(logs_dir),
        default_spread=default_spread,
        slippage_points=slippage_points,
    )
    return runner.run(load_historical_csv(csv_path))
