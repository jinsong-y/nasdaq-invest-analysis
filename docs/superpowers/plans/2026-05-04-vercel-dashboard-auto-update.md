# Vercel Dashboard Auto Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub Actions powered daily updater that fetches market data, publishes the bilingual market regime dashboard to Vercel static files, and archives dated data snapshots.

**Architecture:** Add one focused Python helper script for date detection, no-op decisions, dashboard public sync, snapshot creation, validation, and CLI orchestration. Add a GitHub Actions workflow that runs the existing fetch/report scripts through this helper, commits only when a new market date is published, and leaves Vercel to redeploy from GitHub. Add `public/`, `requirements.txt`, and `vercel.json` so the deployed output is small and explicit.

**Tech Stack:** Python 3.11, standard library `csv/json/shutil/subprocess`, existing pandas/numpy runtime, `unittest`, GitHub Actions, Vercel static deployment.

---

## File Structure

- Create `scripts/update_vercel_dashboard.py`: workflow helper with pure functions and CLI entry point. Owns latest-date detection, no-op decision, running fetch/report commands, copying dashboard files to `public/`, writing `data/snapshots/YYYY-MM-DD/`, and validation.
- Create `tests/test_update_vercel_dashboard.py`: unit tests for helper behavior, no network calls.
- Create `requirements.txt`: runtime dependencies needed by GitHub Actions.
- Create `.github/workflows/update-market-regime-dashboard.yml`: daily/manual workflow.
- Create `vercel.json`: tells Vercel to serve `public/`.
- Create `public/index.html`, `public/latest.json`, `public/daily_regimes.csv`: current static deployment copy generated from `reports/market_regime/*`.
- Modify `.gitignore` only if local commands create new cache files not already ignored. Expected: no change.

## Task 1: Date Detection And No-Op Decision

**Files:**
- Create: `scripts/update_vercel_dashboard.py`
- Create: `tests/test_update_vercel_dashboard.py`

- [ ] **Step 1: Write failing tests for latest date detection**

