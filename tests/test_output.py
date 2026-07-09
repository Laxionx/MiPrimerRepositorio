import unittest
from trading_bot.core.engine import AnalysisEngine
from trading_bot.data.mock_data import MockDataProvider
from trading_bot.signals.liquidity_sweep import LiquiditySweepDetector
from trading_bot.risk.risk_guard import SimpleRiskGuard
from trading_bot.output.json_publisher import RecommendationPublisher
from trading_bot.config.settings import settings

class MockPublisher(RecommendationPublisher):
    def __init__(self):
        self.last_recommendation = None

    def publish(self, recommendation):
        self.last_recommendation = recommendation


class RecordingJournal:
    def __init__(self):
        self.recommendations = []

    def record_setup(self, recommendation):
        self.recommendations.append(recommendation)

class TestOutputSafety(unittest.TestCase):
    def setUp(self):
        settings.DATA_PROVIDER = "mock"
        self.publisher = MockPublisher()
        self.engine = AnalysisEngine(
            market_data=MockDataProvider(scenario="low_sweep"),
            signal_detector=LiquiditySweepDetector(),
            risk_guard=SimpleRiskGuard(),
            publisher=self.publisher
        )

    def test_json_never_allows_submit_even_if_analysis_only_is_false(self):
        settings.ANALYSIS_ONLY = False

        self.engine.run_once()
        rec = self.publisher.last_recommendation

        self.assertIsNotNone(rec)
        self.assertFalse(rec["submit_allowed"])
        self.assertIsNone(rec["command"])
        self.assertFalse(rec["live_execution_enabled"])
        self.assertFalse(rec["broker_api_called"])

        settings.ANALYSIS_ONLY = True

    def test_json_structure_v1_1_0(self):
        self.engine.run_once()
        rec = self.publisher.last_recommendation

        required_keys = [
            "schema_version", "run_id", "mode", "data_provider",
            "generated_at", "symbol", "timeframe", "market_context",
            "market_context_live", "liquidity", "vwap", "volume_profile",
            "order_flow", "setup", "risk", "command", "submit_allowed",
            "broker_api_called", "live_execution_enabled",
            "market_regime", "context_bias", "context_score",
            "context_reason", "entry_score", "entry_reason",
            "blocked_by_context", "blocked_by_entry_score",
            "blocked_by_quality_guard", "quality_block_reason",
            "spread", "entry_distance_from_sweep", "planned_rr",
            "no_chase_blocked", "no_chase_reason", "extension_atr",
            "distance_to_h1_high", "distance_to_h1_low",
            "distance_to_h1_mid",
            "compression_score", "is_compressing", "range_duration_bars",
            "atr_contraction_pct", "recent_range_points", "prior_range_points",
            "pressure_score", "pressure_direction", "price_position_in_range",
            "upper_quartile_closes", "lower_quartile_closes",
            "average_pullback_depth",
        ]

        for key in required_keys:
            self.assertIn(key, rec)

        self.assertEqual(rec["schema_version"], "1.1.0")
        self.assertEqual(rec["mode"], "analysis_only")
        self.assertEqual(rec["data_provider"], "mock")
        self.assertIsInstance(rec["context_score"], int)
        self.assertIsInstance(rec["entry_score"], int)

    def test_blocked_aqtf_setup_is_sent_to_configured_journal(self):
        journal = RecordingJournal()
        engine = AnalysisEngine(
            market_data=MockDataProvider(scenario="low_sweep"),
            signal_detector=LiquiditySweepDetector(),
            risk_guard=SimpleRiskGuard(),
            publisher=self.publisher,
            journal=journal,
        )

        engine.run_once()

        self.assertEqual(len(journal.recommendations), 1)
        self.assertTrue(journal.recommendations[0]["blocked_by_context"])
