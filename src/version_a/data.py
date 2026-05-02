from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import BASELINE_START


REQUIRED_COLUMNS = {
    "date",
    "ndx",
    "vxn",
    "vix",
    "ndxe",
    "sox",
    "cnn_fear_greed",
    "ndxe_ndx",
    "sox_ndx",
}


def load_market_data(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] >= pd.Timestamp(BASELINE_START)].copy()
    df = df.sort_values("date").set_index("date")
    for column in REQUIRED_COLUMNS - {"date"}:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    if df["ndx"].dropna().empty:
        raise ValueError("ndx column has no usable values")
    return df
