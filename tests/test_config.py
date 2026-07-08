import unittest
from trading_bot.config.settings import settings
from trading_bot.data.mock_data import MockDataProvider
from trading_bot.data.mt5_data import MT5DataProvider

class TestConfigurationHardening(unittest.TestCase):
    def test_default_data_provider_is_mock(self):
        self.assertEqual(settings.DATA_PROVIDER, "mock")

    def test_mock_scenario_default_is_no_setup(self):
        self.assertEqual(settings.MOCK_SCENARIO, "no_setup")

    def test_mock_data_provider_instantiation_with_scenario(self):
        provider = MockDataProvider(scenario="high_sweep")
        self.assertEqual(provider.scenario, "high_sweep")

        df = provider.get_ohlcv("EURUSD", "M5", 10)
        self.assertFalse(df.empty)

    def test_json_output_fields(self):
        # Already covered in test_output.py but re-asserting schema
        self.assertIsNotNone(settings.SCHEMA_VERSION)
        self.assertIsNotNone(settings.RUN_ID)

    def test_aqtf_threshold_defaults(self):
        self.assertEqual(settings.CONTEXT_SCORE_MIN, 60)
        self.assertEqual(settings.ENTRY_SCORE_MIN, 65)
        self.assertEqual(settings.NO_CHASE_MAX_ATR, 0.6)
