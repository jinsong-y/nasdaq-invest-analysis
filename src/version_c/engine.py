from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import (
    BUY_THRESHOLD,
    DAILY_BUDGET,
    DOUBLE_BUY_BUDGET,
    DOUBLE_BUY_THRESHOLD,
    FULL_EXIT_THRESHOLD,
    NEAR_PEAK_RATIO,
    SELL_THRESHOLD,
)


@dataclass
class BacktestResult:
    run_id: str
    daily: pd.DataFrame


def run_pe_strategy(
    df: pd.DataFrame,
    *,
    run_id: str,
    price_column: str = "ndx",
    daily_budget: float = DAILY_BUDGET,
    buy_budget: float = DAILY_BUDGET,
    double_buy_budget: float = DOUBLE_BUY_BUDGET,
    buy_threshold: float = BUY_THRESHOLD,
    double_buy_threshold: float = DOUBLE_BUY_THRESHOLD,
    sell_threshold: float = SELL_THRESHOLD,
    full_exit_threshold: float = FULL_EXIT_THRESHOLD,
    near_peak_ratio: float = NEAR_PEAK_RATIO,
) -> BacktestResult:
    required = {price_column, "pe_ratio", "pe_pctile"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing required strategy columns: {sorted(missing)}")

    work = df.copy()
    if "pe_expanding_max" not in work.columns:
        work["pe_expanding_max"] = pd.to_numeric(work["pe_ratio"], errors="coerce").cummax()
    work = work.dropna(subset=[price_column, "pe_ratio", "pe_pctile", "pe_expanding_max"]).copy()
    if work.empty:
        raise ValueError("cannot backtest an empty frame")

    cash = 0.0
    shares = 0.0
    trim_80_done = False
    trim_90_done = False
    rows: list[dict] = []

    for date, row in work.iterrows():
        price = float(row[price_column])
        pe_ratio = float(row["pe_ratio"])
        pe_pctile = float(row["pe_pctile"])
        pe_peak = float(row["pe_expanding_max"])
        cash += daily_budget

        if pe_pctile < buy_threshold:
            trim_80_done = False
            trim_90_done = False

        invested = 0.0
        sold_value = 0.0
        state = "pause"

        if pe_pctile >= 0.98 and pe_ratio >= pe_peak * near_peak_ratio and shares > 0:
            sold_value = shares * price
            shares = 0.0
            state = "clear_peak"
        elif pe_pctile >= full_exit_threshold and shares > 0:
            if not trim_90_done:
                sold_shares = shares * 0.30
                shares -= sold_shares
                sold_value = sold_shares * price
                trim_90_done = True
                state = "trim_90"
            else:
                sold_value = shares * price
                shares = 0.0
                state = "clear_90"
        elif pe_pctile >= sell_threshold and shares > 0 and not trim_80_done:
            sold_shares = shares * 0.30
            shares -= sold_shares
            sold_value = sold_shares * price
            trim_80_done = True
            state = "trim_80"
        elif pe_pctile < double_buy_threshold:
            invested = min(cash, double_buy_budget)
            shares += invested / price if price > 0 else 0.0
            cash -= invested
            state = "double_buy"
        elif pe_pctile < buy_threshold:
            invested = min(cash, buy_budget)
            shares += invested / price if price > 0 else 0.0
            cash -= invested
            state = "normal_buy"

        cash += sold_value
        rows.append(
            {
                "date": date,
                "price": price,
                "pe_ratio": pe_ratio,
                "pe_pctile": pe_pctile,
                "pe_expanding_max": pe_peak,
                "state": state,
                "invested": invested,
                "sold_value": sold_value,
                "cash": cash,
                "shares": shares,
                "portfolio_value": cash + shares * price,
            }
        )

    daily = pd.DataFrame(rows).set_index("date")
    return BacktestResult(run_id=run_id, daily=daily)


def run_mechanical_baseline(
    df: pd.DataFrame,
    *,
    run_id: str,
    price_column: str = "ndx",
    daily_budget: float = DAILY_BUDGET,
) -> BacktestResult:
    work = df.dropna(subset=[price_column]).copy()
    if work.empty:
        raise ValueError("cannot backtest an empty frame")
    prices = pd.to_numeric(work[price_column], errors="coerce").to_numpy(dtype=float)
    shares = np.cumsum(np.where(prices > 0, daily_budget / prices, 0.0))
    invested = np.full(len(work), daily_budget, dtype=float)
    daily = pd.DataFrame(
        {
            "price": prices,
            "state": ["baseline"] * len(work),
            "invested": invested,
            "sold_value": np.zeros(len(work), dtype=float),
            "cash": np.zeros(len(work), dtype=float),
            "shares": shares,
            "portfolio_value": shares * prices,
        },
        index=pd.Index(work.index, name="date"),
    )
    return BacktestResult(run_id=run_id, daily=daily)
