from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import fetch_yahoo_latest_inputs


class FetchYahooLatestInputsTests(unittest.TestCase):
    def _chart_payload(self, symbol: str, price: float, timestamp: int = 1778270400) -> dict:
        return {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": symbol,
                            "regularMarketPrice": price,
                            "regularMarketTime": timestamp,
                            "exchangeTimezoneName": "America/New_York",
                        },
                        "timestamp": [timestamp - 60, timestamp],
                        "indicators": {
                            "quote": [
                                {
                                    "close": [price - 1.0, price],
                                }
                            ]
                        },
                    }
                ],
                "error": None,
            }
        }

    def test_build_latest_inputs_snapshot_maps_quotes_and_derives_ratios(self):
        payloads = {
            "^NDX": self._chart_payload("^NDX", 28600.0),
            "^VIX": self._chart_payload("^VIX", 17.5),
            "^VXN": self._chart_payload("^VXN", 23.7),
            "^NDXE": self._chart_payload("^NDXE", 9530.0),
            "^SOX": self._chart_payload("^SOX", 11480.0),
        }

        snapshot = fetch_yahoo_latest_inputs.build_latest_inputs_snapshot(payloads)

        self.assertEqual("2026-05-08", snapshot["market_date"])
        self.assertEqual("yahoo_finance_chart", snapshot["source"])
        self.assertEqual(28600.0, snapshot["raw_inputs"]["ndx"]["value"])
        self.assertEqual(17.5, snapshot["raw_inputs"]["vix"]["value"])
        self.assertAlmostEqual(9530.0 / 28600.0, snapshot["raw_inputs"]["ndxe_ndx"]["value"])
        self.assertAlmostEqual(11480.0 / 28600.0, snapshot["raw_inputs"]["sox_ndx"]["value"])
        self.assertEqual("^NDX", snapshot["raw_inputs"]["ndx"]["symbol"])

    def test_write_snapshot_creates_processed_and_raw_files(self):
        payloads = {
            "^NDX": self._chart_payload("^NDX", 28600.0),
            "^VIX": self._chart_payload("^VIX", 17.5),
            "^VXN": self._chart_payload("^VXN", 23.7),
            "^NDXE": self._chart_payload("^NDXE", 9530.0),
            "^SOX": self._chart_payload("^SOX", 11480.0),
        }
        snapshot = fetch_yahoo_latest_inputs.build_latest_inputs_snapshot(payloads)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            fetch_yahoo_latest_inputs.write_snapshot(root, snapshot, payloads)

            processed = root / "data" / "processed" / "latest_intraday_inputs.json"
            raw = root / "data" / "raw" / "yahoo" / "latest_quotes.json"
            self.assertTrue(processed.is_file())
            self.assertTrue(raw.is_file())
            self.assertEqual("2026-05-08", json.loads(processed.read_text())["market_date"])


if __name__ == "__main__":
    unittest.main()
