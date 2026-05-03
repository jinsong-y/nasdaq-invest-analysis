# Market Regime Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `warm_recovery` and `top_risk_watch`, tighten pure `recovery`, update bilingual dashboard text, and add a historical evaluation report.

**Architecture:** Keep scoring in `src/market_regime/model.py`, thresholds in `src/market_regime/config.py`, presentation in `src/market_regime/report.py`, and backtest diagnostics in a new standalone script. Latest classification keeps fail-fast validation; historical diagnostics keep `unscorable` rows.

**Tech Stack:** Python 3, pandas, unittest, static HTML/SVG report generation.

---

## File Structure

- Modify `src/market_regime/config.py`: add recovery gate thresholds and `top_risk_watch_threshold`.
- Modify `src/market_regime/model.py`: update regime priority, action mapping, summaries, risks.
- Modify `src/market_regime/report.py`: add new regime bands and bilingual text.
- Modify `tests/test_market_regime.py`: add rule, action, and report text coverage.
- Create `scripts/evaluate_market_regime.py`: compute historical diagnostics from generated daily regime CSV.
- Create `tests/test_market_regime_evaluation.py`: unit-test evaluation helpers and output generation.
- Regenerate `reports/market_regime/`: dashboard HTML, latest JSON, daily regimes.
- Generate `reports/market_regime_evaluation/`: evaluation CSV/JSON/HTML.

---

### Task 1: Add Config Thresholds

**Files:**
- Modify: `src/market_regime/config.py`
- Test: `tests/test_market_regime.py`

- [ ] **Step 1: Write failing config test**

Add these assertions to `MarketRegimeConfigTests.test_default_config_matches_design`:

```python
self.assertEqual(70.0, config.top_risk_watch_threshold)
self.assertEqual(65.0, config.recovery_temperature_ceiling)
self.assertEqual(55.0, config.recovery_top_risk_ceiling)
self.assertEqual(50.0, config.recovery_overheat_ceiling)
self.assertEqual(0.08, config.recovery_dist_sma_ceiling)
self.assertLess(config.top_risk_watch_threshold, config.top_risk_threshold)
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
python3 -m unittest tests.test_market_regime.MarketRegimeConfigTests -v
```

Expected: FAIL with `AttributeError` for `top_risk_watch_threshold`.

- [ ] **Step 3: Add config fields**

In `DashboardConfig`, add:

```python
top_risk_watch_threshold: float = 70.0
recovery_temperature_ceiling: float = 65.0
recovery_top_risk_ceiling: float = 55.0
recovery_overheat_ceiling: float = 50.0
recovery_dist_sma_ceiling: float = 0.08
```

- [ ] **Step 4: Run test and verify pass**

Run:

```bash
python3 -m unittest tests.test_market_regime.MarketRegimeConfigTests -v
```

Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add src/market_regime/config.py tests/test_market_regime.py
git commit -m "feat: add market regime optimization thresholds"
```

---

### Task 2: Update Regime Classification Rules

**Files:**
- Modify: `src/market_regime/model.py`
- Modify: `tests/test_market_regime.py`

- [ ] **Step 1: Write failing classification tests**

Add tests to `MarketRegimeClassificationTests`:

```python
def test_warm_recovery_when_repair_is_high_but_price_extended(self):
    result = self._classify(
        self._row(
            ndx=110.0,
            sma=100.0,
            dist_sma=0.10,
            vxn_pctile=0.40,
            vix_pctile=0.38,
            cnn_fear_greed=66.0,
            cnn_ma5=48.0,
            ndxe_ndx=0.39,
            ndxe_ma=0.35,
            sox_ndx=0.29,
            sox_ma=0.25,
        )
    )
    self.assertEqual("warm_recovery", result.market_regime)
    self.assertEqual("normal_dca", result.dashboard_action)
    self.assertGreaterEqual(result.recovery_score, 55.0)
    self.assertGreaterEqual(result.inputs["dist_sma"], 0.08)


