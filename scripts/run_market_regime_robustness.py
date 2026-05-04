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

import numpy as np
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

REGIME_CODES = {
    "normal": 0,
    "panic_low": 1,
    "stress_low": 2,
    "recovery": 3,
    "warm_recovery": 4,
    "warm": 5,
    "overheated": 6,
    "top_risk_watch": 7,
    "top_risk": 8,
    "unscorable": 9,
}
CODE_REGIMES = {value: key for key, value in REGIME_CODES.items()}
EXTREME_ALLOWED_CODES = {
    date: {REGIME_CODES[regime] for regime in regimes}
    for date, regimes in EXTREME_DATE_EXPECTATIONS.items()
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
        config = DashboardConfig(**dict(zip(keys, values)))
        if is_valid_config(config):
            yield config


def _fmt(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
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


def add_forward_metrics(daily: pd.DataFrame) -> pd.DataFrame:
    _validate_columns(daily, {"date", "market_regime", "ndx"}, "daily")
    out = daily.copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values("date").reset_index(drop=True)
    ndx = pd.to_numeric(out["ndx"], errors="coerce")
    invalid = ndx.isna() & out["ndx"].notna()
    if invalid.any():
        bad = out.loc[invalid, "date"].dt.strftime("%Y-%m-%d").tolist()
        raise ValueError(f"invalid ndx values for dates: {bad}")
    out["ndx"] = ndx
    out = out[out["ndx"].notna()].copy().reset_index(drop=True)
    for days, label in FORWARD_HORIZONS.items():
        out[f"fwd_{label}"] = out["ndx"].shift(-days) / out["ndx"] - 1.0
    out["fwd_12m_mdd"] = _forward_max_drawdown(out["ndx"], 252)
    return out


def _forward_max_drawdown(prices: pd.Series, horizon: int) -> pd.Series:
    values = []
    for idx, start_price in enumerate(prices):
        if pd.isna(start_price) or idx + horizon >= len(prices):
            values.append(float("nan"))
            continue
        window = prices.iloc[idx + 1 : idx + horizon + 1].dropna()
        if window.empty:
            values.append(float("nan"))
            continue
        peak = float(start_price)
        max_drawdown = 0.0
        for price in window:
            peak = max(peak, float(price))
            max_drawdown = min(max_drawdown, float(price) / peak - 1.0)
        values.append(max_drawdown)
    return pd.Series(values, index=prices.index, dtype="float64")


def score_low_zone(daily: pd.DataFrame) -> float:
    base_12m = _mean_or_zero(daily["fwd_12m"])
    low = daily[daily["market_regime"].isin(["panic_low", "stress_low"])]
    low_share = len(low) / max(1, len(daily))
    if len(low) < 20:
        return -20.0
    rarity_penalty = max(0.0, low_share - 0.18) * 80.0
    return (
        max(0.0, (_mean_or_zero(low["fwd_12m"]) - base_12m) * 120.0)
        + _win_or_zero(low["fwd_12m"]) * 18.0
        - rarity_penalty
    )


def score_top_warning(daily: pd.DataFrame) -> float:
    base_3m = _mean_or_zero(daily["fwd_3m"])
    top = daily[daily["market_regime"].isin(["top_risk", "top_risk_watch", "overheated"])]
    top_share = len(top) / max(1, len(daily))
    if len(top) < 20:
        return -10.0
    too_common_penalty = max(0.0, top_share - 0.22) * 90.0
    return (
        max(0.0, (base_3m - _mean_or_zero(top["fwd_3m"])) * 120.0)
        + (1.0 - _win_or_zero(top["fwd_3m"])) * 18.0
        + abs(min(0.0, _mean_or_zero(top["fwd_12m_mdd"]))) * 16.0
        - too_common_penalty
    )


def score_state_stability(daily: pd.DataFrame) -> float:
    working = daily.sort_values("date").copy()
    working = working[working["market_regime"] != "unscorable"]
    if working.empty:
        return 0.0
    switches = working["market_regime"].ne(working["market_regime"].shift()).sum() - 1
    months = max(1, working["date"].dt.to_period("M").nunique())
    switches_per_month = switches / months
    return max(0.0, 25.0 - switches_per_month * 2.2)


def score_extreme_dates(daily: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    _validate_columns(daily, {"date", "market_regime"}, "daily")
    working = daily.copy()
    working["date"] = pd.to_datetime(working["date"])
    if working.empty:
        raise ValueError("cannot score extreme dates with empty daily data")
    date_values = working["date"].astype("int64")
    rows = []
    for requested_text, allowed in EXTREME_DATE_EXPECTATIONS.items():
        requested = pd.Timestamp(requested_text)
        idx = (date_values - requested.value).abs().idxmin()
        row = working.loc[idx]
        regime = str(row["market_regime"])
        result = "pass" if regime in allowed else "fail"
        rows.append(
            {
                "requested_date": requested_text,
                "matched_date": pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
                "market_regime": regime,
                "allowed_regimes": ",".join(sorted(allowed)),
                "result": result,
            }
        )
    table = pd.DataFrame(rows)
    return float((table["result"] == "pass").mean() * 30.0), table


def evaluate_config_result(config_name: str, config: DashboardConfig, daily: pd.DataFrame) -> dict[str, Any]:
    scored = _ensure_forward_metrics(daily)
    low = score_low_zone(scored)
    top = score_top_warning(scored)
    stability = score_state_stability(scored)
    extreme, _ = score_extreme_dates(scored)
    return _result_payload(config_name, config, scored, low, top, stability, extreme)


def _result_payload(
    config_name: str,
    config: DashboardConfig,
    scored: pd.DataFrame,
    low: float,
    top: float,
    stability: float,
    extreme: float,
) -> dict[str, Any]:
    latest = scored.iloc[-1]["market_regime"] if not scored.empty else ""
    latest_penalty = 0.0 if latest == "warm_recovery" else 12.0
    walk_balance = _state_balance_score(scored)
    robust_score = low + top + stability + extreme + walk_balance - latest_penalty
    return {
        "config_id": config_name,
        **config_to_dict(config),
        "low_zone_quality": low,
        "top_warning_quality": top,
        "state_stability": stability,
        "extreme_date_accuracy": extreme,
        "state_balance": walk_balance,
        "latest_target_penalty": latest_penalty,
        "robust_score": robust_score,
    }


def _extreme_positions(daily: pd.DataFrame) -> dict[str, int]:
    working = daily.copy()
    working["date"] = pd.to_datetime(working["date"])
    if working.empty:
        raise ValueError("cannot locate extreme dates with empty daily data")
    date_values = working["date"].astype("int64")
    return {
        requested_text: int((date_values - pd.Timestamp(requested_text).value).abs().idxmin())
        for requested_text in EXTREME_DATE_EXPECTATIONS
    }


def _score_extreme_positions(daily: pd.DataFrame, positions: dict[str, int]) -> float:
    passes = 0
    for requested_text, idx in positions.items():
        allowed = EXTREME_DATE_EXPECTATIONS[requested_text]
        passes += str(daily.loc[idx, "market_regime"]) in allowed
    return passes / len(EXTREME_DATE_EXPECTATIONS) * 30.0


def _score_extreme_code_positions(codes: np.ndarray, positions: dict[str, int]) -> float:
    passes = 0
    for requested_text, idx in positions.items():
        passes += int(codes[idx]) in EXTREME_ALLOWED_CODES[requested_text]
    return passes / len(EXTREME_DATE_EXPECTATIONS) * 30.0


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
    scored = _ensure_forward_metrics(daily)
    _, extreme = score_extreme_dates(scored)
    failed = extreme[extreme["result"] == "fail"].copy()
    failed.insert(0, "config_id", config_name)
    return failed


def config_to_dict(config: DashboardConfig) -> dict[str, Any]:
    return asdict(config)


def write_recommended_config(path: Path, config: DashboardConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    args = ",\n        ".join(f"{key}={value!r}" for key, value in config_to_dict(config).items())
    text = (
        "from __future__ import annotations\n\n"
        "from src.market_regime.config import DashboardConfig\n\n\n"
        "def recommended_config() -> DashboardConfig:\n"
        f"    return DashboardConfig(\n        {args}\n    )\n"
    )
    path.write_text(text, encoding="utf-8")


def write_outputs(
    output_dir: Path,
    grid_results: pd.DataFrame,
    top_configs: pd.DataFrame,
    walk_forward: pd.DataFrame,
    extreme_dates: pd.DataFrame,
    misclassification_review: pd.DataFrame,
    current_config: DashboardConfig,
    recommended_config_value: DashboardConfig,
) -> dict[str, Any]:
    if grid_results.empty or top_configs.empty:
        raise ValueError("cannot write recommendation without grid results")
    output_dir.mkdir(parents=True, exist_ok=True)
    grid_results.to_csv(output_dir / "grid_results.csv", index=False)
    top_configs.to_csv(output_dir / "top_configs.csv", index=False)
    walk_forward.to_csv(output_dir / "walk_forward.csv", index=False)
    extreme_dates.to_csv(output_dir / "extreme_dates.csv", index=False)
    misclassification_review.to_csv(output_dir / "misclassification_review.csv", index=False)
    recommendation = _recommendation_payload(
        grid_results,
        top_configs,
        current_config,
        recommended_config_value,
    )
    (output_dir / "recommendation.json").write_text(
        json.dumps(recommendation, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_recommended_config(output_dir / "recommended_config.py", recommended_config_value)
    (output_dir / "index.html").write_text(
        _render_robustness_html(
            grid_results,
            top_configs,
            walk_forward,
            extreme_dates,
            misclassification_review,
            recommendation,
            output_dir / "recommended_config.py",
        ),
        encoding="utf-8",
    )
    return recommendation


def run_workflow(
    output_dir: Path = DEFAULT_OUTPUT,
    data_path: Path = DATA_PATH,
    dashboard_output_dir: Path = DEFAULT_DASHBOARD_OUTPUT,
    target_date: str = TARGET_DATE,
    max_configs: int | None = None,
) -> DashboardConfig:
    current_config = DashboardConfig()
    featured = _featured_market_data(data_path, current_config)
    target = pd.Timestamp(target_date)
    if target not in featured.index:
        raise ValueError(f"target date not found in market data: {target_date}")
    featured_for_scoring = featured.loc[:target]
    base_daily = classify_daily(featured_for_scoring, config=current_config)
    base_scored = add_forward_metrics(base_daily)
    extreme_positions = _extreme_positions(base_scored)
    arrays = _score_arrays(base_scored)
    rows = []
    current_result = None
    for index, config in enumerate(generate_candidate_configs()):
        if max_configs is not None and index >= max_configs:
            break
        name = config_id(config)
        codes = _regime_codes_from_arrays(arrays, config)
        result = _evaluate_config_arrays(name, config, arrays, codes, extreme_positions)
        rows.append(result)
        if config == current_config:
            current_result = result
    if not rows:
        raise ValueError("grid produced no candidate configs")
    grid = _rank_grid(pd.DataFrame(rows), current_config)
    if current_result is None:
        current_name = config_id(current_config)
        current_codes = _regime_codes_from_arrays(arrays, current_config)
        current_result = _evaluate_config_arrays(current_name, current_config, arrays, current_codes, extreme_positions)
        grid = pd.concat([grid, pd.DataFrame([current_result])], ignore_index=True)
        grid = _rank_grid(grid, current_config)
    top = grid.head(25).copy()
    best_row = top.iloc[0]
    best_config = _config_from_row(best_row)
    best_name = str(best_row["config_id"])
    best_codes = _regime_codes_from_arrays(arrays, best_config)
    best_daily = _daily_from_codes(base_scored, best_codes, best_config)
    _, extreme_dates = score_extreme_dates(best_daily)
    misclassification_review = build_misclassification_review(best_name, best_daily)
    walk_forward = _build_top_walk_forward(top, base_scored)
    recommendation = write_outputs(
        output_dir,
        grid,
        top,
        walk_forward,
        extreme_dates,
        misclassification_review,
        current_config,
        best_config,
    )
    daily = classify_daily(featured_for_scoring, config=best_config)
    summary = latest_summary(featured_for_scoring, config=best_config)
    summary["config_metadata"] = {
        "config_source": "recommended robustness config",
        "recommendation_generated_at": recommendation["generated_at"],
        "robustness_report_path": str(output_dir / "index.html"),
    }
    write_dashboard_outputs(dashboard_output_dir, daily, summary)
    return best_config


def _featured_market_data(data_path: Path, config: DashboardConfig) -> pd.DataFrame:
    raw = load_market_data(data_path)
    return add_features(
        raw,
        sma_period=config.sma_period,
        sentiment_lookback_days=config.sentiment_lookback_days,
        repair_ma_days=config.repair_ma_days,
    )


def _classify_from_base_scores(base_daily: pd.DataFrame, config: DashboardConfig) -> pd.DataFrame:
    daily = base_daily.copy()
    undervaluation = daily["undervaluation_score"].astype(float)
    top_risk = daily["top_risk_score"].astype(float)
    overheat = daily["overheat_score"].astype(float)
    recovery = daily["recovery_score"].astype(float)
    temperature = daily["temperature_score"].astype(float)
    dist_sma = daily["dist_sma"].astype(float)
    vol_high = pd.concat([daily["vxn_pctile"].astype(float), daily["vix_pctile"].astype(float)], axis=1).max(axis=1)
    cnn = daily["cnn_fear_greed"].astype(float)
    recovery_eligible = (
        (recovery >= config.recovery_threshold)
        & (temperature < config.recovery_temperature_ceiling)
        & (top_risk < config.recovery_top_risk_ceiling)
        & (overheat < config.recovery_overheat_ceiling)
        & (dist_sma < config.recovery_dist_sma_ceiling)
    )
    missing = daily["missing_inputs"].fillna("").astype(str).ne("")
    regimes = np.select(
        [
            missing,
            (undervaluation >= config.panic_low_threshold) & (vol_high >= 0.90) & (cnn <= 15.0),
            undervaluation >= config.stress_low_threshold,
            top_risk >= config.top_risk_threshold,
            top_risk >= config.top_risk_watch_threshold,
            overheat >= config.overheat_threshold,
            recovery_eligible,
            recovery >= config.recovery_threshold,
            temperature >= config.warm_threshold,
        ],
        [
            "unscorable",
            "panic_low",
            "stress_low",
            "top_risk",
            "top_risk_watch",
            "overheated",
            "recovery",
            "warm_recovery",
            "warm",
        ],
        default="normal",
    )
    confidence = daily["confidence_score"].astype(float)
    actions = np.select(
        [
            confidence < config.low_confidence_threshold,
            regimes == "panic_low",
            regimes == "stress_low",
            np.isin(regimes, ["recovery", "normal", "warm_recovery"]),
            regimes == "warm",
            regimes == "overheated",
            regimes == "top_risk_watch",
            regimes == "top_risk",
        ],
        [
            "unavailable",
            "add_strong",
            "add_light",
            "normal_dca",
            "reduce_light",
            "reduce",
            "pause_new_buy",
            "pause",
        ],
        default="unavailable",
    )
    daily["market_regime"] = regimes
    daily["dashboard_action"] = actions
    return daily


def _score_arrays(base_daily: pd.DataFrame) -> dict[str, Any]:
    dates = pd.to_datetime(base_daily["date"])
    return {
        "months": max(1, dates.dt.to_period("M").nunique()),
        "undervaluation": base_daily["undervaluation_score"].to_numpy(dtype=float),
        "top_risk": base_daily["top_risk_score"].to_numpy(dtype=float),
        "overheat": base_daily["overheat_score"].to_numpy(dtype=float),
        "recovery": base_daily["recovery_score"].to_numpy(dtype=float),
        "temperature": base_daily["temperature_score"].to_numpy(dtype=float),
        "dist_sma": base_daily["dist_sma"].to_numpy(dtype=float),
        "vol_high": np.fmax(
            base_daily["vxn_pctile"].to_numpy(dtype=float),
            base_daily["vix_pctile"].to_numpy(dtype=float),
        ),
        "cnn": base_daily["cnn_fear_greed"].to_numpy(dtype=float),
        "confidence": base_daily["confidence_score"].to_numpy(dtype=float),
        "missing": base_daily["missing_inputs"].fillna("").astype(str).ne("").to_numpy(),
        "fwd_3m": base_daily["fwd_3m"].to_numpy(dtype=float),
        "fwd_12m": base_daily["fwd_12m"].to_numpy(dtype=float),
        "fwd_12m_mdd": base_daily["fwd_12m_mdd"].to_numpy(dtype=float),
    }


def _regime_codes_from_arrays(arrays: dict[str, Any], config: DashboardConfig) -> np.ndarray:
    recovery_eligible = (
        (arrays["recovery"] >= config.recovery_threshold)
        & (arrays["temperature"] < config.recovery_temperature_ceiling)
        & (arrays["top_risk"] < config.recovery_top_risk_ceiling)
        & (arrays["overheat"] < config.recovery_overheat_ceiling)
        & (arrays["dist_sma"] < config.recovery_dist_sma_ceiling)
    )
    return np.select(
        [
            arrays["missing"],
            (arrays["undervaluation"] >= config.panic_low_threshold)
            & (arrays["vol_high"] >= 0.90)
            & (arrays["cnn"] <= 15.0),
            arrays["undervaluation"] >= config.stress_low_threshold,
            arrays["top_risk"] >= config.top_risk_threshold,
            arrays["top_risk"] >= config.top_risk_watch_threshold,
            arrays["overheat"] >= config.overheat_threshold,
            recovery_eligible,
            arrays["recovery"] >= config.recovery_threshold,
            arrays["temperature"] >= config.warm_threshold,
        ],
        [
            REGIME_CODES["unscorable"],
            REGIME_CODES["panic_low"],
            REGIME_CODES["stress_low"],
            REGIME_CODES["top_risk"],
            REGIME_CODES["top_risk_watch"],
            REGIME_CODES["overheated"],
            REGIME_CODES["recovery"],
            REGIME_CODES["warm_recovery"],
            REGIME_CODES["warm"],
        ],
        default=REGIME_CODES["normal"],
    ).astype(np.int8)


def _evaluate_config_arrays(
    config_name: str,
    config: DashboardConfig,
    arrays: dict[str, Any],
    codes: np.ndarray,
    extreme_positions: dict[str, int],
) -> dict[str, Any]:
    low_mask = np.isin(codes, [REGIME_CODES["panic_low"], REGIME_CODES["stress_low"]])
    top_mask = np.isin(codes, [REGIME_CODES["top_risk"], REGIME_CODES["top_risk_watch"], REGIME_CODES["overheated"]])
    base_12m = _nanmean_or_zero(arrays["fwd_12m"])
    base_3m = _nanmean_or_zero(arrays["fwd_3m"])
    low_share = float(low_mask.mean()) if len(low_mask) else 0.0
    top_share = float(top_mask.mean()) if len(top_mask) else 0.0
    if int(low_mask.sum()) < 20:
        low = -20.0
    else:
        low = (
            max(0.0, (_nanmean_or_zero(arrays["fwd_12m"][low_mask]) - base_12m) * 120.0)
            + _win_or_zero_array(arrays["fwd_12m"][low_mask]) * 18.0
            - max(0.0, low_share - 0.18) * 80.0
        )
    if int(top_mask.sum()) < 20:
        top = -10.0
    else:
        top = (
            max(0.0, (base_3m - _nanmean_or_zero(arrays["fwd_3m"][top_mask])) * 120.0)
            + (1.0 - _win_or_zero_array(arrays["fwd_3m"][top_mask])) * 18.0
            + abs(min(0.0, _nanmean_or_zero(arrays["fwd_12m_mdd"][top_mask]))) * 16.0
            - max(0.0, top_share - 0.22) * 90.0
        )
    stability = _state_stability_codes(codes, arrays["months"])
    extreme = _score_extreme_code_positions(codes, extreme_positions)
    latest = int(codes[-1]) if len(codes) else REGIME_CODES["unscorable"]
    latest_penalty = 0.0 if latest == REGIME_CODES["warm_recovery"] else 12.0
    balance = _state_balance_codes(codes)
    robust_score = low + top + stability + extreme + balance - latest_penalty
    return {
        "config_id": config_name,
        **config_to_dict(config),
        "low_zone_quality": low,
        "top_warning_quality": top,
        "state_stability": stability,
        "extreme_date_accuracy": extreme,
        "state_balance": balance,
        "latest_target_penalty": latest_penalty,
        "robust_score": robust_score,
    }


def _daily_from_codes(base_daily: pd.DataFrame, codes: np.ndarray, config: DashboardConfig) -> pd.DataFrame:
    daily = base_daily.copy()
    regimes = np.array([CODE_REGIMES[int(code)] for code in codes], dtype=object)
    daily["market_regime"] = regimes
    confidence = daily["confidence_score"].to_numpy(dtype=float)
    actions = np.select(
        [
            confidence < config.low_confidence_threshold,
            codes == REGIME_CODES["panic_low"],
            codes == REGIME_CODES["stress_low"],
            np.isin(codes, [REGIME_CODES["recovery"], REGIME_CODES["normal"], REGIME_CODES["warm_recovery"]]),
            codes == REGIME_CODES["warm"],
            codes == REGIME_CODES["overheated"],
            codes == REGIME_CODES["top_risk_watch"],
            codes == REGIME_CODES["top_risk"],
        ],
        [
            "unavailable",
            "add_strong",
            "add_light",
            "normal_dca",
            "reduce_light",
            "reduce",
            "pause_new_buy",
            "pause",
        ],
        default="unavailable",
    )
    daily["dashboard_action"] = actions
    return daily


def _build_top_walk_forward(top: pd.DataFrame, base_daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in top.iterrows():
        config = _config_from_row(row)
        name = str(row["config_id"])
        daily = _classify_from_base_scores(base_daily, config)
        table = build_walk_forward_table(name, config, daily)
        if not table.empty:
            rows.extend(table.to_dict("records"))
    return pd.DataFrame(rows)


def _config_from_row(row: pd.Series) -> DashboardConfig:
    values = {}
    for key, default in config_to_dict(DashboardConfig()).items():
        value = row[key]
        values[key] = int(value) if isinstance(default, int) and not isinstance(default, bool) else float(value)
    return DashboardConfig(**values)


def _rank_grid(grid: pd.DataFrame, current_config: DashboardConfig) -> pd.DataFrame:
    if grid.empty:
        return grid
    current_values = config_to_dict(current_config)
    ranked = grid.copy()
    ranked["changed_param_count"] = ranked.apply(
        lambda row: sum(row[key] != value for key, value in current_values.items()),
        axis=1,
    )
    ranked["param_distance_from_current"] = ranked.apply(
        lambda row: sum(abs(float(row[key]) - float(value)) for key, value in current_values.items()),
        axis=1,
    )
    return ranked.sort_values(
        ["robust_score", "changed_param_count", "param_distance_from_current", "config_id"],
        ascending=[False, True, True, True],
    ).reset_index(drop=True)


def _recommendation_payload(
    grid_results: pd.DataFrame,
    top_configs: pd.DataFrame,
    current_config: DashboardConfig,
    recommended_config_value: DashboardConfig,
) -> dict[str, Any]:
    best = top_configs.iloc[0]
    current_id = config_id(current_config)
    current_rows = grid_results[grid_results["config_id"] == current_id]
    current_score = None if current_rows.empty else float(current_rows.iloc[0]["robust_score"])
    recommended_score = float(best["robust_score"])
    changed = _changed_params(current_config, recommended_config_value)
    weaknesses = []
    if float(best.get("extreme_date_accuracy", 0.0)) < 30.0:
        weaknesses.append("Not all extreme-date expectations pass; review failed dates before relying on signals.")
    if float(best.get("state_stability", 0.0)) < 18.0:
        weaknesses.append("State churn remains high; consider Approach B only if churn persists after threshold review.")
    if not weaknesses:
        weaknesses.append("Threshold-only approach passes current robustness checks; monitor future misclassifications.")
    improvements = [
        f"robust_score {current_score:.4f} -> {recommended_score:.4f}" if current_score is not None else f"robust_score {recommended_score:.4f}",
        f"changed_params={len(changed)}",
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_config_id": current_id,
        "recommended_config_id": str(best["config_id"]),
        "current_score": current_score,
        "robust_score": recommended_score,
        "score_delta": None if current_score is None else recommended_score - current_score,
        "changed_params": changed,
        "current_config": config_to_dict(current_config),
        "recommended_config": config_to_dict(recommended_config_value),
        "key_improvements": improvements,
        "remaining_weaknesses": weaknesses,
        "proceed_to_approach_b": False,
    }


def _changed_params(current: DashboardConfig, recommended: DashboardConfig) -> dict[str, dict[str, Any]]:
    current_values = config_to_dict(current)
    recommended_values = config_to_dict(recommended)
    return {
        key: {"current": current_values[key], "recommended": recommended_values[key]}
        for key in current_values
        if current_values[key] != recommended_values[key]
    }


def _render_robustness_html(
    grid: pd.DataFrame,
    top: pd.DataFrame,
    walk_forward: pd.DataFrame,
    extreme: pd.DataFrame,
    misclassification: pd.DataFrame,
    recommendation: dict[str, Any],
    config_path: Path,
) -> str:
    current_config = recommendation["current_config"]
    recommended_config = recommendation["recommended_config"]
    score_comparison = pd.DataFrame(
        [
            {
                "current_score": recommendation["current_score"],
                "recommended_score": recommendation["robust_score"],
                "score_delta": recommendation["score_delta"],
            }
        ]
    )
    snippet = config_path.read_text(encoding="utf-8") if config_path.exists() else json.dumps(recommended_config, indent=2)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Market Regime Robustness</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #18202a; background: #f6f7f9; }}
    main {{ max-width: 1180px; margin: 0 auto; }}
    section {{ border: 1px solid #d8dee7; border-radius: 8px; background: #fff; padding: 16px; margin: 16px 0; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    th, td {{ border: 1px solid #dde3ea; padding: 6px 8px; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
    th {{ background: #eef2f6; }}
    pre {{ background: #f3f5f7; padding: 12px; overflow-x: auto; }}
  </style>
</head>
<body>
<main>
  <h1>Market Regime Robustness</h1>
  <p>Generated at {escape(str(recommendation["generated_at"]))}. Threshold-only grid; formulas and inputs unchanged.</p>
  <section><h2>Current config</h2><pre>{escape(json.dumps(current_config, indent=2, sort_keys=True))}</pre></section>
  <section><h2>Recommended config</h2><pre>{escape(json.dumps(recommended_config, indent=2, sort_keys=True))}</pre></section>
  <section><h2>Changed params</h2><pre>{escape(json.dumps(recommendation["changed_params"], indent=2, sort_keys=True))}</pre></section>
  <section><h2>Score comparison</h2>{score_comparison.to_html(index=False, float_format="{:.4f}".format)}</section>
  <section><h2>Extreme-date pass/fail</h2>{extreme.to_html(index=False)}</section>
  <section><h2>Misclassification review</h2>{misclassification.to_html(index=False)}</section>
  <section><h2>Walk-forward</h2>{walk_forward.head(250).to_html(index=False, float_format="{:.4f}".format)}</section>
  <section><h2>Top configs</h2>{top.to_html(index=False, float_format="{:.4f}".format)}</section>
  <section><h2>Grid results</h2>{grid.head(250).to_html(index=False, float_format="{:.4f}".format)}</section>
  <section><h2>Copyable config snippet</h2><pre>{escape(snippet)}</pre></section>
</main>
</body>
</html>
"""


def _state_balance_score(daily: pd.DataFrame) -> float:
    regimes = daily[daily["market_regime"] != "unscorable"]["market_regime"]
    if regimes.empty:
        return 0.0
    shares = regimes.value_counts(normalize=True)
    penalty = 0.0
    for regime, max_share in {
        "panic_low": 0.08,
        "stress_low": 0.16,
        "top_risk": 0.08,
        "top_risk_watch": 0.12,
        "overheated": 0.18,
    }.items():
        penalty += max(0.0, float(shares.get(regime, 0.0)) - max_share) * 40.0
    return max(0.0, 10.0 - penalty)


def _state_balance_codes(codes: np.ndarray) -> float:
    scorable = codes[codes != REGIME_CODES["unscorable"]]
    if len(scorable) == 0:
        return 0.0
    counts = np.bincount(scorable, minlength=max(REGIME_CODES.values()) + 1) / len(scorable)
    penalty = 0.0
    for regime, max_share in {
        "panic_low": 0.08,
        "stress_low": 0.16,
        "top_risk": 0.08,
        "top_risk_watch": 0.12,
        "overheated": 0.18,
    }.items():
        penalty += max(0.0, float(counts[REGIME_CODES[regime]]) - max_share) * 40.0
    return max(0.0, 10.0 - penalty)


def _state_stability_codes(codes: np.ndarray, months: int) -> float:
    scorable = codes[codes != REGIME_CODES["unscorable"]]
    if len(scorable) == 0:
        return 0.0
    switches = int(np.count_nonzero(scorable[1:] != scorable[:-1]))
    switches_per_month = switches / max(1, months)
    return max(0.0, 25.0 - switches_per_month * 2.2)


def _mean_or_zero(series: pd.Series) -> float:
    valid = series.dropna()
    return 0.0 if valid.empty else float(valid.mean())


def _nanmean_or_zero(values: np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    valid = values[~np.isnan(values)]
    return 0.0 if len(valid) == 0 else float(valid.mean())


def _ensure_forward_metrics(daily: pd.DataFrame) -> pd.DataFrame:
    required = {f"fwd_{label}" for label in FORWARD_HORIZONS.values()} | {"fwd_12m_mdd"}
    if required.issubset(daily.columns):
        return daily.copy()
    return add_forward_metrics(daily)


def _win_or_zero(series: pd.Series) -> float:
    valid = series.dropna()
    return 0.0 if valid.empty else float((valid > 0).mean())


def _win_or_zero_array(values: np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    valid = values[~np.isnan(values)]
    return 0.0 if len(valid) == 0 else float((valid > 0).mean())


def _validate_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label} missing required columns: {sorted(missing)}")


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


if __name__ == "__main__":
    raise SystemExit(main())
