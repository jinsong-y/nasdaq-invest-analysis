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
    top_risk_watch_threshold: float = 70.0
    recovery_temperature_ceiling: float = 65.0
    recovery_top_risk_ceiling: float = 55.0
    recovery_overheat_ceiling: float = 50.0
    recovery_dist_sma_ceiling: float = 0.08
    low_confidence_threshold: float = 45.0
