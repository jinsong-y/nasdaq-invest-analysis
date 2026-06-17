from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.market_regime.config import DashboardConfig
from src.market_regime.daily_input import find_publishable_market_date, prepare_daily_input


class DailyInputReadinessTests(unittest.TestCase):
    def _write_file(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_daily_input(self, root: Path) -> Path:
        path = root / "data" / "processed" / "market_indicators.csv"
        self._write_file(
            path,
            (
                "date,ndx,vxn,vix,cnn_fear_greed,ndxe,sox,ndxe_ndx,sox_ndx\n"
                "2026-05-02,98,18,13,48,93,38,0.93,0.38\n"
                "2026-05-03,99,19,14,49,94,39,0.94,0.39\n"
                "2026-05-04,100,20,15,50,95,40,0.95,0.40\n"
                "2026-05-05,101,21,16,51,96,41,0.96,0.41\n"
            ),
        )
        return path

    def test_automatic_publish_uses_daily_input_without_intraday_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_path = self._write_daily_input(root)
            latest_inputs_path = root / "data" / "processed" / "latest_intraday_inputs.json"
            self._write_file(
                latest_inputs_path,
                json.dumps(
                    {
                        "market_date": "2026-05-08",
                        "raw_inputs": {
                            "ndx": {"value": 999999.0},
                            "vix": {"value": 1.0},
                        },
                    }
                ),
            )

            readiness = prepare_daily_input(
                data_path,
                config=DashboardConfig(sma_period=2, sentiment_lookback_days=3, repair_ma_days=2),
                latest_inputs_path=latest_inputs_path,
                allow_latest_inputs_overlay=False,
            )

        self.assertEqual("2026-05-05", readiness.publishable_market_date)
        self.assertEqual("2026-05-05", readiness.latest_inputs["ndx"]["as_of_date"])
        self.assertNotIn("2026-05-08", readiness.featured.index.strftime("%Y-%m-%d"))

    def test_publishable_market_date_uses_only_complete_daily_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_path = self._write_daily_input(root)
            with data_path.open("a", encoding="utf-8") as handle:
                handle.write("2026-05-06,102,,17,52,97,42,0.97,0.42\n")

            publishable_date = find_publishable_market_date(data_path)

        self.assertEqual("2026-05-05", publishable_date)

    def test_publishable_market_date_fails_fast_for_bad_daily_input(self):
        cases = [
            (
                "missing column",
                "date,ndx,vxn,vix,cnn_fear_greed,ndxe_ndx\n"
                "2026-05-05,101,21,16,51,0.96\n",
                "missing required columns",
            ),
            (
                "bad date",
                "date,ndx,vxn,vix,cnn_fear_greed,ndxe_ndx,sox_ndx\n"
                "bad-date,101,21,16,51,0.96,0.41\n",
                "invalid date",
            ),
            (
                "non finite",
                "date,ndx,vxn,vix,cnn_fear_greed,ndxe_ndx,sox_ndx\n"
                "2026-05-05,nan,21,16,51,0.96,0.41\n",
                "invalid Daily Input value",
            ),
        ]
        for name, csv_text, message in cases:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    data_path = root / "data" / "processed" / "market_indicators.csv"
                    self._write_file(data_path, csv_text)

                    with self.assertRaisesRegex(ValueError, message):
                        find_publishable_market_date(data_path)


if __name__ == "__main__":
    unittest.main()
