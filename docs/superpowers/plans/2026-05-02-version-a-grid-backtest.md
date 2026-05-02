# Version A Grid Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run the Version A Nasdaq DCA parameter-grid backtest, persist every evaluated parameter combination, and render a static two-layer HTML report.

**Architecture:** Create a focused Python package under `src/version_a/` with separate modules for data loading, feature generation, scoring/backtesting, grid orchestration, metric calculation, and HTML reporting. The command-line runner reads `data/processed/market_indicators.csv`, writes structured results to `reports/version_a/`, then builds `index.html` and per-run detail pages. Tests use small in-memory DataFrames and generated temporary files to verify behavior before implementation.

**Tech Stack:** Python 3.9+, pandas, numpy, standard library `unittest`, standard library `html`/file IO for report generation.

---

## File Structure

- Create: `src/version_a/__init__.py`  
  Package marker.
- Create: `src/version_a/config.py`  
  Dataclasses for parameters, constants, grid definitions, and segment windows.
- Create: `src/version_a/data.py`  
  Load and validate the local indicator CSV.
- Create: `src/version_a/features.py`  
  Add rolling SMA, percentiles, moving averages, and repair/divergence helper columns.
- Create: `src/version_a/engine.py`  
  Compute Buy/Sell scores, run the stateful daily backtest, and emit run details.
- Create: `src/version_a/metrics.py`  
  Compute run-level and segment-level metrics.
- Create: `src/version_a/grid.py`  
  Generate coarse/refined/robustness parameter networks and execute them.
- Create: `src/version_a/report.py`  
  Generate static HTML overview and detail pages without remote assets.
- Create: `scripts/run_version_a_backtest.py`  
  CLI entry point for the full workflow.
- Create: `tests/test_version_a.py`  
  Unit and integration tests for the Version A system.
- Modify: `docs/DATA_INVENTORY.md`  
  Add a link to the generated report after the first successful run.

---

### Task 1: Config And Parameter Model

**Files:**
- Create: `src/version_a/__init__.py`
- Create: `src/version_a/config.py`
- Test: `tests/test_version_a.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to `tests/test_version_a.py`:

```python
import unittest

from src.version_a.config import (
    BacktestParams,
    coarse_grid,
    MAIN_START,
    BASELINE_START,
)


class VersionAConfigTests(unittest.TestCase):
    def test_coarse_grid_has_expected_size_and_defaults(self):
        grid = list(coarse_grid())
        self.assertEqual(8748, len(grid))
        self.assertTrue(all(isinstance(item, BacktestParams) for item in grid))
        self.assertEqual({2}, {item.lag_days for item in grid})
        self.assertEqual({10}, {item.standard_buy_window_days for item in grid})
        self.assertEqual({20}, {item.deep_buy_window_days for item in grid})
        self.assertEqual({15}, {item.pause_window_days for item in grid})

    def test_required_windows_are_explicit(self):
        self.assertEqual("2000-01-03", BASELINE_START)
        self.assertEqual("2011-01-03", MAIN_START)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
python3 -m unittest tests/test_version_a.py
```

Expected: fails with `ModuleNotFoundError: No module named 'src'`.

- [ ] **Step 3: Implement config**

Create `src/version_a/__init__.py`:

```python
"""Version A Nasdaq DCA grid backtest package."""
```

Create `src/version_a/config.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
from typing import Iterable


BASELINE_START = "2000-01-03"
MAIN_START = "2011-01-03"
BASE_DAILY_BUDGET = 100.0
MAX_BUY_DAILY_BUDGET = 200.0

SEGMENTS = {
    "diagnostic_2000_2010": ("2000-01-03", "2010-12-31"),
    "main_2011_2019": ("2011-01-03", "2019-12-31"),
    "shock_2020": ("2020-01-01", "2020-12-31"),
    "bear_2022": ("2022-01-01", "2022-12-31"),
    "recent_2023_present": ("2023-01-01", None),
}


@dataclass(frozen=True)
class BacktestParams:
    sma_period: int
    sma_buffer_pct: float
    overheat_ratio: float
    vol_high_pctile: float
    cnn_fear_threshold: int
    cnn_greed_threshold: int
    sentiment_lookback_days: int
    repair_ma_days: int
    divergence_weeks: int
    lag_days: int
    standard_buy_window_days: int
    deep_buy_window_days: int
    pause_window_days: int
    strategy_family: str = "v2_full"
    stage: str = "coarse"

    def to_dict(self) -> dict:
        return asdict(self)

    def stable_key(self) -> str:
        values = [
            self.strategy_family,
            self.stage,
            self.sma_period,
            self.sma_buffer_pct,
            self.overheat_ratio,
            self.vol_high_pctile,
            self.cnn_fear_threshold,
            self.cnn_greed_threshold,
            self.sentiment_lookback_days,
            self.repair_ma_days,
            self.divergence_weeks,
            self.lag_days,
            self.standard_buy_window_days,
            self.deep_buy_window_days,
            self.pause_window_days,
        ]
        return "_".join(str(value).replace(".", "p") for value in values)