def test_recovery_when_repair_is_high_and_gates_pass(self):
    result = self._classify(
        self._row(
            ndx=104.0,
            sma=100.0,
            dist_sma=0.04,
            vxn_pctile=0.45,
            vix_pctile=0.42,
            cnn_fear_greed=58.0,
            cnn_ma5=42.0,
            ndxe_ndx=0.38,
            ndxe_ma=0.35,
            sox_ndx=0.28,
            sox_ma=0.25,
        )
    )
    self.assertEqual("recovery", result.market_regime)
    self.assertEqual("normal_dca", result.dashboard_action)
    self.assertLess(result.temperature_score, 65.0)
    self.assertLess(result.top_risk_score, 55.0)
    self.assertLess(result.overheat_score, 50.0)


def test_top_risk_watch_between_watch_and_full_threshold(self):
    result = self._classify(
        self._row(
            ndx=118.0,
            sma=100.0,
            dist_sma=0.18,
            vxn_pctile=0.10,
            vix_pctile=0.10,
            cnn_fear_greed=75.0,
            cnn_ma5=72.0,
            ndxe_ndx=0.33,
            ndxe_ma=0.36,
            sox_ndx=0.23,
            sox_ma=0.25,
        )
    )
    self.assertEqual("top_risk_watch", result.market_regime)
    self.assertEqual("pause_new_buy", result.dashboard_action)
    self.assertGreaterEqual(result.top_risk_score, 70.0)
    self.assertLess(result.top_risk_score, 75.0)
```

Update `test_warm_fixture` expected action:

```python
self.assertEqual("reduce_light", result.dashboard_action)
```

- [ ] **Step 2: Run targeted tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_market_regime.MarketRegimeClassificationTests -v
```

Expected: FAIL because `warm_recovery`, `top_risk_watch`, and `reduce_light` are not implemented.

- [ ] **Step 3: Implement helper functions and rules**

In `src/market_regime/model.py`, add helpers near `_confidence_score`:

```python
def _is_recovery_eligible(
    config: DashboardConfig,
    *,
    recovery_score: float,
    temperature_score: float,
    top_risk_score: float,
    overheat_score: float,
    dist_sma: float,
) -> bool:
    return (
        recovery_score >= config.recovery_threshold
        and temperature_score < config.recovery_temperature_ceiling
        and top_risk_score < config.recovery_top_risk_ceiling
        and overheat_score < config.recovery_overheat_ceiling
        and dist_sma < config.recovery_dist_sma_ceiling
    )
```

Pass `dist_sma` into `_market_regime` from `_scorable_result`.

Change `_market_regime` signature to include:

```python
dist_sma: float,
```

Replace `_market_regime` body with:

```python
if undervaluation_score >= config.panic_low_threshold and vol_high >= 0.90 and cnn <= 15.0:
    return "panic_low"
if undervaluation_score >= config.stress_low_threshold:
    return "stress_low"
if top_risk_score >= config.top_risk_threshold:
    return "top_risk"
if top_risk_score >= config.top_risk_watch_threshold:
    return "top_risk_watch"
if overheat_score >= config.overheat_threshold:
    return "overheated"
if _is_recovery_eligible(
    config,
    recovery_score=recovery_score,
    temperature_score=temperature_score,
    top_risk_score=top_risk_score,
    overheat_score=overheat_score,
    dist_sma=dist_sma,
):
    return "recovery"
if recovery_score >= config.recovery_threshold:
    return "warm_recovery"
if temperature_score >= config.warm_threshold:
    return "warm"
return "normal"
```

Update `_dashboard_action`:

```python
if market_regime in {"recovery", "normal", "warm_recovery"}:
    return "normal_dca"
if market_regime == "warm":
    return "reduce_light"
if market_regime == "overheated":
    return "reduce"
if market_regime == "top_risk_watch":
    return "pause_new_buy"
if market_regime == "top_risk":
    return "pause"
```

Update `_summary_text` with:

```python
"warm_recovery": "Repair signals are strong, but conditions are already warm.",
"top_risk_watch": "Top-risk evidence is elevated but below full risk.",
```

Update `_risks` so `top_risk_score >= 70` appends `"top_risk_watch"` before generic `top_risk` naming. Replace the current top-risk risk block with:

