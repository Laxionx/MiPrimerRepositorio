from dotenv import load_dotenv
from trading_bot.config.settings import settings
from trading_bot.utils.logger import logger
from trading_bot.data.factory import get_data_provider
from trading_bot.signals.liquidity_sweep import LiquiditySweepDetector
from trading_bot.risk.risk_guard import SimpleRiskGuard
from trading_bot.output.json_publisher import JSONRecommendationPublisher
from trading_bot.core.engine import AnalysisEngine
from trading_bot.journal.paper_forward import PaperForwardJournal

def main():
    load_dotenv()

    logger.info("Initializing Hardened Modular Trading Lab (Analysis-Only)...")
    logger.info(f"Run ID: {settings.RUN_ID}")
    logger.info(f"Data Provider: {settings.DATA_PROVIDER}")

    # 1. Market Data (via Factory)
    try:
        market_data = get_data_provider()
    except ValueError as e:
        logger.error(f"Initialization failed: {e}")
        return

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
    journal = PaperForwardJournal("logs")

    # 5. Engine (Executor strictly removed)
    engine = AnalysisEngine(
        market_data=market_data,
        signal_detector=signal_detector,
        risk_guard=risk_guard,
        publisher=publisher,
        journal=journal,
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