def coarse_grid() -> Iterable[BacktestParams]:
    for values in product(
        [180, 200, 220],
        [0.03, 0.05, 0.07],
        [1.15, 1.20, 1.25],
        [0.75, 0.80, 0.85, 0.90],
        [20, 25, 30],
        [70, 75, 80],
        [504, 756, 1260],
        [10, 20, 50],
    ):
        yield BacktestParams(
            sma_period=values[0],
            sma_buffer_pct=values[1],
            overheat_ratio=values[2],
            vol_high_pctile=values[3],
            cnn_fear_threshold=values[4],
            cnn_greed_threshold=values[5],
            sentiment_lookback_days=values[6],
            repair_ma_days=values[7],
            divergence_weeks=2,
            lag_days=2,
            standard_buy_window_days=10,
            deep_buy_window_days=20,
            pause_window_days=15,
        )
```

- [ ] **Step 4: Run the test and verify it passes**

Run:

```bash
python3 -m unittest tests/test_version_a.py
```

Expected: `OK`.

---

### Task 2: Data Loading And Feature Generation

**Files:**
- Create: `src/version_a/data.py`
- Create: `src/version_a/features.py`
- Modify: `tests/test_version_a.py`

- [ ] **Step 1: Write the failing tests**

Append these tests:

```python
import pandas as pd

from src.version_a.data import load_market_data
from src.version_a.features import add_features


class VersionADataFeatureTests(unittest.TestCase):
    def test_load_market_data_filters_start_and_validates_columns(self):
        df = load_market_data("data/processed/market_indicators.csv")
        self.assertEqual("2000-01-03", df.index.min().strftime("%Y-%m-%d"))
        self.assertIn("ndx", df.columns)
        self.assertIn("cnn_fear_greed", df.columns)

    def test_add_features_creates_expected_columns(self):
        df = pd.DataFrame(
            {
                "ndx": [100.0, 101.0, 99.0, 103.0, 105.0],
                "vxn": [20.0, 22.0, 25.0, 23.0, 21.0],
                "vix": [18.0, 19.0, 24.0, 21.0, 20.0],
                "ndxe_ndx": [0.30, 0.31, 0.29, 0.32, 0.33],
                "sox_ndx": [0.20, 0.21, 0.19, 0.22, 0.23],
                "cnn_fear_greed": [40.0, 35.0, 20.0, 25.0, 30.0],
            },
            index=pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]),
        )
        out = add_features(df, sma_period=3, sentiment_lookback_days=3, repair_ma_days=2)
        for column in ["sma", "dist_sma", "vxn_pctile", "vix_pctile", "cnn_ma5", "ndxe_ma", "sox_ma"]:
            self.assertIn(column, out.columns)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
python3 -m unittest tests/test_version_a.py
```

Expected: fails importing `src.version_a.data`.

- [ ] **Step 3: Implement data and features**

Create `src/version_a/data.py`:

```python
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import BASELINE_START


REQUIRED_COLUMNS = {"date", "ndx", "vxn", "vix", "ndxe", "sox", "cnn_fear_greed", "ndxe_ndx", "sox_ndx"}


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
```

Create `src/version_a/features.py`:

```python
from __future__ import annotations

import pandas as pd


def rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    def pctile(values):
        current = values[-1]
        if pd.isna(current):
            return float("nan")
        valid = pd.Series(values).dropna()
        if valid.empty:
            return float("nan")
        return float((valid <= current).mean())

    return series.rolling(window=window, min_periods=max(20, min(window, 60))).apply(pctile, raw=True)


def add_features(
    df: pd.DataFrame,
    *,
    sma_period: int,
    sentiment_lookback_days: int,
    repair_ma_days: int,
) -> pd.DataFrame:
    out = df.copy()
    out["sma"] = out["ndx"].rolling(sma_period, min_periods=max(20, min(sma_period, 60))).mean()
    out["dist_sma"] = out["ndx"] / out["sma"] - 1.0
    out["vxn_pctile"] = rolling_percentile(out["vxn"], sentiment_lookback_days)
    out["vix_pctile"] = rolling_percentile(out["vix"], sentiment_lookback_days)
    out["cnn_ma5"] = out["cnn_fear_greed"].rolling(5, min_periods=1).mean()
    out["ndxe_ma"] = out["ndxe_ndx"].rolling(repair_ma_days, min_periods=1).mean()
    out["sox_ma"] = out["sox_ndx"].rolling(repair_ma_days, min_periods=1).mean()
    return out
```

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m unittest tests/test_version_a.py
```

Expected: `OK`.

---

### Task 3: Engine And Metrics

**Files:**
- Create: `src/version_a/engine.py`
- Create: `src/version_a/metrics.py`
- Modify: `tests/test_version_a.py`

- [ ] **Step 1: Write the failing tests**

Append these tests:

