from typing import Dict, Any
from trading_bot.core.interfaces import Executor
from trading_bot.utils.logger import logger

class DryRunExecutor(Executor):
    def execute(self, recommendation: Dict[str, Any]) -> bool:
        setup = recommendation.get('setup')
        if not setup:
            return False

        action = setup['type']
        price = setup['entry_price']
        sl = setup.get('stop_loss')
        tp = setup.get('take_profit')
        reason = setup.get('technical_reason', 'No reason')

        logger.info(f"[DRY RUN] Simulating {action} order at {price:.5f}. SL: {sl:.5f}, TP: {tp:.5f}. Reason: {reason}")
        return True
