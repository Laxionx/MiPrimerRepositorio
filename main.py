import os
from dotenv import load_dotenv
from trading_bot.config.settings import settings
from trading_bot.utils.logger import logger
from trading_bot.data.mt5_data import MT5DataProvider
from trading_bot.data.mock_data import MockDataProvider
from trading_bot.strategy.liquidity_sweep import LiquiditySweepStrategy
from trading_bot.risk.risk_manager import SimpleRiskManager
from trading_bot.execution.mt5_executor import MT5Executor
from trading_bot.execution.dry_run_executor import DryRunExecutor
from trading_bot.core.engine import TradingEngine

def main():
    load_dotenv()

    logger.info("Initializing Modular Trading Bot...")
    logger.info(f"Mode: {'LIVE' if settings.LIVE_TRADING else 'DRY RUN'}")

    # Choose Data Provider
    # On Linux/No MT5, we fall back to Mock if not careful.
    # But here we let the user configuration decide, and the provider handle the failure.
    if settings.LIVE_TRADING:
        data_provider = MT5DataProvider(
            login=settings.MT5_LOGIN,
            password=settings.MT5_PASSWORD,
            server=settings.MT5_SERVER
        )
        executor = MT5Executor(symbol=settings.SYMBOL)
    else:
        data_provider = MockDataProvider()
        executor = DryRunExecutor()

    strategy = LiquiditySweepStrategy(
        lookback=settings.SWING_LOOKBACK,
        reward_risk_ratio=settings.REWARD_RISK_RATIO
    )

    risk_manager = SimpleRiskManager(
        max_risk_per_trade=settings.MAX_RISK_PER_TRADE,
        max_daily_loss=settings.MAX_DAILY_LOSS,
        max_trades_per_day=settings.MAX_TRADES_PER_DAY,
        spread_filter=settings.SPREAD_FILTER
    )

    engine = TradingEngine(
        data_provider=data_provider,
        strategy=strategy,
        executor=executor,
        risk_manager=risk_manager
    )

    try:
        # Run once for demonstration/dry-run, or start loop
        if not settings.LIVE_TRADING:
            logger.info("Running a single iteration in dry-run mode.")
            engine.run_once()
        else:
            engine.start(interval=60)
    except KeyboardInterrupt:
        engine.stop()

if __name__ == "__main__":
    main()
