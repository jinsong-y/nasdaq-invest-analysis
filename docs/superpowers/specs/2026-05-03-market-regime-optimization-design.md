# Market Regime Dashboard Optimization Design

Date: 2026-05-03

## Goal

Optimize the market regime dashboard for long-term return support and clear market-state explanation. The dashboard should not become an aggressive short-term timing system. It should identify panic lows, normal participation zones, warming markets, recovery phases, and top-risk conditions with rules that can be explained and backtested.

## Accepted Baseline Findings

Historical backtest on `reports/market_regime/daily_regimes.csv` shows:

- `panic_low` is strong: 3-month forward return about `+16.96%`, 12-month forward return about `+32.62%`.
- `stress_low` is useful for light adding: 12-month forward return about `+21.40%`.
- `overheated` and `top_risk` are useful short-term warning states: 3-month forward returns are negative on average.
- Current `recovery` is too broad. It can classify a warm or high-risk market as recovery when breadth and semiconductor repair signals are strong.

## Optimization Approach

Use a rule-based design with backtest validation. Do not let historical fitting fully drive the model because the sample size for extreme regimes is small. Use the backtest to catch bad thresholds and confirm that each state has sensible forward-return behavior.

## Regime Model

The optimized model adds two states:

- `warm_recovery`: repair signals are strong, but the market is already warm.
- `top_risk_watch`: top-risk evidence is meaningful, but not severe enough for full `top_risk`.

The regime priority should be:

1. `panic_low`
2. `stress_low`
3. `top_risk`
4. `top_risk_watch`
5. `overheated`
6. `recovery`
7. `warm_recovery`
8. `warm`
9. `normal`

`recovery` must be gated. It should only apply when:

- `recovery_score >= recovery_threshold`
- `temperature_score < 65`
- `top_risk_score < 55`
- `overheat_score < 50`
- `dist_sma < 0.08`

If `recovery_score` is high but any heat, extension, or risk gate fails, classify as `warm_recovery` unless a higher-priority risk state applies.

`top_risk_watch` should apply when:

- `top_risk_score >= 70`
- `top_risk_score < top_risk_threshold`

`top_risk` remains the full-risk state at the configured threshold.

## Dashboard Actions

Actions should become more gradual:

- `panic_low`: `add_strong`
- `stress_low`: `add_light`
- `recovery`: `normal_dca`
- `normal`: `normal_dca`
- `warm_recovery`: `normal_dca`
- `warm`: `reduce_light`
- `overheated`: `reduce`
- `top_risk_watch`: `pause_new_buy`
- `top_risk`: `pause`
- `unscorable`: `unavailable`

The dashboard should present `warm_recovery` as "repair signals are strong, but conditions are already warm." This avoids implying a fresh low-risk recovery.

## Visualization

The half-circle gauge should continue to use a `0-100` temperature scale. The legend should include the new states:

- low/stress zone
- normal/recovery zone
- warm recovery zone
- warm/overheated zone
- top-risk zone

The bilingual English/Chinese toggle must include all new labels, summaries, risk notes, and action text.

## Backtest Evaluation

Add a formal evaluation report under `reports/market_regime_evaluation/`.

The evaluation should compare current and optimized rules using:

- regime counts
- 1-month, 3-month, 6-month, and 12-month forward returns
- 12-month forward maximum drawdown
- positive-return hit rate
- key-date sanity checks
- old-vs-new classification changes

Required sanity dates:

- 2011-08-08
- 2015-08-24
- 2018-12-24
- 2020-02-19
- 2020-03-16
- 2021-11-19
- 2022-01-03
- 2022-10-14
- 2024-07-10
- 2026-04-30

Expected key-date behavior:

- `2021-11-19` should become `warm_recovery` because price extension is above the pure recovery gate.
- `2024-07-10` should become `warm_recovery` because price extension and risk evidence are above pure recovery gates.
- `2026-04-30` should become `warm_recovery` because price extension is above the pure recovery gate.

## Error Handling

Keep fail-fast behavior for latest dashboard classification. If latest required inputs are missing, invalid, infinite, or denominator moving averages are non-positive, the run should fail.

Historical rows can remain `unscorable` when required inputs are missing. This preserves honest backtest coverage and avoids silent fallback.

## Testing

Add or update tests for:

- `warm_recovery` classification when recovery is high but heat/risk gates fail.
- `recovery` classification when recovery is high and all gates pass.
- `top_risk_watch` classification at `top_risk_score >= 70` and below the full threshold.
- Dashboard action mapping for new states.
- Bilingual report content for new labels.
- Evaluation script output files and summary metrics.

Run the full unit test suite after implementation.

## Out of Scope

- Machine-learning classification.
- Portfolio-level rebalancing backtest.
- Changing Version A, Version B, or Version C strategy engines.
- Replacing existing market data sources.
