import unittest
from trading_bot.config.settings import settings
from trading_bot.data.factory import get_data_provider
from trading_bot.data.mock_data import MockDataProvider
from trading_bot.data.mt5_data import MT5DataProvider
from trading_bot.risk.risk_guard import SimpleRiskGuard

class TestHardening(unittest.TestCase):
    def test_default_provider_is_mock(self):
        # Ensure default settings
        settings.DATA_PROVIDER = "mock"
        provider = get_data_provider()
        self.assertIsInstance(provider, MockDataProvider)

    def test_credentials_alone_do_not_activate_mt5(self):
        settings.DATA_PROVIDER = "mock"
        settings.MT5_LOGIN = 12345
        settings.MT5_PASSWORD = "password"

        provider = get_data_provider()
        self.assertIsInstance(provider, MockDataProvider)

    def test_mt5_provider_requires_explicit_config(self):
        settings.DATA_PROVIDER = "mt5"
        settings.MT5_LOGIN = 12345
        settings.MT5_PASSWORD = "password"

        provider = get_data_provider()
        self.assertIsInstance(provider, MT5DataProvider)

    def test_risk_guard_blocks_missing_data(self):
        risk_guard = SimpleRiskGuard()
        settings.BLOCK_IF_DATA_MISSING = True

        setup_data = {"setup": {"type": "LONG"}}
        # Scenario: connected but spread is missing
        context = {"connected": True, "spread": None, "volatility": 0.001}

        report = risk_guard.validate_setup(setup_data, context)
        self.assertFalse(report["allowed"])
        self.assertIn("spread data missing", report["reason"])

    def test_risk_guard_blocks_missing_volatility(self):
        risk_guard = SimpleRiskGuard()
        settings.BLOCK_IF_DATA_MISSING = True

        setup_data = {"setup": {"type": "LONG"}}
        # Scenario: connected but volatility is missing
        context = {"connected": True, "spread": 5, "volatility": None}

        report = risk_guard.validate_setup(setup_data, context)
        self.assertFalse(report["allowed"])
        self.assertIn("volatility data missing", report["reason"])

    def test_no_execution_path_reachable(self):
        # In AnalysisEngine, there is literally no reference to an Executor anymore.
        from trading_bot.core.engine import AnalysisEngine
        import inspect

        init_params = inspect.signature(AnalysisEngine.__init__).parameters
        self.assertNotIn("executor", init_params)