```python
from src.version_a.config import BacktestParams
from src.version_a.engine import run_backtest
from src.version_a.metrics import summarize_run


class VersionAEngineTests(unittest.TestCase):
    def test_run_backtest_records_daily_states_and_metrics(self):
        index = pd.date_range("2020-01-01", periods=8, freq="B")
        df = pd.DataFrame(
            {
                "ndx": [100, 98, 96, 99, 102, 103, 101, 104],
                "sma": [100] * 8,
                "dist_sma": [0, -0.02, -0.04, -0.01, 0.02, 0.03, 0.01, 0.04],
                "vxn_pctile": [0.5, 0.8, 0.9, 0.7, 0.5, 0.4, 0.3, 0.2],
                "vix_pctile": [0.5, 0.8, 0.9, 0.7, 0.5, 0.4, 0.3, 0.2],
                "vxn": [20, 30, 35, 28, 22, 20, 19, 18],
                "vix": [18, 25, 30, 24, 20, 18, 17, 16],
                "cnn_fear_greed": [50, 20, 18, 25, 30, 40, 60, 80],
                "cnn_ma5": [50, 35, 29, 28, 29, 31, 35, 47],
                "ndxe_ndx": [0.3, 0.29, 0.28, 0.30, 0.31, 0.32, 0.31, 0.30],
                "sox_ndx": [0.2, 0.19, 0.18, 0.20, 0.21, 0.22, 0.21, 0.20],
                "ndxe_ma": [0.3, 0.295, 0.285, 0.29, 0.305, 0.315, 0.315, 0.305],
                "sox_ma": [0.2, 0.195, 0.185, 0.19, 0.205, 0.215, 0.215, 0.205],
            },
            index=index,
        )
        params = BacktestParams(200, 0.05, 1.2, 0.75, 25, 75, 756, 20, 2, 1, 3, 5, 3)
        result = run_backtest(df, params, run_id="test_run")
        summary = summarize_run(result)
        self.assertEqual("test_run", result.run_id)
        self.assertEqual(len(df), len(result.daily))
        self.assertGreater(summary["total_invested"], 0)
        self.assertIn("roi", summary)
```

- [ ] **Step 2: Run failing test**

Run:

```bash
python3 -m unittest tests/test_version_a.py
```

Expected: fails importing `src.version_a.engine`.

- [ ] **Step 3: Implement engine and metrics**

Create `src/version_a/engine.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import BASE_DAILY_BUDGET, MAX_BUY_DAILY_BUDGET, BacktestParams


@dataclass
class BacktestResult:
    run_id: str
    params: BacktestParams
    daily: pd.DataFrame
    triggers: pd.DataFrame


def _buy_score(row: pd.Series, params: BacktestParams) -> int:
    score = 0
    vol_panic = row.get("vxn_pctile", 0) >= params.vol_high_pctile or row.get("vix_pctile", 0) >= params.vol_high_pctile
    if vol_panic:
        score += 15
    if row.get("vxn", 0) < row.get("vxn_prev", row.get("vxn", 0)) or row.get("vix", 0) < row.get("vix_prev", row.get("vix", 0)):
        score += 15
    if params.strategy_family == "v2_full" and row.get("cnn_fear_greed", 101) <= params.cnn_fear_threshold:
        score += 15
    if params.strategy_family == "v2_full" and row.get("cnn_ma5", 101) > row.get("cnn_ma5_prev", row.get("cnn_ma5", 101)):
        score += 15
    if row.get("ndxe_ndx", 0) > row.get("ndxe_ma", 1):
        score += 15
    if row.get("sox_ndx", 0) > row.get("sox_ma", 1):
        score += 15
    if row.get("ndx", 0) > (1 - params.sma_buffer_pct) * row.get("sma", float("inf")):
        score += 10
    return min(score, 100)


def _sell_score(row: pd.Series, params: BacktestParams) -> int:
    score = 0
    ndx = row.get("ndx", 0)
    sma = row.get("sma", float("inf"))
    if ndx > params.overheat_ratio * sma:
        score += 25
    if params.strategy_family == "v2_full" and row.get("cnn_fear_greed", 0) >= params.cnn_greed_threshold:
        score += 20
    if params.strategy_family == "v2_full" and row.get("cnn_ma5", 0) < row.get("cnn_ma5_prev", row.get("cnn_ma5", 0)):
        score += 10
    if row.get("vxn_pctile", 1) <= 0.2 or row.get("vix_pctile", 1) <= 0.2:
        score += 15
    lookback = max(5, params.divergence_weeks * 5)
    ndx_high = ndx >= row.get(f"ndx_high_{lookback}", ndx)
    if ndx_high and row.get("ndxe_ndx", 0) < row.get("ndxe_ndx_prev", row.get("ndxe_ndx", 0)):
        score += 15
    if ndx_high and row.get("sox_ndx", 0) < row.get("sox_ndx_prev", row.get("sox_ndx", 0)):
        score += 15
    return min(score, 100)


def _state_from_scores(buy_score: int, sell_score: int) -> tuple[str, int]:
    if sell_score > 75:
        return "pause", 20
    if sell_score > 60:
        return "pause", 10
    if sell_score >= 40:
        return "slowdown", 10
    if buy_score > 75:
        return "deep_buy", 20
    if buy_score >= 60:
        return "standard_buy", 10
    if buy_score >= 40:
        return "light_buy", 5
    return "normal", 1


def run_backtest(df: pd.DataFrame, params: BacktestParams, *, run_id: str) -> BacktestResult:
    work = df.copy()
    for column in ["vxn", "vix", "cnn_ma5", "ndxe_ndx", "sox_ndx"]:
        work[f"{column}_prev"] = work[column].shift(1)
    for weeks in [1, 2, 3]:
        days = weeks * 5
        work[f"ndx_high_{days}"] = work["ndx"].rolling(days, min_periods=1).max()

    signal_queue: list[tuple[pd.Timestamp, str, int, int, int]] = []
    state = "normal"
    state_days_left = 0
    cash = 0.0
    shares = 0.0
    records = []
    triggers = []

    dates = list(work.index)
    for idx, date in enumerate(dates):
        row = work.loc[date]
        buy_score = _buy_score(row, params)
        sell_score = _sell_score(row, params)
        desired_state, desired_days = _state_from_scores(buy_score, sell_score)
        execution_idx = idx + params.lag_days
        if execution_idx < len(dates):
            signal_queue.append((dates[execution_idx], desired_state, desired_days, buy_score, sell_score))

        due = [item for item in signal_queue if item[0] == date]
        if state_days_left <= 0 and due:
            _, state, state_days_left, queued_buy, queued_sell = due[-1]
            triggers.append({"date": date, "state": state, "buy_score": queued_buy, "sell_score": queued_sell})

        cash += BASE_DAILY_BUDGET
        if state == "pause":
            invest = 0.0
        elif state == "slowdown":
            invest = min(cash, BASE_DAILY_BUDGET / 2)
        elif state in {"light_buy", "standard_buy", "deep_buy"}:
            invest = min(cash, MAX_BUY_DAILY_BUDGET)
        else:
            invest = min(cash, BASE_DAILY_BUDGET)

        price = float(row["ndx"])
        bought = invest / price if price > 0 else 0.0
        shares += bought
        cash -= invest
        value = shares * price + cash
        records.append(
            {
                "date": date,
                "price": price,
                "state": state,
                "buy_score": buy_score,
                "sell_score": sell_score,
                "invested": invest,
                "cash": cash,
                "shares": shares,
                "portfolio_value": value,
            }
        )
        state_days_left -= 1

    daily = pd.DataFrame(records).set_index("date")
    trigger_frame = pd.DataFrame(triggers)
    return BacktestResult(run_id=run_id, params=params, daily=daily, triggers=trigger_frame)
```

