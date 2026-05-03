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
        if _is_missing_or_invalid_input(value):
            missing.append(column)
    return missing


def _is_missing_or_invalid_input(value: object) -> bool:
    if pd.isna(value):
        return True
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return True
    return bool(np.isnan(numeric_value))


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
