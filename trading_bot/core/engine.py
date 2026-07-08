import time
from trading_bot.core.interfaces import DataProvider, Strategy, Executor, RiskManager
from trading_bot.utils.logger import logger
from trading_bot.config.settings import settings

class TradingEngine:
    def __init__(self,
                 data_provider: DataProvider,
                 strategy: Strategy,
                 executor: Executor,
                 risk_manager: RiskManager):
        self.data_provider = data_provider
        self.strategy = strategy
        self.executor = executor
        self.risk_manager = risk_manager
        self.running = False

    def run_once(self):
        try:
            logger.debug(f"Fetching data for {settings.SYMBOL}...")
            data = self.data_provider.get_ohlc(settings.SYMBOL, settings.TIMEFRAME, settings.SWING_LOOKBACK + 5)

            if data.empty:
                logger.warning("No data received from provider.")
                return

            signal = self.strategy.generate_signal(data)

            if signal['action'] != "HOLD":
                logger.info(f"Signal generated: {signal}")

                # In a more advanced version, these would come from the data_provider
                context = {
                    'connected': self.data_provider.is_connected(),
                    'spread': 5,
                }

                if self.risk_manager.validate_trade(signal, context):
                    success = self.executor.execute(signal)
                    if success:
                        # Update stats (assuming 0 for PnL for now as it's just opened)
                        if hasattr(self.risk_manager, 'update_daily_stats'):
                            self.risk_manager.update_daily_stats(0.0)
                else:
                    logger.info("Trade rejected by Risk Manager.")
            else:
                logger.debug("Strategy: HOLD")

        except Exception as e:
            logger.error(f"Error in engine loop: {e}", exc_info=True)

    def start(self, interval: int = 10):
        logger.info("Starting Trading Engine...")
        self.running = True
        while self.running:
            self.run_once()
            time.sleep(interval)

    def stop(self):
        logger.info("Stopping Trading Engine...")
        self.running = False
