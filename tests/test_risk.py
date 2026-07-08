import unittest
from trading_bot.risk.risk_manager import SimpleRiskManager

class TestRiskManager(unittest.TestCase):
    def setUp(self):
        self.risk_manager = SimpleRiskManager(
            max_risk_per_trade=0.01,
            max_daily_loss=0.05,
            max_trades_per_day=2,
            spread_filter=10
        )

    def test_validate_trade_connected(self):
        signal = {"action": "BUY", "price": 1.1000}

        # Test disconnected
        context = {"connected": False, "spread": 5}
        self.assertFalse(self.risk_manager.validate_trade(signal, context))

        # Test connected
        context = {"connected": True, "spread": 5}
        self.assertTrue(self.risk_manager.validate_trade(signal, context))

    def test_spread_filter(self):
        signal = {"action": "BUY", "price": 1.1000}
        context = {"connected": True, "spread": 15} # Higher than 10
        self.assertFalse(self.risk_manager.validate_trade(signal, context))

    def test_max_trades_per_day(self):
        signal = {"action": "BUY", "price": 1.1000}
        context = {"connected": True, "spread": 5}

        # 1st trade
        self.assertTrue(self.risk_manager.validate_trade(signal, context))
        self.risk_manager.update_daily_stats(0.01)

        # 2nd trade
        self.assertTrue(self.risk_manager.validate_trade(signal, context))
        self.risk_manager.update_daily_stats(0.01)

        # 3rd trade - should be blocked
        self.assertFalse(self.risk_manager.validate_trade(signal, context))

    def test_max_daily_loss(self):
        signal = {"action": "BUY", "price": 1.1000}
        context = {"connected": True, "spread": 5}

        # Lose 6% (max is 5%)
        self.risk_manager.update_daily_stats(-0.06)
        self.assertFalse(self.risk_manager.validate_trade(signal, context))
