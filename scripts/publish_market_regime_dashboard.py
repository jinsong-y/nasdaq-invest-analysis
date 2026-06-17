#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market_regime.daily_input import find_publishable_market_date, parse_market_date

PUBLISHED_FILES = ("index.html", "latest.json", "daily_regimes.csv")
BILINGUAL_MARKERS = (
    "Nasdaq 100 Market Regime Dashboard",
    "纳指100市场状态仪表盘",
    'data-language="en"',
    'data-language="zh"',
)


@dataclass(frozen=True)
class PublishResult:
    changed: bool
    market_date: str
    artifact_paths: tuple[Path, ...]
    commit_message: str

    def __bool__(self) -> bool:
        return self.changed


def fail(message: str) -> None:
    raise RuntimeError(message)


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


def run_command(args: list[str], *, cwd: Path, allowed_exit_codes: tuple[int, ...] = (0,)) -> int:
    result = subprocess.run(args, cwd=cwd, check=False)
    if result.returncode not in allowed_exit_codes:
        fail(f"command failed with exit {result.returncode}: {' '.join(args)}")
    return result.returncode


def commit_published_artifacts(root: Path, result: PublishResult, *, push: bool = False) -> bool:
    if not result.changed:
        print("No Published Artifact changes to commit.")
        return False

    root = Path(root)
    run_command(["git", "config", "user.name", "github-actions[bot]"], cwd=root)
    run_command(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=root)
    run_command(["git", "add", "--", *(str(path) for path in result.artifact_paths)], cwd=root)
    diff_code = run_command(["git", "diff", "--cached", "--quiet"], cwd=root, allowed_exit_codes=(0, 1))
    if diff_code == 0:
        print("No Published Artifact changes after Automatic Publish.")
        return False
    run_command(["git", "commit", "-m", result.commit_message], cwd=root)
    if push:
        run_command(["git", "push"], cwd=root)
    return True


def run_automatic_publish(root: Path, *, fetch: bool = True) -> PublishResult:
    root = Path(root)
    data_path = root / "data" / "processed" / "market_indicators.csv"
    public_dir = root / "public"

    if fetch:
        run_command([sys.executable, "scripts/fetch_data.py"], cwd=root)

    try:
        publishable_date = find_publishable_market_date(data_path)
    except ValueError as exc:
        fail(str(exc))
    current_date = published_market_date(public_dir)
    artifact_paths = tuple(public_dir / filename for filename in PUBLISHED_FILES)
    commit_message = f"chore: publish market regime dashboard {publishable_date}"
    if not should_publish(publishable_date, current_date):
        print(
            f"No new Publishable Market Date. Latest publishable: {publishable_date}. "
            f"Latest published: {current_date}."
        )
        return PublishResult(
            changed=False,
            market_date=publishable_date,
            artifact_paths=artifact_paths,
            commit_message=commit_message,
        )

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
    return PublishResult(
        changed=True,
        market_date=publishable_date,
        artifact_paths=artifact_paths,
        commit_message=commit_message,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_automatic_publish(args.root, fetch=not args.skip_fetch)
        if args.commit:
            commit_published_artifacts(args.root, result, push=args.push)
    except Exception as exc:
        print(f"publish_market_regime_dashboard failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
