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
REQUIRED_DASHBOARD_COLUMNS = (
    "ndx",
    "vxn",
    "vix",
    "cnn_fear_greed",
    "ndxe_ndx",
    "sox_ndx",
)
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


def latest_publishable_market_date(path: Path) -> str:
    if not path.exists():
        fail(f"market indicators CSV missing: {path}")
    dates: list[str] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        required = ("date", *REQUIRED_DASHBOARD_COLUMNS)
        missing = [column for column in required if column not in fieldnames]
        if missing:
            fail(f"missing required dashboard columns in {path}: {', '.join(missing)}")
        for row in reader:
            value = (row.get("date") or "").strip()
            if not value:
                continue
            if all((row.get(column) or "").strip() for column in REQUIRED_DASHBOARD_COLUMNS):
                dates.append(parse_market_date(value))
    if not dates:
        fail(f"no publishable market dates found in {path}")
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
    root = Path(root)
    data_path = root / "data" / "processed" / "market_indicators.csv"
    latest_json_path = root / "reports" / "market_regime" / "latest.json"
    snapshots_dir = root / "data" / "snapshots"
    report_dir = root / "reports" / "market_regime"
    public_dir = root / "public"

    if fetch:
        run_command([sys.executable, "scripts/fetch_data.py"], cwd=root)

    fetched_date = latest_publishable_market_date(data_path)
    published_date = latest_published_date(latest_json_path, snapshots_dir)
    if not should_publish(fetched_date, published_date):
        print(
            f"No new market date. Latest fetched: {fetched_date}. "
            f"Latest published: {published_date}."
        )
        print("PUBLISHED=false")
        return False

    run_command(
        [
            sys.executable,
            "scripts/run_market_regime_dashboard.py",
            "--target-date",
            fetched_date,
        ],
        cwd=root,
    )
    snapshot_dir = write_data_snapshot(root, fetched_date)
    validate_snapshot(snapshot_dir)
    sync_dashboard_to_public(report_dir, public_dir)
    validate_public_outputs(public_dir, fetched_date)
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
