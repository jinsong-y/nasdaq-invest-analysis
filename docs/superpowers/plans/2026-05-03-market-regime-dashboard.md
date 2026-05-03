# Market Regime Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a strict market-regime dashboard that classifies Nasdaq 100 market state from existing Version A indicators, emits daily CSV/latest JSON/static HTML, and fails fast when latest required inputs are missing.

**Architecture:** Add `src/market_regime/` as a reusable analytic layer separate from Version A trading logic. Reuse Version A data loading and feature engineering, compute explainable component scores, classify regimes, then generate report artifacts under `reports/market_regime/`.

**Tech Stack:** Python 3, pandas, stdlib `dataclasses`, stdlib `json`, stdlib `html`, `unittest`, existing project scripts.

---

## File Structure

- Create `src/market_regime/__init__.py`: package exports.
- Create `src/market_regime/config.py`: model constants, required fields, thresholds, default parameters.
- Create `src/market_regime/model.py`: validation, score computation, regime classification, latest summary building.
- Create `src/market_regime/report.py`: CSV, JSON, HTML report writers.
- Create `scripts/run_market_regime_dashboard.py`: CLI/workflow entry point.
- Create `tests/test_market_regime.py`: focused unit and workflow tests.
- No changes to Version A engine behavior.

---

### Task 1: Config And Package Skeleton

**Files:**
- Create: `src/market_regime/__init__.py`
- Create: `src/market_regime/config.py`
- Test: `tests/test_market_regime.py`

- [ ] **Step 1: Write failing config tests**

Add this file:

```python
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market_regime.config import DashboardConfig, REQUIRED_DERIVED_COLUMNS, REQUIRED_RAW_COLUMNS


class MarketRegimeConfigTests(unittest.TestCase):
    def test_required_columns_are_explicit(self):
        self.assertEqual(
            {
                "ndx",
                "vxn",
                "vix",
                "cnn_fear_greed",
                "ndxe_ndx",
                "sox_ndx",
            },
            REQUIRED_RAW_COLUMNS,
        )
        self.assertEqual(
            {
                "sma",
                "dist_sma",
                "vxn_pctile",
                "vix_pctile",
                "cnn_ma5",
                "ndxe_ma",
                "sox_ma",
            },
            REQUIRED_DERIVED_COLUMNS,
        )

    def test_default_config_matches_design(self):
        config = DashboardConfig()
        self.assertEqual(180, config.sma_period)
        self.assertEqual(1260, config.sentiment_lookback_days)
        self.assertEqual(50, config.repair_ma_days)
        self.assertEqual(252, config.rolling_high_days)
        self.assertGreater(config.top_risk_threshold, config.warm_threshold)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_market_regime.MarketRegimeConfigTests -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.market_regime'`.

- [ ] **Step 3: Create package skeleton**

Create `src/market_regime/__init__.py`:

```python
from __future__ import annotations

from .config import DashboardConfig

__all__ = ["DashboardConfig"]
```

Create `src/market_regime/config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


REQUIRED_RAW_COLUMNS = {
    "ndx",
    "vxn",
    "vix",
    "cnn_fear_greed",
    "ndxe_ndx",
    "sox_ndx",
}

REQUIRED_DERIVED_COLUMNS = {
    "sma",
    "dist_sma",
    "vxn_pctile",
    "vix_pctile",
    "cnn_ma5",
    "ndxe_ma",
    "sox_ma",
}

OUTPUT_COLUMNS = [
    "date",
    "market_regime",
    "temperature_score",
    "undervaluation_score",
    "overheat_score",
    "trend_score",
    "volatility_score",
    "sentiment_score",
    "breadth_score",
    "semiconductor_score",
    "top_risk_score",
    "recovery_score",
    "confidence_score",
    "dashboard_action",
    "missing_inputs",
    "ndx",
    "sma",
    "dist_sma",
    "vxn",
    "vix",
    "vxn_pctile",
    "vix_pctile",
    "cnn_fear_greed",
    "cnn_ma5",
    "ndxe_ndx",
    "ndxe_ma",
    "sox_ndx",
    "sox_ma",
]


@dataclass(frozen=True)
class DashboardConfig:
    sma_period: int = 180
    sentiment_lookback_days: int = 1260
    repair_ma_days: int = 50
    rolling_high_days: int = 252
    panic_low_threshold: float = 75.0
    stress_low_threshold: float = 55.0
    recovery_threshold: float = 55.0
    warm_threshold: float = 60.0
    overheat_threshold: float = 70.0
    top_risk_threshold: float = 75.0
    low_confidence_threshold: float = 45.0
```

- [ ] **Step 4: Run config tests**

Run: `python3 -m unittest tests.test_market_regime.MarketRegimeConfigTests -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/market_regime/__init__.py src/market_regime/config.py tests/test_market_regime.py
git commit -m "feat: add market regime config"
```

Expected: commit succeeds.

---

### Task 2: Strict Model Validation

**Files:**
- Modify: `tests/test_market_regime.py`
- Create: `src/market_regime/model.py`

