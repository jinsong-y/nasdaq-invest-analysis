# Market Regime Robustness Loop Design

Date: 2026-05-04

## Goal

Build a repeatable robustness loop for the market regime dashboard. The loop should find a threshold and state-boundary configuration that reflects market conditions well across history, especially lows, tops, warm recoveries, and stressed regimes.

The goal is not maximum return. The goal is stable, explainable, historically robust market-state classification.

## Scope

This design uses approach A:

- Do not change the score formulas in `src/market_regime/model.py`.
- Do not add new market inputs.
- Do not optimize portfolio allocation.
- Tune only thresholds and state-boundary parameters exposed through `DashboardConfig`.

The optimized output is a recommended `DashboardConfig` plus evidence.

## Inputs

Use the existing market data pipeline:

- `data/processed/market_indicators.csv`
- `src.version_a.data.load_market_data`
- `src.version_a.features.add_features`
- `src.market_regime.model.classify_daily`

Use the current score columns:

- `temperature_score`
- `undervaluation_score`
- `overheat_score`
- `top_risk_score`
- `recovery_score`
- supporting scores already produced by the dashboard

Historical rows with missing inputs can remain `unscorable`. Latest classification remains fail-fast.

## Grid Parameters

Search only these threshold parameters:

| Parameter | Values |
| --- | --- |
| `stress_low_threshold` | `50, 55, 60` |
| `recovery_threshold` | `50, 55, 60, 65` |
| `warm_threshold` | `55, 60, 65` |
| `overheat_threshold` | `65, 70, 75` |
| `top_risk_watch_threshold` | `65, 70` |
| `top_risk_threshold` | `72.5, 75, 80` |
| `recovery_temperature_ceiling` | `60, 65, 70` |
| `recovery_top_risk_ceiling` | `50, 55, 60` |
| `recovery_overheat_ceiling` | `45, 50, 55` |
| `recovery_dist_sma_ceiling` | `0.06, 0.08, 0.10` |

Invalid combinations must be skipped:

- `top_risk_watch_threshold >= top_risk_threshold`
- `warm_threshold >= overheat_threshold`
- `recovery_top_risk_ceiling >= top_risk_watch_threshold`

## Evaluation Metrics

Each grid configuration should produce a scorecard with these components.

### Low-Zone Quality

`panic_low` and `stress_low` should behave like low-zone states:

- 6-month and 12-month forward returns should be above all-scorable baseline.
- 12-month win rate should be high.
- Panic lows should appear on known panic dates.

### Top-Warning Quality

`top_risk`, `top_risk_watch`, and `overheated` should behave like caution states:

- 1-month and 3-month forward returns should be below all-scorable baseline.
- 3-month win rate should be lower than normal/warm states.
- They should not fire constantly.

### State Stability

State labels should not churn excessively:

- Compute monthly switch count.
- Penalize high switch frequency.
- Penalize configurations where any major state has too few observations to evaluate.

### Walk-Forward Consistency

Use rolling historical windows:

- Train/evaluate periods are calendar windows, not random splits.
- Candidate configs should rank well across multiple windows.
- Penalize configs that perform well in one era but fail in others.

Suggested windows:

- `2011-01-01` to `2015-12-31`
- `2016-01-01` to `2020-12-31`
- `2021-01-01` to `2026-04-30`

Also evaluate stress eras:

- `2011-07-01` to `2011-12-31`
- `2015-08-01` to `2016-02-29`
- `2018-10-01` to `2019-03-31`
- `2020-02-01` to `2020-06-30`
- `2021-10-01` to `2022-12-31`
- `2024-06-01` to `2024-09-30`

### Extreme-Date Accuracy

Required sanity dates:

- `2011-08-08`: should be `panic_low` or `stress_low`
- `2015-08-24`: should be `panic_low` or `stress_low`
- `2018-12-24`: should be `panic_low` or `stress_low`
- `2020-02-19`: should be `warm`, `overheated`, `top_risk_watch`, or `top_risk`
- `2020-03-16`: should be `panic_low` or `stress_low`
- `2021-11-19`: should be `warm_recovery`, `warm`, `overheated`, `top_risk_watch`, or `top_risk`
- `2022-10-14`: should be `panic_low` or `stress_low`
- `2024-07-10`: should be `warm_recovery`, `overheated`, `top_risk_watch`, or `top_risk`
- `2026-04-30`: should be `warm_recovery`

The loop should report mismatches clearly.

## Robust Score

Compute a composite score:

```text
robust_score =
  low_zone_quality
+ top_warning_quality
+ state_stability
+ walk_forward_consistency
+ extreme_date_accuracy
- overfit_penalty
- excessive_switch_penalty
```

The exact numeric weights should be simple and documented in the implementation plan. They should favor interpretability and stability over raw return.

## Misclassification Review

For top-ranked configurations, produce a review table with:

- date
- old regime
- candidate regime
- expected class if known date
- 1-month, 3-month, 6-month, 12-month forward return
- 12-month forward max drawdown
- reason for possible misclassification

This table is for human review. It should highlight where the model still confuses:

- warm recovery vs true recovery
- warm vs top-risk watch
- stress low vs panic low
- normal vs warm

## Outputs

Create `reports/market_regime_robustness/` with:

- `grid_results.csv`
- `top_configs.csv`
- `walk_forward.csv`
- `extreme_dates.csv`
- `misclassification_review.csv`
- `recommendation.json`
- `recommended_config.py`
- `index.html`

`recommendation.json` should include:

- recommended config values
- current config values
- robust score
- key improvements
- remaining weaknesses
- whether to proceed to approach B, changing score weights

`recommended_config.py` should contain a directly usable `DashboardConfig` factory:

```python
from src.market_regime.config import DashboardConfig


def recommended_config() -> DashboardConfig:
    return DashboardConfig(...)
```

The robustness `index.html` should show:

- current config
- recommended config
- changed parameters
- robust score comparison
- key-date pass/fail table
- copyable Python config snippet

The market regime dashboard HTML should also be refreshed after the recommendation is selected. It should show which config was used:

- default/current config
- recommended robustness config
- recommendation timestamp
- link or path to `reports/market_regime_robustness/index.html`

## Acceptance Criteria

The loop is successful when it can:

- Evaluate all valid grid configurations without manual intervention.
- Rank configurations by robustness score.
- Show whether the current dashboard config is already close to optimal.
- Produce a recommended threshold-only config.
- Write the recommendation to `reports/market_regime_robustness/recommended_config.py`.
- Refresh the dashboard HTML using the recommended config or clearly label when the dashboard still uses the current default config.
- Explain why the recommendation is better, not just higher-scoring.
- Identify remaining weak points for a possible next round.

## Out of Scope

- Changing score formulas.
- Adding PE, rates, credit, macro, or external data.
- Changing Version A/B/C strategy engines.
- Optimizing buy/sell allocation rules.
- Replacing the dashboard UI.