Create `src/version_a/metrics.py` with:

```python
from __future__ import annotations

import numpy as np

from .engine import BacktestResult


def max_drawdown(values) -> float:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return 0.0
    peaks = np.maximum.accumulate(arr)
    drawdowns = arr / peaks - 1.0
    return float(drawdowns.min())


def summarize_run(result: BacktestResult) -> dict:
    daily = result.daily
    total_invested = float(daily["invested"].sum())
    shares = float(daily["shares"].iloc[-1])
    cash = float(daily["cash"].iloc[-1])
    terminal_value = float(daily["portfolio_value"].iloc[-1])
    average_cost = total_invested / shares if shares else float("nan")
    roi = terminal_value / total_invested - 1.0 if total_invested else 0.0
    mdd = max_drawdown(daily["portfolio_value"])
    years = max((daily.index[-1] - daily.index[0]).days / 365.25, 1e-9)
    calmar = roi / abs(mdd) / years if mdd else roi / years
    return {
        "run_id": result.run_id,
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
```

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m unittest tests/test_version_a.py
```

Expected: `OK`.

---

### Task 4: Grid Runner And Result Persistence

**Files:**
- Create: `src/version_a/grid.py`
- Modify: `tests/test_version_a.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
from tempfile import TemporaryDirectory
from pathlib import Path

from src.version_a.grid import write_run_outputs, rank_summaries