- [ ] **Step 1: Add failing validation tests**

Append to `tests/test_market_regime.py`:

```python
import pandas as pd

from src.market_regime.model import classify_latest, missing_inputs_for_row


class MarketRegimeValidationTests(unittest.TestCase):
    def _valid_row(self):
        return {
            "ndx": 100.0,
            "sma": 100.0,
            "dist_sma": 0.0,
            "vxn": 20.0,
            "vix": 18.0,
            "vxn_pctile": 0.50,
            "vix_pctile": 0.50,
            "cnn_fear_greed": 50.0,
            "cnn_ma5": 50.0,
            "ndxe_ndx": 0.35,
            "ndxe_ma": 0.35,
            "sox_ndx": 0.25,
            "sox_ma": 0.25,
        }

    def test_missing_inputs_for_row_lists_nan_fields(self):
        row = pd.Series(self._valid_row())
        row["vix"] = float("nan")
        row["vxn"] = None
        self.assertEqual(["vix", "vxn"], missing_inputs_for_row(row))

    def test_latest_classification_fails_when_required_latest_inputs_missing(self):
        frame = pd.DataFrame([self._valid_row()], index=pd.to_datetime(["2026-05-01"]))
        frame.loc[pd.Timestamp("2026-05-01"), "vix"] = float("nan")
        with self.assertRaisesRegex(ValueError, "2026-05-01.*vix"):
            classify_latest(frame)
```

- [ ] **Step 2: Run validation tests to verify failure**

Run: `python3 -m unittest tests.test_market_regime.MarketRegimeValidationTests -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.market_regime.model'`.

- [ ] **Step 3: Implement validation shell**

Create `src/market_regime/model.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from .config import DashboardConfig, REQUIRED_DERIVED_COLUMNS, REQUIRED_RAW_COLUMNS


REQUIRED_COLUMNS = tuple(sorted(REQUIRED_RAW_COLUMNS | REQUIRED_DERIVED_COLUMNS))


@dataclass(frozen=True)
class RegimeResult:
    date: pd.Timestamp
    market_regime: str
    temperature_score: float
    undervaluation_score: float
    overheat_score: float
    trend_score: float
    volatility_score: float
    sentiment_score: float
    breadth_score: float
    semiconductor_score: float
    top_risk_score: float
    recovery_score: float
    confidence_score: float
    dashboard_action: str
    missing_inputs: list[str]
    inputs: dict[str, float]

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["date"] = self.date.strftime("%Y-%m-%d")
        row.update(self.inputs)
        del row["inputs"]
        row["missing_inputs"] = ",".join(self.missing_inputs)
        return row


def _clip_score(value: float) -> float:
    if np.isnan(value):
        return 0.0
    return float(min(100.0, max(0.0, value)))


def missing_inputs_for_row(row: pd.Series) -> list[str]:
    missing = []
    for column in REQUIRED_COLUMNS:
        value = row.get(column)
        if pd.isna(value):
            missing.append(column)
    return missing


def classify_latest(df: pd.DataFrame, config: DashboardConfig | None = None) -> RegimeResult:
    if df.empty:
        raise ValueError("cannot classify empty market regime frame")
    config = config or DashboardConfig()
    date = pd.Timestamp(df.index[-1])
    result = classify_row(df.iloc[-1], date=date, config=config, strict=True)
    return result


def classify_row(
    row: pd.Series,
    *,
    date: pd.Timestamp,
    config: DashboardConfig | None = None,
    strict: bool,
) -> RegimeResult:
    config = config or DashboardConfig()
    missing = missing_inputs_for_row(row)
    if missing and strict:
        raise ValueError(f"missing market regime inputs for {date.strftime('%Y-%m-%d')}: {missing}")
    if missing:
        return _unscorable_result(row, date, missing)
    return _scorable_result(row, date, config)


def _unscorable_result(row: pd.Series, date: pd.Timestamp, missing: list[str]) -> RegimeResult:
    inputs = {column: _float_or_nan(row.get(column)) for column in REQUIRED_COLUMNS}
    return RegimeResult(
        date=date,
        market_regime="unscorable",
        temperature_score=0.0,
        undervaluation_score=0.0,
        overheat_score=0.0,
        trend_score=0.0,
        volatility_score=0.0,
        sentiment_score=0.0,
        breadth_score=0.0,
        semiconductor_score=0.0,
        top_risk_score=0.0,
        recovery_score=0.0,
        confidence_score=0.0,
        dashboard_action="unavailable",
        missing_inputs=missing,
        inputs=inputs,
    )


def _float_or_nan(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _scorable_result(row: pd.Series, date: pd.Timestamp, config: DashboardConfig) -> RegimeResult:
    inputs = {column: _float_or_nan(row.get(column)) for column in REQUIRED_COLUMNS}
    return RegimeResult(
        date=date,
        market_regime="normal",
        temperature_score=50.0,
        undervaluation_score=0.0,
        overheat_score=0.0,
        trend_score=50.0,
        volatility_score=50.0,
        sentiment_score=50.0,
        breadth_score=50.0,
        semiconductor_score=50.0,
        top_risk_score=0.0,
        recovery_score=0.0,
        confidence_score=60.0,
        dashboard_action="normal_dca",
        missing_inputs=[],
        inputs=inputs,
    )
```

