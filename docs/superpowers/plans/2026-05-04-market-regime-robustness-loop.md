# Market Regime Robustness Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a threshold-only robustness loop that ranks market-regime configs, writes a recommended `DashboardConfig`, and refreshes HTML reports using that recommendation.

**Architecture:** Add a standalone robustness script under `scripts/` and keep model score formulas unchanged. The script generates candidate `DashboardConfig` values, classifies history, scores robustness, writes CSV/JSON/HTML outputs, writes a usable `recommended_config.py`, then refreshes the market-regime dashboard with the recommended config and visible config metadata.

**Tech Stack:** Python 3, pandas, unittest, existing `src.market_regime` and `src.version_a` modules, static HTML.

---

## File Structure

- Create `scripts/run_market_regime_robustness.py`: grid generation, scoring, output writing, recommendation file generation, and optional dashboard refresh.
- Create `tests/test_market_regime_robustness.py`: focused unit tests for grid validity, scoring, recommendation file content, and output files.
- Modify `src/market_regime/report.py`: allow dashboard summary metadata to show config source, recommendation timestamp, and robustness report path.
- Modify `scripts/run_market_regime_dashboard.py`: accept optional recommended-config module path or config object support without changing default behavior.
- Generate `reports/market_regime_robustness/`: grid and recommendation artifacts.
- Regenerate `reports/market_regime/`: dashboard HTML/latest/daily using the recommended config or visibly labeled current config.

---

### Task 1: Robustness Grid Core

**Files:**
- Create: `scripts/run_market_regime_robustness.py`
- Create: `tests/test_market_regime_robustness.py`

- [ ] **Step 1: Write failing grid tests**

Create `tests/test_market_regime_robustness.py` with imports and tests:

```python
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_market_regime_robustness import (
    GRID_VALUES,
    config_id,
    generate_candidate_configs,
)
from src.market_regime.config import DashboardConfig


class MarketRegimeRobustnessGridTests(unittest.TestCase):
    def test_generate_candidate_configs_skips_invalid_threshold_orders(self):
        configs = list(generate_candidate_configs())
        self.assertGreater(len(configs), 0)
        self.assertLess(len(configs), 3 * 4 * 3 * 3 * 2 * 3 * 3 * 3 * 3 * 3)
        for config in configs:
            self.assertLess(config.top_risk_watch_threshold, config.top_risk_threshold)
            self.assertLess(config.warm_threshold, config.overheat_threshold)
            self.assertLess(config.recovery_top_risk_ceiling, config.top_risk_watch_threshold)

    def test_config_id_is_stable_and_includes_thresholds(self):
        config = DashboardConfig(
            stress_low_threshold=55.0,
            recovery_threshold=60.0,
            warm_threshold=60.0,
            overheat_threshold=70.0,
            top_risk_watch_threshold=70.0,
            top_risk_threshold=75.0,
            recovery_temperature_ceiling=65.0,
            recovery_top_risk_ceiling=55.0,
            recovery_overheat_ceiling=50.0,
            recovery_dist_sma_ceiling=0.08,
        )
        ident = config_id(config)
        self.assertIn("stress55", ident)
        self.assertIn("rec60", ident)
        self.assertIn("top75", ident)

    def test_grid_values_match_spec(self):
        self.assertEqual([50.0, 55.0, 60.0], GRID_VALUES["stress_low_threshold"])
        self.assertEqual([50.0, 55.0, 60.0, 65.0], GRID_VALUES["recovery_threshold"])
        self.assertEqual([0.06, 0.08, 0.10], GRID_VALUES["recovery_dist_sma_ceiling"])
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
python3 -m unittest tests.test_market_regime_robustness -v
```

Expected: FAIL because `scripts.run_market_regime_robustness` does not exist.

- [ ] **Step 3: Implement grid core**

Create `scripts/run_market_regime_robustness.py` with:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market_regime.config import DashboardConfig
from src.market_regime.model import classify_daily, latest_summary
from src.market_regime.report import write_dashboard_outputs
from src.version_a.data import load_market_data
from src.version_a.features import add_features