```python
if result.top_risk_score >= 75:
    risks.append("top_risk")
elif result.top_risk_score >= 70:
    risks.append("top_risk_watch")
```

- [ ] **Step 4: Run targeted tests and verify pass**

Run:

```bash
python3 -m unittest tests.test_market_regime.MarketRegimeClassificationTests tests.test_market_regime.MarketRegimeSummaryTests -v
```

Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add src/market_regime/model.py tests/test_market_regime.py
git commit -m "feat: refine market regime classification"
```

---

### Task 3: Update Dashboard Labels and Gauge Legend

**Files:**
- Modify: `src/market_regime/report.py`
- Modify: `tests/test_market_regime.py`

- [ ] **Step 1: Write failing report text test**

Add test class:

```python
from src.market_regime.report import ZH_TEXT, REGIME_BANDS


class MarketRegimeReportTextTests(unittest.TestCase):
    def test_report_knows_new_regime_labels(self):
        labels = {band[0]: band[1] for band in REGIME_BANDS}
        self.assertEqual("Warm Recovery", labels["warm_recovery"])
        self.assertEqual("Top Risk Watch", labels["top_risk_watch"])
        self.assertEqual("暖修复", ZH_TEXT["Warm Recovery"])
        self.assertEqual("顶部风险观察", ZH_TEXT["Top Risk Watch"])
        self.assertEqual("暂停新买入", ZH_TEXT["pause_new_buy"])
        self.assertEqual("轻降节奏", ZH_TEXT["reduce_light"])
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
python3 -m unittest tests.test_market_regime.MarketRegimeReportTextTests -v
```

Expected: FAIL because new labels are missing.

- [ ] **Step 3: Update gauge bands**

Replace `REGIME_BANDS` with:

```python
REGIME_BANDS = [
    ("panic_low", "Panic Low", 0, 12, "#7f1d1d", "Severe stress; prices and sentiment are deeply depressed."),
    ("stress_low", "Stress Low", 12, 26, "#c2410c", "Below-trend market with elevated stress."),
    ("recovery", "Recovery", 26, 42, "#d97706", "Repair signals improving after stress."),
    ("normal", "Normal", 42, 58, "#15803d", "Balanced market; no major extreme dominates."),
    ("warm_recovery", "Warm Recovery", 58, 68, "#84cc16", "Repair signals are strong, but conditions are already warm."),
    ("warm", "Warm", 68, 78, "#65a30d", "Above-trend market with warmer conditions."),
    ("overheated", "Overheated", 78, 88, "#dc2626", "Multiple overheat signals are active."),
    ("top_risk_watch", "Top Risk Watch", 88, 94, "#ea580c", "Top-risk evidence is elevated but below full risk."),
    ("top_risk", "Top Risk", 94, 100, "#7c2d12", "Overheat plus structural deterioration risk."),
]
```

- [ ] **Step 4: Update bilingual dictionary**

Add entries to `ZH_TEXT`:

```python
"Warm Recovery": "暖修复",
"Top Risk Watch": "顶部风险观察",
"Repair signals are strong, but conditions are already warm.": "修复信号强，但市场已经偏热。",
"Top-risk evidence is elevated but below full risk.": "顶部风险证据升高，但尚未达到完整风险状态。",
"reduce_light": "轻降节奏",
"pause_new_buy": "暂停新买入",
"top_risk_watch": "顶部风险观察",
```

- [ ] **Step 5: Run report text test**

Run:

```bash
python3 -m unittest tests.test_market_regime.MarketRegimeReportTextTests -v
```

Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add src/market_regime/report.py tests/test_market_regime.py
git commit -m "feat: update market regime dashboard labels"
```

---

### Task 4: Add Evaluation Script

**Files:**
- Create: `scripts/evaluate_market_regime.py`
- Create: `tests/test_market_regime_evaluation.py`

- [ ] **Step 1: Write failing helper tests**

Create `tests/test_market_regime_evaluation.py`:

