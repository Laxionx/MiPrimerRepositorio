import pandas as pd
from typing import Dict, Any
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from trading_bot.core.interfaces import MarketDataProvider
from trading_bot.utils.logger import logger

class MT5DataProvider(MarketDataProvider):
    def __init__(self, login, password, server):
        self.login = login
        self.password = password
        self.server = server
        self.initialized = False

    def connect(self):
        if mt5 is None:
            logger.error("MetaTrader5 package not installed or not supported on this OS.")
            return False

        if not mt5.initialize(login=self.login, password=self.password, server=self.server):
            logger.error(f"Failed to initialize MT5: {mt5.last_error()}")
            return False

        self.initialized = True
        return True

    def get_ohlcv(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        if not self.initialized:
            if not self.connect():
                return pd.DataFrame()

        tf = getattr(mt5, timeframe, mt5.TIMEFRAME_M5)

        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            logger.error(f"Failed to get rates for {symbol}: {mt5.last_error()}")
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    def get_market_context(self, symbol: str) -> Dict[str, Any]:
        if not self.initialized:
            if not self.connect():
                return {"spread": None, "volatility": None, "error": "Not connected"}

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return {"spread": None, "volatility": None, "error": "Symbol info unavailable"}

        return {
            "spread": float(symbol_info.spread),
            "volatility": None,
            "connected": self.is_connected()
        }

    def is_connected(self) -> bool:
        if mt5 is None: return False
        terminal_info = mt5.terminal_info()
        return terminal_info.connected if terminal_info else False

    def get_last_error(self) -> str:
        if mt5 is None: return "MT5 not installed"
        return str(mt5.last_error())