- [ ] **Step 4: Run validation tests**

Run: `python3 -m unittest tests.test_market_regime.MarketRegimeValidationTests -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/market_regime/model.py tests/test_market_regime.py
git commit -m "feat: add strict market regime validation"
```

Expected: commit succeeds.

---

### Task 3: Component Scores And Regime Classification

**Files:**
- Modify: `tests/test_market_regime.py`
- Modify: `src/market_regime/model.py`

- [ ] **Step 1: Add failing regime tests**

Append to `tests/test_market_regime.py`:

```python
class MarketRegimeClassificationTests(unittest.TestCase):
    def _row(
        self,
        *,
        ndx=100.0,
        sma=100.0,
        dist_sma=0.0,
        vxn=20.0,
        vix=18.0,
        vxn_pctile=0.50,
        vix_pctile=0.50,
        cnn_fear_greed=50.0,
        cnn_ma5=50.0,
        ndxe_ndx=0.35,
        ndxe_ma=0.35,
        sox_ndx=0.25,
        sox_ma=0.25,
    ):
        return pd.Series(
            {
                "ndx": ndx,
                "sma": sma,
                "dist_sma": dist_sma,
                "vxn": vxn,
                "vix": vix,
                "vxn_pctile": vxn_pctile,
                "vix_pctile": vix_pctile,
                "cnn_fear_greed": cnn_fear_greed,
                "cnn_ma5": cnn_ma5,
                "ndxe_ndx": ndxe_ndx,
                "ndxe_ma": ndxe_ma,
                "sox_ndx": sox_ndx,
                "sox_ma": sox_ma,
            }
        )

    def _classify(self, row):
        from src.market_regime.model import classify_row

        return classify_row(row, date=pd.Timestamp("2026-04-30"), strict=True)

    def test_panic_low_fixture(self):
        result = self._classify(
            self._row(
                ndx=78.0,
                sma=100.0,
                dist_sma=-0.22,
                vxn=55.0,
                vix=48.0,
                vxn_pctile=0.98,
                vix_pctile=0.97,
                cnn_fear_greed=8.0,
                cnn_ma5=10.0,
                ndxe_ndx=0.30,
                ndxe_ma=0.36,
                sox_ndx=0.18,
                sox_ma=0.25,
            )
        )
        self.assertEqual("panic_low", result.market_regime)
        self.assertEqual("add_strong", result.dashboard_action)
        self.assertGreaterEqual(result.undervaluation_score, 75.0)

    def test_stress_low_fixture(self):
        result = self._classify(
            self._row(
                ndx=90.0,
                sma=100.0,
                dist_sma=-0.10,
                vxn_pctile=0.82,
                vix_pctile=0.80,
                cnn_fear_greed=22.0,
                cnn_ma5=24.0,
            )
        )
        self.assertEqual("stress_low", result.market_regime)
        self.assertEqual("add_light", result.dashboard_action)

    def test_recovery_fixture(self):
        result = self._classify(
            self._row(
                ndx=99.0,
                sma=100.0,
                dist_sma=-0.01,
                vxn=21.0,
                vix=18.0,
                vxn_pctile=0.55,
                vix_pctile=0.50,
                cnn_fear_greed=35.0,
                cnn_ma5=42.0,
                ndxe_ndx=0.37,
                ndxe_ma=0.35,
                sox_ndx=0.27,
                sox_ma=0.25,
            )
        )
        self.assertEqual("recovery", result.market_regime)
        self.assertEqual("normal_dca", result.dashboard_action)

    def test_normal_fixture(self):
        result = self._classify(self._row())
        self.assertEqual("normal", result.market_regime)
        self.assertEqual("normal_dca", result.dashboard_action)

    def test_warm_fixture(self):
        result = self._classify(
            self._row(
                ndx=109.0,
                sma=100.0,
                dist_sma=0.09,
                vxn_pctile=0.30,
                vix_pctile=0.28,
                cnn_fear_greed=66.0,
                cnn_ma5=64.0,
                ndxe_ndx=0.36,
                ndxe_ma=0.35,
                sox_ndx=0.26,
                sox_ma=0.25,
            )
        )
        self.assertEqual("warm", result.market_regime)
        self.assertEqual("reduce", result.dashboard_action)

    def test_overheated_fixture(self):
        result = self._classify(
            self._row(
                ndx=118.0,
                sma=100.0,
                dist_sma=0.18,
                vxn_pctile=0.12,
                vix_pctile=0.10,
                cnn_fear_greed=82.0,
                cnn_ma5=80.0,
                ndxe_ndx=0.36,
                ndxe_ma=0.35,
                sox_ndx=0.26,
                sox_ma=0.25,
            )
        )
        self.assertEqual("overheated", result.market_regime)
        self.assertEqual("reduce", result.dashboard_action)

    def test_top_risk_fixture(self):
        result = self._classify(
            self._row(
                ndx=124.0,
                sma=100.0,
                dist_sma=0.24,
                vxn_pctile=0.08,
                vix_pctile=0.06,
                cnn_fear_greed=88.0,
                cnn_ma5=84.0,
                ndxe_ndx=0.32,
                ndxe_ma=0.36,
                sox_ndx=0.21,
                sox_ma=0.25,
            )
        )
        self.assertEqual("top_risk", result.market_regime)
        self.assertEqual("pause", result.dashboard_action)
        self.assertGreaterEqual(result.top_risk_score, 75.0)
```

