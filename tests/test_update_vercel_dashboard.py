import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import update_vercel_dashboard


class UpdateDashboardDateTests(unittest.TestCase):
    def _write_market_csv(self, path: Path, dates: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["date", "ndx"])
            writer.writeheader()
            for idx, day in enumerate(dates, start=1):
                writer.writerow({"date": day, "ndx": str(100 + idx)})

    def test_latest_market_date_reads_max_valid_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "market_indicators.csv"
            self._write_market_csv(path, ["2026-05-01", "2026-04-30", "2026-05-04"])

            result = update_vercel_dashboard.latest_market_date(path)

        self.assertEqual("2026-05-04", result)

    def test_latest_market_date_fails_on_empty_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "market_indicators.csv"
            self._write_market_csv(path, [])

            with self.assertRaisesRegex(RuntimeError, "no market dates"):
                update_vercel_dashboard.latest_market_date(path)

    def test_latest_market_date_fails_on_bad_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "market_indicators.csv"
            self._write_market_csv(path, ["2026-05-01", "bad-date"])

            with self.assertRaisesRegex(RuntimeError, "invalid date"):
                update_vercel_dashboard.latest_market_date(path)

    def test_latest_published_date_prefers_latest_json_and_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            latest_json = root / "reports" / "market_regime" / "latest.json"
            latest_json.parent.mkdir(parents=True)
            latest_json.write_text(json.dumps({"as_of_date": "2026-05-02"}), encoding="utf-8")
            (root / "data" / "snapshots" / "2026-05-03").mkdir(parents=True)
            (root / "data" / "snapshots" / "not-a-date").mkdir()

            result = update_vercel_dashboard.latest_published_date(
                latest_json,
                root / "data" / "snapshots",
            )

        self.assertEqual("2026-05-03", result)

    def test_latest_published_date_returns_none_when_no_artifacts_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = update_vercel_dashboard.latest_published_date(
                root / "reports" / "market_regime" / "latest.json",
                root / "data" / "snapshots",
            )

        self.assertIsNone(result)

    def test_should_publish_only_when_fetched_date_is_newer(self):
        self.assertTrue(update_vercel_dashboard.should_publish("2026-05-04", None))
        self.assertTrue(update_vercel_dashboard.should_publish("2026-05-04", "2026-05-03"))
        self.assertFalse(update_vercel_dashboard.should_publish("2026-05-04", "2026-05-04"))
        self.assertFalse(update_vercel_dashboard.should_publish("2026-05-04", "2026-05-05"))


if __name__ == "__main__":
    unittest.main()
