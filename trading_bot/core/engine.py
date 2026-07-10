import time
from datetime import datetime
from typing import Dict, Any, Optional
from trading_bot.core.interfaces import MarketDataProvider, SignalDetector, RiskGuard, RecommendationPublisher
from trading_bot.utils.logger import logger
from trading_bot.config.settings import settings

class AnalysisEngine:
    def __init__(self,
                 market_data: MarketDataProvider,
                 signal_detector: SignalDetector,
                 risk_guard: RiskGuard,
                 publisher: RecommendationPublisher):
        self.market_data = market_data
        self.signal_detector = signal_detector
        self.risk_guard = risk_guard
        self.publisher = publisher
        self.running = False

    def run_once(self):
        try:
            logger.debug(f"Fetching data for {settings.SYMBOL}...")
            data = self.market_data.get_ohlcv(settings.SYMBOL, settings.TIMEFRAME, settings.SWING_LOOKBACK + 5)

            if data.empty:
                logger.warning("No data received from market data provider.")
                return

            # 1. Detect Signals
            signal_report = self.signal_detector.detect_signals(data)

            # 2. Risk Guarding (Using dynamic market context)
            market_context = self.market_data.get_market_context(settings.SYMBOL)
            risk_report = self.risk_guard.validate_setup(signal_report, market_context)

            # 3. Create Recommendation with Absolute Safety Fields
            recommendation = {
                "schema_version": settings.SCHEMA_VERSION,
                "run_id": settings.RUN_ID,
                "mode": "analysis_only",
                "data_provider": settings.DATA_PROVIDER,
                "mock_scenario": settings.MOCK_SCENARIO if settings.DATA_PROVIDER == "mock" else None,
                "generated_at": datetime.now().isoformat(),
                "symbol": settings.SYMBOL,
                "timeframe": settings.TIMEFRAME,
                "market_context": signal_report.get("market_context"),
                "market_context_live": market_context,
                "liquidity": signal_report.get("liquidity"),
                "vwap": signal_report.get("vwap"),
                "volume_profile": signal_report.get("volume_profile"),
                "order_flow": signal_report.get("order_flow"),
                "setup": signal_report.get("setup"),
                "risk": risk_report,
                "command": None,
                "submit_allowed": False,
                "broker_api_called": False,
                "live_execution_enabled": False
            }

            # 4. Publish
            self.publisher.publish(recommendation)

        except Exception as e:
            logger.error(f"Error in analysis engine loop: {e}", exc_info=True)

    def start(self, interval: int = 60):
        logger.info(f"Starting Algorithmic Trading Lab Engine (Mode: analysis_only, Provider: {settings.DATA_PROVIDER})...")
        self.running = True
        while self.running:
            self.run_once()
            time.sleep(interval)

    def stop(self):
        self.running = False
