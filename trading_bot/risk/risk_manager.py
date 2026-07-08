from typing import Dict, Any
from trading_bot.core.interfaces import RiskManager
from trading_bot.utils.logger import logger

class SimpleRiskManager(RiskManager):
    def __init__(self,
                 max_risk_per_trade: float = 0.01,
                 max_daily_loss: float = 0.05,
                 max_trades_per_day: int = 5,
                 spread_filter: int = 20):
        self.max_risk_per_trade = max_risk_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_trades_per_day = max_trades_per_day
        self.spread_filter = spread_filter

        self.trades_today = 0
        self.daily_loss_pct = 0.0

    def validate_trade(self, signal: Dict[str, Any], context: Dict[str, Any]) -> bool:
        if signal['action'] == "HOLD":
            return False

        # 1. MT5 Connection Check
        if not context.get('connected', False):
            logger.warning("Risk Management: MT5 is disconnected. Blocking trade.")
            return False

        # 2. Spread Filter
        current_spread = context.get('spread', 999)
        if current_spread > self.spread_filter:
            logger.warning(f"Risk Management: Spread too high ({current_spread} > {self.spread_filter}). Blocking trade.")
            return False

        # 3. Max Trades Per Day
        if self.trades_today >= self.max_trades_per_day:
            logger.warning(f"Risk Management: Max trades per day reached ({self.trades_today}). Blocking trade.")
            return False

        # 4. Max Daily Loss
        if self.daily_loss_pct >= self.max_daily_loss:
            logger.warning(f"Risk Management: Max daily loss reached ({self.daily_loss_pct:.2%}). Blocking trade.")
            return False

        # 5. Risk Per Trade (Calculated by strategy, but could be adjusted here)
        # For now we just allow it if other rules pass.

        logger.info(f"Risk Management: Trade validated for {signal['action']} @ {signal['price']}")
        return True

    def update_daily_stats(self, pnl_pct: float):
        self.trades_today += 1
        self.daily_loss_pct -= pnl_pct # Assuming negative pnl increases loss
