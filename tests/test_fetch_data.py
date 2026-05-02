import csv
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import fetch_data


class FetchDataTests(unittest.TestCase):
    def test_merged_rows_are_filtered_to_configured_start_date(self):
        fred_rows = {
            "NASDAQ100": [
                {"date": "1999-12-31", "ndx": "100"},
                {"date": "2000-01-03", "ndx": "101"},
            ],
            "VXNCLS": [{"date": "2000-01-03", "vxn": "20"}],
            "VIXCLS": [{"date": "2000-01-03", "vix": "21"}],
            "NASDAQNDXE": [{"date": "2005-06-28", "ndxe": "50"}],
            "NASDAQSOX": [{"date": "2004-09-02", "sox": "60"}],
        }
        cnn_history = {
            "daily": [
                {"d": "1999-12-31", "fg": 40, "spx": 1000},
                {"d": "2011-01-03", "fg": 68, "spx": 1271.87},
            ]
        }

        rows = fetch_data.merge_by_date(fred_rows, cnn_history)

        self.assertEqual(fetch_data.START_DATE, rows[0]["date"])
        self.assertTrue(all(row["date"] >= fetch_data.START_DATE for row in rows))
        self.assertNotIn("1999-12-31", {row["date"] for row in rows})

    def test_processed_csv_starts_at_configured_start_date_when_present(self):
        path = ROOT / "data" / "processed" / "market_indicators.csv"
        if not path.exists():
            self.skipTest("processed CSV has not been generated")

        with path.open(newline="", encoding="utf-8") as handle:
            first_row = next(csv.DictReader(handle))

        self.assertEqual(fetch_data.START_DATE, first_row["date"])


if __name__ == "__main__":
    unittest.main()
