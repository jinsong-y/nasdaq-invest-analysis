#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DAILY = ROOT / "reports" / "market_regime" / "daily_regimes.csv"
DEFAULT_OUTPUT = ROOT / "reports" / "market_regime_evaluation"
FORWARD_HORIZONS = {21: "1m", 63: "3m", 126: "6m", 252: "12m"}
KNOWN_DATES = (
    "2011-08-08",
    "2015-08-24",
    "2018-12-24",
    "2020-02-19",
    "2020-03-16",
    "2021-11-19",
    "2022-01-03",
    "2022-10-14",
    "2024-07-10",
    "2026-04-30",
)

REQUIRED_COLUMNS = {"date", "market_regime", "ndx"}
REGIME_LABEL_COLUMNS = {"date", "market_regime"}


def _validate_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label} missing required columns: {sorted(missing)}")


def _prepare_daily(df: pd.DataFrame) -> pd.DataFrame:
    _validate_columns(df, REQUIRED_COLUMNS, "daily regime data")
    daily = df.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    daily["ndx"] = pd.to_numeric(daily["ndx"], errors="coerce")
    daily = daily.sort_values("date").reset_index(drop=True)
    return daily


def _prepare_regime_labels(df: pd.DataFrame) -> pd.DataFrame:
    _validate_columns(df, REGIME_LABEL_COLUMNS, "regime label data")
    labels = df.copy()
    labels["date"] = pd.to_datetime(labels["date"])
    return labels.sort_values("date").reset_index(drop=True)


def merge_previous_regimes(current: pd.DataFrame, previous: pd.DataFrame) -> pd.DataFrame:
    """Attach prior regime labels for classification-change analysis."""
    current_daily = _prepare_daily(current)
    previous_daily = _prepare_regime_labels(previous)
    previous_labels = previous_daily[["date", "market_regime"]].rename(
        columns={"market_regime": "previous_market_regime"}
    )
    return current_daily.merge(previous_labels, on="date", how="left")


def _forward_max_drawdown(prices: pd.Series, horizon: int) -> pd.Series:
    values = []
    for idx, start_price in enumerate(prices):
        if pd.isna(start_price) or idx + horizon >= len(prices):
            values.append(pd.NA)
            continue
        window = prices.iloc[idx + 1 : idx + horizon + 1].dropna()
        if window.empty:
            values.append(pd.NA)
            continue
        peak = start_price
        max_drawdown = 0.0
        for price in window:
            peak = max(peak, price)
            max_drawdown = min(max_drawdown, (price / peak) - 1.0)
        values.append(max_drawdown)
    return pd.Series(values, index=prices.index, dtype="Float64")


