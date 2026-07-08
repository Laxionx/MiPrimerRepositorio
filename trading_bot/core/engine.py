import time
from datetime import datetime
from typing import Dict, Any, Optional
from trading_bot.core.interfaces import MarketDataProvider, SignalDetector, RiskGuard, RecommendationPublisher, Executor
from trading_bot.utils.logger import logger
from trading_bot.config.settings import settings

class AnalysisEngine:
    def __init__(self,
                 market_data: MarketDataProvider,
                 signal_detector: SignalDetector,
                 risk_guard: RiskGuard,
                 publisher: RecommendationPublisher,
                 executor: Optional[Executor] = None):
        self.market_data = market_data
        self.signal_detector = signal_detector
        self.risk_guard = risk_guard
        self.publisher = publisher
        self.executor = executor
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

            # 2. Risk Guarding
            context = {
                'connected': self.market_data.is_connected(),
                'spread': 5, # Mock/Simulated spread
                'volatility': 0.001 # Mock volatility
            }
            risk_report = self.risk_guard.validate_setup(signal_report, context)

            # 3. Create Recommendation
            recommendation = {
                "symbol": settings.SYMBOL,
                "timeframe": settings.TIMEFRAME,
                "timestamp": datetime.now().isoformat(),
                "market_context": signal_report.get("market_context"),
                "liquidity": signal_report.get("liquidity"),
                "vwap": signal_report.get("vwap"),
                "volume_profile": signal_report.get("volume_profile"),
                "order_flow": signal_report.get("order_flow"),
                "setup": signal_report.get("setup"),
                "risk": risk_report,
                "command": None,
                "submit_allowed": False,
                "broker_api_called": False,
                "live_execution_enabled": settings.LIVE_TRADING
            }

            # 4. Execution Logic (if not in analysis-only mode)
            if not settings.ANALYSIS_ONLY and self.executor and risk_report.get("allowed"):
                logger.info("Executing recommendation...")
                success = self.executor.execute(recommendation)
                if success:
                    recommendation["broker_api_called"] = True
                    if settings.LIVE_TRADING:
                        recommendation["command"] = "order_sent"
                    else:
                        recommendation["command"] = "dry_run_simulated"

                    if hasattr(self.risk_guard, 'update_daily_stats'):
                        self.risk_guard.update_daily_stats(0.0)

            # 5. Publish
            self.publisher.publish(recommendation)

        except Exception as e:
            logger.error(f"Error in analysis engine loop: {e}", exc_info=True)

    def start(self, interval: int = 60):
        logger.info("Starting Algorithmic Trading Lab Engine...")
        self.running = True
        while self.running:
            self.run_once()
            time.sleep(interval)

    def stop(self):
        self.running = False
