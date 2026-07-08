from typing import Dict, Any
from trading_bot.core.interfaces import Executor
from trading_bot.utils.logger import logger

class DryRunExecutor(Executor):
    def execute(self, signal: Dict[str, Any]) -> bool:
        action = signal['action']
        price = signal['price']
        sl = signal.get('stop_loss')
        tp = signal.get('take_profit')
        reason = signal.get('reason', 'No reason')

        logger.info(f"[DRY RUN] Simulating {action} order at {price:.5f}. SL: {sl:.5f}, TP: {tp:.5f}. Reason: {reason}")
        return True