Add this file:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m unittest tests.test_update_vercel_dashboard -v
```

Expected: FAIL with `ImportError: cannot import name 'update_vercel_dashboard' from 'scripts'` or `ModuleNotFoundError` because the helper script does not exist yet.

- [ ] **Step 3: Implement date helper functions**

Create `scripts/update_vercel_dashboard.py` with this content:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_FILES = ("index.html", "latest.json", "daily_regimes.csv")
BILINGUAL_MARKERS = (
    "Market Regime Dashboard",
    "市场状态仪表盘",
    'data-language="en"',
    'data-language="zh"',
)


def fail(message: str) -> None:
    raise RuntimeError(message)


def parse_market_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        fail(f"invalid date {value!r}: {exc}")
    raise AssertionError("unreachable")


def latest_market_date(path: Path) -> str:
    if not path.exists():
        fail(f"market indicators CSV missing: {path}")
    dates: list[str] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "date" not in (reader.fieldnames or []):
            fail(f"market indicators CSV missing date column: {path}")
        for row in reader:
            value = (row.get("date") or "").strip()
            if value:
                dates.append(parse_market_date(value))
    if not dates:
        fail(f"no market dates found in {path}")
    return max(dates)


def latest_published_date(latest_json_path: Path, snapshots_dir: Path) -> str | None:
    dates: list[str] = []
    if latest_json_path.exists():
        payload = json.loads(latest_json_path.read_text(encoding="utf-8"))
        value = str(payload.get("as_of_date", "")).strip()
        if value:
            dates.append(parse_market_date(value))
    if snapshots_dir.exists():
        for child in snapshots_dir.iterdir():
            if not child.is_dir():
                continue
            try:
                dates.append(parse_market_date(child.name))
            except RuntimeError:
                continue
    return max(dates) if dates else None


def should_publish(fetched_date: str, published_date: str | None) -> bool:
    fetched = parse_market_date(fetched_date)
    if published_date is None:
        return True
    published = parse_market_date(published_date)
    return fetched > published


def assert_non_empty_file(path: Path) -> None:
    if not path.exists():
        fail(f"required file missing: {path}")
    if not path.is_file():
        fail(f"required path is not a file: {path}")
    if path.stat().st_size <= 0:
        fail(f"required file is empty: {path}")


def run_command(args: list[str], *, cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, check=False)
    if result.returncode != 0:
        fail(f"command failed with exit {result.returncode}: {' '.join(args)}")


def sync_dashboard_to_public(report_dir: Path, public_dir: Path) -> None:
    public_dir.mkdir(parents=True, exist_ok=True)
    for filename in REPORT_FILES:
        source = report_dir / filename
        assert_non_empty_file(source)
        shutil.copy2(source, public_dir / filename)


def validate_bilingual_dashboard(public_dir: Path) -> None:
    html_path = public_dir / "index.html"
    assert_non_empty_file(html_path)
    html = html_path.read_text(encoding="utf-8")
    missing = [marker for marker in BILINGUAL_MARKERS if marker not in html]
    if missing:
        fail(f"public dashboard missing bilingual markers: {', '.join(missing)}")


def write_data_snapshot(root: Path, market_date: str) -> Path:
    market_date = parse_market_date(market_date)
    snapshot_dir = root / "data" / "snapshots" / market_date
    if snapshot_dir.exists():
        fail(f"snapshot already exists: {snapshot_dir}")

    processed_dir = root / "data" / "processed"
    raw_dir = root / "data" / "raw"
    assert_non_empty_file(processed_dir / "market_indicators.csv")
    assert_non_empty_file(processed_dir / "data_manifest.json")
    if not (raw_dir / "fred").is_dir():
        fail(f"raw FRED directory missing: {raw_dir / 'fred'}")
    if not (raw_dir / "cnn").is_dir():
        fail(f"raw CNN directory missing: {raw_dir / 'cnn'}")

    snapshot_dir.mkdir(parents=True)
    shutil.copy2(processed_dir / "market_indicators.csv", snapshot_dir / "market_indicators.csv")
    shutil.copy2(processed_dir / "data_manifest.json", snapshot_dir / "data_manifest.json")
    shutil.copytree(raw_dir / "fred", snapshot_dir / "raw" / "fred")
    shutil.copytree(raw_dir / "cnn", snapshot_dir / "raw" / "cnn")
    return snapshot_dir


def validate_snapshot(snapshot_dir: Path) -> None:
    assert_non_empty_file(snapshot_dir / "market_indicators.csv")
    assert_non_empty_file(snapshot_dir / "data_manifest.json")
    fred_files = sorted((snapshot_dir / "raw" / "fred").glob("*.csv"))
    cnn_files = sorted((snapshot_dir / "raw" / "cnn").glob("*.json"))
    if not fred_files:
        fail(f"snapshot has no raw FRED CSV files: {snapshot_dir}")
    if not cnn_files:
        fail(f"snapshot has no raw CNN JSON files: {snapshot_dir}")
    for path in [*fred_files, *cnn_files]:
        assert_non_empty_file(path)


def validate_public_outputs(public_dir: Path, market_date: str) -> None:
    for filename in REPORT_FILES:
        assert_non_empty_file(public_dir / filename)
    payload = json.loads((public_dir / "latest.json").read_text(encoding="utf-8"))
    as_of_date = parse_market_date(str(payload.get("as_of_date", "")))
    expected_date = parse_market_date(market_date)
    if as_of_date != expected_date:
        fail(f"public latest.json as_of_date {as_of_date} does not match {expected_date}")
    validate_bilingual_dashboard(public_dir)


def run_update(root: Path, *, fetch: bool) -> bool:
    root = root.resolve()
    data_path = root / "data" / "processed" / "market_indicators.csv"
    latest_json_path = root / "reports" / "market_regime" / "latest.json"
    snapshots_dir = root / "data" / "snapshots"
    report_dir = root / "reports" / "market_regime"
    public_dir = root / "public"

    if fetch:
        run_command([sys.executable, "scripts/fetch_data.py"], cwd=root)

    fetched_date = latest_market_date(data_path)
    published_date = latest_published_date(latest_json_path, snapshots_dir)
    if not should_publish(fetched_date, published_date):
        print(
            f"No new market date. Latest fetched: {fetched_date}. "
            f"Latest published: {published_date}."
        )
        print("PUBLISHED=false")
        return False

    run_command([sys.executable, "scripts/run_market_regime_dashboard.py"], cwd=root)
    sync_dashboard_to_public(report_dir, public_dir)
    snapshot_dir = write_data_snapshot(root, fetched_date)
    validate_public_outputs(public_dir, fetched_date)
    validate_snapshot(snapshot_dir)
    print(f"Published market regime dashboard for {fetched_date}.")
    print("PUBLISHED=true")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args(argv)
    try:
        run_update(args.root, fetch=args.fetch)
    except Exception as exc:
        print(f"update_vercel_dashboard failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
python -m unittest tests.test_update_vercel_dashboard -v
```

Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/update_vercel_dashboard.py tests/test_update_vercel_dashboard.py
git commit -m "feat: add dashboard update date checks"
```

## Task 2: Snapshot, Public Sync, And Bilingual Validation Tests

**Files:**
- Modify: `tests/test_update_vercel_dashboard.py`
- Modify: `scripts/update_vercel_dashboard.py`

- [ ] **Step 1: Add failing tests for public sync and snapshot validation**

Append this test class before the `if __name__ == "__main__":` block in `tests/test_update_vercel_dashboard.py`:

```python
class UpdateDashboardFileTests(unittest.TestCase):
    def _write_file(self, path: Path, text: str = "x") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_source_tree(self, root: Path) -> None:
        self._write_file(root / "data" / "processed" / "market_indicators.csv", "date,ndx\n2026-05-04,100\n")
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
```

- [ ] **Step 2: Run tests**

Run:

```bash
python -m unittest tests.test_update_vercel_dashboard -v
```

Expected: PASS because Task 1 added the file helpers used by these tests.

- [ ] **Step 3: Commit**

```bash
git add scripts/update_vercel_dashboard.py tests/test_update_vercel_dashboard.py
git commit -m "test: cover dashboard public sync snapshots"
```

## Task 3: CLI Orchestration Tests

**Files:**
- Modify: `tests/test_update_vercel_dashboard.py`
- Modify: `scripts/update_vercel_dashboard.py`

- [ ] **Step 1: Add failing tests for no-op and publish paths**

Append this test class before the `if __name__ == "__main__":` block:

```python
from unittest import mock