- [ ] **Step 2: Run classification tests to verify failure**

Run: `python3 -m unittest tests.test_market_regime.MarketRegimeClassificationTests -v`

Expected: FAIL because all scorable rows still classify as `normal`.

- [ ] **Step 3: Replace `_scorable_result` and add score helpers**

In `src/market_regime/model.py`, replace `_scorable_result` with:

```python
def _scorable_result(row: pd.Series, date: pd.Timestamp, config: DashboardConfig) -> RegimeResult:
    dist_sma = _float_or_nan(row["dist_sma"])
    vxn_pctile = _float_or_nan(row["vxn_pctile"])
    vix_pctile = _float_or_nan(row["vix_pctile"])
    cnn = _float_or_nan(row["cnn_fear_greed"])
    cnn_ma5 = _float_or_nan(row["cnn_ma5"])
    ndxe_ndx = _float_or_nan(row["ndxe_ndx"])
    ndxe_ma = _float_or_nan(row["ndxe_ma"])
    sox_ndx = _float_or_nan(row["sox_ndx"])
    sox_ma = _float_or_nan(row["sox_ma"])

    vol_high = max(vxn_pctile, vix_pctile)
    vol_low = 1.0 - min(vxn_pctile, vix_pctile)
    breadth_delta = _ratio_delta(ndxe_ndx, ndxe_ma)
    semiconductor_delta = _ratio_delta(sox_ndx, sox_ma)

    trend_score = _clip_score(50.0 + dist_sma * 250.0)
    volatility_score = _clip_score(max(vol_high, vol_low) * 100.0)
    sentiment_score = _clip_score(cnn)
    breadth_score = _clip_score(50.0 + breadth_delta * 500.0)
    semiconductor_score = _clip_score(50.0 + semiconductor_delta * 500.0)

    low_price = _clip_score((-dist_sma) / 0.20 * 55.0)
    high_vol = _clip_score((vol_high - 0.55) / 0.40 * 30.0)
    fear = _clip_score((35.0 - cnn) / 35.0 * 35.0)
    undervaluation_score = _clip_score(low_price + high_vol + fear)

    high_price = _clip_score(dist_sma / 0.20 * 45.0)
    low_vol = _clip_score((0.35 - min(vxn_pctile, vix_pctile)) / 0.35 * 25.0)
    greed = _clip_score((cnn - 60.0) / 35.0 * 30.0)
    overheat_score = _clip_score(high_price + low_vol + greed)

    divergence = 0.0
    if breadth_delta < 0:
        divergence += min(25.0, abs(breadth_delta) * 500.0)
    if semiconductor_delta < 0:
        divergence += min(25.0, abs(semiconductor_delta) * 500.0)
    top_risk_score = _clip_score(overheat_score * 0.75 + divergence)

    recovery_score = _clip_score(
        _positive_part(cnn_ma5 - cnn) * 2.0
        + _positive_part(breadth_delta) * 450.0
        + _positive_part(semiconductor_delta) * 450.0
        + _clip_score((dist_sma + 0.08) / 0.12 * 20.0)
    )

    temperature_score = _clip_score(50.0 + overheat_score * 0.50 - undervaluation_score * 0.45)
    confidence_score = _confidence_score(
        undervaluation_score=undervaluation_score,
        overheat_score=overheat_score,
        top_risk_score=top_risk_score,
        recovery_score=recovery_score,
    )
    market_regime = _market_regime(
        config,
        undervaluation_score=undervaluation_score,
        overheat_score=overheat_score,
        top_risk_score=top_risk_score,
        recovery_score=recovery_score,
        temperature_score=temperature_score,
        vol_high=vol_high,
        cnn=cnn,
    )
    action = _dashboard_action(market_regime, confidence_score, config)
    inputs = {column: _float_or_nan(row.get(column)) for column in REQUIRED_COLUMNS}
    return RegimeResult(
        date=date,
        market_regime=market_regime,
        temperature_score=temperature_score,
        undervaluation_score=undervaluation_score,
        overheat_score=overheat_score,
        trend_score=trend_score,
        volatility_score=volatility_score,
        sentiment_score=sentiment_score,
        breadth_score=breadth_score,
        semiconductor_score=semiconductor_score,
        top_risk_score=top_risk_score,
        recovery_score=recovery_score,
        confidence_score=confidence_score,
        dashboard_action=action,
        missing_inputs=[],
        inputs=inputs,
    )
```

