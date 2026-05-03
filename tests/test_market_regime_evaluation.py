import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_market_regime import (
    FORWARD_HORIZONS,
    KNOWN_DATES,
    evaluate_daily_regimes,
    merge_previous_regimes,
    write_evaluation_outputs,
)


class MarketRegimeEvaluationTests(unittest.TestCase):
    def _sample(self):
        dates = pd.bdate_range("2026-01-01", periods=270)
        regimes = ["normal"] * len(dates)
        regimes[0] = "panic_low"
        regimes[1] = "warm_recovery"
        regimes[2] = "top_risk_watch"
        return pd.DataFrame(
            {
                "date": dates,
                "market_regime": regimes,
                "ndx": [100.0 + i for i in range(len(dates))],
                "temperature_score": [50.0] * len(dates),
                "top_risk_score": [0.0] * len(dates),
                "overheat_score": [0.0] * len(dates),
                "recovery_score": [0.0] * len(dates),
            }
        )

    def test_evaluate_daily_regimes_returns_expected_tables(self):
        current = self._sample()
        previous = current[["date", "market_regime"]].copy()
        previous.loc[previous.index[1], "market_regime"] = "recovery"
        merged = merge_previous_regimes(current, previous)
        result = evaluate_daily_regimes(merged)
        self.assertEqual(list(FORWARD_HORIZONS.values()), ["1m", "3m", "6m", "12m"])
        self.assertIn("regime_summary", result)
        self.assertIn("known_dates", result)
        self.assertIn("classification_changes", result)
        self.assertEqual(1, len(result["classification_changes"]))
        self.assertIn("panic_low", set(result["regime_summary"]["market_regime"]))

    def test_write_evaluation_outputs_creates_files(self):
        result = evaluate_daily_regimes(self._sample())
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_evaluation_outputs(out, result)
            self.assertTrue((out / "summary.json").exists())
            self.assertTrue((out / "regime_summary.csv").exists())
            self.assertTrue((out / "known_dates.csv").exists())
            self.assertTrue((out / "index.html").exists())
            payload = json.loads((out / "summary.json").read_text())
            self.assertIn("generated_at", payload)

    def test_forward_12m_mdd_uses_peak_to_trough_path_math(self):
        dates = pd.bdate_range("2026-01-01", periods=253)
        prices = [100.0, 150.0, 120.0] + [130.0] * 250
        result = evaluate_daily_regimes(
            pd.DataFrame(
                {
                    "date": dates,
                    "market_regime": ["normal"] * len(dates),
                    "ndx": prices,
                }
            )
        )
        self.assertAlmostEqual(
            -0.20,
            result["daily_with_forward"].loc[0, "fwd_12m_mdd"],
            places=6,
        )

    def test_known_dates_use_nearest_available_rows(self):
        dates = pd.to_datetime(["2011-08-05", "2011-08-09"])
        result = evaluate_daily_regimes(
            pd.DataFrame(
                {
                    "date": dates,
                    "market_regime": ["normal", "normal"],
                    "ndx": [100.0, 101.0],
                }
            )
        )
        known = result["known_dates"]
        self.assertEqual(len(KNOWN_DATES), len(known))
        self.assertIn("requested_date", known.columns)
        self.assertIn("matched_date", known.columns)
        self.assertFalse(known["matched_date"].isna().any())
        first = known[known["requested_date"] == pd.Timestamp("2011-08-08")].iloc[0]
        self.assertEqual(pd.Timestamp("2011-08-09"), first["matched_date"])

    def test_empty_schema_valid_frame_raises_clear_value_error(self):
        empty = pd.DataFrame(columns=["date", "market_regime", "ndx"])
        with self.assertRaisesRegex(ValueError, "cannot evaluate empty daily regimes frame"):
            evaluate_daily_regimes(empty)

    def test_hit_rate_ignores_missing_forward_returns(self):
        dates = pd.bdate_range("2026-01-01", periods=22)
        result = evaluate_daily_regimes(
            pd.DataFrame(
                {
                    "date": dates,
                    "market_regime": ["normal"] * len(dates),
                    "ndx": [100.0 + i for i in range(len(dates))],
                }
            )
        )
        summary = result["regime_summary"]
        normal = summary[summary["market_regime"] == "normal"].iloc[0]
        self.assertEqual(1.0, normal["fwd_1m_win_rate"])

    def test_previous_missing_rows_do_not_count_as_classification_changes(self):
        current = self._sample()
        previous = current.loc[[0], ["date", "market_regime"]].copy()
        merged = merge_previous_regimes(current, previous)
        result = evaluate_daily_regimes(merged)
        self.assertEqual(0, len(result["classification_changes"]))

    def test_regime_summary_excludes_unscorable_rows(self):
        df = pd.DataFrame(
            {
                "date": pd.bdate_range("2026-01-01", periods=3),
                "market_regime": ["unscorable", "normal", "unscorable"],
                "ndx": [100.0, 101.0, 102.0],
            }
        )
        result = evaluate_daily_regimes(df)
        self.assertNotIn("unscorable", set(result["regime_summary"]["market_regime"]))
        self.assertIn("normal", set(result["regime_summary"]["market_regime"]))

    def test_invalid_ndx_raises_value_error(self):
        df = pd.DataFrame(
            {
                "date": pd.bdate_range("2026-01-01", periods=3),
                "market_regime": ["normal", "normal", "normal"],
                "ndx": [100.0, "bad", 102.0],
            }
        )
        with self.assertRaisesRegex(ValueError, "invalid ndx"):
            evaluate_daily_regimes(df)

    def test_non_finite_ndx_raises_value_error(self):
        df = pd.DataFrame(
            {
                "date": pd.bdate_range("2026-01-01", periods=3),
                "market_regime": ["normal", "normal", "normal"],
                "ndx": [100.0, float("inf"), 102.0],
            }
        )
        with self.assertRaisesRegex(ValueError, "invalid ndx"):
            evaluate_daily_regimes(df)
