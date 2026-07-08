import pandas as pd
import pandas_ta as ta
from typing import Dict, Any
from trading_bot.core.interfaces import Strategy
from trading_bot.utils.logger import logger

class LiquiditySweepStrategy(Strategy):
    def __init__(self, lookback: int = 20, reward_risk_ratio: float = 2.0):
        self.lookback = lookback
        self.reward_risk_ratio = reward_risk_ratio

    def generate_signal(self, data: pd.DataFrame) -> Dict[str, Any]:
        if len(data) < self.lookback + 1:
            return {"action": "HOLD", "reason": "Insufficient data"}

        df = data.copy()

        # Calculate VWAP
        # Note: pandas_ta vwap needs a datetime index
        df.set_index('time', inplace=True)
        df['vwap'] = ta.vwap(df.high, df.low, df.close, df.tick_volume)

        # Current bar (last complete bar)
        current_bar = df.iloc[-1]

        # Previous lookback bars
        lookback_df = df.iloc[-(self.lookback+1):-1]
        recent_high = lookback_df['high'].max()
        recent_low = lookback_df['low'].min()

        signal = {"action": "HOLD", "price": current_bar['close']}

        # Liquidity Sweep of High (potential SELL)
        # Price went above recent high but closed below it
        if current_bar['high'] > recent_high and current_bar['close'] < recent_high:
            # Additional filter: Price above VWAP for a short
            if current_bar['close'] > current_bar['vwap']:
                sl = current_bar['high'] + (current_bar['high'] - current_bar['low']) * 0.1 # slight buffer
                risk = sl - current_bar['close']
                tp = current_bar['close'] - (risk * self.reward_risk_ratio)

                signal.update({
                    "action": "SELL",
                    "stop_loss": sl,
                    "take_profit": tp,
                    "reason": f"Sweep of high {recent_high:.5f}"
                })

        # Liquidity Sweep of Low (potential BUY)
        # Price went below recent low but closed above it
        elif current_bar['low'] < recent_low and current_bar['close'] > recent_low:
            # Additional filter: Price below VWAP for a long
            if current_bar['close'] < current_bar['vwap']:
                sl = current_bar['low'] - (current_bar['high'] - current_bar['low']) * 0.1 # slight buffer
                risk = current_bar['close'] - sl
                tp = current_bar['close'] + (risk * self.reward_risk_ratio)

                signal.update({
                    "action": "BUY",
                    "stop_loss": sl,
                    "take_profit": tp,
                    "reason": f"Sweep of low {recent_low:.5f}"
                })

        return signal