Add these helpers below `_scorable_result`:

```python
def _ratio_delta(value: float, moving_average: float) -> float:
    if moving_average == 0:
        return 0.0
    return value / moving_average - 1.0


def _positive_part(value: float) -> float:
    return max(0.0, value)


def _confidence_score(
    *,
    undervaluation_score: float,
    overheat_score: float,
    top_risk_score: float,
    recovery_score: float,
) -> float:
    strongest = max(undervaluation_score, overheat_score, top_risk_score, recovery_score)
    second = sorted([undervaluation_score, overheat_score, top_risk_score, recovery_score])[-2]
    separation = max(0.0, strongest - second)
    return _clip_score(55.0 + strongest * 0.25 + separation * 0.20)


def _market_regime(
    config: DashboardConfig,
    *,
    undervaluation_score: float,
    overheat_score: float,
    top_risk_score: float,
    recovery_score: float,
    temperature_score: float,
    vol_high: float,
    cnn: float,
) -> str:
    if top_risk_score >= config.top_risk_threshold:
        return "top_risk"
    if overheat_score >= config.overheat_threshold:
        return "overheated"
    if undervaluation_score >= config.panic_low_threshold and vol_high >= 0.90 and cnn <= 15.0:
        return "panic_low"
    if undervaluation_score >= config.stress_low_threshold:
        return "stress_low"
    if recovery_score >= config.recovery_threshold:
        return "recovery"
    if temperature_score >= config.warm_threshold:
        return "warm"
    return "normal"


def _dashboard_action(market_regime: str, confidence_score: float, config: DashboardConfig) -> str:
    if confidence_score < config.low_confidence_threshold:
        return "unavailable"
    if market_regime == "panic_low":
        return "add_strong"
    if market_regime == "stress_low":
        return "add_light"
    if market_regime in {"recovery", "normal"}:
        return "normal_dca"
    if market_regime in {"warm", "overheated"}:
        return "reduce"
    if market_regime == "top_risk":
        return "pause"
    return "unavailable"
```

- [ ] **Step 4: Run classification tests**

Run: `python3 -m unittest tests.test_market_regime.MarketRegimeClassificationTests -v`

Expected: PASS.

- [ ] **Step 5: Run all market regime tests**

Run: `python3 -m unittest tests.test_market_regime -v`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/market_regime/model.py tests/test_market_regime.py
git commit -m "feat: classify market regimes"
```

Expected: commit succeeds.

---

### Task 4: Daily Classification And Latest Summary

**Files:**
- Modify: `tests/test_market_regime.py`
- Modify: `src/market_regime/model.py`

- [ ] **Step 1: Add failing daily/latest summary tests**

Append to `tests/test_market_regime.py`:

```python
from src.market_regime.model import classify_daily, latest_summary


class MarketRegimeSummaryTests(unittest.TestCase):
    def _frame(self):
        rows = [
            {
                "ndx": 100.0,
                "sma": 100.0,
                "dist_sma": 0.0,
                "vxn": 20.0,
                "vix": 18.0,
                "vxn_pctile": 0.50,
                "vix_pctile": 0.50,
                "cnn_fear_greed": 50.0,
                "cnn_ma5": 50.0,
                "ndxe_ndx": 0.35,
                "ndxe_ma": 0.35,
                "sox_ndx": 0.25,
                "sox_ma": 0.25,
            },
            {
                "ndx": 118.0,
                "sma": 100.0,
                "dist_sma": 0.18,
                "vxn": 14.0,
                "vix": 12.0,
                "vxn_pctile": 0.12,
                "vix_pctile": 0.10,
                "cnn_fear_greed": 82.0,
                "cnn_ma5": 80.0,
                "ndxe_ndx": 0.36,
                "ndxe_ma": 0.35,
                "sox_ndx": 0.26,
                "sox_ma": 0.25,
            },
        ]
        return pd.DataFrame(rows, index=pd.to_datetime(["2026-04-29", "2026-04-30"]))

    def test_classify_daily_marks_historical_missing_as_unscorable(self):
        frame = self._frame()
        frame.loc[pd.Timestamp("2026-04-29"), "vix"] = float("nan")
        out = classify_daily(frame)
        self.assertEqual("unscorable", out.iloc[0]["market_regime"])
        self.assertEqual("overheated", out.iloc[1]["market_regime"])
        self.assertEqual(0.0, out.iloc[0]["confidence_score"])

    def test_latest_summary_contains_drivers_risks_inputs(self):
        summary = latest_summary(self._frame())
        self.assertEqual("2026-04-30", summary["as_of_date"])
        self.assertEqual("overheated", summary["market_regime"])
        self.assertIn("drivers", summary)
        self.assertIn("risks", summary)
        self.assertIn("inputs", summary)
        self.assertIn("dashboard_action", summary)
