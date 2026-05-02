from __future__ import annotations

import numpy as np

from .config import DAILY_BUDGET
from .engine import BacktestResult


def max_drawdown(values) -> float:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return 0.0
    peaks = np.maximum.accumulate(arr)
    drawdowns = arr / peaks - 1.0
    return float(np.nanmin(drawdowns))


def summarize_run(result: BacktestResult, *, daily_budget: float = DAILY_BUDGET) -> dict:
    daily = result.daily
    if daily.empty:
        return {
            "run_id": result.run_id,
            "days": 0,
            "total_contributed": 0.0,
            "total_bought": 0.0,
            "total_sold": 0.0,
            "cash": 0.0,
            "shares": 0.0,
            "terminal_value": 0.0,
            "roi": 0.0,
            "max_drawdown": 0.0,
        }

    total_contributed = float(len(daily) * daily_budget)
    terminal_value = float(daily["portfolio_value"].iloc[-1])
    return {
        "run_id": result.run_id,
        "days": int(len(daily)),
        "total_contributed": total_contributed,
        "total_bought": float(daily["invested"].sum()),
        "total_sold": float(daily["sold_value"].sum()),
        "cash": float(daily["cash"].iloc[-1]),
        "shares": float(daily["shares"].iloc[-1]),
        "terminal_value": terminal_value,
        "roi": terminal_value / total_contributed - 1.0 if total_contributed else 0.0,
        "max_drawdown": max_drawdown(daily["portfolio_value"]),
    }
