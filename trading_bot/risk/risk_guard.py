from typing import Dict, Any
from trading_bot.core.interfaces import RiskGuard
from trading_bot.utils.logger import logger
from trading_bot.config.settings import settings as bot_settings

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
        if (
            setup_data.get("blocked_by_context")
            or setup_data.get("blocked_by_entry_score")
            or setup_data.get("no_chase_blocked")
        ):
            return {"allowed": False, "reason": "AQTF context or entry filter blocked setup"}

        # Check for missing required data
        # context now contains keys: spread, volatility, connected
        is_spread_missing = context.get('spread') is None
        is_volatility_missing = context.get('volatility') is None

        if bot_settings.BLOCK_IF_DATA_MISSING:
            if is_spread_missing:
                return {"allowed": False, "reason": "Required spread data missing"}
            if is_volatility_missing:
                # We know MT5 currently returns None for volatility
                return {"allowed": False, "reason": "Required volatility data missing"}

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
            "trades_today": self.trades_today,
            "data_quality": "degraded" if (is_spread_missing or is_volatility_missing) else "optimal"
        }

    def update_daily_stats(self, pnl_pct: float):
        self.trades_today += 1
        self.daily_loss_pct -= pnl_pct
