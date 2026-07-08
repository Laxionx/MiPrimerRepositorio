import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from trading_bot.core.interfaces import DataProvider

class MockDataProvider(DataProvider):
    def __init__(self):
        self._last_error = ""

    def get_ohlc(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        # Generate some synthetic data that looks like it could have liquidity sweeps
        dates = [datetime.now() - timedelta(minutes=5*i) for i in range(count)]
        dates.reverse()

        # Simple random walk for mock data
        base_price = 1.1000
        closes = base_price + np.cumsum(np.random.normal(0, 0.0001, count))
        opens = closes - np.random.normal(0, 0.0001, count)
        highs = np.maximum(opens, closes) + np.random.uniform(0, 0.0002, count)
        lows = np.minimum(opens, closes) - np.random.uniform(0, 0.0002, count)
        volumes = np.random.randint(100, 1000, count)

        df = pd.DataFrame({
            'time': dates,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'tick_volume': volumes,
            'real_volume': volumes
        })
        return df

    def is_connected(self) -> bool:
        return True

    def get_last_error(self) -> str:
        return self._last_error
