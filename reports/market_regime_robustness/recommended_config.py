from __future__ import annotations

from src.market_regime.config import DashboardConfig


def recommended_config() -> DashboardConfig:
    return DashboardConfig(
        sma_period=180,
        sentiment_lookback_days=1260,
        repair_ma_days=50,
        rolling_high_days=252,
        panic_low_threshold=75.0,
        stress_low_threshold=60.0,
        recovery_threshold=60.0,
        warm_threshold=65.0,
        overheat_threshold=75.0,
        top_risk_threshold=75.0,
        top_risk_watch_threshold=70.0,
        recovery_temperature_ceiling=60.0,
        recovery_top_risk_ceiling=55.0,
        recovery_overheat_ceiling=50.0,
        recovery_dist_sma_ceiling=0.06,
        low_confidence_threshold=45.0
    )
