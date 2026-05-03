import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market_regime.config import DashboardConfig, REQUIRED_DERIVED_COLUMNS, REQUIRED_RAW_COLUMNS


class MarketRegimeConfigTests(unittest.TestCase):
    def test_required_columns_are_explicit(self):
        self.assertEqual(
            {
                "ndx",
                "vxn",
                "vix",
                "cnn_fear_greed",
                "ndxe_ndx",
                "sox_ndx",
            },
            REQUIRED_RAW_COLUMNS,
        )
        self.assertEqual(
            {
                "sma",
                "dist_sma",
                "vxn_pctile",
                "vix_pctile",
                "cnn_ma5",
                "ndxe_ma",
                "sox_ma",
            },
            REQUIRED_DERIVED_COLUMNS,
        )

    def test_default_config_matches_design(self):
        config = DashboardConfig()
        self.assertEqual(180, config.sma_period)
        self.assertEqual(1260, config.sentiment_lookback_days)
        self.assertEqual(50, config.repair_ma_days)
        self.assertEqual(252, config.rolling_high_days)
        self.assertEqual(75.0, config.panic_low_threshold)
        self.assertEqual(55.0, config.stress_low_threshold)
        self.assertEqual(55.0, config.recovery_threshold)
        self.assertEqual(60.0, config.warm_threshold)
        self.assertEqual(70.0, config.overheat_threshold)
        self.assertEqual(75.0, config.top_risk_threshold)
        self.assertEqual(45.0, config.low_confidence_threshold)
        self.assertGreater(config.top_risk_threshold, config.warm_threshold)