```

- [ ] **Step 2: Run summary tests to verify failure**

Run: `python3 -m unittest tests.test_market_regime.MarketRegimeSummaryTests -v`

Expected: FAIL with import errors for `classify_daily` and `latest_summary`.

- [ ] **Step 3: Implement daily classification and summary**

Add to `src/market_regime/model.py`:

```python
def classify_daily(df: pd.DataFrame, config: DashboardConfig | None = None) -> pd.DataFrame:
    config = config or DashboardConfig()
    rows = []
    for date, row in df.iterrows():
        rows.append(classify_row(row, date=pd.Timestamp(date), config=config, strict=False).to_row())
    return pd.DataFrame(rows)


def latest_summary(df: pd.DataFrame, config: DashboardConfig | None = None) -> dict[str, Any]:
    result = classify_latest(df, config=config)
    row = result.to_row()
    return {
        "as_of_date": row["date"],
        "market_regime": result.market_regime,
        "temperature_score": result.temperature_score,
        "confidence_score": result.confidence_score,
        "dashboard_action": result.dashboard_action,
        "summary": _summary_text(result),
        "drivers": _drivers(result),
        "risks": _risks(result),
        "inputs": result.inputs,
    }


def _summary_text(result: RegimeResult) -> str:
    labels = {
        "panic_low": "Severe stress with low-market evidence.",
        "stress_low": "Market stress and below-trend evidence.",
        "recovery": "Repair signals improving after stress.",
        "normal": "No dominant extreme signal.",
        "warm": "Above-trend market with warmer conditions.",
        "overheated": "Multiple overheat signals active.",
        "top_risk": "Overheat with structural deterioration risk.",
        "unscorable": "Required inputs missing.",
    }
    return labels[result.market_regime]


def _drivers(result: RegimeResult) -> list[str]:
    scores = [
        ("undervaluation", result.undervaluation_score),
        ("overheat", result.overheat_score),
        ("top_risk", result.top_risk_score),
        ("recovery", result.recovery_score),
        ("trend", result.trend_score),
        ("volatility", result.volatility_score),
        ("sentiment", result.sentiment_score),
        ("breadth", result.breadth_score),
        ("semiconductor", result.semiconductor_score),
    ]
    return [name for name, score in sorted(scores, key=lambda item: item[1], reverse=True)[:3]]


def _risks(result: RegimeResult) -> list[str]:
    risks = []
    if result.top_risk_score >= 60:
        risks.append("top_risk")
    if result.overheat_score >= 60:
        risks.append("overheat")
    if result.undervaluation_score >= 60:
        risks.append("market_stress")
    if result.confidence_score < 55:
        risks.append("low_confidence")
    if not risks:
        risks.append("no_major_extreme")
    return risks
```

- [ ] **Step 4: Run summary tests**

Run: `python3 -m unittest tests.test_market_regime.MarketRegimeSummaryTests -v`

Expected: PASS.

- [ ] **Step 5: Run all market regime tests**

Run: `python3 -m unittest tests.test_market_regime -v`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/market_regime/model.py tests/test_market_regime.py
git commit -m "feat: summarize market regimes"
```

Expected: commit succeeds.

---

### Task 5: Report Writers

**Files:**
- Modify: `tests/test_market_regime.py`
- Create: `src/market_regime/report.py`

- [ ] **Step 1: Add failing report writer test**

Append to `tests/test_market_regime.py`:

```python
from tempfile import TemporaryDirectory

from src.market_regime.report import write_dashboard_outputs


class MarketRegimeReportTests(unittest.TestCase):
    def test_write_dashboard_outputs_creates_csv_json_html(self):
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            daily = pd.DataFrame(
                [
                    {
                        "date": "2026-04-30",
                        "market_regime": "normal",
                        "temperature_score": 50.0,
                        "undervaluation_score": 0.0,
                        "overheat_score": 0.0,
                        "trend_score": 50.0,
                        "volatility_score": 50.0,
                        "sentiment_score": 50.0,
                        "breadth_score": 50.0,
                        "semiconductor_score": 50.0,
                        "top_risk_score": 0.0,
                        "recovery_score": 0.0,
                        "confidence_score": 60.0,
                        "dashboard_action": "normal_dca",
                        "missing_inputs": "",
                        "ndx": 100.0,
                        "sma": 100.0,
                        "dist_sma": 0.0,
                        "vxn": 20.0,
                        "vix": 18.0,
                        "vxn_pctile": 0.5,
                        "vix_pctile": 0.5,
                        "cnn_fear_greed": 50.0,
                        "cnn_ma5": 50.0,
                        "ndxe_ndx": 0.35,
                        "ndxe_ma": 0.35,
                        "sox_ndx": 0.25,
                        "sox_ma": 0.25,
                    }
                ]
            )
            summary = {
                "as_of_date": "2026-04-30",
                "market_regime": "normal",
                "temperature_score": 50.0,
                "confidence_score": 60.0,
                "dashboard_action": "normal_dca",
                "summary": "No dominant extreme signal.",
                "drivers": ["trend", "volatility", "sentiment"],
                "risks": ["no_major_extreme"],
                "inputs": {"ndx": 100.0},
            }
            write_dashboard_outputs(output_dir, daily, summary)
            self.assertTrue((output_dir / "daily_regimes.csv").exists())
            self.assertTrue((output_dir / "latest.json").exists())
            self.assertTrue((output_dir / "index.html").exists())
            self.assertIn("normal", (output_dir / "index.html").read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run report test to verify failure**

Run: `python3 -m unittest tests.test_market_regime.MarketRegimeReportTests -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.market_regime.report'`.

