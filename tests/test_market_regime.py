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


import pandas as pd

from src.market_regime.model import classify_latest, missing_inputs_for_row


class MarketRegimeValidationTests(unittest.TestCase):
    def _valid_row(self):
        return {
            "ndx": 100.0,
            "sma": 100.0,
            "dist_sma": 0.0,
            "vxn": 20.0,
            "vix": 18.0,
            "vxn_pctile": 0.50,
            "vix_pctile": 0.50,
            "cnn_fear_greed": 50.0,
            "cnn_ma5": 50.0,
            "ndxe_ndx": 0.35,
            "ndxe_ma": 0.35,
            "sox_ndx": 0.25,
            "sox_ma": 0.25,
        }

    def test_missing_inputs_for_row_lists_nan_fields(self):
        row = pd.Series(self._valid_row())
        row["vix"] = float("nan")
        row["vxn"] = None
        self.assertEqual(["vix", "vxn"], missing_inputs_for_row(row))

    def test_latest_classification_fails_when_required_latest_inputs_missing(self):
        frame = pd.DataFrame([self._valid_row()], index=pd.to_datetime(["2026-05-01"]))
        frame.loc[pd.Timestamp("2026-05-01"), "vix"] = float("nan")
        with self.assertRaisesRegex(ValueError, "2026-05-01.*vix"):
            classify_latest(frame)
