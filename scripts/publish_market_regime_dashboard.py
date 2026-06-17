#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_FILES = ("index.html", "latest.json", "daily_regimes.csv")
REQUIRED_DAILY_INPUT_COLUMNS = (
    "ndx",
    "vxn",
    "vix",
    "cnn_fear_greed",
    "ndxe_ndx",
    "sox_ndx",
)
BILINGUAL_MARKERS = (
    "Nasdaq 100 Market Regime Dashboard",
    "纳指100市场状态仪表盘",
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


def publishable_market_date(path: Path) -> str:
    if not path.exists():
        fail(f"Daily Input CSV missing: {path}")
    dates: list[str] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        required = ("date", *REQUIRED_DAILY_INPUT_COLUMNS)
        missing = [column for column in required if column not in fieldnames]
        if missing:
            fail(f"Daily Input missing required columns in {path}: {', '.join(missing)}")
        for row in reader:
            raw_date = (row.get("date") or "").strip()
            if not raw_date:
                continue
            market_date = parse_market_date(raw_date)
            complete = True
            for column in REQUIRED_DAILY_INPUT_COLUMNS:
                value = (row.get(column) or "").strip()
                if not value:
                    complete = False
                    continue
                try:
                    numeric_value = float(value)
                except ValueError:
                    fail(f"invalid Daily Input value for {column} on {market_date}: {value!r}")
                if not math.isfinite(numeric_value):
                    fail(f"invalid Daily Input value for {column} on {market_date}: {value!r}")
            if complete:
                dates.append(market_date)
    if not dates:
        fail(f"no Publishable Market Date found in {path}")
    return max(dates)


def published_market_date(public_dir: Path) -> str | None:
    latest_json = public_dir / "latest.json"
    if not latest_json.exists():
        return None
    payload = json.loads(latest_json.read_text(encoding="utf-8"))
    value = str(payload.get("as_of_date", "")).strip()
    return parse_market_date(value) if value else None


def should_publish(publishable_date: str, published_date: str | None) -> bool:
    if published_date is None:
        return True
    return parse_market_date(publishable_date) > parse_market_date(published_date)


def assert_non_empty_file(path: Path) -> None:
    if not path.exists():
        fail(f"required Published Artifact missing: {path}")
    if not path.is_file():
        fail(f"required Published Artifact path is not a file: {path}")
    if path.stat().st_size <= 0:
        fail(f"required Published Artifact is empty: {path}")


def validate_published_artifacts(public_dir: Path, market_date: str) -> None:
    for filename in PUBLISHED_FILES:
        assert_non_empty_file(public_dir / filename)
    payload = json.loads((public_dir / "latest.json").read_text(encoding="utf-8"))
    as_of_date = parse_market_date(str(payload.get("as_of_date", "")))
    expected_date = parse_market_date(market_date)
    if as_of_date != expected_date:
        fail(f"public latest.json as_of_date {as_of_date} does not match {expected_date}")
    html = (public_dir / "index.html").read_text(encoding="utf-8")
    missing = [marker for marker in BILINGUAL_MARKERS if marker not in html]
    if missing:
        fail(f"public dashboard missing bilingual markers: {', '.join(missing)}")


def run_command(args: list[str], *, cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, check=False)
    if result.returncode != 0:
        fail(f"command failed with exit {result.returncode}: {' '.join(args)}")


def run_automatic_publish(root: Path, *, fetch: bool = True) -> bool:
    root = Path(root)
    data_path = root / "data" / "processed" / "market_indicators.csv"
    public_dir = root / "public"

    if fetch:
        run_command([sys.executable, "scripts/fetch_data.py"], cwd=root)

    publishable_date = publishable_market_date(data_path)
    current_date = published_market_date(public_dir)
    if not should_publish(publishable_date, current_date):
        print(
            f"No new Publishable Market Date. Latest publishable: {publishable_date}. "
            f"Latest published: {current_date}."
        )
        print("PUBLISHED=false")
        return False

    run_command(
        [
            sys.executable,
            "scripts/run_market_regime_dashboard.py",
            "--output-dir",
            str(public_dir),
            "--target-date",
            publishable_date,
            "--no-latest-inputs-overlay",
        ],
        cwd=root,
    )
    validate_published_artifacts(public_dir, publishable_date)
    print(f"Published Market Regime Dashboard for {publishable_date}.")
    print("PUBLISHED=true")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args(argv)
    try:
        run_automatic_publish(args.root, fetch=not args.skip_fetch)
    except Exception as exc:
        print(f"publish_market_regime_dashboard failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
