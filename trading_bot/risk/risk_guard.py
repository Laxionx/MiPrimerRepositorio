from typing import Dict, Any
from trading_bot.core.interfaces import RiskGuard
from trading_bot.utils.logger import logger

class SimpleRiskGuard(RiskGuard):
    def __init__(self,
                 max_risk_per_trade: float = 0.01,
                 max_daily_loss: float = 0.05,
                 max_trades_per_day: int = 5,
                 spread_limit: int = 20,
                 volatility_limit: float = 0.005):
        self.max_risk_per_trade = max_risk_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_trades_per_day = max_trades_per_day
        self.spread_limit = spread_limit
        self.volatility_limit = volatility_limit

        self.trades_today = 0
        self.daily_loss_pct = 0.0

    def validate_setup(self, setup_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        setup = setup_data.get('setup')
        if not setup:
            return {"allowed": False, "reason": "No setup detected"}

        # Check for missing required data
        if context.get('connected') is None or context.get('spread') is None:
            return {"allowed": False, "reason": "Required market data missing (connection/spread)"}

        # 1. Connection Check
        if not context.get('connected', False):
            return {"allowed": False, "reason": "Market provider disconnected"}

        # 2. Spread Filter
        current_spread = context.get('spread')
        if current_spread is not None and current_spread > self.spread_limit:
            return {"allowed": False, "reason": f"Spread too high ({current_spread} > {self.spread_limit})"}

        # 3. Max Trades Per Day
        if self.trades_today >= self.max_trades_per_day:
            return {"allowed": False, "reason": "Max trades per day reached"}

        # 4. Max Daily Loss
        if self.daily_loss_pct >= self.max_daily_loss:
            return {"allowed": False, "reason": "Max daily loss reached"}

        # 5. Volatility Limit
        volatility = context.get('volatility')
        if volatility is not None and volatility > self.volatility_limit:
            return {"allowed": False, "reason": f"Volatility too high ({volatility:.5f} > {self.volatility_limit:.5f})"}

        return {
            "allowed": True,
            "max_risk_pct": self.max_risk_per_trade,
            "daily_loss_pct": self.daily_loss_pct,
            "trades_today": self.trades_today
        }

    def update_daily_stats(self, pnl_pct: float):
        self.trades_today += 1
        self.daily_loss_pct -= pnl_pct