class UpdateDashboardWorkflowTests(unittest.TestCase):
    def _write_file(self, path: Path, text: str = "x") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_minimal_root(self, root: Path, *, market_date: str, published_date: str | None) -> None:
        self._write_file(
            root / "data" / "processed" / "market_indicators.csv",
            f"date,ndx\n{market_date},100\n",
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

    def test_run_update_publishes_when_fetched_date_is_newer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_minimal_root(root, market_date="2026-05-04", published_date="2026-05-03")

            def fake_run_command(args, *, cwd):
                self.assertEqual(root, cwd)
                if args[-1] == "scripts/run_market_regime_dashboard.py":
                    self._write_generated_dashboard(root, "2026-05-04")

            with mock.patch.object(update_vercel_dashboard, "run_command", side_effect=fake_run_command) as run_command:
                published = update_vercel_dashboard.run_update(root, fetch=False)

            self.assertTrue(published)
            self.assertEqual(1, run_command.call_count)
            self.assertTrue((root / "public" / "index.html").is_file())
            self.assertTrue((root / "data" / "snapshots" / "2026-05-04" / "market_indicators.csv").is_file())

    def test_run_update_fetches_before_date_detection_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_minimal_root(root, market_date="2026-05-04", published_date="2026-05-03")

            def fake_run_command(args, *, cwd):
                self.assertEqual(root, cwd)
                if args[-1] == "scripts/run_market_regime_dashboard.py":
                    self._write_generated_dashboard(root, "2026-05-04")

            with mock.patch.object(update_vercel_dashboard, "run_command", side_effect=fake_run_command) as run_command:
                published = update_vercel_dashboard.run_update(root, fetch=True)

            self.assertTrue(published)
            self.assertEqual(
                [
                    [sys.executable, "scripts/fetch_data.py"],
                    [sys.executable, "scripts/run_market_regime_dashboard.py"],
                ],
                [call.args[0] for call in run_command.call_args_list],
            )
```

- [ ] **Step 2: Run tests**

Run:

```bash
python -m unittest tests.test_update_vercel_dashboard -v
```

Expected: PASS if Task 1 implementation already included `run_update`. If a test fails because snapshot already exists, check the no-op branch compares against `latest_published_date` before writing any files.

- [ ] **Step 3: Commit**

```bash
git add scripts/update_vercel_dashboard.py tests/test_update_vercel_dashboard.py
git commit -m "feat: orchestrate dashboard publish workflow"
```

## Task 4: Runtime Dependencies And Static Deploy Config

**Files:**
- Create: `requirements.txt`
- Create: `vercel.json`

- [ ] **Step 1: Add `requirements.txt`**

Create `requirements.txt`:

```text
pandas
numpy
```

- [ ] **Step 2: Add `vercel.json`**

Create `vercel.json`:

```json
{
  "outputDirectory": "public"
}
```

- [ ] **Step 3: Verify dependencies install in a clean command**

Run:

```bash
python -m pip install -r requirements.txt
```

Expected: exits 0. Existing installed packages may print `Requirement already satisfied`.

- [ ] **Step 4: Verify JSON config parses**

Run:

```bash
python -m json.tool vercel.json >/tmp/vercel-json-check.json
```

Expected: exits 0.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt vercel.json
git commit -m "chore: add vercel static deploy config"
```

## Task 5: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/update-market-regime-dashboard.yml`

- [ ] **Step 1: Create workflow**

Create `.github/workflows/update-market-regime-dashboard.yml`:

```yaml
name: Update Market Regime Dashboard

on:
  schedule:
    - cron: "0 23 * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: market-regime-dashboard-update
  cancel-in-progress: false

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: python -m pip install -r requirements.txt

      - name: Fetch data and build dashboard
        id: update
        shell: bash
        run: |
          set -euo pipefail
          python scripts/update_vercel_dashboard.py --fetch | tee /tmp/dashboard-update.log
          if grep -q '^PUBLISHED=true$' /tmp/dashboard-update.log; then
            echo "published=true" >> "$GITHUB_OUTPUT"
          else
            echo "published=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Commit dashboard update
        if: steps.update.outputs.published == 'true'
        shell: bash
        run: |
          set -euo pipefail
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/raw/fred data/raw/cnn data/processed/market_indicators.csv data/processed/data_manifest.json docs/DATA_INVENTORY.md reports/market_regime public data/snapshots
          if git diff --cached --quiet; then
            echo "No staged changes after dashboard update."
            exit 0
          fi
          market_date="$(python - <<'PY'
          import json
          from pathlib import Path
          print(json.loads(Path("public/latest.json").read_text(encoding="utf-8"))["as_of_date"])
          PY
          )"
          git commit -m "chore: update market regime dashboard ${market_date}"
          git push
```

- [ ] **Step 2: Validate workflow YAML parses**

Run:

```bash
python - <<'PY'
from pathlib import Path
path = Path(".github/workflows/update-market-regime-dashboard.yml")
text = path.read_text(encoding="utf-8")
required = [
    'cron: "0 23 * * *"',
    "workflow_dispatch:",
    "contents: write",
    "python scripts/update_vercel_dashboard.py --fetch",
    "PUBLISHED=true",
    "git add data/raw/fred data/raw/cnn",
]
missing = [item for item in required if item not in text]
if missing:
    raise SystemExit(f"missing workflow markers: {missing}")
print("workflow markers ok")
PY
```

Expected:

```text
workflow markers ok
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/update-market-regime-dashboard.yml
git commit -m "ci: add daily dashboard update workflow"
```

## Task 6: Initial Public Dashboard Copy

**Files:**
- Create: `public/index.html`
- Create: `public/latest.json`
- Create: `public/daily_regimes.csv`

- [ ] **Step 1: Publish current local data or bootstrap `public/`**

Run the helper against current local data:

```bash
python scripts/update_vercel_dashboard.py
```

Expected when local processed data is newer than `reports/market_regime/latest.json`:

```text
Published market regime dashboard for YYYY-MM-DD.
PUBLISHED=true
```

Expected when the current dashboard already matches local processed data:

```text
No new market date. Latest fetched: YYYY-MM-DD. Latest published: YYYY-MM-DD.
PUBLISHED=false
```

If the command prints `PUBLISHED=false`, create the initial `public/` files from the current report:

Run:

```bash
python - <<'PY'
from pathlib import Path
from scripts.update_vercel_dashboard import sync_dashboard_to_public, validate_public_outputs

root = Path(".").resolve()
latest_date = __import__("json").loads((root / "reports" / "market_regime" / "latest.json").read_text(encoding="utf-8"))["as_of_date"]
sync_dashboard_to_public(root / "reports" / "market_regime", root / "public")
validate_public_outputs(root / "public", latest_date)
print(f"public dashboard ready for {latest_date}")
PY
```

Expected:

```text
public dashboard ready for 2026-04-30
```

If the date differs because reports were regenerated, the command should print the actual current `as_of_date`.

- [ ] **Step 2: Verify bilingual markers in current public HTML**

Run:

```bash
python - <<'PY'
from pathlib import Path
html = Path("public/index.html").read_text(encoding="utf-8")
markers = ["Market Regime Dashboard", "市场状态仪表盘", 'data-language="en"', 'data-language="zh"']
missing = [marker for marker in markers if marker not in html]
if missing:
    raise SystemExit(f"missing bilingual markers: {missing}")
print("bilingual markers ok")
PY
```

Expected:

```text
bilingual markers ok
```

- [ ] **Step 3: Commit**

```bash
git add public/index.html public/latest.json public/daily_regimes.csv data/snapshots reports/market_regime
git commit -m "chore: add initial public dashboard"
```

## Task 7: End-To-End Verification

**Files:**
- No new files expected.

- [ ] **Step 1: Run focused tests**

Run:

```bash
python -m unittest tests.test_update_vercel_dashboard -v
```

Expected: PASS.

- [ ] **Step 2: Run existing relevant tests**

Run:

```bash
python -m unittest tests.test_fetch_data tests.test_market_regime -v
```

Expected: PASS.

- [ ] **Step 3: Run helper no-fetch smoke**

Run:

```bash
python scripts/update_vercel_dashboard.py
```

Expected after Task 6: exits 0 and prints:

```text
No new market date. Latest fetched: YYYY-MM-DD. Latest published: YYYY-MM-DD.
PUBLISHED=false
```

If it prints `PUBLISHED=true`, inspect the new `data/snapshots/YYYY-MM-DD/` and `public/` outputs, then commit them with:

```bash
git add data/snapshots public reports/market_regime
git commit -m "chore: refresh public dashboard snapshot"
```

- [ ] **Step 4: Check final git status**

Run:

```bash
git status --short
```

Expected: no output.

## Spec Coverage Review

- Vercel deploys only latest dashboard: Tasks 4 and 6 add `vercel.json` and `public/*`.
- Bilingual dashboard preserved: Tasks 1, 2, and 6 validate bilingual markers.
- Daily GitHub Actions after close: Task 5 adds `0 23 * * *`.
- Existing fail-fast fetch remains source of truth: Task 3 and Task 5 call `scripts/fetch_data.py` through `--fetch`.
- Dated snapshots: Task 2 implements and tests `data/snapshots/YYYY-MM-DD/`.
- Commit changed data/dashboard files: Task 5 stages exact data, report, public, and snapshot paths.
- Weekends, holidays, delayed data: Task 1 and Task 3 implement no-op decision on latest fetched date versus latest published date.
- No Vercel functions or cron: Task 5 uses GitHub Actions only.

## Execution Notes

- The plan uses direct commits after each task. If working on a feature branch, keep these commits. If working on `main`, confirm branch policy before pushing.
- The workflow intentionally ignores dirty no-op fetch output because the commit step runs only when `PUBLISHED=true`.
- The snapshot writer fails if a same-date snapshot already exists. That protects historical data from accidental overwrite.
