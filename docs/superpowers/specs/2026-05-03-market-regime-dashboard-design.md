# Market Regime Dashboard Design

Date: 2026-05-03

## Goal

Build a market regime dashboard from the existing Version A market indicators that describes the Nasdaq 100 market state clearly and separately from any investment action.

The dashboard should answer:

- What state is the market in today?
- Is the market low, normal, warm, overheated, or showing top risk?
- Which signals are driving that classification?
- Is the classification reliable given the available data?
- What DCA action, if any, would be implied by the state?

This feature must fail fast. If required inputs for a market-state calculation are missing, the calculation must not silently continue with a misleading state.

## Existing Context

Version A currently computes features in `src/version_a/features.py`:

- `dist_sma`: NDX distance from moving average.
- `vxn_pctile`: VXN rolling percentile.
- `vix_pctile`: VIX rolling percentile.
- `cnn_ma5`: CNN Fear & Greed 5-day moving average.
- `ndxe_ma`: equal-weight Nasdaq relative strength moving average.
- `sox_ma`: semiconductor relative strength moving average.

Version A currently computes `buy_score`, `sell_score`, and execution states in `src/version_a/engine.py`. These states are useful for DCA execution, but they are not market regimes. The new dashboard will reuse Version A inputs and features, but it will not treat `light_buy`, `standard_buy`, `slowdown`, or `pause` as market-state labels.

## Recommended Architecture

Add a new package:

```text
src/market_regime/
  __init__.py
  config.py
  model.py
  report.py
```

Add a runner script:

```text
scripts/run_market_regime_dashboard.py
```

Add tests:

```text
tests/test_market_regime.py
```

The package is intentionally separate from `src/version_a/` because market regime classification is a reusable analytic layer, not a Version A trading variant.

## Data Flow

1. Load `data/processed/market_indicators.csv` using the existing Version A loader or an equivalent strict loader.
2. Add Version A features with selected dashboard parameters.
3. Validate required columns for each row being classified.
4. Compute component scores.
5. Compute final market regime.
6. Emit:
   - Daily regime CSV.
   - Latest regime JSON summary.
   - Static HTML dashboard report.

## Required Inputs

Required raw inputs:

- `ndx`
- `vxn`
- `vix`
- `cnn_fear_greed`
- `ndxe_ndx`
- `sox_ndx`

Required derived inputs:

- `sma`
- `dist_sma`
- `vxn_pctile`
- `vix_pctile`
- `cnn_ma5`
- `ndxe_ma`
- `sox_ma`

For strict current-state classification, all required inputs must be present on the target date. If any are missing, raise a clear `ValueError` that includes the date and missing fields.

For historical daily output, rows with missing required values may be marked as `unscorable`, but the latest summary must still fail if the target latest row is missing required values.

## Output Fields

Daily CSV columns:

- `date`
- `market_regime`
- `temperature_score`
- `undervaluation_score`
- `overheat_score`
- `trend_score`
- `volatility_score`
- `sentiment_score`
- `breadth_score`
- `semiconductor_score`
- `top_risk_score`
- `recovery_score`
- `confidence_score`
- `dashboard_action`
- `missing_inputs`
- `ndx`
- `sma`
- `dist_sma`
- `vxn`
- `vix`
- `vxn_pctile`
- `vix_pctile`
- `cnn_fear_greed`
- `cnn_ma5`
- `ndxe_ndx`
- `ndxe_ma`
- `sox_ndx`
- `sox_ma`

Latest JSON fields:

- `as_of_date`
- `market_regime`
- `temperature_score`
- `confidence_score`
- `dashboard_action`
- `summary`
- `drivers`
- `risks`
- `inputs`

## Market Regimes

The model will produce seven scorable regimes plus one data-quality state:

- `panic_low`: severe stress, high volatility, weak price trend, fear conditions.
- `stress_low`: below-trend or stressed market, but not full panic.
- `recovery`: stress is easing; breadth, semiconductors, volatility, or sentiment are improving.
- `normal`: no extreme low or high conditions dominate.
- `warm`: above-trend market with optimistic conditions, but not yet overheated.
- `overheated`: high distance above trend, low volatility, greed, or concentration risk.
- `top_risk`: overheated market with new-high divergence or structural deterioration.
- `unscorable`: missing required inputs in historical output only.