DATA_PATH = ROOT / "data" / "processed" / "market_indicators.csv"
DEFAULT_OUTPUT = ROOT / "reports" / "market_regime_robustness"
DEFAULT_DASHBOARD_OUTPUT = ROOT / "reports" / "market_regime"
TARGET_DATE = "2026-04-30"

GRID_VALUES: dict[str, list[float]] = {
    "stress_low_threshold": [50.0, 55.0, 60.0],
    "recovery_threshold": [50.0, 55.0, 60.0, 65.0],
    "warm_threshold": [55.0, 60.0, 65.0],
    "overheat_threshold": [65.0, 70.0, 75.0],
    "top_risk_watch_threshold": [65.0, 70.0],
    "top_risk_threshold": [72.5, 75.0, 80.0],
    "recovery_temperature_ceiling": [60.0, 65.0, 70.0],
    "recovery_top_risk_ceiling": [50.0, 55.0, 60.0],
    "recovery_overheat_ceiling": [45.0, 50.0, 55.0],
    "recovery_dist_sma_ceiling": [0.06, 0.08, 0.10],
}


def is_valid_config(config: DashboardConfig) -> bool:
    return (
        config.top_risk_watch_threshold < config.top_risk_threshold
        and config.warm_threshold < config.overheat_threshold
        and config.recovery_top_risk_ceiling < config.top_risk_watch_threshold
    )


def generate_candidate_configs() -> Iterable[DashboardConfig]:
    keys = list(GRID_VALUES)
    for values in itertools.product(*(GRID_VALUES[key] for key in keys)):
        overrides = dict(zip(keys, values))
        config = DashboardConfig(**overrides)
        if is_valid_config(config):
            yield config


def _fmt(value: float) -> str:
    return str(value).replace(".", "p")


def config_id(config: DashboardConfig) -> str:
    return "_".join(
        [
            f"stress{_fmt(config.stress_low_threshold)}",
            f"rec{_fmt(config.recovery_threshold)}",
            f"warm{_fmt(config.warm_threshold)}",
            f"over{_fmt(config.overheat_threshold)}",
            f"watch{_fmt(config.top_risk_watch_threshold)}",
            f"top{_fmt(config.top_risk_threshold)}",
            f"rectemp{_fmt(config.recovery_temperature_ceiling)}",
            f"rectop{_fmt(config.recovery_top_risk_ceiling)}",
            f"recover{_fmt(config.recovery_overheat_ceiling)}",
            f"recdist{_fmt(config.recovery_dist_sma_ceiling)}",
        ]
    )
```

- [ ] **Step 4: Run test**

Run:

```bash
python3 -m unittest tests.test_market_regime_robustness -v
```

Expected: OK for the three grid tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_market_regime_robustness.py tests/test_market_regime_robustness.py
git commit -m "feat: add market regime robustness grid"
```

---

### Task 2: Robustness Scoring

**Files:**
- Modify: `scripts/run_market_regime_robustness.py`
- Modify: `tests/test_market_regime_robustness.py`

- [ ] **Step 1: Add scoring tests**

Append:

```python
import pandas as pd

from scripts.run_market_regime_robustness import (
    EXTREME_DATE_EXPECTATIONS,
    add_forward_metrics,
    build_misclassification_review,
    build_walk_forward_table,
    evaluate_config_result,
    score_extreme_dates,
    score_state_stability,
)


class MarketRegimeRobustnessScoringTests(unittest.TestCase):
    def _daily(self):
        dates = pd.bdate_range("2026-01-01", periods=270)
        regimes = ["normal"] * len(dates)
        regimes[0:5] = ["panic_low"] * 5
        regimes[50:55] = ["top_risk"] * 5
        return pd.DataFrame(
            {
                "date": dates,
                "market_regime": regimes,
                "ndx": [100.0 + i for i in range(len(dates))],
                "temperature_score": [50.0] * len(dates),
                "undervaluation_score": [0.0] * len(dates),
                "overheat_score": [0.0] * len(dates),
                "top_risk_score": [0.0] * len(dates),
                "recovery_score": [0.0] * len(dates),
            }
        )

    def test_add_forward_metrics_adds_returns_and_mdd(self):
        out = add_forward_metrics(self._daily())
        self.assertIn("fwd_1m", out.columns)
        self.assertIn("fwd_12m_mdd", out.columns)

    def test_state_stability_penalizes_churn(self):
        stable = self._daily()
        churn = stable.copy()
        churn["market_regime"] = ["normal", "warm"] * (len(churn) // 2)
        self.assertGreater(score_state_stability(stable), score_state_stability(churn))

    def test_extreme_dates_score_accepts_expected_regime(self):
        rows = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-04-30"]),
                "market_regime": ["warm_recovery"],
            }
        )
        score, table = score_extreme_dates(rows)
        latest = table[table["requested_date"] == "2026-04-30"].iloc[0]
        self.assertGreater(score, 0)
        self.assertEqual("pass", latest["result"])

    def test_evaluate_config_result_returns_robust_score(self):
        result = evaluate_config_result("sample", DashboardConfig(), self._daily())
        self.assertIn("robust_score", result)
        self.assertIn("low_zone_quality", result)
        self.assertIn("top_warning_quality", result)

    def test_walk_forward_table_scores_named_windows(self):
        table = build_walk_forward_table("sample", DashboardConfig(), self._daily())
        self.assertIn("window_name", table.columns)
        self.assertIn("robust_score", table.columns)

    def test_misclassification_review_marks_failed_extreme_dates(self):
        daily = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-04-30"]),
                "market_regime": ["normal"],
                "ndx": [100.0],
            }
        )
        review = build_misclassification_review("sample", daily)
        latest = review[review["requested_date"] == "2026-04-30"].iloc[0]
        self.assertEqual("2026-04-30", latest["requested_date"])
        self.assertEqual("fail", latest["result"])
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_market_regime_robustness -v
```

Expected: FAIL because scoring functions do not exist.

- [ ] **Step 3: Implement scoring functions**

Add:

```python
EXTREME_DATE_EXPECTATIONS: dict[str, set[str]] = {
    "2011-08-08": {"panic_low", "stress_low"},
    "2015-08-24": {"panic_low", "stress_low"},
    "2018-12-24": {"panic_low", "stress_low"},
    "2020-02-19": {"warm", "overheated", "top_risk_watch", "top_risk"},
    "2020-03-16": {"panic_low", "stress_low"},
    "2021-11-19": {"warm_recovery", "warm", "overheated", "top_risk_watch", "top_risk"},
    "2022-10-14": {"panic_low", "stress_low"},
    "2024-07-10": {"warm_recovery", "overheated", "top_risk_watch", "top_risk"},
    "2026-04-30": {"warm_recovery"},
}

FORWARD_HORIZONS = {21: "1m", 63: "3m", 126: "6m", 252: "12m"}


def add_forward_metrics(daily: pd.DataFrame) -> pd.DataFrame:
    out = daily.copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values("date").reset_index(drop=True)
    out = out[pd.to_numeric(out["ndx"], errors="coerce").notna()].copy()
    out["ndx"] = pd.to_numeric(out["ndx"], errors="raise")
    for days, label in FORWARD_HORIZONS.items():
        out[f"fwd_{label}"] = out["ndx"].shift(-days) / out["ndx"] - 1.0
    mdds = []
    for idx, start in enumerate(out["ndx"]):
        window = out["ndx"].iloc[idx + 1 : idx + 253]
        if len(window) < 252:
            mdds.append(float("nan"))
            continue
        peak = start
        drawdown = 0.0
        for value in window:
            peak = max(peak, value)
            drawdown = min(drawdown, value / peak - 1.0)
        mdds.append(drawdown)
    out["fwd_12m_mdd"] = mdds
    return out


def _mean_or_zero(series: pd.Series) -> float:
    valid = series.dropna()
    return 0.0 if valid.empty else float(valid.mean())


def _win_or_zero(series: pd.Series) -> float:
    valid = series.dropna()
    return 0.0 if valid.empty else float((valid > 0).mean())


def score_low_zone(daily: pd.DataFrame) -> float:
    base_12m = _mean_or_zero(daily["fwd_12m"])
    low = daily[daily["market_regime"].isin(["panic_low", "stress_low"])]
    if len(low) < 20:
        return -20.0
    return (
        max(0.0, (_mean_or_zero(low["fwd_12m"]) - base_12m) * 100.0)
        + _win_or_zero(low["fwd_12m"]) * 20.0
    )


def score_top_warning(daily: pd.DataFrame) -> float:
    base_3m = _mean_or_zero(daily["fwd_3m"])
    top = daily[daily["market_regime"].isin(["top_risk", "top_risk_watch", "overheated"])]
    if len(top) < 20:
        return -10.0
    too_common_penalty = max(0.0, len(top) / len(daily) - 0.20) * 100.0
    return max(0.0, (base_3m - _mean_or_zero(top["fwd_3m"])) * 100.0) + (1.0 - _win_or_zero(top["fwd_3m"])) * 20.0 - too_common_penalty


def score_state_stability(daily: pd.DataFrame) -> float:
    working = daily.sort_values("date").copy()
    switches = working["market_regime"].ne(working["market_regime"].shift()).sum()
    months = max(1, working["date"].dt.to_period("M").nunique())
    switches_per_month = switches / months
    return max(0.0, 25.0 - switches_per_month * 2.0)


def score_extreme_dates(daily: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    rows = []
    date_values = daily["date"].astype("int64")
    for requested_text, allowed in EXTREME_DATE_EXPECTATIONS.items():
        requested = pd.Timestamp(requested_text)
        idx = (date_values - requested.value).abs().idxmin()
        row = daily.loc[idx]
        result = "pass" if row["market_regime"] in allowed else "fail"
        rows.append(
            {
                "requested_date": requested_text,
                "matched_date": row["date"].strftime("%Y-%m-%d"),
                "market_regime": row["market_regime"],
                "allowed_regimes": ",".join(sorted(allowed)),
                "result": result,
            }
        )
    table = pd.DataFrame(rows)
    return float((table["result"] == "pass").mean() * 30.0), table


def evaluate_config_result(config_name: str, config: DashboardConfig, daily: pd.DataFrame) -> dict[str, Any]:
    scored = add_forward_metrics(daily)
    low = score_low_zone(scored)
    top = score_top_warning(scored)
    stability = score_state_stability(scored)
    extreme, _ = score_extreme_dates(scored)
    robust_score = low + top + stability + extreme
    return {
        "config_id": config_name,
        **asdict(config),
        "low_zone_quality": low,
        "top_warning_quality": top,
        "state_stability": stability,
        "extreme_date_accuracy": extreme,
        "robust_score": robust_score,
    }


WALK_FORWARD_WINDOWS = (
    ("2011_2015", "2011-01-01", "2015-12-31"),
    ("2016_2020", "2016-01-01", "2020-12-31"),
    ("2021_2026", "2021-01-01", "2026-04-30"),
    ("stress_2011", "2011-07-01", "2011-12-31"),
    ("stress_2015", "2015-08-01", "2016-02-29"),
    ("stress_2018", "2018-10-01", "2019-03-31"),
    ("stress_2020", "2020-02-01", "2020-06-30"),
    ("stress_2021_2022", "2021-10-01", "2022-12-31"),
    ("stress_2024", "2024-06-01", "2024-09-30"),
)


def build_walk_forward_table(config_name: str, config: DashboardConfig, daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    working = daily.copy()
    working["date"] = pd.to_datetime(working["date"])
    for name, start, end in WALK_FORWARD_WINDOWS:
        window = working[(working["date"] >= pd.Timestamp(start)) & (working["date"] <= pd.Timestamp(end))]
        if window.empty:
            continue
        score = evaluate_config_result(config_name, config, window)
        rows.append({"window_name": name, **score})
    return pd.DataFrame(rows)


def build_misclassification_review(config_name: str, daily: pd.DataFrame) -> pd.DataFrame:
    scored = add_forward_metrics(daily)
    _, extreme = score_extreme_dates(scored)
    failed = extreme[extreme["result"] == "fail"].copy()
    failed.insert(0, "config_id", config_name)
    return failed
```

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m unittest tests.test_market_regime_robustness -v
```

Expected: OK for grid and scoring tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_market_regime_robustness.py tests/test_market_regime_robustness.py
git commit -m "feat: score market regime robustness"
```

