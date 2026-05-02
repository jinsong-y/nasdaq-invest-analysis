from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import START_DATE


def load_market_data(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"date", "ndx"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing required market columns: {sorted(missing)}")
    df["date"] = pd.to_datetime(df["date"])
    df["ndx"] = pd.to_numeric(df["ndx"], errors="coerce")
    df = df[df["date"] >= pd.Timestamp(START_DATE)].copy()
    df = df.dropna(subset=["ndx"]).sort_values("date")
    if df.empty:
        raise ValueError("market data has no usable ndx rows")
    return df[["date", "ndx"]]


def load_pe_data(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"date", "pe_ratio"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing required PE columns: {sorted(missing)}")
    df["date"] = pd.to_datetime(df["date"])
    df["pe_ratio"] = pd.to_numeric(df["pe_ratio"], errors="coerce")
    df = df.dropna(subset=["date", "pe_ratio"]).sort_values("date")
    if df.empty:
        raise ValueError("PE data has no usable rows")
    return df[["date", "pe_ratio"]]


def _expanding_percentile(series: pd.Series) -> pd.Series:
    history: list[float] = []
    out: list[float] = []
    for value in series.tolist():
        history.append(float(value))
        rank = sum(item <= value for item in history) / len(history)
        out.append(float(rank))
    return pd.Series(out, index=series.index, dtype=float)


def merge_market_with_pe(market: pd.DataFrame, pe: pd.DataFrame) -> pd.DataFrame:
    market_work = market.copy()
    pe_work = pe.copy()
    if "date" not in market_work.columns or "ndx" not in market_work.columns:
        raise ValueError("market frame must contain date and ndx columns")
    if "date" not in pe_work.columns or "pe_ratio" not in pe_work.columns:
        raise ValueError("PE frame must contain date and pe_ratio columns")

    market_work["date"] = pd.to_datetime(market_work["date"])
    pe_work["date"] = pd.to_datetime(pe_work["date"])
    market_work["ndx"] = pd.to_numeric(market_work["ndx"], errors="coerce")
    pe_work["pe_ratio"] = pd.to_numeric(pe_work["pe_ratio"], errors="coerce")
    market_work = market_work.dropna(subset=["date", "ndx"]).sort_values("date")
    pe_work = pe_work.dropna(subset=["date", "pe_ratio"]).sort_values("date")
    if market_work.empty:
        raise ValueError("market frame is empty after cleaning")
    if pe_work.empty:
        raise ValueError("PE frame is empty after cleaning")

    pe_work["pe_pctile"] = _expanding_percentile(pe_work["pe_ratio"])
    pe_work["pe_expanding_max"] = pe_work["pe_ratio"].cummax()

    merged = pd.merge_asof(
        market_work,
        pe_work[["date", "pe_ratio", "pe_pctile", "pe_expanding_max"]],
        on="date",
        direction="backward",
    )
    merged = merged.dropna(subset=["pe_ratio", "pe_pctile"]).copy()
    if merged.empty:
        raise ValueError("no overlapping market/PE history after merge")
    return merged.set_index("date")
