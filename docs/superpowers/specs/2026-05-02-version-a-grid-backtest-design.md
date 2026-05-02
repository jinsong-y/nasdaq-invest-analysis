# Version A Grid Backtest Design

**Goal:** Build a local Version A backtest system for the Nasdaq DCA framework that evaluates parameter-grid combinations, records every run, and renders a two-layer HTML report for sweet-spot analysis.

**Architecture:** Use the existing daily market indicator dataset as the single input source, derive all indicators in a feature layer, evaluate each parameter combination through a deterministic daily state machine, and persist every run as structured outputs. The main ranking window uses the common multi-signal history, while the pre-2011 period is kept only for trend-only diagnostics and baseline context. A static HTML report is generated from the saved result tables, with one overview page and one detail page per parameter combination.

**Tech Stack:** Python 3.9+, pandas, numpy, standard-library HTML generation, embedded CSS/JavaScript, static file output, local CSV/JSON storage. The generated HTML must not depend on remote CDN assets.

---

## Scope

### In scope
- Version A only, using `NDX` as the proxy price series.
- Mechanical DCA baseline comparison.
- Signal strategy comparison for the project's four-layer system.
- Grid search across SMA, sentiment thresholds, structure filters, and execution delay.
- Full per-combination result persistence.
- Static HTML reporting with overview and detail pages.

### Out of scope
- Version B real fund NAV execution.
- Broker integration.
- Live trading.
- Any replacement data source for missing fund NAV.

## Data Window

### Primary evaluation window
- `2011-01-03` to the latest common date available across the core signals.
- This is the main ranking window for the full four-layer strategy because CNN Fear & Greed starts in 2011.

### Diagnostic extension window
- `2000-01-03` to `2010-12-31`.
- Used only for trend-only and baseline context, not for the main sweet-spot ranking of the full strategy.

### Current local input
- `data/processed/market_indicators.csv`
- Current unified dataset starts at `2000-01-03`.
- Core common signal coverage is `2011-01-03` to `2026-04-30`.

---

## Core Concepts

### Strategy families
1. **Mechanical baseline**
   - Fixed daily contribution.
   - No signal gating.
   - Used as the benchmark.

2. **Signal strategy v1**
   - Trend + volatility + structure filters.
   - No CNN sentiment module.

3. **Signal strategy v2**
   - Full four-layer system.
   - Includes CNN sentiment confirmation.

### Execution model
- Daily loop on trading days only.
- Signals are generated from information available at the close of day `T`.
- Execution is deferred by `lag_days` in `{1, 2, 3}`.
- Active windows are stateful:
  - once a buy or pause window starts, it persists for its configured length;
  - intermediate day-to-day signal flips do not instantly cancel the active window.

### Budget model
- Baseline daily budget: `100` currency units.
- Triggered buy window rate: `200` currency units per day.
- Unused capital remains in a cash bucket.
- Cash bucket is carried forward and can be deployed later according to the active window rules.

---

## Signal Features

### Trend layer
- `sma_period` in `{180, 200, 220}`
- `sma_buffer_pct` in `{0.03, 0.05, 0.07}`
- `overheat_ratio` in `{1.15, 1.20, 1.25}`

### Sentiment layer
- `vol_high_pctile` in `{0.75, 0.80, 0.85, 0.90}`
- The same `vol_high_pctile` threshold is applied to both VXN and VIX; a volatility panic condition is true when either one exceeds the threshold.
- `cnn_fear_threshold` in `{20, 25, 30}`
- `cnn_greed_threshold` in `{70, 75, 80}`
- `sentiment_lookback_days` in `{504, 756, 1260}`

### Structure layer
- `repair_ma_days` in `{10, 20, 50}`
- `divergence_weeks` in `{1, 2, 3}`

### Execution layer
- `lag_days` in `{1, 2, 3}`
- `standard_buy_window_days` in `{5, 10, 15}`
- `deep_buy_window_days` in `{15, 20, 30}`
- `pause_window_days` in `{10, 15, 20}`

---

## Backtest Logic

### Inputs per day
- `ndx`
- `vxn`
- `vix`
- `ndxe`
- `sox`
- `cnn_fear_greed`
- derived ratios such as `ndxe_ndx` and `sox_ndx`

### Derived indicators
- `sma`
- `dist_sma`
- `vxn_pctile`
- `vix_pctile`
- `cnn_ma5`
- `ndxe_ma`
- `sox_ma`

### Buy score
The engine computes a 0-100 Buy Score from the project rules:
- VXN/VIX panic confirmation
- VXN/VIX turn-down confirmation
- CNN fear / CNN rebound confirmation
- NDXE/NDX repair
- SOX/NDX repair
- trend protection

### Sell score
The engine computes a 0-100 Sell Score from the project rules:
- price overheating
- CNN greed and CNN turn-down
- low volatility regime
- breadth divergence
- main-line divergence

### State machine
At each execution date the engine chooses one of these states:
- `baseline`
- `normal`
- `light_buy`
- `standard_buy`
- `deep_buy`
- `slowdown`
- `pause`

