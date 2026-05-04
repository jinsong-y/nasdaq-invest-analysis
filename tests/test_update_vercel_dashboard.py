import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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


class UpdateDashboardWorkflowTests(unittest.TestCase):
    def _write_file(self, path: Path, text: str = "x") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_generated_dashboard(self, root: Path, market_date: str) -> None:
        html = (
            "<!doctype html><title>Market Regime Dashboard</title>"
            "<body>市场状态仪表盘"
            '<button data-language="en">English</button>'
            '<button data-language="zh">中文</button>'
            "</body>"
        )
        self._write_file(root / "reports" / "market_regime" / "index.html", html)
        self._write_file(root / "reports" / "market_regime" / "latest.json", json.dumps({"as_of_date": market_date}))
        self._write_file(root / "reports" / "market_regime" / "daily_regimes.csv", "date,market_regime\n")

    def test_run_update_does_not_mutate_public_when_snapshot_validation_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_file(
                root / "data" / "processed" / "market_indicators.csv",
                "date,ndx\n2026-05-04,100\n",
            )
            self._write_file(root / "data" / "processed" / "data_manifest.json", '{"ok": true}\n')
            self._write_file(root / "data" / "raw" / "fred" / "NASDAQ100.csv", "date,ndx\n")
            (root / "data" / "raw" / "cnn").mkdir(parents=True)
            self._write_file(
                root / "reports" / "market_regime" / "latest.json",
                json.dumps({"as_of_date": "2026-05-03"}),
            )

            def fake_run_command(args, *, cwd):
                self.assertEqual(root.resolve(), cwd)
                self.assertEqual([sys.executable, "scripts/run_market_regime_dashboard.py"], args)
                self._write_generated_dashboard(root, "2026-05-04")

            with mock.patch.object(update_vercel_dashboard, "run_command", side_effect=fake_run_command):
                with self.assertRaisesRegex(RuntimeError, "snapshot has no raw CNN JSON"):
                    update_vercel_dashboard.run_update(root, fetch=False)

            self.assertFalse((root / "public").exists())


if __name__ == "__main__":
    unittest.main()