def _known_date_rows(daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    date_distances = daily["date"].astype("int64")
    for requested in pd.to_datetime(list(KNOWN_DATES)):
        nearest_idx = (date_distances - requested.value).abs().idxmin()
        row = daily.loc[nearest_idx].copy()
        row["requested_date"] = requested
        row["matched_date"] = row["date"]
        rows.append(row)
    return pd.DataFrame(rows).reset_index(drop=True)


def evaluate_daily_regimes(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    daily = _prepare_daily(df)
    if daily.empty:
        raise ValueError("cannot evaluate empty daily regimes frame")

    for horizon, label in FORWARD_HORIZONS.items():
        daily[f"fwd_{label}"] = (daily["ndx"].shift(-horizon) / daily["ndx"]) - 1.0
    daily["fwd_12m_mdd"] = _forward_max_drawdown(daily["ndx"], 252)

    fwd_columns = [f"fwd_{label}" for label in FORWARD_HORIZONS.values()]
    summary_parts = []
    for regime, group in daily.groupby("market_regime", dropna=False):
        row: dict[str, Any] = {
            "market_regime": regime,
            "days": int(len(group)),
        }
        for column in fwd_columns + ["fwd_12m_mdd"]:
            valid = group[column].dropna()
            row[f"{column}_avg"] = valid.mean() if len(valid) else float("nan")
            row[f"{column}_median"] = valid.median() if len(valid) else float("nan")
        for column in fwd_columns:
            valid = group[column].dropna()
            row[f"{column}_win_rate"] = (valid > 0).mean() if len(valid) else float("nan")
        summary_parts.append(row)
    regime_summary = pd.DataFrame(summary_parts).sort_values(
        ["days", "market_regime"], ascending=[False, True]
    )

    known_dates = _known_date_rows(daily)

    if "previous_market_regime" in daily.columns:
        compared = daily[daily["previous_market_regime"].notna()].copy()
        classification_changes = compared[
            compared["market_regime"] != compared["previous_market_regime"]
        ].copy()
    else:
        classification_changes = pd.DataFrame(
            columns=["date", "previous_market_regime", "market_regime"]
        )

    return {
        "daily_with_forward": daily,
        "regime_summary": regime_summary,
        "known_dates": known_dates,
        "classification_changes": classification_changes,
    }


def _json_summary(result: dict[str, pd.DataFrame]) -> dict[str, Any]:
    daily = result["daily_with_forward"]
    changes = result["classification_changes"]
    start_date = daily["date"].min()
    end_date = daily["date"].max()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "daily_rows": int(len(daily)),
        "start_date": None if pd.isna(start_date) else start_date.date().isoformat(),
        "end_date": None if pd.isna(end_date) else end_date.date().isoformat(),
        "regime_count": int(daily["market_regime"].nunique(dropna=False)),
        "known_date_rows": int(len(result["known_dates"])),
        "classification_change_rows": int(len(changes)),
    }


def _render_html(result: dict[str, pd.DataFrame], summary: dict[str, Any]) -> str:
    regime_html = result["regime_summary"].to_html(index=False, float_format="{:.4f}".format)
    known_html = result["known_dates"].to_html(index=False, float_format="{:.4f}".format)
    changes_html = result["classification_changes"].to_html(
        index=False, float_format="{:.4f}".format
    )
    title = "Market Regime Historical Evaluation"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #1f2933; }}
    h1, h2 {{ line-height: 1.2; }}
    table {{ border-collapse: collapse; width: 100%; margin: 16px 0 32px; font-size: 14px; }}
    th, td {{ border: 1px solid #d9e2ec; padding: 8px 10px; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
    th {{ background: #f0f4f8; }}
    .meta {{ color: #52606d; }}
  </style>
</head>
<body>
  <h1>{escape(title)}</h1>
  <p class="meta">Generated at {escape(str(summary["generated_at"]))}. Rows: {summary["daily_rows"]}.</p>
  <h2>Regime Summary</h2>
  {regime_html}
  <h2>Known Dates</h2>
  {known_html}
  <h2>Classification Changes</h2>
  {changes_html}
</body>
</html>
"""


def write_evaluation_outputs(output_dir: Path, result: dict[str, pd.DataFrame]) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result["daily_with_forward"].to_csv(output_dir / "daily_with_forward.csv", index=False)
    result["regime_summary"].to_csv(output_dir / "regime_summary.csv", index=False)
    result["known_dates"].to_csv(output_dir / "known_dates.csv", index=False)
    result["classification_changes"].to_csv(
        output_dir / "classification_changes.csv", index=False
    )

    summary = _json_summary(result)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "index.html").write_text(
        _render_html(result, summary),
        encoding="utf-8",
    )


def run_workflow(
    daily_path: Path = DEFAULT_DAILY,
    output_dir: Path = DEFAULT_OUTPUT,
    previous_daily_path: Path | None = None,
) -> dict[str, pd.DataFrame]:
    daily_path = Path(daily_path)
    output_dir = Path(output_dir)
    if not daily_path.exists():
        raise FileNotFoundError(f"daily regime file not found: {daily_path}")

    daily = pd.read_csv(daily_path)
    if previous_daily_path is not None:
        previous_daily_path = Path(previous_daily_path)
        if not previous_daily_path.exists():
            raise FileNotFoundError(f"previous daily regime file not found: {previous_daily_path}")
        daily = merge_previous_regimes(daily, pd.read_csv(previous_daily_path))

    result = evaluate_daily_regimes(daily)
    write_evaluation_outputs(output_dir, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily-path", type=Path, default=DEFAULT_DAILY)
    parser.add_argument("--previous-daily-path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run_workflow(
        daily_path=args.daily_path,
        output_dir=args.output_dir,
        previous_daily_path=args.previous_daily_path,
    )
    print(f"Wrote market regime evaluation to {args.output_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
