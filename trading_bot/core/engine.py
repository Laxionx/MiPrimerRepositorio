import time
from datetime import datetime
from typing import Dict, Any, Optional
from trading_bot.core.interfaces import MarketDataProvider, SignalDetector, RiskGuard, RecommendationPublisher
from trading_bot.utils.logger import logger
from trading_bot.config.settings import settings
from trading_bot.signals.aqtf import ContextEngine, EntryScorer

class AnalysisEngine:
    def __init__(self,
                 market_data: MarketDataProvider,
                 signal_detector: SignalDetector,
                 risk_guard: RiskGuard,
                 publisher: RecommendationPublisher,
                 context_engine: ContextEngine | None = None,
                 entry_scorer: EntryScorer | None = None):
        self.market_data = market_data
        self.signal_detector = signal_detector
        self.risk_guard = risk_guard
        self.publisher = publisher
        self.context_engine = context_engine or ContextEngine()
        self.entry_scorer = entry_scorer or EntryScorer(
            context_score_min=settings.CONTEXT_SCORE_MIN,
            entry_score_min=settings.ENTRY_SCORE_MIN,
            no_chase_max_atr=settings.NO_CHASE_MAX_ATR,
            spread_limit=settings.SPREAD_LIMIT,
            volatility_limit=settings.VOLATILITY_LIMIT,
        )
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

            # 2. AQTF context and entry quality
            h1_data = self.market_data.get_ohlcv(
                settings.SYMBOL,
                "TIMEFRAME_H1",
                settings.CONTEXT_LOOKBACK,
            )
            aqtf_context = self.context_engine.evaluate(h1_data)
            market_context = self.market_data.get_market_context(settings.SYMBOL)
            entry_quality = self.entry_scorer.evaluate(
                signal_report,
                data,
                aqtf_context,
                market_context,
            )
            signal_report.update(aqtf_context)
            signal_report.update(entry_quality)

            # 3. Risk Guarding (Using dynamic market context)
            risk_report = self.risk_guard.validate_setup(signal_report, market_context)

            # 4. Create Recommendation with Absolute Safety Fields
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
                "market_regime": signal_report["market_regime"],
                "context_bias": signal_report["context_bias"],
                "context_score": signal_report["context_score"],
                "context_reason": signal_report["context_reason"],
                "entry_score": signal_report["entry_score"],
                "entry_reason": signal_report["entry_reason"],
                "blocked_by_context": signal_report["blocked_by_context"],
                "blocked_by_entry_score": signal_report["blocked_by_entry_score"],
                "no_chase_blocked": signal_report["no_chase_blocked"],
                "no_chase_reason": signal_report["no_chase_reason"],
                "extension_atr": signal_report["extension_atr"],
                "risk": risk_report,
                "command": None,
                "submit_allowed": False,
                "broker_api_called": False,
                "live_execution_enabled": False
            }

            # 5. Publish
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