- [ ] **Step 3: Implement report writer**

Create `src/market_regime/report.py`:

```python
from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

from .config import OUTPUT_COLUMNS


CSS = """
:root{--ink:#161616;--muted:#666;--paper:#f7f5ef;--panel:#fffdf8;--line:#ddd6c8;--red:#a03a2a;--gold:#a47122;--green:#216c4a;--blue:#245c9e}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif}
main{max-width:1180px;margin:0 auto;padding:34px clamp(16px,4vw,46px) 54px}
h1{font-size:clamp(34px,5vw,58px);line-height:1;margin:0 0 12px;letter-spacing:0}
h2{font-size:20px;margin:0 0 12px}p{color:var(--muted);line-height:1.5}
.hero{border-bottom:1px solid var(--line);padding-bottom:24px;margin-bottom:24px}
.regime{font-size:13px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;color:var(--blue)}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}
.card{background:var(--panel);border:1px solid var(--line);padding:16px;overflow:auto}
.label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}.value{font-size:28px;font-weight:750;margin-top:6px}
.bar{height:12px;background:#ece5d8;border:1px solid var(--line);margin:8px 0 12px}.fill{height:100%;background:var(--blue)}
table{width:100%;border-collapse:collapse;background:var(--panel);font-size:13px}th,td{padding:8px 9px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}
@media(max-width:800px){.grid{grid-template-columns:1fr 1fr}}@media(max-width:520px){.grid{grid-template-columns:1fr}}
"""


def write_dashboard_outputs(output_dir: Path, daily: pd.DataFrame, summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = [column for column in OUTPUT_COLUMNS if column in daily.columns]
    daily.to_csv(output_dir / "daily_regimes.csv", index=False, columns=ordered)
    (output_dir / "latest.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "index.html").write_text(_html_page(daily, summary), encoding="utf-8")


def _html_page(daily: pd.DataFrame, summary: dict[str, Any]) -> str:
    recent = daily.tail(30)
    rows = "".join(
        "<tr>"
        f"<td>{escape(str(row.get('date', '')))}</td>"
        f"<td>{escape(str(row.get('market_regime', '')))}</td>"
        f"<td>{_fmt(row.get('temperature_score'))}</td>"
        f"<td>{_fmt(row.get('confidence_score'))}</td>"
        f"<td>{escape(str(row.get('dashboard_action', '')))}</td>"
        "</tr>"
        for _, row in recent.iterrows()
    )
    bars = "".join(
        _score_card(label, summary.get(label, 0.0))
        for label in ["temperature_score", "confidence_score"]
    )
    body = (
        "<section class='hero'>"
        f"<div class='regime'>{escape(str(summary.get('market_regime', '')))}</div>"
        f"<h1>Market Regime Dashboard</h1>"
        f"<p>As of {escape(str(summary.get('as_of_date', '')))}. {escape(str(summary.get('summary', '')))}</p>"
        "</section>"
        "<section class='grid'>"
        f"{bars}"
        f"<div class='card'><div class='label'>Action</div><div class='value'>{escape(str(summary.get('dashboard_action', '')))}</div></div>"
        f"<div class='card'><div class='label'>Drivers</div><p>{escape(', '.join(summary.get('drivers', [])))}</p></div>"
        "</section>"
        "<section class='card'><h2>Recent Regimes</h2><table><thead><tr><th>Date</th><th>Regime</th><th>Temp</th><th>Confidence</th><th>Action</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Market Regime Dashboard</title><style>{CSS}</style></head><body><main>{body}</main></body></html>"


def _score_card(label: str, value: object) -> str:
    numeric = _number(value)
    return (
        "<div class='card'>"
        f"<div class='label'>{escape(label.replace('_', ' '))}</div>"
        f"<div class='value'>{numeric:.1f}</div>"
        "<div class='bar'>"
        f"<div class='fill' style='width:{max(0.0, min(100.0, numeric)):.1f}%'></div>"
        "</div></div>"
    )


def _number(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fmt(value: object) -> str:
    return f"{_number(value):.1f}"
```

- [ ] **Step 4: Run report tests**

Run: `python3 -m unittest tests.test_market_regime.MarketRegimeReportTests -v`

Expected: PASS.

- [ ] **Step 5: Run all market regime tests**