---

### Task 3: End-to-End Robustness Workflow and Outputs

**Files:**
- Modify: `scripts/run_market_regime_robustness.py`
- Modify: `tests/test_market_regime_robustness.py`

- [ ] **Step 1: Add output tests**

Append:

```python
import json
import tempfile

from scripts.run_market_regime_robustness import (
    write_outputs,
    write_recommended_config,
)


class MarketRegimeRobustnessOutputTests(unittest.TestCase):
    def _sample(self):
        dates = pd.bdate_range("2026-01-01", periods=270)
        return pd.DataFrame(
            {
                "date": dates,
                "market_regime": ["normal"] * len(dates),
                "ndx": [100.0 + i for i in range(len(dates))],
            }
        )

    def test_write_recommended_config_creates_importable_factory(self):
        config = DashboardConfig(stress_low_threshold=60.0, recovery_threshold=65.0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recommended_config.py"
            write_recommended_config(path, config)
            text = path.read_text()
            self.assertIn("def recommended_config() -> DashboardConfig:", text)
            self.assertIn("stress_low_threshold=60.0", text)
            self.assertIn("recovery_threshold=65.0", text)

    def test_write_outputs_creates_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            config = DashboardConfig()
            grid = pd.DataFrame([evaluate_config_result("current", config, self._sample())])
            extreme = pd.DataFrame(
                [{"requested_date": "2026-04-30", "market_regime": "warm_recovery", "result": "pass"}]
            )
            write_outputs(out, grid, grid.head(1), pd.DataFrame(), extreme, pd.DataFrame(), config, config)
            for name in [
                "grid_results.csv",
                "top_configs.csv",
                "walk_forward.csv",
                "extreme_dates.csv",
                "misclassification_review.csv",
                "recommendation.json",
                "recommended_config.py",
                "index.html",
            ]:
                self.assertTrue((out / name).exists(), name)
            payload = json.loads((out / "recommendation.json").read_text())
            self.assertIn("recommended_config", payload)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_market_regime_robustness -v
```

Expected: FAIL because output functions do not exist.

- [ ] **Step 3: Implement output functions**

Add:

```python
def config_to_dict(config: DashboardConfig) -> dict[str, Any]:
    return asdict(config)


def write_recommended_config(path: Path, config: DashboardConfig) -> None:
    values = config_to_dict(config)
    args = ",\n        ".join(f"{key}={value!r}" for key, value in values.items())
    text = (
        "from __future__ import annotations\n\n"
        "from src.market_regime.config import DashboardConfig\n\n\n"
        "def recommended_config() -> DashboardConfig:\n"
        f"    return DashboardConfig(\n        {args}\n    )\n"
    )
    path.write_text(text, encoding="utf-8")


def _render_robustness_html(grid: pd.DataFrame, top: pd.DataFrame, recommendation: dict[str, Any]) -> str:
    title = "Market Regime Robustness"
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>{escape(title)}</title>
<style>body{{font-family:Arial,sans-serif;margin:32px;color:#18202a}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:6px 8px}}pre{{background:#f6f7f9;padding:12px;white-space:pre-wrap}}</style></head>
<body>
<h1>{escape(title)}</h1>
<h2>Recommendation</h2>
<pre>{escape(json.dumps(recommendation, indent=2, sort_keys=True))}</pre>
<h2>Top Configs</h2>
{top.to_html(index=False, float_format="{:.4f}".format)}
<h2>Grid Results</h2>
{grid.head(200).to_html(index=False, float_format="{:.4f}".format)}
</body></html>
"""


def write_outputs(
    output_dir: Path,
    grid_results: pd.DataFrame,
    top_configs: pd.DataFrame,
    walk_forward: pd.DataFrame,
    extreme_dates: pd.DataFrame,
    misclassification_review: pd.DataFrame,
    current_config: DashboardConfig,
    recommended_config_value: DashboardConfig,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    grid_results.to_csv(output_dir / "grid_results.csv", index=False)
    top_configs.to_csv(output_dir / "top_configs.csv", index=False)
    walk_forward.to_csv(output_dir / "walk_forward.csv", index=False)
    extreme_dates.to_csv(output_dir / "extreme_dates.csv", index=False)
    misclassification_review.to_csv(output_dir / "misclassification_review.csv", index=False)
    recommendation = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_config": config_to_dict(current_config),
        "recommended_config": config_to_dict(recommended_config_value),
        "robust_score": None if top_configs.empty else float(top_configs.iloc[0]["robust_score"]),
        "key_improvements": [],
        "remaining_weaknesses": [],
        "proceed_to_approach_b": False,
    }
    (output_dir / "recommendation.json").write_text(
        json.dumps(recommendation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_recommended_config(output_dir / "recommended_config.py", recommended_config_value)
    (output_dir / "index.html").write_text(
        _render_robustness_html(grid_results, top_configs, recommendation),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run tests**

Run:

```bash
python3 -m unittest tests.test_market_regime_robustness -v
```

Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_market_regime_robustness.py tests/test_market_regime_robustness.py
git commit -m "feat: write market regime robustness outputs"
```

---

### Task 4: Dashboard Config Metadata

**Files:**
- Modify: `src/market_regime/report.py`
- Modify: `scripts/run_market_regime_dashboard.py`
- Modify: `tests/test_market_regime.py`

- [ ] **Step 1: Add dashboard metadata test**

In `tests/test_market_regime.py`, add to `MarketRegimeReportTests`:

```python
def test_write_dashboard_outputs_renders_config_metadata(self):
    daily = self._daily()
    summary = self._summary()
    summary["config_metadata"] = {
        "config_source": "recommended robustness config",
        "recommendation_generated_at": "2026-05-04T00:00:00+00:00",
        "robustness_report_path": "reports/market_regime_robustness/index.html",
    }
    with tempfile.TemporaryDirectory() as tmp:
        write_dashboard_outputs(Path(tmp), daily, summary)
        html = (Path(tmp) / "index.html").read_text()
    self.assertIn("recommended robustness config", html)
    self.assertIn("reports/market_regime_robustness/index.html", html)
```

- [ ] **Step 2: Run targeted test and verify failure**

Run:

```bash
python3 -m unittest tests.test_market_regime.MarketRegimeReportTests.test_write_dashboard_outputs_renders_config_metadata -v
```

Expected: FAIL because metadata is not rendered.

- [ ] **Step 3: Render metadata in report**

In `src/market_regime/report.py`, update HTML generation to render an optional panel when `summary.get("config_metadata")` exists:

```python
def _config_metadata_html(summary: dict[str, Any]) -> str:
    metadata = summary.get("config_metadata")
    if not metadata:
        return ""
    items = "".join(
        f"<li><strong>{escape(str(key))}</strong>: {escape(str(value))}</li>"
        for key, value in metadata.items()
    )
    return f"<h2>{_localized('Config')}</h2><div class=\"panel\"><ul>{items}</ul></div>"
```

Insert `_config_metadata_html(summary)` after the summary cards and before gauge or after gauge, following existing report structure.

