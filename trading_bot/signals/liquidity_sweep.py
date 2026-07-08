import pandas as pd
import pandas_ta as ta
from typing import Dict, Any
from trading_bot.core.interfaces import SignalDetector
from trading_bot.utils.logger import logger

class LiquiditySweepDetector(SignalDetector):
    def __init__(self, lookback: int = 20, reward_risk_ratio: float = 2.0):
        self.lookback = lookback
        self.reward_risk_ratio = reward_risk_ratio

    def detect_signals(self, data: pd.DataFrame) -> Dict[str, Any]:
        if len(data) < self.lookback + 1:
            return {"setup": None, "market_context": {"error": "Insufficient data"}}

        df = data.copy()

        # Calculate VWAP
        if 'time' in df.columns:
            df.set_index('time', inplace=True)

        df['vwap'] = ta.vwap(df.high, df.low, df.close, df.tick_volume)

        current_bar = df.iloc[-1]
        lookback_df = df.iloc[-(self.lookback+1):-1]

        recent_high = lookback_df['high'].max()
        recent_low = lookback_df['low'].min()

        market_context = {
            "current_price": float(current_bar['close']),
            "vwap": float(current_bar['vwap']) if not pd.isna(current_bar['vwap']) else None,
            "recent_high": float(recent_high),
            "recent_low": float(recent_low)
        }

        setup = None

        # Liquidity Sweep of High (potential SELL)
        if current_bar['high'] > recent_high and current_bar['close'] < recent_high:
            if current_bar['close'] > current_bar['vwap']:
                sl = float(current_bar['high'] + (current_bar['high'] - current_bar['low']) * 0.1)
                risk = sl - float(current_bar['close'])
                tp = float(current_bar['close'] - (risk * self.reward_risk_ratio))

                setup = {
                    "type": "SHORT",
                    "name": "High Liquidity Sweep",
                    "entry_zone": [float(recent_high), float(current_bar['high'])],
                    "entry_price": float(current_bar['close']),
                    "stop_loss": sl,
                    "take_profit": tp,
                    "invalidation_level": sl,
                    "technical_reason": f"Price swept recent high of {recent_high:.5f} and closed back inside range. Above VWAP filter active."
                }

        # Liquidity Sweep of Low (potential BUY)
        elif current_bar['low'] < recent_low and current_bar['close'] > recent_low:
            if current_bar['close'] < current_bar['vwap']:
                sl = float(current_bar['low'] - (current_bar['high'] - current_bar['low']) * 0.1)
                risk = float(current_bar['close']) - sl
                tp = float(current_bar['close'] + (risk * self.reward_risk_ratio))

                setup = {
                    "type": "LONG",
                    "name": "Low Liquidity Sweep",
                    "entry_zone": [float(current_bar['low']), float(recent_low)],
                    "entry_price": float(current_bar['close']),
                    "stop_loss": sl,
                    "take_profit": tp,
                    "invalidation_level": sl,
                    "technical_reason": f"Price swept recent low of {recent_low:.5f} and closed back inside range. Below VWAP filter active."
                }

        return {
            "market_context": market_context,
            "liquidity": {
                "recent_high": float(recent_high),
                "recent_low": float(recent_low),
                "high_sweep": bool(current_bar['high'] > recent_high),
                "low_sweep": bool(current_bar['low'] < recent_low)
            },
            "vwap": {"value": market_context['vwap']},
            "volume_profile": {"status": "not_available_in_simulated_ohlcv"},
            "order_flow": {"status": "not_available_in_simulated_ohlcv"},
            "setup": setup
        }