State changes are driven by the score thresholds and the active window timers, not by a single day spike.

---

## Grid Search Strategy

### Stage 1: coarse scan
Evaluate this exact coarse parameter network:
- `sma_period` in `{180, 200, 220}`
- `sma_buffer_pct` in `{0.03, 0.05, 0.07}`
- `overheat_ratio` in `{1.15, 1.20, 1.25}`
- `vol_high_pctile` in `{0.75, 0.80, 0.85, 0.90}`
- `cnn_fear_threshold` in `{20, 25, 30}`
- `cnn_greed_threshold` in `{70, 75, 80}`
- `sentiment_lookback_days` in `{504, 756, 1260}`
- `repair_ma_days` in `{10, 20, 50}`
- `divergence_weeks = 2`
- `lag_days = 2`
- `standard_buy_window_days = 10`
- `deep_buy_window_days = 20`
- `pause_window_days = 15`

This stage evaluates `8748` full strategy v2 combinations and keeps every run result.

### Stage 2: neighborhood refinement
- Select the top 5% of Stage 1 by composite score, capped at 300 seed combinations.
- Expand each seed to adjacent listed values for all Stage 1 dimensions.
- Add execution-window neighbors:
  - `standard_buy_window_days` in `{5, 10, 15}`
  - `deep_buy_window_days` in `{15, 20, 30}`
  - `pause_window_days` in `{10, 15, 20}`
- Add structure confirmation neighbors:
  - `divergence_weeks` in `{1, 2, 3}`
- De-duplicate expanded combinations before running.
- Keep every refined run result and mark each run with `stage = refined`.

### Stage 3: robustness sweep
- Select the top 100 Stage 2 combinations by composite score.
- Re-run each selected combination under `lag_days` in `{1, 2, 3}`.
- Re-run each selected combination with `strategy_family` in `{v1_no_cnn, v2_full}`.
- Segment metrics are computed for:
  - 2000-01-03 to 2010-12-31 for baseline and v1 diagnostic context;
  - 2011-01-03 to 2019-12-31 for full v1/v2 comparison;
  - 2020 for V-shaped crash/rebound behavior;
  - 2022 for persistent bear-market behavior;
  - 2023-present for recent high-concentration behavior.

### Note on search size
- The full theoretical cartesian product is intentionally not used as the first pass because it contains more than two million combinations.
- The staged parameter network above is the project baseline for Version A.
- The search engine must preserve full per-run records for every evaluated combination in each stage.

---

## Metrics

Every run records:
- total invested amount
- total shares acquired
- average cost basis
- terminal portfolio value
- ROI
- max drawdown
- Calmar ratio
- excess return vs baseline
- cash idle ratio
- buy-window frequency
- pause-window frequency
- lag sensitivity
- segment performance

### Segment slices
- 2000-01-03 to 2010-12-31
- 2011-01-03 to 2019-12-31
- 2020
- 2022
- 2023-present

### Sweet spot criteria
A parameter combo is preferred when:
- it beats the baseline on the main window,
- it improves drawdown or risk-adjusted return,
- neighboring parameter points are also strong,
- lag 3 does not collapse the strategy,
- it does not rely on a single sharp peak.

### Composite score
The report computes a 0-100 composite score per stage:
- 30% ROI percentile rank
- 25% Calmar ratio percentile rank
- 20% excess return percentile rank
- 15% average-cost improvement percentile rank
- 10% lag robustness percentile rank

Lag robustness is measured as the percentage deterioration from `lag_days = 1` to `lag_days = 3` for matching parameter sets in Stage 3.

---

## Outputs

### Data files
- `reports/version_a/runs.csv`
- `reports/version_a/runs.json`
- `reports/version_a/summary.csv`
- `reports/version_a/summary.json`
- `reports/version_a/feature_snapshot.csv`

### HTML files
- `reports/version_a/index.html`
- `reports/version_a/runs/<run_id>.html`

### Report content
Overview page:
- top-ranked parameter sets
- heatmap or matrix views of the grid
- plateau / sweet-spot markers
- segment performance summary
- baseline comparison

Detail page:
- one parameter set
- equity curve vs baseline
- buy / sell trigger log
- daily state transitions
- metric breakdown
- lag comparison

---

## Validation

The system is considered correct when:
- the baseline run produces stable outputs for the full dataset,
- at least one full-grid stage writes every evaluated combo to disk,
- the HTML overview opens locally without broken links,
- each detail page links back to the overview,
- the recorded results match the CSV/JSON summary counts,
- the main-window ranking and the diagnostic pre-2011 window are clearly separated.

---

## Assumptions

- `NDX` is the proxy price series for Version A.
- CNN Fear & Greed is unavailable before 2011 and is not synthesized.
- The main strategy ranking uses the common core signal window from 2011 onward.
- The pre-2011 period is only a trend and baseline diagnostic.
- Version B will be handled separately once real fund NAV data is available.
