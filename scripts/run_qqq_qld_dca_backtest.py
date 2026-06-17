#!/usr/bin/env python3
"""Compare daily DCA into QQQ vs QLD (2x leveraged QQQ) over 20/10/5/3 years.

Uses NDX index data as proxy for QQQ (1:1 tracking). QLD is simulated via
2x daily returns with daily compounding (rebalancing). Daily investment = $300.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA_PATH = ROOT / "data" / "processed" / "market_indicators.csv"
OUTPUT_DIR = ROOT / "reports" / "qqq_vs_qld_dca"


def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, parse_dates=["date"])
    df = df[["date", "ndx"]].dropna().sort_values("date").reset_index(drop=True)
    df["daily_ret"] = df["ndx"].pct_change()
    df = df.dropna().reset_index(drop=True)
    return df


def simulate_dca(df: pd.DataFrame, start_date: str, daily_invest: float = 300.0) -> dict:
    """Run daily DCA for QQQ and QLD from start_date to end of data."""
    sub = df[df["date"] >= start_date].copy().reset_index(drop=True)
    if len(sub) < 2:
        return None

    # QQQ: accumulate shares at daily price (normalize NDX to start at 1)
    qqq_price = sub["ndx"].values / sub["ndx"].values[0]
    # QLD: 2x daily returns, compounded
    qld_ret = sub["daily_ret"].values * 2
    qld_price = np.cumprod(1 + qld_ret)
    qld_price[0] = 1.0  # normalize start

    # Daily DCA: buy shares each day
    qqq_shares = 0.0
    qld_shares = 0.0
    total_invested = 0.0
    n_days = len(sub)

    for i in range(n_days):
        total_invested += daily_invest
        qqq_shares += daily_invest / qqq_price[i]
        qld_shares += daily_invest / qld_price[i]

    qqq_final_value = qqq_shares * qqq_price[-1]
    qld_final_value = qld_shares * qld_price[-1]

    qqq_return_pct = (qqq_final_value / total_invested - 1) * 100
    qld_return_pct = (qld_final_value / total_invested - 1) * 100

    # Max drawdown for portfolio value over time
    qqq_cum_values = []
    qld_cum_values = []
    qqq_s = 0.0
    qld_s = 0.0
    for i in range(n_days):
        qqq_s += daily_invest
        qld_s += daily_invest
        # Current value = shares held * current price (approx: invested so far + return)
        qqq_cum_values.append(qqq_shares * qqq_price[i] if i == n_days - 1 else
                              sum(daily_invest / qqq_price[j] * qqq_price[i] for j in range(i + 1)))
        qld_cum_values.append(qld_shares * qld_price[i] if i == n_days - 1 else
                              sum(daily_invest / qld_price[j] * qld_price[i] for j in range(i + 1)))

    # Simpler max drawdown: track portfolio value day by day
    qqq_vals = np.zeros(n_days)
    qld_vals = np.zeros(n_days)
    qqq_cum_shares = 0.0
    qld_cum_shares = 0.0
    qqq_cum_invested = 0.0
    qld_cum_invested = 0.0
    for i in range(n_days):
        qqq_cum_shares += daily_invest / qqq_price[i]
        qld_cum_shares += daily_invest / qld_price[i]
        qqq_cum_invested += daily_invest
        qld_cum_invested += daily_invest
        qqq_vals[i] = qqq_cum_shares * qqq_price[i]
        qld_vals[i] = qld_cum_shares * qld_price[i]

    def max_drawdown(vals):
        peak = vals[0]
        mdd = 0.0
        for v in vals:
            if v > peak:
                peak = v
            dd = (peak - v) / peak
            if dd > mdd:
                mdd = dd
        return mdd * 100

    # Annualized return (simple: based on total return and years)
    years = n_days / 252
    qqq_annual = ((qqq_final_value / total_invested) ** (1 / years) - 1) * 100 if years > 0 else 0
    qld_annual = ((qld_final_value / total_invested) ** (1 / years) - 1) * 100 if years > 0 else 0

    return {
        "start": sub["date"].iloc[0].strftime("%Y-%m-%d"),
        "end": sub["date"].iloc[-1].strftime("%Y-%m-%d"),
        "trading_days": n_days,
        "years": round(years, 1),
        "total_invested": round(total_invested, 2),
        "qqq_final_value": round(qqq_final_value, 2),
        "qld_final_value": round(qld_final_value, 2),
        "qqq_return_pct": round(qqq_return_pct, 2),
        "qld_return_pct": round(qld_return_pct, 2),
        "qqq_annual_pct": round(qqq_annual, 2),
        "qld_annual_pct": round(qld_annual, 2),
        "qqq_max_drawdown_pct": round(max_drawdown(qqq_vals), 2),
        "qld_max_drawdown_pct": round(max_drawdown(qld_vals), 2),
        "qld_vs_qqq_diff": round(qld_final_value - qqq_final_value, 2),
        "qld_vs_qqq_diff_pct": round(qld_return_pct - qqq_return_pct, 2),
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = load_data()
    latest = df["date"].iloc[-1]
    print(f"Data range: {df['date'].iloc[0].date()} ~ {latest.date()}")
    print(f"Daily DCA amount: $300\n")

    # Define periods: 20, 10, 5, 3 years from latest date
    periods = {}
    for years in [20, 10, 5, 3]:
        start = latest - pd.DateOffset(years=years)
        # Find nearest trading day
        mask = df["date"] >= start
        if mask.any():
            start_date = df.loc[mask, "date"].iloc[0]
            periods[f"{years}Y"] = start_date.strftime("%Y-%m-%d")

    results = []
    for label, start_date in periods.items():
        r = simulate_dca(df, start_date, daily_invest=300)
        if r:
            r["period"] = label
            results.append(r)

    # Print results table
    print("=" * 100)
    print(f"{'Period':<8} {'Range':<25} {'Days':>6} {'Invested':>14} "
          f"{'QQQ Value':>14} {'QQQ Ret%':>10} {'QQQ Ann%':>10} "
          f"{'QLD Value':>14} {'QLD Ret%':>10} {'QLD Ann%':>10} "
          f"{'Diff($)':>14} {'Diff(%)':>10}")
    print("-" * 100)

    for r in results:
        print(f"{r['period']:<8} {r['start']}~{r['end']}  {r['trading_days']:>6} "
              f"${r['total_invested']:>12,.0f} "
              f"${r['qqq_final_value']:>12,.0f} {r['qqq_return_pct']:>9.1f}% {r['qqq_annual_pct']:>9.1f}% "
              f"${r['qld_final_value']:>12,.0f} {r['qld_return_pct']:>9.1f}% {r['qld_annual_pct']:>9.1f}% "
              f"${r['qld_vs_qqq_diff']:>12,.0f} {r['qld_vs_qqq_diff_pct']:>9.1f}%")

    print("=" * 100)

    # Max drawdown summary
    print(f"\n{'Period':<8} {'QQQ MaxDD%':>12} {'QLD MaxDD%':>12}")
    print("-" * 35)
    for r in results:
        print(f"{r['period']:<8} {r['qqq_max_drawdown_pct']:>11.1f}% {r['qld_max_drawdown_pct']:>11.1f}%")

    # Save to CSV
    df_results = pd.DataFrame(results)
    cols = ["period", "start", "end", "trading_days", "years",
            "total_invested", "qqq_final_value", "qld_final_value",
            "qqq_return_pct", "qld_return_pct",
            "qqq_annual_pct", "qld_annual_pct",
            "qqq_max_drawdown_pct", "qld_max_drawdown_pct",
            "qld_vs_qqq_diff", "qld_vs_qqq_diff_pct"]
    df_results = df_results[cols]
    csv_path = OUTPUT_DIR / "qqq_vs_qld_dca_results.csv"
    df_results.to_csv(csv_path, index=False)
    print(f"\nResults saved to: {csv_path}")


if __name__ == "__main__":
    main()
