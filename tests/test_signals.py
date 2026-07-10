import unittest
from trading_bot.signals.liquidity_sweep import LiquiditySweepDetector
from trading_bot.data.mock_data import MockDataProvider

class TestLiquiditySweepDetector(unittest.TestCase):
    def setUp(self):
        self.detector = LiquiditySweepDetector(lookback=5, reward_risk_ratio=2.0)

    def test_low_sweep_produces_long_recommendation(self):
        data_provider = MockDataProvider(scenario="low_sweep")
        df = data_provider.get_ohlcv("EURUSD", "M5", 10)

        report = self.detector.detect_signals(df)
        setup = report.get('setup')

        self.assertIsNotNone(setup)
        self.assertEqual(setup['type'], "LONG")
        self.assertIn("swept recent low", setup['technical_reason'])

    def test_high_sweep_produces_short_recommendation(self):
        data_provider = MockDataProvider(scenario="high_sweep")
        df = data_provider.get_ohlcv("EURUSD", "M5", 10)

        report = self.detector.detect_signals(df)
        setup = report.get('setup')

        self.assertIsNotNone(setup)
        self.assertEqual(setup['type'], "SHORT")
        self.assertIn("swept recent high", setup['technical_reason'])

    def test_no_sweep_produces_no_setup(self):
        data_provider = MockDataProvider(scenario="no_setup")
        df = data_provider.get_ohlcv("EURUSD", "M5", 10)

        report = self.detector.detect_signals(df)
        self.assertIsNone(report.get('setup'))
