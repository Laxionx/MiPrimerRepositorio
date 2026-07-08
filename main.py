import os
from dotenv import load_dotenv
from trading_bot.config.settings import settings
from trading_bot.utils.logger import logger
from trading_bot.data.mt5_data import MT5DataProvider
from trading_bot.data.mock_data import MockDataProvider
from trading_bot.signals.liquidity_sweep import LiquiditySweepDetector
from trading_bot.risk.risk_guard import SimpleRiskGuard
from trading_bot.execution.mt5_executor import MT5Executor
from trading_bot.execution.dry_run_executor import DryRunExecutor
from trading_bot.output.json_publisher import JSONRecommendationPublisher, ConsolePublisher
from trading_bot.core.engine import AnalysisEngine

def main():
    load_dotenv()

    logger.info("Initializing Modular Trading Lab...")
    logger.info(f"Analysis Only: {settings.ANALYSIS_ONLY}")
    logger.info(f"Live Trading Enabled: {settings.LIVE_TRADING}")

    # 1. Market Data
    # In analysis-only mode without credentials, we use Mock data.
    if settings.LIVE_TRADING or (settings.MT5_LOGIN and not settings.ANALYSIS_ONLY):
        market_data = MT5DataProvider(
            login=settings.MT5_LOGIN,
            password=settings.MT5_PASSWORD,
            server=settings.MT5_SERVER
        )
    else:
        market_data = MockDataProvider()

    # 2. Signal Detector
    signal_detector = LiquiditySweepDetector(
        lookback=settings.SWING_LOOKBACK,
        reward_risk_ratio=settings.REWARD_RISK_RATIO
    )

    # 3. Risk Guard
    risk_guard = SimpleRiskGuard(
        max_risk_per_trade=settings.MAX_RISK_PER_TRADE,
        max_daily_loss=settings.MAX_DAILY_LOSS,
        max_trades_per_day=settings.MAX_TRADES_PER_DAY,
        spread_limit=settings.SPREAD_LIMIT,
        volatility_limit=settings.VOLATILITY_LIMIT
    )

    # 4. Publisher
    publisher = JSONRecommendationPublisher()
    # publisher = ConsolePublisher() # Use this for debugging

    # 5. Executor (Optional)
    executor = None
    if not settings.ANALYSIS_ONLY:
        if settings.LIVE_TRADING:
            executor = MT5Executor(symbol=settings.SYMBOL)
        else:
            executor = DryRunExecutor()

    # 6. Engine
    engine = AnalysisEngine(
        market_data=market_data,
        signal_detector=signal_detector,
        risk_guard=risk_guard,
        publisher=publisher,
        executor=executor
    )

    try:
        if settings.ANALYSIS_ONLY:
            logger.info("Running single analysis pass...")
            engine.run_once()
        else:
            engine.start(interval=60)
    except KeyboardInterrupt:
        engine.stop()

if __name__ == "__main__":
    main()
