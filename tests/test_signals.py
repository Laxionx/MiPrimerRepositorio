import unittest
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
from trading_bot.signals.liquidity_sweep import LiquiditySweepDetector

class TestLiquiditySweepDetector(unittest.TestCase):
    def setUp(self):
        # Using a small lookback for tests
        self.detector = LiquiditySweepDetector(lookback=5, reward_risk_ratio=2.0)

    def test_low_sweep_produces_long_recommendation(self):
        dates = [datetime.now() - timedelta(minutes=5*i) for i in range(10)]
        dates.reverse()

        # Recent low should be in indices 4-8 for lookback=5
        highs = [11.0] * 10
        lows  = [10.0, 10.0, 10.0, 10.0, 9.0, 10.0, 10.0, 10.0, 10.0, 8.5]
        closes = [10.5, 10.5, 10.5, 10.5, 10.0, 10.5, 10.5, 10.5, 10.5, 9.2]
        volumes = [100] * 10

        df = pd.DataFrame({
            'time': dates,
            'high': highs,
            'low': lows,
            'close': closes,
            'tick_volume': volumes
        })

        report = self.detector.detect_signals(df)
        setup = report.get('setup')

        self.assertIsNotNone(setup, f"No setup detected when a low sweep occurred. Report: {report}")
        self.assertEqual(setup['type'], "LONG")
        # In the detector it's "swept recent low"
        self.assertIn("swept recent low", setup['technical_reason'])

    def test_high_sweep_produces_short_recommendation(self):
        dates = [datetime.now() - timedelta(minutes=5*i) for i in range(10)]
        dates.reverse()

        # Recent high should be in indices 4-8
        highs = [10.0, 10.0, 10.0, 10.0, 11.0, 10.0, 10.0, 10.0, 10.0, 11.5]
        lows  = [ 9.0] * 10
        closes = [ 9.5,  9.5,  9.5,  9.5, 10.0,  9.5,  9.5,  9.5,  9.5, 10.8]
        volumes = [100] * 10

        df = pd.DataFrame({
            'time': dates,
            'high': highs,
            'low': lows,
            'close': closes,
            'tick_volume': volumes
        })

        report = self.detector.detect_signals(df)
        setup = report.get('setup')

        self.assertIsNotNone(setup, f"No setup detected when a high sweep occurred. Report: {report}")
        self.assertEqual(setup['type'], "SHORT")
        # In the detector it's "swept recent high"
        self.assertIn("swept recent high", setup['technical_reason'])

    def test_no_sweep_produces_no_setup(self):
        dates = [datetime.now() - timedelta(minutes=5*i) for i in range(10)]
        dates.reverse()

        highs = [11] * 10
        lows  = [ 9] * 10
        closes = [10] * 10
        volumes = [100] * 10

        df = pd.DataFrame({
            'time': dates,
            'high': highs,
            'low': lows,
            'close': closes,
            'tick_volume': volumes
        })

        report = self.detector.detect_signals(df)
        self.assertIsNone(report.get('setup'))