```python
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_market_regime import (
    FORWARD_HORIZONS,
    evaluate_daily_regimes,
    merge_previous_regimes,
    write_evaluation_outputs,
)


class MarketRegimeEvaluationTests(unittest.TestCase):
    def _sample(self):
        dates = pd.bdate_range("2026-01-01", periods=270)
        regimes = ["normal"] * len(dates)
        regimes[0] = "panic_low"
        regimes[1] = "warm_recovery"
        regimes[2] = "top_risk_watch"
        return pd.DataFrame(
            {
                "date": dates,
                "market_regime": regimes,
                "ndx": [100.0 + i for i in range(len(dates))],
                "temperature_score": [50.0] * len(dates),
                "top_risk_score": [0.0] * len(dates),
                "overheat_score": [0.0] * len(dates),
                "recovery_score": [0.0] * len(dates),
            }
        )

    def test_evaluate_daily_regimes_returns_expected_tables(self):
        current = self._sample()
        previous = current[["date", "market_regime"]].copy()
        previous.loc[previous.index[1], "market_regime"] = "recovery"
        merged = merge_previous_regimes(current, previous)
        result = evaluate_daily_regimes(merged)
        self.assertEqual(list(FORWARD_HORIZONS.values()), ["1m", "3m", "6m", "12m"])
        self.assertIn("regime_summary", result)
        self.assertIn("known_dates", result)
        self.assertIn("classification_changes", result)
        self.assertEqual(1, len(result["classification_changes"]))
        self.assertIn("panic_low", set(result["regime_summary"]["market_regime"]))

    def test_write_evaluation_outputs_creates_files(self):
        result = evaluate_daily_regimes(self._sample())
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_evaluation_outputs(out, result)
            self.assertTrue((out / "summary.json").exists())
            self.assertTrue((out / "regime_summary.csv").exists())
            self.assertTrue((out / "known_dates.csv").exists())
            self.assertTrue((out / "index.html").exists())
            payload = json.loads((out / "summary.json").read_text())
            self.assertIn("generated_at", payload)
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
python3 -m unittest tests.test_market_regime_evaluation -v
```

Expected: FAIL because `scripts.evaluate_market_regime` does not exist.

- [ ] **Step 3: Create evaluation script**

Create `scripts/evaluate_market_regime.py` with these public functions:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


DEFAULT_DAILY = ROOT / "reports" / "market_regime" / "daily_regimes.csv"
DEFAULT_OUTPUT = ROOT / "reports" / "market_regime_evaluation"
FORWARD_HORIZONS = {21: "1m", 63: "3m", 126: "6m", 252: "12m"}
KNOWN_DATES = [
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
]


