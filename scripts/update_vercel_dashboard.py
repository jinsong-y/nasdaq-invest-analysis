#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.publish_market_regime_dashboard import ROOT, run_automatic_publish


def run_update(root: Path, *, fetch: bool, fetch_intraday: bool = False) -> bool:
    if fetch_intraday:
        raise RuntimeError("intraday overlay is not part of Automatic Publish")
    return run_automatic_publish(root, fetch=fetch)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--fetch", action="store_true", help="Fetch Daily Input before publishing.")
    parser.add_argument(
        "--fetch-intraday",
        action="store_true",
        help="Unsupported: intraday overlay is not part of Automatic Publish.",
    )
    args = parser.parse_args(argv)
    try:
        run_update(args.root, fetch=args.fetch, fetch_intraday=args.fetch_intraday)
    except Exception as exc:
        print(f"update_vercel_dashboard failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