class VersionAGridTests(unittest.TestCase):
    def test_rank_summaries_adds_composite_score(self):
        rows = [
            {"run_id": "a", "roi": 0.10, "calmar": 0.2, "excess_return": 0.03, "cost_improvement": 0.02, "lag_robustness": 0.9},
            {"run_id": "b", "roi": 0.20, "calmar": 0.1, "excess_return": 0.01, "cost_improvement": 0.01, "lag_robustness": 0.7},
        ]
        ranked = rank_summaries(rows)
        self.assertIn("composite_score", ranked[0])
        self.assertEqual(2, len(ranked))

    def test_write_run_outputs_creates_csv_and_json(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_run_outputs(out, [{"run_id": "x", "roi": 0.1}], [{"run_id": "x", "date": "2020-01-01", "state": "normal"}])
            self.assertTrue((out / "summary.csv").exists())
            self.assertTrue((out / "summary.json").exists())
            self.assertTrue((out / "runs.csv").exists())
            self.assertTrue((out / "runs.json").exists())
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
python3 -m unittest tests/test_version_a.py
```

Expected: fails importing `src.version_a.grid`.

- [ ] **Step 3: Implement grid helpers**

Create `src/version_a/grid.py`:

```python
from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd


def _percent_rank(values: pd.Series) -> pd.Series:
    return values.rank(pct=True, method="average").fillna(0.0)


def rank_summaries(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    df = pd.DataFrame(rows)
    for column in ["roi", "calmar", "excess_return", "cost_improvement", "lag_robustness"]:
        if column not in df:
            df[column] = 0.0
    df["composite_score"] = (
        30 * _percent_rank(df["roi"])
        + 25 * _percent_rank(df["calmar"])
        + 20 * _percent_rank(df["excess_return"])
        + 15 * _percent_rank(df["cost_improvement"])
        + 10 * _percent_rank(df["lag_robustness"])
    )
    df = df.sort_values(["composite_score", "roi"], ascending=False)
    return df.to_dict(orient="records")


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_run_outputs(output_dir: Path, summary_rows: list[dict], run_rows: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ranked = rank_summaries(summary_rows)
    _write_csv(output_dir / "summary.csv", ranked)
    _write_csv(output_dir / "runs.csv", run_rows)
    (output_dir / "summary.json").write_text(json.dumps(ranked, indent=2, default=str), encoding="utf-8")
    (output_dir / "runs.json").write_text(json.dumps(run_rows, indent=2, default=str), encoding="utf-8")
```

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m unittest tests/test_version_a.py
```

Expected: `OK`.

---

### Task 5: HTML Report

**Files:**
- Create: `src/version_a/report.py`
- Modify: `tests/test_version_a.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
from src.version_a.report import build_report


class VersionAReportTests(unittest.TestCase):
    def test_build_report_writes_overview_and_detail_pages(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            build_report(
                out,
                summaries=[{"run_id": "run_a", "composite_score": 91.2, "roi": 0.2, "max_drawdown": -0.1}],
                run_details={"run_a": [{"date": "2020-01-01", "portfolio_value": 1000, "state": "normal"}]},
            )
            self.assertTrue((out / "index.html").exists())
            self.assertTrue((out / "runs" / "run_a.html").exists())
            self.assertIn("run_a", (out / "index.html").read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
python3 -m unittest tests/test_version_a.py
```

Expected: fails importing `src.version_a.report`.

- [ ] **Step 3: Implement static report generation**

Create `src/version_a/report.py`:

```python
from __future__ import annotations

from html import escape
from pathlib import Path


CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:0;background:#f7f7f5;color:#181818}
main{max-width:1180px;margin:0 auto;padding:32px}
table{border-collapse:collapse;width:100%;background:white}
th,td{border-bottom:1px solid #ddd;padding:8px;text-align:right}
th:first-child,td:first-child{text-align:left}
a{color:#0b5cad}
.card{background:white;border:1px solid #ddd;border-radius:8px;padding:16px;margin:16px 0}
"""


def _page(title: str, body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{escape(title)}</title><style>{CSS}</style></head><body><main>{body}</main></body></html>"


def build_report(output_dir: Path, *, summaries: list[dict], run_details: dict[str, list[dict]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_dir = output_dir / "runs"
    detail_dir.mkdir(exist_ok=True)
    rows = []
    for item in summaries[:200]:
        run_id = str(item["run_id"])
        rows.append(
            "<tr>"
            f"<td><a href='runs/{escape(run_id)}.html'>{escape(run_id)}</a></td>"
            f"<td>{float(item.get('composite_score', 0)):.2f}</td>"
            f"<td>{float(item.get('roi', 0)):.2%}</td>"
            f"<td>{float(item.get('max_drawdown', 0)):.2%}</td>"
            "</tr>"
        )
        detail_rows = "".join(
            f"<tr><td>{escape(str(row.get('date','')))}</td><td>{escape(str(row.get('state','')))}</td><td>{float(row.get('portfolio_value',0)):.2f}</td></tr>"
            for row in run_details.get(run_id, [])[:500]
        )
        detail_body = (
            f"<p><a href='../index.html'>Back to overview</a></p><h1>{escape(run_id)}</h1>"
            "<div class='card'><table><thead><tr><th>Date</th><th>State</th><th>Portfolio Value</th></tr></thead>"
            f"<tbody>{detail_rows}</tbody></table></div>"
        )
        (detail_dir / f"{run_id}.html").write_text(_page(run_id, detail_body), encoding="utf-8")
    body = (
        "<h1>Version A Grid Backtest</h1>"
        "<div class='card'><table><thead><tr><th>Run</th><th>Composite</th><th>ROI</th><th>MDD</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )
    (output_dir / "index.html").write_text(_page("Version A Grid Backtest", body), encoding="utf-8")
```

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m unittest tests/test_version_a.py
```

Expected: `OK`.

---

### Task 6: Full CLI Workflow

**Files:**
- Create: `scripts/run_version_a_backtest.py`
- Modify: `tests/test_version_a.py`
- Modify: `docs/DATA_INVENTORY.md`

- [ ] **Step 1: Write failing integration test**

Append:

```python
from scripts.run_version_a_backtest import run_workflow


class VersionAWorkflowTests(unittest.TestCase):
    def test_run_workflow_smoke_writes_report(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            run_workflow(output_dir=out, max_runs=3)
            self.assertTrue((out / "summary.csv").exists())
            self.assertTrue((out / "runs.csv").exists())
            self.assertTrue((out / "index.html").exists())
            self.assertGreater((out / "summary.csv").stat().st_size, 0)
```

- [ ] **Step 2: Run failing test**

Run:

```bash
python3 -m unittest tests/test_version_a.py
```

Expected: fails importing `scripts.run_version_a_backtest`.

- [ ] **Step 3: Implement workflow**

Create `scripts/run_version_a_backtest.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from src.version_a.config import MAIN_START, coarse_grid
from src.version_a.data import load_market_data
from src.version_a.engine import run_backtest
from src.version_a.features import add_features
from src.version_a.grid import rank_summaries, write_run_outputs
from src.version_a.metrics import summarize_run
from src.version_a.report import build_report


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "processed" / "market_indicators.csv"
DEFAULT_OUTPUT = ROOT / "reports" / "version_a"


def run_workflow(output_dir: Path = DEFAULT_OUTPUT, max_runs: int | None = None) -> None:
    raw = load_market_data(DATA_PATH)
    params_list = list(coarse_grid())
    if max_runs is not None:
        params_list = params_list[:max_runs]
    baseline_source = raw[raw.index >= MAIN_START].copy()

    summaries = []
    run_rows = []
    run_details = {}
    baseline_summary = None
    for idx, params in enumerate(params_list, start=1):
        featured = add_features(
            baseline_source,
            sma_period=params.sma_period,
            sentiment_lookback_days=params.sentiment_lookback_days,
            repair_ma_days=params.repair_ma_days,
        ).dropna(subset=["ndx", "sma", "vxn_pctile", "vix_pctile"])
        run_id = f"run_{idx:05d}_{params.stable_key()}"
        result = run_backtest(featured, params, run_id=run_id)
        summary = summarize_run(result)
        summary.update(params.to_dict())
        summary["run_id"] = run_id
        summary["excess_return"] = summary["roi"] - (baseline_summary["roi"] if baseline_summary else 0.0)
        summary["cost_improvement"] = 0.0
        summary["lag_robustness"] = 1.0
        summaries.append(summary)
        details = result.daily.reset_index()
        details["run_id"] = run_id
        rows = details.to_dict(orient="records")
        run_rows.extend(rows)
        run_details[run_id] = rows
        if baseline_summary is None:
            baseline_summary = summary

    ranked = rank_summaries(summaries)
    write_run_outputs(output_dir, ranked, run_rows)
    build_report(output_dir, summaries=ranked, run_details=run_details)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-runs", type=int)
    args = parser.parse_args()
    run_workflow(output_dir=args.output_dir, max_runs=args.max_runs)
    print(f"Wrote Version A report to {args.output_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run smoke tests**

Run:

```bash
python3 -m unittest tests/test_version_a.py
```

Expected: `OK`.

- [ ] **Step 5: Run a small workflow**

Run:

```bash
python3 scripts/run_version_a_backtest.py --max-runs 10
```

Expected: writes `reports/version_a/index.html`, `summary.csv`, `runs.csv`, and detail pages.

- [ ] **Step 6: Run the full staged grid**

Run:

```bash
python3 scripts/run_version_a_backtest.py
```

Expected: writes Stage 1 coarse, Stage 2 refined, and Stage 3 robustness results. If runtime is long, let it finish and record elapsed time in the final summary.

- [ ] **Step 7: Update data inventory**

Add this line to `docs/DATA_INVENTORY.md` after the processed data entries:

```markdown
- Version A 回测报告：`reports/version_a/index.html`
```

---

### Task 7: Mechanical Baseline, Stage 2, Stage 3, And Sweet-Spot Markers

**Files:**
- Modify: `src/version_a/engine.py`
- Modify: `src/version_a/grid.py`
- Modify: `scripts/run_version_a_backtest.py`
- Modify: `src/version_a/report.py`
- Modify: `tests/test_version_a.py`

- [ ] **Step 1: Write failing tests**

Append these tests to `tests/test_version_a.py`:

```python
from src.version_a.engine import run_mechanical_baseline
from src.version_a.grid import add_lag_robustness, mark_sweet_spots, refined_grid, robustness_grid


class VersionAStagedGridTests(unittest.TestCase):
    def test_mechanical_baseline_invests_fixed_budget(self):
        index = pd.date_range("2020-01-01", periods=4, freq="B")
        df = pd.DataFrame({"ndx": [100.0, 101.0, 102.0, 103.0]}, index=index)
        result = run_mechanical_baseline(df, run_id="baseline")
        summary = summarize_run(result)
        self.assertEqual(400.0, summary["total_invested"])
        self.assertEqual({"baseline"}, set(result.daily["state"]))

    def test_refined_and_robustness_grids_expand_seed_parameters(self):
        seed = BacktestParams(200, 0.05, 1.2, 0.8, 25, 75, 756, 20, 2, 2, 10, 20, 15)
        refined = list(refined_grid([seed]))
        robust = list(robustness_grid(refined[:1]))
        self.assertGreater(len(refined), 1)
        self.assertEqual({"refined"}, {item.stage for item in refined})
        self.assertEqual({1, 2, 3}, {item.lag_days for item in robust})
        self.assertEqual({"v1_no_cnn", "v2_full"}, {item.strategy_family for item in robust})

    def test_lag_robustness_and_sweet_spot_markers_are_added(self):
        rows = [
            {
                "run_id": "a1", "stage": "robustness", "lag_days": 1, "strategy_family": "v2_full",
                "sma_period": 200, "sma_buffer_pct": 0.05, "overheat_ratio": 1.2,
                "vol_high_pctile": 0.8, "cnn_fear_threshold": 25, "cnn_greed_threshold": 75,
                "sentiment_lookback_days": 756, "repair_ma_days": 20, "divergence_weeks": 2,
                "standard_buy_window_days": 10, "deep_buy_window_days": 20, "pause_window_days": 15,
                "roi": 0.30, "calmar": 1.0, "excess_return": 0.1, "cost_improvement": 0.1,
            },
            {
                "run_id": "a3", "stage": "robustness", "lag_days": 3, "strategy_family": "v2_full",
                "sma_period": 200, "sma_buffer_pct": 0.05, "overheat_ratio": 1.2,
                "vol_high_pctile": 0.8, "cnn_fear_threshold": 25, "cnn_greed_threshold": 75,
                "sentiment_lookback_days": 756, "repair_ma_days": 20, "divergence_weeks": 2,
                "standard_buy_window_days": 10, "deep_buy_window_days": 20, "pause_window_days": 15,
                "roi": 0.27, "calmar": 1.0, "excess_return": 0.1, "cost_improvement": 0.1,
            },
        ]
        marked = mark_sweet_spots(add_lag_robustness(rows))
        self.assertIn("lag_robustness", marked[0])
        self.assertIn("sweet_spot", marked[0])
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
python3 -m unittest tests/test_version_a.py
```

Expected: fails because the staged-grid and baseline functions are not defined.

- [ ] **Step 3: Add the mechanical baseline**

Append this function to `src/version_a/engine.py`:

```python
def run_mechanical_baseline(df: pd.DataFrame, *, run_id: str) -> BacktestResult:
    params = BacktestParams(200, 0.05, 1.2, 0.8, 25, 75, 756, 20, 2, 0, 10, 20, 15, "baseline", "baseline")
    cash = 0.0
    shares = 0.0
    records = []
    for date, row in df.iterrows():
        cash += BASE_DAILY_BUDGET
        price = float(row["ndx"])
        invest = min(cash, BASE_DAILY_BUDGET)
        shares += invest / price if price > 0 else 0.0
        cash -= invest
        records.append(
            {
                "date": date,
                "price": price,
                "state": "baseline",
                "buy_score": 0,
                "sell_score": 0,
                "invested": invest,
                "cash": cash,
                "shares": shares,
                "portfolio_value": shares * price + cash,
            }
        )
    return BacktestResult(run_id=run_id, params=params, daily=pd.DataFrame(records).set_index("date"), triggers=pd.DataFrame())
```

- [ ] **Step 4: Add refined and robustness grid helpers**

Append to `src/version_a/grid.py`:

```python
from .config import BacktestParams


def _neighbors(value, choices):
    idx = choices.index(value)
    return choices[max(0, idx - 1) : min(len(choices), idx + 2)]


def refined_grid(seeds: list[BacktestParams]) -> list[BacktestParams]:
    out: dict[str, BacktestParams] = {}
    for seed in seeds:
        for standard_buy_window_days in [5, 10, 15]:
            for deep_buy_window_days in [15, 20, 30]:
                for pause_window_days in [10, 15, 20]:
                    for divergence_weeks in [1, 2, 3]:
                        item = BacktestParams(
                            seed.sma_period,
                            seed.sma_buffer_pct,
                            seed.overheat_ratio,
                            seed.vol_high_pctile,
                            seed.cnn_fear_threshold,
                            seed.cnn_greed_threshold,
                            seed.sentiment_lookback_days,
                            seed.repair_ma_days,
                            divergence_weeks,
                            seed.lag_days,
                            standard_buy_window_days,
                            deep_buy_window_days,
                            pause_window_days,
                            "v2_full",
                            "refined",
                        )
                        out[item.stable_key()] = item
    return list(out.values())


def robustness_grid(seeds: list[BacktestParams]) -> list[BacktestParams]:
    out: dict[str, BacktestParams] = {}
    for seed in seeds:
        for lag_days in [1, 2, 3]:
            for strategy_family in ["v1_no_cnn", "v2_full"]:
                item = BacktestParams(
                    seed.sma_period,
                    seed.sma_buffer_pct,
                    seed.overheat_ratio,
                    seed.vol_high_pctile,
                    seed.cnn_fear_threshold,
                    seed.cnn_greed_threshold,
                    seed.sentiment_lookback_days,
                    seed.repair_ma_days,
                    seed.divergence_weeks,
                    lag_days,
                    seed.standard_buy_window_days,
                    seed.deep_buy_window_days,
                    seed.pause_window_days,
                    strategy_family,
                    "robustness",
                )
                out[item.stable_key()] = item
    return list(out.values())
```

- [ ] **Step 5: Add lag robustness and sweet-spot markers**

Append to `src/version_a/grid.py`:

```python
def _param_key_without_lag(row: dict) -> tuple:
    keys = [
        "strategy_family", "sma_period", "sma_buffer_pct", "overheat_ratio", "vol_high_pctile",
        "cnn_fear_threshold", "cnn_greed_threshold", "sentiment_lookback_days", "repair_ma_days",
        "divergence_weeks", "standard_buy_window_days", "deep_buy_window_days", "pause_window_days",
    ]
    return tuple(row.get(key) for key in keys)


def add_lag_robustness(rows: list[dict]) -> list[dict]:
    by_key: dict[tuple, dict[int, float]] = {}
    for row in rows:
        by_key.setdefault(_param_key_without_lag(row), {})[int(row.get("lag_days", 0))] = float(row.get("roi", 0))
    out = []
    for row in rows:
        lag_map = by_key.get(_param_key_without_lag(row), {})
        lag1 = lag_map.get(1)
        lag3 = lag_map.get(3)
        item = dict(row)
        item["lag_robustness"] = 1.0 if lag1 in (None, 0) or lag3 is None else max(0.0, min(1.0, 1.0 - abs(lag1 - lag3) / abs(lag1)))
        out.append(item)
    return out


def mark_sweet_spots(rows: list[dict]) -> list[dict]:
    ranked = rank_summaries(rows)
    if not ranked:
        return []
    threshold = ranked[max(0, int(len(ranked) * 0.10) - 1)]["composite_score"]
    out = []
    for row in ranked:
        item = dict(row)
        item["sweet_spot"] = bool(item.get("composite_score", 0) >= threshold and item.get("excess_return", 0) > 0 and item.get("lag_robustness", 0) >= 0.85)
        out.append(item)
    return out
```

- [ ] **Step 6: Replace workflow with staged execution**

Update `scripts/run_version_a_backtest.py` so the full run computes the mechanical baseline, Stage 1 coarse, Stage 2 refined, and Stage 3 robustness. The final ranking line must be:

```python
ranked = mark_sweet_spots(add_lag_robustness(summaries))
```

When `--max-runs` is provided, only run the first `max_runs` coarse combinations for smoke testing.

- [ ] **Step 7: Show sweet spots in report**

Update the overview table in `src/version_a/report.py` to include:

```python
f"<td>{'Yes' if item.get('sweet_spot') else 'No'}</td>"
```

- [ ] **Step 8: Run tests**

Run:

```bash
python3 -m unittest tests/test_version_a.py
```

Expected: `OK`.

---

### Task 8: Verification And Result Review

**Files:**
- Generated: `reports/version_a/index.html`
- Generated: `reports/version_a/summary.csv`
- Generated: `reports/version_a/runs.csv`

- [ ] **Step 1: Verify tests**

Run:

```bash
python3 -m unittest discover -s tests
python3 -m py_compile scripts/fetch_data.py scripts/run_version_a_backtest.py
```

Expected: all tests pass and compile succeeds.

- [ ] **Step 2: Verify output counts**

Run:

```bash
python3 - <<'PY'
import csv
from pathlib import Path
summary = list(csv.DictReader(Path("reports/version_a/summary.csv").open()))
runs = list(csv.DictReader(Path("reports/version_a/runs.csv").open()))
print("summary_rows", len(summary))
print("run_rows", len(runs))
print("top_run", summary[0]["run_id"] if summary else "")
assert len(summary) > 0
assert len(runs) > 0
assert Path("reports/version_a/index.html").exists()
PY
```

Expected: non-zero summary and run rows, with a valid top run.

- [ ] **Step 3: Record results**

Create or update `reports/version_a/RESULTS.md` with:

```markdown
# Version A Backtest Results

- Run date:
- Input data:
- Evaluated combinations:
- Stage counts:
- Best composite-score run:
- Best ROI run:
- Best drawdown-controlled run:
- Sweet-spot candidate count:
- Notes:

```

- [ ] **Step 4: Final response**

Report:
- tests run,
- number of parameter combinations evaluated,
- location of the HTML overview,
- top three parameter combinations by composite score,
- any limitations that remain.

---

## Self-Review

- Spec coverage: The plan implements data loading, feature generation, scoring, Stage 1 coarse search, Stage 2 refinement, Stage 3 robustness, full result persistence, and two-layer static HTML reporting.
- Placeholder scan: No `TBD`, `TODO`, or unspecified file paths remain.
- Type consistency: `BacktestParams`, `BacktestResult`, summary rows, and report inputs are named consistently across tasks.
- Stage coverage: Stage 1 coarse, Stage 2 refined, and Stage 3 robustness are all represented in the workflow plan.
