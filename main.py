import os
from dotenv import load_dotenv
from trading_bot.config.settings import settings
from trading_bot.utils.logger import logger
from trading_bot.data.mt5_data import MT5DataProvider
from trading_bot.data.mock_data import MockDataProvider
from trading_bot.signals.liquidity_sweep import LiquiditySweepDetector
from trading_bot.risk.risk_guard import SimpleRiskGuard
from trading_bot.output.json_publisher import JSONRecommendationPublisher
from trading_bot.core.engine import AnalysisEngine

def main():
    load_dotenv()

    logger.info("Initializing Modular Trading Lab (Analysis-Only Hardening)...")
    logger.info(f"Run ID: {settings.RUN_ID}")
    logger.info(f"Data Provider: {settings.DATA_PROVIDER}")

    # Explicit Data Provider Selection
    if settings.DATA_PROVIDER == "mt5":
        if not settings.MT5_LOGIN or not settings.MT5_PASSWORD:
            logger.error("MT5_LOGIN and MT5_PASSWORD are required for DATA_PROVIDER=mt5")
            return

        market_data = MT5DataProvider(
            login=settings.MT5_LOGIN,
            password=settings.MT5_PASSWORD,
            server=settings.MT5_SERVER
        )
    else:
        # Default to mock
        logger.info(f"Mock Scenario: {settings.MOCK_SCENARIO}")
        market_data = MockDataProvider(scenario=settings.MOCK_SCENARIO)

    # Signal Detector
    signal_detector = LiquiditySweepDetector(
        lookback=settings.SWING_LOOKBACK,
        reward_risk_ratio=settings.REWARD_RISK_RATIO
    )

    # Risk Guard
    risk_guard = SimpleRiskGuard(
        max_risk_per_trade=settings.MAX_RISK_PER_TRADE,
        max_daily_loss=settings.MAX_DAILY_LOSS,
        max_trades_per_day=settings.MAX_TRADES_PER_DAY,
        spread_limit=settings.SPREAD_LIMIT,
        volatility_limit=settings.VOLATILITY_LIMIT
    )

    # Publisher
    publisher = JSONRecommendationPublisher()

    # Engine (Executor strictly removed)
    engine = AnalysisEngine(
        market_data=market_data,
        signal_detector=signal_detector,
        risk_guard=risk_guard,
        publisher=publisher
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
