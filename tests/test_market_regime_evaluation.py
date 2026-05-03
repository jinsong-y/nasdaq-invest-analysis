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
