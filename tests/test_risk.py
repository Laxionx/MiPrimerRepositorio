import unittest
from trading_bot.risk.risk_guard import SimpleRiskGuard

class TestRiskGuard(unittest.TestCase):
    def setUp(self):
        self.risk_guard = SimpleRiskGuard(
            max_risk_per_trade=0.01,
            max_daily_loss=0.05,
            max_trades_per_day=2,
            spread_limit=10,
            volatility_limit=0.01
        )

    def test_high_spread_blocks_setup(self):
        setup_data = {"setup": {"type": "LONG"}}
        # context now comes from provider
        context = {"connected": True, "spread": 15, "volatility": 0.001}
        report = self.risk_guard.validate_setup(setup_data, context)
        self.assertFalse(report["allowed"])
        self.assertIn("Spread too high", report["reason"])

    def test_max_daily_loss_blocks_setup(self):
        setup_data = {"setup": {"type": "LONG"}}
        context = {"connected": True, "spread": 5, "volatility": 0.001}

        self.risk_guard.update_daily_stats(-0.06)
        report = self.risk_guard.validate_setup(setup_data, context)
        self.assertFalse(report["allowed"])
        self.assertIn("Max daily loss reached", report["reason"])

    def test_volatility_limit_blocks_setup(self):
        setup_data = {"setup": {"type": "LONG"}}
        context = {"connected": True, "spread": 5, "volatility": 0.02}
        report = self.risk_guard.validate_setup(setup_data, context)
        self.assertFalse(report["allowed"])
        self.assertIn("Volatility too high", report["reason"])

    def test_missing_data_blocks_setup(self):
        setup_data = {"setup": {"type": "LONG"}}
        context = {"connected": True} # Missing spread
        report = self.risk_guard.validate_setup(setup_data, context)
        self.assertFalse(report["allowed"])
        self.assertIn("Required market data missing", report["reason"])