Add this translation entry:

```python
ZH_TEXT["Config"] = "配置"
```

- [ ] **Step 4: Add optional config import support to dashboard script**

In `scripts/run_market_regime_dashboard.py`, add `import json` near the other imports and add CLI:

```python
parser.add_argument("--recommended-config-path", type=Path)
```

Add helper:

```python
def load_recommended_config(path: Path) -> DashboardConfig:
    import importlib.util
    spec = importlib.util.spec_from_file_location("recommended_market_regime_config", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load recommended config: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.recommended_config()
```

When provided, use this config and attach summary metadata before `write_dashboard_outputs`:

```python
recommendation = json.loads((path.parent / "recommendation.json").read_text())
summary["config_metadata"] = {
    "config_source": "recommended robustness config",
    "recommendation_generated_at": recommendation["generated_at"],
    "robustness_report_path": "reports/market_regime_robustness/index.html",
}
```

Read `reports/market_regime_robustness/recommendation.json` when it exists next to the recommended config file. Use its `generated_at` value as `recommendation_generated_at`. If the JSON file is missing, raise `FileNotFoundError`; do not silently use a fallback timestamp.

- [ ] **Step 5: Run tests**

Run:

```bash
python3 -m unittest tests.test_market_regime.MarketRegimeReportTests -v
```

Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add src/market_regime/report.py scripts/run_market_regime_dashboard.py tests/test_market_regime.py
git commit -m "feat: show market regime config metadata"
```

---

### Task 5: Run Robustness Loop and Refresh Reports

**Files:**
- Modify: `scripts/run_market_regime_robustness.py`
- Generate: `reports/market_regime_robustness/*`
- Regenerate: `reports/market_regime/*`

- [ ] **Step 1: Implement workflow main**

Add `run_workflow`:

```python
def _featured_market_data(data_path: Path, config: DashboardConfig) -> pd.DataFrame:
    raw = load_market_data(data_path)
    return add_features(
        raw,
        sma_period=config.sma_period,
        sentiment_lookback_days=config.sentiment_lookback_days,
        repair_ma_days=config.repair_ma_days,
    )


def run_workflow(
    output_dir: Path = DEFAULT_OUTPUT,
    data_path: Path = DATA_PATH,
    dashboard_output_dir: Path = DEFAULT_DASHBOARD_OUTPUT,
    target_date: str = TARGET_DATE,
    max_configs: int | None = None,
) -> DashboardConfig:
    current_config = DashboardConfig()
    featured = _featured_market_data(data_path, current_config)
    rows = []
    walk_rows = []
    daily_by_config: dict[str, pd.DataFrame] = {}
    for index, config in enumerate(generate_candidate_configs()):
        if max_configs is not None and index >= max_configs:
            break
        daily = classify_daily(featured, config=config)
        name = config_id(config)
        daily_by_config[name] = daily
        rows.append(evaluate_config_result(name, config, daily))
        walk = build_walk_forward_table(name, config, daily)
        if not walk.empty:
            walk_rows.extend(walk.to_dict("records"))
    grid = pd.DataFrame(rows).sort_values("robust_score", ascending=False)
    top = grid.head(25).copy()
    walk_forward = pd.DataFrame(walk_rows)
    best_row = top.iloc[0]
    best_config = DashboardConfig(
        **{key: best_row[key] for key in asdict(DashboardConfig()).keys()}
    )
    best_daily = daily_by_config[best_row["config_id"]]
    _, extreme_dates = score_extreme_dates(add_forward_metrics(best_daily))
    misclassification_review = build_misclassification_review(best_row["config_id"], best_daily)
    write_outputs(
        output_dir,
        grid,
        top,
        walk_forward,
        extreme_dates,
        misclassification_review,
        current_config,
        best_config,
    )
    featured_for_summary = featured.loc[: pd.Timestamp(target_date)]
    daily = classify_daily(featured_for_summary, config=best_config)
    summary = latest_summary(featured_for_summary, config=best_config)
    summary["config_metadata"] = {
        "config_source": "recommended robustness config",
        "recommendation_generated_at": datetime.now(timezone.utc).isoformat(),
        "robustness_report_path": str(output_dir / "index.html"),
    }
    write_dashboard_outputs(dashboard_output_dir, daily, summary)
    return best_config
```

Add CLI:

```python
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--data-path", type=Path, default=DATA_PATH)
    parser.add_argument("--dashboard-output-dir", type=Path, default=DEFAULT_DASHBOARD_OUTPUT)
    parser.add_argument("--target-date", default=TARGET_DATE)
    parser.add_argument("--max-configs", type=int)
    args = parser.parse_args()
    config = run_workflow(
        output_dir=args.output_dir,
        data_path=args.data_path,
        dashboard_output_dir=args.dashboard_output_dir,
        target_date=args.target_date,
        max_configs=args.max_configs,
    )
    print(f"Wrote robustness report to {args.output_dir / 'index.html'}")
    print(f"Recommended config: {config}")
    return 0
```

- [ ] **Step 2: Run a smoke loop**

Run:

```bash
python3 scripts/run_market_regime_robustness.py --output-dir /tmp/market_regime_robustness_smoke --dashboard-output-dir /tmp/market_regime_dashboard_smoke --max-configs 5
```

Expected: exits `0`, writes smoke reports.

- [ ] **Step 3: Run full loop**

Run:

```bash
python3 scripts/run_market_regime_robustness.py --output-dir reports/market_regime_robustness --dashboard-output-dir reports/market_regime --target-date 2026-04-30
```

Expected: exits `0`, writes robustness and refreshed dashboard reports.

- [ ] **Step 4: Verify outputs**

Run:

```bash
python3 - <<'PY'
import importlib.util
import json
from pathlib import Path

root = Path("reports/market_regime_robustness")
for name in [
    "grid_results.csv",
    "top_configs.csv",
    "walk_forward.csv",
    "extreme_dates.csv",
    "misclassification_review.csv",
    "recommendation.json",
    "recommended_config.py",
    "index.html",
]:
    if not (root / name).exists():
        raise SystemExit(f"missing {name}")
payload = json.loads((root / "recommendation.json").read_text())
print("robust_score", payload["robust_score"])
spec = importlib.util.spec_from_file_location("recommended_config", root / "recommended_config.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module.recommended_config())
html = Path("reports/market_regime/index.html").read_text()
if "recommended robustness config" not in html:
    raise SystemExit("dashboard missing recommended config metadata")
PY
```

Expected: prints robust score and config; exits `0`.

- [ ] **Step 5: Run full tests**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: OK.

- [ ] **Step 6: Commit reports and script**

```bash
git add scripts/run_market_regime_robustness.py tests/test_market_regime_robustness.py src/market_regime/report.py scripts/run_market_regime_dashboard.py tests/test_market_regime.py reports/market_regime reports/market_regime_robustness
git commit -m "feat: add market regime robustness loop"
```

---

### Task 6: Final Review Summary

**Files:**
- No planned edits.

- [ ] **Step 1: Summarize recommendation**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path("reports/market_regime_robustness/recommendation.json").read_text())
print(json.dumps(payload["recommended_config"], indent=2, sort_keys=True))
print("robust_score", payload["robust_score"])
PY
```

- [ ] **Step 2: Inspect top configs**

Run:

```bash
python3 - <<'PY'
import pandas as pd
print(pd.read_csv("reports/market_regime_robustness/top_configs.csv").head(10).to_string(index=False))
PY
```

- [ ] **Step 3: Confirm dirty status**

Run:

```bash
git status --short
```

Expected: only unrelated Version C dirty files may remain if they pre-existed.

- [ ] **Step 4: Final response**

Report:

- recommended config path
- robustness report path
- updated dashboard path
- current latest regime under recommended config
- tests run
- remaining weaknesses and whether approach B is recommended
