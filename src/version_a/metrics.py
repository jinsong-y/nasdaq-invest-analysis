from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SEGMENTS
from .engine import BacktestResult


def max_drawdown(values) -> float:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return 0.0
    peaks = np.maximum.accumulate(arr)
    drawdowns = arr / peaks - 1.0
    return float(np.nanmin(drawdowns))


def summarize_frame(daily: pd.DataFrame) -> dict:
    if daily.empty:
        return {
            "total_invested": 0.0,
            "shares": 0.0,
            "cash": 0.0,
            "terminal_value": 0.0,
            "average_cost": float("nan"),
            "roi": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
            "cash_idle_ratio": 0.0,
            "buy_window_count": 0,
            "pause_window_count": 0,
        }
    total_invested = float(daily["invested"].sum())
    shares = float(daily["shares"].iloc[-1])
    cash = float(daily["cash"].iloc[-1])
    terminal_value = float(daily["portfolio_value"].iloc[-1])
    average_cost = total_invested / shares if shares else float("nan")
    roi = terminal_value / total_invested - 1.0 if total_invested else 0.0
    mdd = max_drawdown(daily["portfolio_value"])
    years = max((daily.index[-1] - daily.index[0]).days / 365.25, 1e-9)
    annualized_return = (1.0 + roi) ** (1.0 / years) - 1.0 if roi > -1 else -1.0
    calmar = annualized_return / abs(mdd) if mdd else annualized_return
    return {
        "total_invested": total_invested,
        "shares": shares,
        "cash": cash,
        "terminal_value": terminal_value,
        "average_cost": average_cost,
        "roi": roi,
        "max_drawdown": mdd,
        "calmar": calmar,
        "cash_idle_ratio": float(daily["cash"].mean() / max(daily["portfolio_value"].mean(), 1e-9)),
        "buy_window_count": int(daily["state"].isin(["light_buy", "standard_buy", "deep_buy"]).sum()),
        "pause_window_count": int((daily["state"] == "pause").sum()),
    }


def summarize_run(result: BacktestResult) -> dict:
    summary = {"run_id": result.run_id}
    summary.update(summarize_frame(result.daily))
    for name, (start, end) in SEGMENTS.items():
        segment = result.daily[result.daily.index >= pd.Timestamp(start)]
        if end is not None:
            segment = segment[segment.index <= pd.Timestamp(end)]
        segment_summary = summarize_frame(segment)
        summary[f"{name}_roi"] = segment_summary["roi"]
        summary[f"{name}_max_drawdown"] = segment_summary["max_drawdown"]
    return summary
