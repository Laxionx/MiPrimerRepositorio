import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from trading_bot.core.interfaces import MarketDataProvider

class MockDataProvider(MarketDataProvider):
    def __init__(self, scenario: Optional[str] = "no_setup"):
        self._last_error = ""
        self.scenario = scenario

    def get_ohlcv(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        dates = [datetime.now() - timedelta(minutes=5*i) for i in range(count)]
        dates.reverse()

        if self.scenario == "low_sweep":
            highs = [11.0] * count
            lows = [10.0] * count
            lows[count//2] = 9.0
            closes = [10.5] * count
            lows[-1] = 8.5
            closes[-1] = 9.5
            volumes = [100] * count

        elif self.scenario == "high_sweep":
            highs = [10.0] * count
            highs[count//2] = 11.0
            lows = [9.0] * count
            closes = [9.5] * count
            highs[-1] = 11.5
            closes[-1] = 10.5
            volumes = [100] * count

        else: # no_setup
            highs = [11.0] * count
            lows = [9.0] * count
            closes = [10.0] * count
            volumes = [100] * count

        df = pd.DataFrame({
            'time': dates,
            'open': [c - 0.1 for c in closes],
            'high': highs,
            'low': lows,
            'close': closes,
            'tick_volume': volumes,
            'real_volume': volumes
        })
        return df

    def get_market_context(self, symbol: str) -> Dict[str, Any]:
        return {
            "spread": 5.0,
            "volatility": 0.001,
            "connected": True
        }

    def is_connected(self) -> bool:
        return True

    def get_last_error(self) -> str:
        return self._last_error
