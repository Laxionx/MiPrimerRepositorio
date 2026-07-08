from typing import Dict, Any
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from trading_bot.core.interfaces import Executor
from trading_bot.utils.logger import logger

class MT5Executor(Executor):
    def __init__(self, symbol: str):
        self.symbol = symbol

    def execute(self, signal: Dict[str, Any]) -> bool:
        if mt5 is None:
            logger.error("MT5 package not available for execution.")
            return False

        action = signal['action']
        sl = signal.get('stop_loss')
        tp = signal.get('take_profit')

        order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL

        # Determine price based on action
        symbol_info = mt5.symbol_info_tick(self.symbol)
        if symbol_info is None:
            logger.error(f"Failed to get symbol info for {self.symbol}")
            return False

        price = symbol_info.ask if action == "BUY" else symbol_info.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": 0.01, # Default minimum lot
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 123456,
            "comment": "Sent by Python Trading Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        logger.info(f"Sending {action} order to MT5: {request}")

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed: {result.retcode} - {result.comment}")
            return False

        logger.info(f"Order executed successfully: Ticket {result.order}")
        return True
