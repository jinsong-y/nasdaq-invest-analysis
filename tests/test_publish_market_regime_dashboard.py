from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import publish_market_regime_dashboard


class AutomaticPublishEntrypointTests(unittest.TestCase):
    def _write_file(self, path: Path, text: str = "x") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_daily_inputs(self, root: Path, market_date: str) -> None:
        self._write_file(
            root / "data" / "processed" / "market_indicators.csv",
            (
                "date,ndx,vxn,vix,cnn_fear_greed,ndxe_ndx,sox_ndx\n"
                f"{market_date},100,20,15,50,0.95,0.40\n"
            ),
        )

    def test_noops_without_mutating_public_when_publishable_market_date_is_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_daily_inputs(root, "2026-05-04")
            self._write_file(root / "public" / "index.html", "current html")
            self._write_file(root / "public" / "latest.json", json.dumps({"as_of_date": "2026-05-04"}))
            self._write_file(root / "public" / "daily_regimes.csv", "current csv")
            before = {
                path.name: path.read_text(encoding="utf-8")
                for path in (root / "public").iterdir()
            }

            with mock.patch.object(publish_market_regime_dashboard, "run_command") as run_command:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    published = publish_market_regime_dashboard.run_automatic_publish(root, fetch=False)

            after = {
                path.name: path.read_text(encoding="utf-8")
                for path in (root / "public").iterdir()
            }
            self.assertFalse(published)
            self.assertEqual(before, after)
            run_command.assert_not_called()
            self.assertIn("No new Publishable Market Date", output.getvalue())
            self.assertIn("PUBLISHED=false", output.getvalue())

    def test_publishes_new_market_date_directly_to_public_without_intraday_or_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_daily_inputs(root, "2026-05-04")
            self._write_file(root / "public" / "latest.json", json.dumps({"as_of_date": "2026-05-03"}))
            self._write_file(
                root / "data" / "processed" / "latest_intraday_inputs.json",
                json.dumps({"market_date": "2026-05-08", "raw_inputs": {"ndx": {"value": 999999}}}),
            )

            def fake_run_command(args: list[str], *, cwd: Path) -> None:
                self.assertEqual(root, cwd)
                self.assertEqual(
                    [
                        sys.executable,
                        "scripts/run_market_regime_dashboard.py",
                        "--output-dir",
                        str(root / "public"),
                        "--target-date",
                        "2026-05-04",
                        "--no-latest-inputs-overlay",
                    ],
                    args,
                )
                self._write_file(
                    root / "public" / "index.html",
                    (
                        "<!doctype html><title>Nasdaq 100 Market Regime Dashboard</title>"
                        "<body>纳指100市场状态仪表盘"
                        '<button data-language="en">English</button>'
                        '<button data-language="zh">中文</button>'
                        "</body>"
                    ),
                )
                self._write_file(root / "public" / "latest.json", json.dumps({"as_of_date": "2026-05-04"}))
                self._write_file(root / "public" / "daily_regimes.csv", "date,market_regime\n2026-05-04,normal\n")

            with mock.patch.object(publish_market_regime_dashboard, "run_command", side_effect=fake_run_command):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    published = publish_market_regime_dashboard.run_automatic_publish(root, fetch=False)

            self.assertTrue(published)
            self.assertTrue((root / "public" / "index.html").is_file())
            self.assertFalse((root / "reports" / "market_regime").exists())
            self.assertFalse((root / "data" / "snapshots").exists())
            self.assertIn("Published Market Regime Dashboard for 2026-05-04", output.getvalue())
            self.assertIn("PUBLISHED=true", output.getvalue())

    def test_publishable_market_date_uses_only_complete_daily_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_file(
                root / "data" / "processed" / "market_indicators.csv",
                (
                    "date,ndx,vxn,vix,cnn_fear_greed,ndxe_ndx,sox_ndx\n"
                    "2026-05-04,100,20,15,50,0.95,0.40\n"
                    "2026-05-05,101,,16,55,0.96,0.41\n"
                ),
            )
            self._write_file(root / "public" / "latest.json", json.dumps({"as_of_date": "2026-05-03"}))

            def fake_run_command(args: list[str], *, cwd: Path) -> None:
                self.assertEqual("2026-05-04", args[5])
                self._write_file(
                    root / "public" / "index.html",
                    (
                        "<!doctype html><title>Nasdaq 100 Market Regime Dashboard</title>"
                        "<body>纳指100市场状态仪表盘"
                        '<button data-language="en">English</button>'
                        '<button data-language="zh">中文</button>'
                        "</body>"
                    ),
                )
                self._write_file(root / "public" / "latest.json", json.dumps({"as_of_date": "2026-05-04"}))
                self._write_file(root / "public" / "daily_regimes.csv", "date,market_regime\n2026-05-04,normal\n")

            with mock.patch.object(publish_market_regime_dashboard, "run_command", side_effect=fake_run_command):
                published = publish_market_regime_dashboard.run_automatic_publish(root, fetch=False)

            self.assertTrue(published)

    def test_invalid_daily_input_value_fails_fast_without_mutating_public(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_file(
                root / "data" / "processed" / "market_indicators.csv",
                "date,ndx,vxn,vix,cnn_fear_greed,ndxe_ndx,sox_ndx\n2026-05-04,nan,20,15,50,0.95,0.40\n",
            )
            self._write_file(root / "public" / "index.html", "current html")
            before = (root / "public" / "index.html").read_text(encoding="utf-8")

            with mock.patch.object(publish_market_regime_dashboard, "run_command") as run_command:
                with self.assertRaisesRegex(RuntimeError, "invalid Daily Input value"):
                    publish_market_regime_dashboard.run_automatic_publish(root, fetch=False)

            run_command.assert_not_called()
            self.assertEqual(before, (root / "public" / "index.html").read_text(encoding="utf-8"))

    def test_fetches_daily_input_before_publishing_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls: list[list[str]] = []

            def fake_run_command(args: list[str], *, cwd: Path) -> None:
                self.assertEqual(root, cwd)
                calls.append(args)
                if args == [sys.executable, "scripts/fetch_data.py"]:
                    self._write_daily_inputs(root, "2026-05-04")
                    return
                self.assertEqual("2026-05-04", args[5])
                self._write_file(
                    root / "public" / "index.html",
                    (
                        "<!doctype html><title>Nasdaq 100 Market Regime Dashboard</title>"
                        "<body>纳指100市场状态仪表盘"
                        '<button data-language="en">English</button>'
                        '<button data-language="zh">中文</button>'
                        "</body>"
                    ),
                )
                self._write_file(root / "public" / "latest.json", json.dumps({"as_of_date": "2026-05-04"}))
                self._write_file(root / "public" / "daily_regimes.csv", "date,market_regime\n2026-05-04,normal\n")

            with mock.patch.object(publish_market_regime_dashboard, "run_command", side_effect=fake_run_command):
                published = publish_market_regime_dashboard.run_automatic_publish(root)

            self.assertTrue(published)
            self.assertEqual(
                [
                    [sys.executable, "scripts/fetch_data.py"],
                    [
                        sys.executable,
                        "scripts/run_market_regime_dashboard.py",
                        "--output-dir",
                        str(root / "public"),
                        "--target-date",
                        "2026-05-04",
                        "--no-latest-inputs-overlay",
                    ],
                ],
                calls,
            )


if __name__ == "__main__":
    unittest.main()
