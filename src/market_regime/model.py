from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from .config import DashboardConfig, REQUIRED_DERIVED_COLUMNS, REQUIRED_RAW_COLUMNS


REQUIRED_COLUMNS = tuple(sorted(REQUIRED_RAW_COLUMNS | REQUIRED_DERIVED_COLUMNS))
DENOMINATOR_COLUMNS = {"ndxe_ma", "sox_ma"}


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
        if _is_missing_or_invalid_input(value) or _is_invalid_denominator(column, value):
            missing.append(column)
    return missing


def _is_missing_or_invalid_input(value: object) -> bool:
    if pd.isna(value):
        return True
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return True
    return not bool(np.isfinite(numeric_value))


def _is_invalid_denominator(column: str, value: object) -> bool:
    if column not in DENOMINATOR_COLUMNS or _is_missing_or_invalid_input(value):
        return False
    return float(value) <= 0.0


def classify_latest(df: pd.DataFrame, config: DashboardConfig | None = None) -> RegimeResult:
    if df.empty:
        raise ValueError("cannot classify empty market regime frame")
    config = config or DashboardConfig()
    date = pd.Timestamp(df.index.max())
    result = classify_row(df.loc[date], date=date, config=config, strict=True)
    return result


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
        _positive_part(cnn - cnn_ma5) * 2.0
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
        dist_sma=dist_sma,
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


def _ratio_delta(value: float, moving_average: float) -> float:
    if not np.isfinite(moving_average) or moving_average <= 0.0:
        raise ValueError("ratio moving average denominator must be positive and finite")
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
    dist_sma: float,
) -> str:
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


def _dashboard_action(market_regime: str, confidence_score: float, config: DashboardConfig) -> str:
    if confidence_score < config.low_confidence_threshold:
        return "unavailable"
    if market_regime == "panic_low":
        return "add_strong"
    if market_regime == "stress_low":
        return "add_light"
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
    return "unavailable"


def _summary_text(result: RegimeResult) -> str:
    labels = {
        "panic_low": "Severe stress with low-market evidence.",
        "stress_low": "Market stress and below-trend evidence.",
        "recovery": "Repair signals improving after stress.",
        "warm_recovery": "Repair signals are strong, but conditions are already warm.",
        "normal": "No dominant extreme signal.",
        "warm": "Above-trend market with warmer conditions.",
        "overheated": "Multiple overheat signals active.",
        "top_risk_watch": "Top-risk evidence is elevated but below full risk.",
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
    if result.top_risk_score >= 75:
        risks.append("top_risk")
    elif result.top_risk_score >= 70:
        risks.append("top_risk_watch")
    if result.overheat_score >= 60:
        risks.append("overheat")
    if result.undervaluation_score >= 60:
        risks.append("market_stress")
    if result.confidence_score < 55:
        risks.append("low_confidence")
    if not risks:
        risks.append("no_major_extreme")
    return risks