## Component Scores

Scores should be normalized to 0-100.

`trend_score` measures NDX position relative to moving average:

- Very below trend increases low-market evidence.
- Modestly above trend supports normal/warm conditions.
- Far above trend increases overheat evidence.

`volatility_score` measures VIX/VXN regime:

- High volatility percentiles increase low/panic evidence.
- Very low volatility percentiles increase warm/overheat evidence.
- Middle percentiles support normal conditions.

`sentiment_score` measures CNN Fear & Greed:

- Very low values increase low/panic evidence.
- Very high values increase overheat/top-risk evidence.
- Middle values support normal conditions.

`breadth_score` measures `ndxe_ndx` relative to `ndxe_ma`:

- Breadth above its moving average supports trend health and recovery.
- Breadth below its moving average during index highs increases top-risk evidence.

`semiconductor_score` measures `sox_ndx` relative to `sox_ma`:

- Semiconductor strength supports trend health and recovery.
- Semiconductor weakness during index highs increases top-risk evidence.

`top_risk_score` combines:

- NDX near a rolling high.
- NDX far above its moving average.
- Low volatility percentile.
- High CNN greed.
- Breadth or semiconductor deterioration.

`recovery_score` combines:

- Recent improvement in CNN moving average.
- Falling VIX or VXN.
- Breadth or semiconductor ratios moving back above their moving averages.
- Price reclaiming trend support.

## Regime Rules

Initial rule priority:

1. If required latest inputs are missing, fail fast.
2. If `top_risk_score` is high, classify `top_risk`.
3. If `overheat_score` is high, classify `overheated`.
4. If `undervaluation_score` is very high and volatility/sentiment are extreme, classify `panic_low`.
5. If `undervaluation_score` is high, classify `stress_low`.
6. If `recovery_score` is high after stress, classify `recovery`.
7. If `temperature_score` is moderately high, classify `warm`.
8. Otherwise classify `normal`.

The exact numeric thresholds should live in `config.py` and be easy to tune.

## Dashboard Actions

Actions are separate from regimes:

- `add_strong`: usually maps from `panic_low` or high-confidence `stress_low`.
- `add_light`: usually maps from `stress_low` or early `recovery`.
- `normal_dca`: usually maps from `normal` or low-risk `recovery`.
- `reduce`: usually maps from `warm` or `overheated`.
- `pause`: usually maps from high-confidence `top_risk`.
- `unavailable`: missing data or low confidence.

The action must be presented as an implication of the regime, not as the primary output.

## Confidence

`confidence_score` reflects:

- Data completeness.
- Agreement among component scores.
- Whether classification is driven by one signal or by several aligned signals.

For strict latest classification, missing required fields fail before confidence is computed.

Historical rows marked `unscorable` should have confidence `0`.

## Report Design

The HTML report should include:

- Current regime headline.
- Temperature gauge from 0 to 100.
- Component score bars.
- Top positive and negative drivers.
- Latest raw inputs.
- Historical regime timeline.
- Recent daily table.

The report should avoid implying precision beyond the model. Labels should be plain and conservative.

Reports should be written under:

```text
reports/market_regime/
```

The first version should use `sma_period=180`, matching the strongest Version A run that motivated this work. Thresholds should be hand-defined in `config.py` for v1. Historical calibration against known market episodes can be added after the strict, explainable dashboard is working.

## Tests

Test coverage should include:

- Missing latest `vix` or `vxn` raises `ValueError`.
- Panic-low fixture classifies as `panic_low`.
- Stress-low fixture classifies as `stress_low`.
- Normal fixture classifies as `normal`.
- Warm fixture classifies as `warm`.
- Overheated fixture classifies as `overheated`.
- Top-risk fixture classifies as `top_risk`.
- Historical missing row can become `unscorable` without breaking the whole report.

## Non-Goals

- No machine-learning classifier in v1.
- No new external data source in v1.
- No claim that regimes are trading signals by themselves.
- No silent fallback for missing required latest data.