Run: `python3 -m unittest tests.test_market_regime -v`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/market_regime/report.py tests/test_market_regime.py
git commit -m "feat: write market regime dashboard outputs"
```

Expected: commit succeeds.

---

### Task 6: Workflow Runner

**Files:**
- Modify: `tests/test_market_regime.py`
- Create: `scripts/run_market_regime_dashboard.py`

- [ ] **Step 1: Add failing workflow test**

Append to `tests/test_market_regime.py`:

```python
class MarketRegimeWorkflowTests(unittest.TestCase):
    def test_run_workflow_writes_outputs_for_complete_target_date(self):
        from scripts.run_market_regime_dashboard import run_workflow

        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            run_workflow(output_dir=output_dir, target_date="2026-04-30")
            self.assertTrue((output_dir / "daily_regimes.csv").exists())
            self.assertTrue((output_dir / "latest.json").exists())
            self.assertTrue((output_dir / "index.html").exists())
            self.assertIn("market_regime", (output_dir / "latest.json").read_text(encoding="utf-8"))

    def test_run_workflow_fails_fast_for_latest_missing_volatility(self):
        from scripts.run_market_regime_dashboard import run_workflow

        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "2026-05-01.*vix.*vxn"):
                run_workflow(output_dir=Path(tmp), target_date="2026-05-01")
```

- [ ] **Step 2: Run workflow tests to verify failure**

Run: `python3 -m unittest tests.test_market_regime.MarketRegimeWorkflowTests -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.run_market_regime_dashboard'`.

- [ ] **Step 3: Implement workflow script**

Create `scripts/run_market_regime_dashboard.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market_regime.config import DashboardConfig
from src.market_regime.model import classify_daily, latest_summary
from src.market_regime.report import write_dashboard_outputs
from src.version_a.data import load_market_data
from src.version_a.features import add_features


DATA_PATH = ROOT / "data" / "processed" / "market_indicators.csv"
DEFAULT_OUTPUT = ROOT / "reports" / "market_regime"


def run_workflow(
    output_dir: Path = DEFAULT_OUTPUT,
    *,
    data_path: Path = DATA_PATH,
    target_date: str | None = None,
    config: DashboardConfig | None = None,
) -> None:
    config = config or DashboardConfig()
    raw = load_market_data(data_path)
    featured = add_features(
        raw,
        sma_period=config.sma_period,
        sentiment_lookback_days=config.sentiment_lookback_days,
        repair_ma_days=config.repair_ma_days,
    )
    if target_date is not None:
        target = pd.Timestamp(target_date)
        if target not in featured.index:
            raise ValueError(f"target date not found in market data: {target_date}")
        featured_for_summary = featured.loc[:target]
    else:
        featured_for_summary = featured
    daily = classify_daily(featured_for_summary, config=config)
    summary = latest_summary(featured_for_summary, config=config)
    write_dashboard_outputs(output_dir, daily, summary)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--data-path", type=Path, default=DATA_PATH)
    parser.add_argument("--target-date")
    args = parser.parse_args()
    run_workflow(output_dir=args.output_dir, data_path=args.data_path, target_date=args.target_date)
    print(f"Wrote market regime dashboard to {args.output_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run workflow tests**

Run: `python3 -m unittest tests.test_market_regime.MarketRegimeWorkflowTests -v`

Expected: PASS.

- [ ] **Step 5: Run all market regime tests**

Run: `python3 -m unittest tests.test_market_regime -v`

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add scripts/run_market_regime_dashboard.py tests/test_market_regime.py
git commit -m "feat: add market regime dashboard workflow"
```

Expected: commit succeeds.

---

### Task 7: End-To-End Verification

**Files:**
- Generated: `reports/market_regime/daily_regimes.csv`
- Generated: `reports/market_regime/latest.json`
- Generated: `reports/market_regime/index.html`

- [ ] **Step 1: Run full test suite**

Run: `python3 -m unittest tests.test_market_regime tests.test_version_a -v`

Expected: PASS.

- [ ] **Step 2: Verify fail-fast behavior on current latest row**

Run: `python3 scripts/run_market_regime_dashboard.py --output-dir reports/market_regime`

Expected: FAIL with `ValueError` naming `2026-05-01` and missing `vix`, `vxn`.

- [ ] **Step 3: Generate dashboard for latest complete local row**

Run: `python3 scripts/run_market_regime_dashboard.py --output-dir reports/market_regime --target-date 2026-04-30`

Expected: PASS and prints `Wrote market regime dashboard to reports/market_regime/index.html`.

- [ ] **Step 4: Inspect generated latest summary**

Run: `python3 -m json.tool reports/market_regime/latest.json`

Expected: JSON includes `as_of_date`, `market_regime`, `temperature_score`, `confidence_score`, `dashboard_action`, `drivers`, `risks`, and `inputs`.

- [ ] **Step 5: Check generated CSV columns**

Run: `python3 - <<'PY'
import pandas as pd
df = pd.read_csv("reports/market_regime/daily_regimes.csv")
print(df.columns.tolist())
print(df.tail(3)[["date", "market_regime", "temperature_score", "confidence_score", "dashboard_action"]])
PY`

Expected: output includes configured dashboard columns and latest date `2026-04-30`.

- [ ] **Step 6: Commit generated report**

Run:

```bash
git add reports/market_regime
git commit -m "chore: add market regime dashboard report"
```

Expected: commit succeeds.
