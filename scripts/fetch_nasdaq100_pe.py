#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.version_c.config import PE_DATA_PATH


SOURCE_URL = "https://worldperatio.com/index/nasdaq-100/"


def fetch_html(url: str = SOURCE_URL) -> str:
    result = subprocess.run(
        ["curl", "-L", "-A", "Mozilla/5.0", "-sS", url],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.stdout


def _extract_current_pe(html: str) -> float | None:
    patterns = [
        r"P/E Ratio:\s*<b[^>]*>\s*([0-9]+(?:\.[0-9]+)?)\s*</b>",
        r"estimated .*? is <b>([0-9]+(?:\.[0-9]+)?)</b>",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return float(match.group(1))
    return None


def _parse_series_block(block: str) -> pd.DataFrame:
    matches = re.findall(r"Date\.UTC\((\d+),\s*(\d+),\s*(\d+)\),\s*([0-9]+(?:\.[0-9]+)?)", block)
    rows = [
        {"date": pd.Timestamp(year=int(year), month=int(month) + 1, day=int(day)), "pe_ratio": float(value)}
        for year, month, day, value in matches
    ]
    return pd.DataFrame(rows)


def extract_pe_series(html: str) -> pd.DataFrame:
    candidates = []

    for line in html.splitlines():
        if "Date.UTC" not in line or "=" not in line:
            continue
        if "detailPE_data =" in line or "detailPE_data_" in line:
            payload = line.split("=", 1)[1].strip()
            if payload.endswith(";"):
                payload = payload[:-1]
            frame = _parse_series_block(payload)
            if not frame.empty:
                candidates.append(frame)

    if not candidates:
        for match in re.finditer(r"detailPE_data(?:\[\d+\])?\s*=\s*(\[.*?\]);", html, flags=re.DOTALL):
            frame = _parse_series_block(match.group(1))
            if not frame.empty:
                candidates.append(frame)

    if not candidates:
        raise ValueError("could not find any PE history series in source HTML")

    current_pe = _extract_current_pe(html)
    if current_pe is not None:
        candidates.sort(key=lambda frame: (abs(float(frame["pe_ratio"].iloc[-1]) - current_pe), -len(frame)))
    else:
        candidates.sort(key=lambda frame: -len(frame))

    best = candidates[0].drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    if best.empty:
        raise ValueError("parsed PE history is empty")
    return best


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PE_DATA_PATH)
    args = parser.parse_args()

    html = fetch_html()
    df = extract_pe_series(html)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"Wrote {len(df)} monthly PE rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