def _add_forward_metrics(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values("date").reset_index(drop=True).copy()
    for days, label in FORWARD_HORIZONS.items():
        out[f"fwd_{label}"] = out["ndx"].shift(-days) / out["ndx"] - 1.0
    prices = out["ndx"].astype(float)
    mdds = []
    for idx, price in enumerate(prices):
        window = prices.iloc[idx + 1 : idx + 253]
        if len(window) == 252 and pd.notna(price):
            mdds.append(float(window.min() / price - 1.0))
        else:
            mdds.append(float("nan"))
    out["fwd_12m_mdd"] = mdds
    return out


def _regime_summary(df: pd.DataFrame) -> pd.DataFrame:
    scorable = df[df["market_regime"] != "unscorable"].copy()
    rows = []
    for regime, group in scorable.groupby("market_regime", sort=False):
        row: dict[str, Any] = {"market_regime": regime, "count": int(len(group))}
        for label in FORWARD_HORIZONS.values():
            col = f"fwd_{label}"
            row[f"{col}_mean"] = float(group[col].mean())
            row[f"{col}_median"] = float(group[col].median())
            row[f"{col}_hit_rate"] = float((group[col].dropna() > 0).mean())
        row["fwd_12m_mdd_mean"] = float(group["fwd_12m_mdd"].mean())
        rows.append(row)
    return pd.DataFrame(rows).sort_values("market_regime").reset_index(drop=True)


def _known_dates(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for date_text in KNOWN_DATES:
        target = pd.Timestamp(date_text)
        idx = (df["date"] - target).abs().idxmin()
        row = df.loc[idx]
        rows.append(
            {
                "requested_date": date_text,
                "matched_date": row["date"].strftime("%Y-%m-%d"),
                "market_regime": row["market_regime"],
                "temperature_score": row.get("temperature_score"),
                "top_risk_score": row.get("top_risk_score"),
                "overheat_score": row.get("overheat_score"),
                "recovery_score": row.get("recovery_score"),
                "dist_sma": row.get("dist_sma"),
            }
        )
    return pd.DataFrame(rows)


def _classification_changes(df: pd.DataFrame) -> pd.DataFrame:
    if "previous_market_regime" not in df.columns:
        return pd.DataFrame(columns=["date", "previous_market_regime", "market_regime"])
    changed = df[df["previous_market_regime"] != df["market_regime"]]
    return changed[["date", "previous_market_regime", "market_regime"]].copy()


def merge_previous_regimes(current: pd.DataFrame, previous: pd.DataFrame | None) -> pd.DataFrame:
    if previous is None:
        return current.copy()
    required = {"date", "market_regime"}
    missing = sorted(required - set(previous.columns))
    if missing:
        raise ValueError(f"missing previous-regime columns: {missing}")
    left = current.copy()
    left["date"] = pd.to_datetime(left["date"])
    right = previous[["date", "market_regime"]].copy()
    right["date"] = pd.to_datetime(right["date"])
    right = right.rename(columns={"market_regime": "previous_market_regime"})
    return left.merge(right, on="date", how="left")


def evaluate_daily_regimes(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    required = {"date", "market_regime", "ndx"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"missing evaluation columns: {missing}")
    working = df.copy()
    working["date"] = pd.to_datetime(working["date"])
    working = _add_forward_metrics(working)
    return {
        "daily_with_forward": working,
        "regime_summary": _regime_summary(working),
        "known_dates": _known_dates(working),
        "classification_changes": _classification_changes(working),
    }


def _html_table(title: str, frame: pd.DataFrame) -> str:
    return f"<h2>{title}</h2>\\n{frame.to_html(index=False, float_format=lambda value: f'{value:.4f}')}"


def write_evaluation_outputs(output_dir: Path, result: dict[str, pd.DataFrame]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result["daily_with_forward"].to_csv(output_dir / "daily_with_forward.csv", index=False)
    result["regime_summary"].to_csv(output_dir / "regime_summary.csv", index=False)
    result["known_dates"].to_csv(output_dir / "known_dates.csv", index=False)
    result["classification_changes"].to_csv(output_dir / "classification_changes.csv", index=False)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": int(len(result["daily_with_forward"])),
        "scorable_rows": int((result["daily_with_forward"]["market_regime"] != "unscorable").sum()),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    html = "\\n".join(
        [
            "<!doctype html><meta charset='utf-8'><title>Market Regime Evaluation</title>",
            "<style>body{font-family:Arial,sans-serif;margin:32px;color:#18202a}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:6px 8px}</style>",
            "<h1>Market Regime Evaluation</h1>",
            _html_table("Regime Summary", result["regime_summary"]),
            _html_table("Known Dates", result["known_dates"]),
            _html_table("Classification Changes", result["classification_changes"].head(100)),
        ]
    )
    (output_dir / "index.html").write_text(html, encoding="utf-8")


def run_workflow(
    daily_path: Path = DEFAULT_DAILY,
    output_dir: Path = DEFAULT_OUTPUT,
    previous_daily_path: Path | None = None,
) -> None:
    if not daily_path.exists():
        raise FileNotFoundError(f"daily regimes file not found: {daily_path}")
    df = pd.read_csv(daily_path)
    previous = None
    if previous_daily_path is not None:
        if not previous_daily_path.exists():
            raise FileNotFoundError(f"previous daily regimes file not found: {previous_daily_path}")
        previous = pd.read_csv(previous_daily_path)
    result = evaluate_daily_regimes(merge_previous_regimes(df, previous))
    write_evaluation_outputs(output_dir, result)


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
```

- [ ] **Step 4: Run evaluation tests**

Run:

```bash
python3 -m unittest tests.test_market_regime_evaluation -v
```

Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add scripts/evaluate_market_regime.py tests/test_market_regime_evaluation.py
git commit -m "feat: add market regime evaluation report"
```

---

### Task 5: Regenerate Reports and Verify Historical Behavior

**Files:**
- Modify generated: `reports/market_regime/daily_regimes.csv`
- Modify generated: `reports/market_regime/index.html`
- Modify generated: `reports/market_regime/latest.json`
- Create generated: `reports/market_regime_evaluation/daily_with_forward.csv`
- Create generated: `reports/market_regime_evaluation/regime_summary.csv`
- Create generated: `reports/market_regime_evaluation/known_dates.csv`
- Create generated: `reports/market_regime_evaluation/classification_changes.csv`
- Create generated: `reports/market_regime_evaluation/summary.json`
- Create generated: `reports/market_regime_evaluation/index.html`

- [ ] **Step 1: Run full unit suite**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: OK.

- [ ] **Step 2: Regenerate dashboard**

Run:

```bash
cp reports/market_regime/daily_regimes.csv /tmp/market_regime_daily_before_optimization.csv
python3 scripts/run_market_regime_dashboard.py --output-dir reports/market_regime --target-date 2026-04-30
```

Expected: copies the pre-optimization daily regimes, then prints `Wrote market regime dashboard to reports/market_regime/index.html`.

- [ ] **Step 3: Run evaluation**

Run:

```bash
python3 scripts/evaluate_market_regime.py --daily-path reports/market_regime/daily_regimes.csv --previous-daily-path /tmp/market_regime_daily_before_optimization.csv --output-dir reports/market_regime_evaluation
```

Expected: prints `Wrote market regime evaluation to reports/market_regime_evaluation/index.html`.

- [ ] **Step 4: Verify key-date outcomes**

Run:

```bash
python3 - <<'PY'
import pandas as pd
df = pd.read_csv("reports/market_regime_evaluation/known_dates.csv")
print(df[["requested_date", "market_regime"]].to_string(index=False))
checks = {
    "2021-11-19": "warm_recovery",
    "2024-07-10": "warm_recovery",
    "2026-04-30": "warm_recovery",
}
actual = dict(zip(df["requested_date"], df["market_regime"]))
for date, expected in checks.items():
    if actual.get(date) != expected:
        raise SystemExit(f"{date}: expected {expected}, got {actual.get(date)}")
PY
```

Expected: command exits `0`.

- [ ] **Step 5: Verify latest JSON**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path("reports/market_regime/latest.json").read_text())
print(payload["as_of_date"], payload["market_regime"], payload["dashboard_action"])
if payload["as_of_date"] != "2026-04-30":
    raise SystemExit("wrong latest date")
if payload["market_regime"] != "warm_recovery":
    raise SystemExit("latest regime should be warm_recovery")
if payload["dashboard_action"] != "normal_dca":
    raise SystemExit("latest action should be normal_dca")
PY
```

Expected: prints `2026-04-30 warm_recovery normal_dca`.

- [ ] **Step 6: Commit generated reports**

```bash
git add reports/market_regime reports/market_regime_evaluation
git commit -m "chore: refresh market regime reports"
```

---

### Task 6: Final Verification and Browser Check

**Files:**
- No planned code edits.

- [ ] **Step 1: Run full unit suite**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: OK.

- [ ] **Step 2: Inspect git status**

Run:

```bash
git status --short
```

Expected: only unrelated Version C user changes may remain:

```text
 M scripts/run_version_c_pe_backtest.py
 M src/version_c/data.py
 M src/version_c/engine.py
 M tests/test_version_c.py
?? reports/version_c_pe_5000/
?? reports/version_c_pe_5000_2020_2026/
```

- [ ] **Step 3: Browser verification**

Open:

```text
file:///Users/jinsong/Downloads/nasdq-analysis/reports/market_regime/index.html
```

Verify:

- gauge renders
- English/Chinese toggle works
- latest state shows `warm_recovery` / `暖修复`
- legend includes `Top Risk Watch` / `顶部风险观察`
- no overlapping text

- [ ] **Step 4: Final summary**

Report:

- optimized latest regime
- key-date sanity results
- tests run
- generated report paths
- note unrelated Version C dirty files were not touched
