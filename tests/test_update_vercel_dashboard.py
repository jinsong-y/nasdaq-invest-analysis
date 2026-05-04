from __future__ import annotations

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

    def test_latest_publishable_market_date_skips_incomplete_latest_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "market_indicators.csv"
            self._write_dashboard_market_csv(
                path,
                [
                    {
                        "date": "2026-04-30",
                        "ndx": "100",
                        "vxn": "20",
                        "vix": "15",
                        "cnn_fear_greed": "50",
                        "ndxe_ndx": "0.95",
                        "sox_ndx": "0.40",
                    },
                    {
                        "date": "2026-05-01",
                        "ndx": "101",
                        "vxn": "",
                        "vix": "",
                        "cnn_fear_greed": "51",
                        "ndxe_ndx": "0.96",
                        "sox_ndx": "0.41",
                    },
                ],
            )

            result = update_vercel_dashboard.latest_publishable_market_date(path)

        self.assertEqual("2026-04-30", result)

    def test_latest_publishable_market_date_fails_when_required_column_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "market_indicators.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["date", "ndx", "vix", "cnn_fear_greed", "ndxe_ndx", "sox_ndx"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "date": "2026-04-30",
                        "ndx": "100",
                        "vix": "15",
                        "cnn_fear_greed": "50",
                        "ndxe_ndx": "0.95",
                        "sox_ndx": "0.40",
                    }
                )

            with self.assertRaisesRegex(RuntimeError, "missing required dashboard columns"):
                update_vercel_dashboard.latest_publishable_market_date(path)

    def test_latest_publishable_market_date_fails_when_no_complete_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "market_indicators.csv"
            self._write_dashboard_market_csv(
                path,
                [
                    {
                        "date": "2026-04-30",
                        "ndx": "100",
                        "vxn": "",
                        "vix": "",
                        "cnn_fear_greed": "50",
                        "ndxe_ndx": "0.95",
                        "sox_ndx": "0.40",
                    }
                ],
            )

            with self.assertRaisesRegex(RuntimeError, "no publishable market dates"):
                update_vercel_dashboard.latest_publishable_market_date(path)

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

    def _write_dashboard_market_csv(self, path: Path, rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = ["date", "ndx", "vxn", "vix", "cnn_fear_greed", "ndxe_ndx", "sox_ndx"]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


class UpdateDashboardWorkflowTests(unittest.TestCase):
    def _write_file(self, path: Path, text: str = "x") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_minimal_root(self, root: Path, *, market_date: str, published_date: str | None) -> None:
        self._write_file(
            root / "data" / "processed" / "market_indicators.csv",
            (
                "date,ndx,vxn,vix,cnn_fear_greed,ndxe_ndx,sox_ndx\n"
                f"{market_date},100,20,15,50,0.95,0.40\n"
            ),
        )
        self._write_file(root / "data" / "processed" / "data_manifest.json", '{"ok": true}\n')
        self._write_file(root / "data" / "raw" / "fred" / "NASDAQ100.csv", "observation_date,NASDAQ100\n")
        self._write_file(root / "data" / "raw" / "cnn" / "fear_greed_live.json", '{"score": 50}\n')
        if published_date is not None:
            self._write_file(
                root / "reports" / "market_regime" / "latest.json",
                json.dumps({"as_of_date": published_date}),
            )

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

    def test_run_update_noops_when_latest_date_already_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_minimal_root(root, market_date="2026-05-04", published_date="2026-05-04")

            with mock.patch.object(update_vercel_dashboard, "run_command") as run_command:
                published = update_vercel_dashboard.run_update(root, fetch=False)

            self.assertFalse(published)
            run_command.assert_not_called()
            self.assertFalse((root / "public").exists())
            self.assertFalse((root / "data" / "snapshots" / "2026-05-04").exists())

    def test_run_update_noops_when_raw_latest_is_newer_but_publishable_date_is_already_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_file(
                root / "data" / "processed" / "market_indicators.csv",
                (
                    "date,ndx,vxn,vix,cnn_fear_greed,ndxe_ndx,sox_ndx\n"
                    "2026-04-30,100,20,15,50,0.95,0.40\n"
                    "2026-05-01,101,,,51,0.96,0.41\n"
                ),
            )
            self._write_file(
                root / "reports" / "market_regime" / "latest.json",
                json.dumps({"as_of_date": "2026-04-30"}),
            )

            with mock.patch.object(update_vercel_dashboard, "run_command") as run_command:
                published = update_vercel_dashboard.run_update(root, fetch=False)

            self.assertFalse(published)
            run_command.assert_not_called()
            self.assertFalse((root / "public").exists())

    def test_run_update_publishes_when_fetched_date_is_newer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_minimal_root(root, market_date="2026-05-04", published_date="2026-05-03")

            def fake_run_command(args, *, cwd):
                self.assertEqual(root, cwd)
                if args[1] == "scripts/run_market_regime_dashboard.py":
                    self._write_generated_dashboard(root, "2026-05-04")

            with mock.patch.object(update_vercel_dashboard, "run_command", side_effect=fake_run_command) as run_command:
                published = update_vercel_dashboard.run_update(root, fetch=False)

            self.assertTrue(published)
            self.assertEqual(1, run_command.call_count)
            self.assertEqual(
                [
                    sys.executable,
                    "scripts/run_market_regime_dashboard.py",
                    "--target-date",
                    "2026-05-04",
                ],
                run_command.call_args.args[0],
            )
            self.assertTrue((root / "public" / "index.html").is_file())
            self.assertTrue((root / "data" / "snapshots" / "2026-05-04" / "market_indicators.csv").is_file())

    def test_run_update_fetches_before_date_detection_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_minimal_root(root, market_date="2026-05-04", published_date="2026-05-03")

            def fake_run_command(args, *, cwd):
                self.assertEqual(root, cwd)
                if args[1] == "scripts/run_market_regime_dashboard.py":
                    self._write_generated_dashboard(root, "2026-05-04")

            with mock.patch.object(update_vercel_dashboard, "run_command", side_effect=fake_run_command) as run_command:
                published = update_vercel_dashboard.run_update(root, fetch=True)

            self.assertTrue(published)
            self.assertEqual(
                [
                    [sys.executable, "scripts/fetch_data.py"],
                    [
                        sys.executable,
                        "scripts/run_market_regime_dashboard.py",
                        "--target-date",
                        "2026-05-04",
                    ],
                ],
                [call.args[0] for call in run_command.call_args_list],
            )

    def test_run_update_does_not_mutate_public_when_snapshot_validation_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_file(
                root / "data" / "processed" / "market_indicators.csv",
                "date,ndx,vxn,vix,cnn_fear_greed,ndxe_ndx,sox_ndx\n2026-05-04,100,20,15,50,0.95,0.40\n",
            )
            self._write_file(root / "data" / "processed" / "data_manifest.json", '{"ok": true}\n')
            self._write_file(root / "data" / "raw" / "fred" / "NASDAQ100.csv", "date,ndx\n")
            (root / "data" / "raw" / "cnn").mkdir(parents=True)
            self._write_file(
                root / "reports" / "market_regime" / "latest.json",
                json.dumps({"as_of_date": "2026-05-03"}),
            )

            def fake_run_command(args, *, cwd):
                self.assertEqual(root, cwd)
                self.assertEqual(
                    [
                        sys.executable,
                        "scripts/run_market_regime_dashboard.py",
                        "--target-date",
                        "2026-05-04",
                    ],
                    args,
                )
                self._write_generated_dashboard(root, "2026-05-04")

            with mock.patch.object(update_vercel_dashboard, "run_command", side_effect=fake_run_command):
                with self.assertRaisesRegex(RuntimeError, "snapshot has no raw CNN JSON"):
                    update_vercel_dashboard.run_update(root, fetch=False)

            self.assertFalse((root / "public").exists())


class UpdateDashboardFileTests(unittest.TestCase):
    def _write_file(self, path: Path, text: str = "x") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_source_tree(self, root: Path) -> None:
        self._write_file(
            root / "data" / "processed" / "market_indicators.csv",
            "date,ndx,vxn,vix,cnn_fear_greed,ndxe_ndx,sox_ndx\n2026-05-04,100,20,15,50,0.95,0.40\n",
        )
        self._write_file(root / "data" / "processed" / "data_manifest.json", '{"ok": true}\n')
        self._write_file(root / "data" / "raw" / "fred" / "NASDAQ100.csv", "observation_date,NASDAQ100\n2026-05-04,100\n")
        self._write_file(root / "data" / "raw" / "cnn" / "fear_greed_live.json", '{"score": 50, "timestamp": 1}\n')

    def _write_report_tree(self, root: Path) -> None:
        report_dir = root / "reports" / "market_regime"
        html = (
            "<!doctype html><title>Market Regime Dashboard</title>"
            "<body>市场状态仪表盘"
            '<button data-language="en">English</button>'
            '<button data-language="zh">中文</button>'
            "</body>"
        )
        self._write_file(report_dir / "index.html", html)
        self._write_file(report_dir / "latest.json", '{"as_of_date": "2026-05-04"}\n')
        self._write_file(report_dir / "daily_regimes.csv", "date,market_regime\n2026-05-04,normal\n")

    def test_sync_dashboard_to_public_copies_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_report_tree(root)

            update_vercel_dashboard.sync_dashboard_to_public(
                root / "reports" / "market_regime",
                root / "public",
            )

            self.assertTrue((root / "public" / "index.html").is_file())
            self.assertTrue((root / "public" / "latest.json").is_file())
            self.assertTrue((root / "public" / "daily_regimes.csv").is_file())

    def test_validate_bilingual_dashboard_fails_when_chinese_marker_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            public_dir = Path(tmp) / "public"
            self._write_file(
                public_dir / "index.html",
                '<title>Market Regime Dashboard</title><button data-language="en">English</button><button data-language="zh">中文</button>',
            )

            with self.assertRaisesRegex(RuntimeError, "bilingual markers"):
                update_vercel_dashboard.validate_bilingual_dashboard(public_dir)

    def test_write_data_snapshot_copies_processed_and_raw_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_source_tree(root)

            snapshot_dir = update_vercel_dashboard.write_data_snapshot(root, "2026-05-04")
            update_vercel_dashboard.validate_snapshot(snapshot_dir)

            self.assertEqual(root / "data" / "snapshots" / "2026-05-04", snapshot_dir)
            self.assertTrue((snapshot_dir / "market_indicators.csv").is_file())
            self.assertTrue((snapshot_dir / "data_manifest.json").is_file())
            self.assertTrue((snapshot_dir / "raw" / "fred" / "NASDAQ100.csv").is_file())
            self.assertTrue((snapshot_dir / "raw" / "cnn" / "fear_greed_live.json").is_file())

    def test_write_data_snapshot_fails_when_snapshot_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_source_tree(root)
            (root / "data" / "snapshots" / "2026-05-04").mkdir(parents=True)

            with self.assertRaisesRegex(RuntimeError, "snapshot already exists"):
                update_vercel_dashboard.write_data_snapshot(root, "2026-05-04")

    def test_validate_public_outputs_checks_latest_date_and_bilingual_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_report_tree(root)
            update_vercel_dashboard.sync_dashboard_to_public(
                root / "reports" / "market_regime",
                root / "public",
            )

            update_vercel_dashboard.validate_public_outputs(root / "public", "2026-05-04")


if __name__ == "__main__":
    unittest.main()
