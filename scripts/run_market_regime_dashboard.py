#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market_regime.config import DashboardConfig
from src.market_regime.model import REQUIRED_COLUMNS, classify_daily, latest_summary
from src.market_regime.report import write_dashboard_outputs
from src.version_a.data import load_market_data
from src.version_a.features import add_features


DATA_PATH = ROOT / "data" / "processed" / "market_indicators.csv"
DEFAULT_OUTPUT = ROOT / "reports" / "market_regime"
DEFAULT_LATEST_INPUTS = ROOT / "data" / "processed" / "latest_intraday_inputs.json"
LATEST_INPUT_DEPENDENCIES = {
    "cnn_ma5": ("cnn_fear_greed",),
    "dist_sma": ("ndx",),
    "sma": ("ndx",),
    "vix_pctile": ("vix",),
    "vxn_pctile": ("vxn",),
    "ndxe_ma": ("ndxe_ndx",),
    "sox_ma": ("sox_ndx",),
}


def load_recommended_config(path: Path) -> DashboardConfig:
    spec = importlib.util.spec_from_file_location("recommended_market_regime_config", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load recommended config: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "recommended_config"):
        raise ValueError(f"recommended config module missing recommended_config(): {path}")
    config = module.recommended_config()
    if not isinstance(config, DashboardConfig):
        raise ValueError(f"recommended_config() must return DashboardConfig: {path}")
    return config


def load_recommendation_metadata(path: Path) -> dict[str, Any]:
    recommendation_path = path.parent / "recommendation.json"
    recommendation = json.loads(recommendation_path.read_text(encoding="utf-8"))
    return {
        "config_source": "recommended robustness config",
        "recommendation_generated_at": recommendation["generated_at"],
        "robustness_report_path": str(path.parent / "index.html"),
    }


def run_workflow(
    output_dir: Path = DEFAULT_OUTPUT,
    *,
    data_path: Path = DATA_PATH,
    target_date: str | None = None,
    config: DashboardConfig | None = None,
    config_metadata: dict[str, Any] | None = None,
    latest_inputs_path: Path | None = DEFAULT_LATEST_INPUTS,
) -> None:
    config = config or DashboardConfig()
    raw = load_market_data(data_path)
    raw = apply_latest_inputs_overlay(raw, latest_inputs_path)
    featured = add_features(
        raw,
        sma_period=config.sma_period,
        sentiment_lookback_days=config.sentiment_lookback_days,
        repair_ma_days=config.repair_ma_days,
    )
    if target_date is not None:
        target = pd.Timestamp(target_date)
        if target not in featured.index:
            raise ValueError(f"target date not found in market data: {target_date}")
        featured_for_summary = featured.loc[:target]
    else:
        featured_for_summary = featured
    daily = classify_daily(featured_for_summary, config=config)
    summary = latest_summary(featured_for_summary, config=config)
    summary["latest_inputs"] = latest_input_snapshot(featured, summary.get("inputs", {}).keys())
    summary["latest_input_history"] = latest_input_history(featured, summary.get("inputs", {}).keys())
    if config_metadata is not None:
        summary["config_metadata"] = config_metadata
    write_dashboard_outputs(output_dir, daily, summary)


def apply_latest_inputs_overlay(raw: pd.DataFrame, latest_inputs_path: Path | None) -> pd.DataFrame:
    if latest_inputs_path is None or not latest_inputs_path.exists():
        return raw
    payload = json.loads(latest_inputs_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"latest inputs overlay must be a JSON object: {latest_inputs_path}")
    market_date = pd.Timestamp(str(payload.get("market_date", "")))
    raw_inputs = payload.get("raw_inputs")
    if not isinstance(raw_inputs, dict) or not raw_inputs:
        raise ValueError(f"latest inputs overlay missing raw_inputs: {latest_inputs_path}")
    out = raw.copy()
    if market_date not in out.index:
        out.loc[market_date, :] = pd.NA
    for key, entry in raw_inputs.items():
        if key not in out.columns:
            continue
        if not isinstance(entry, dict) or "value" not in entry:
            raise ValueError(f"latest inputs overlay entry missing value: {key}")
        value = float(entry["value"])
        if not math.isfinite(value):
            raise ValueError(f"latest inputs overlay value must be finite: {key}")
        out.loc[market_date, str(key)] = value
    if "ndx" in out.columns and out.loc[market_date, "ndx"] not in ("", None):
        ndx = float(out.loc[market_date, "ndx"])
        if math.isfinite(ndx) and not math.isclose(ndx, 0.0):
            if "ndxe" in out.columns and "ndxe_ndx" in out.columns and pd.notna(out.loc[market_date, "ndxe"]):
                out.loc[market_date, "ndxe_ndx"] = float(out.loc[market_date, "ndxe"]) / ndx
            if "sox" in out.columns and "sox_ndx" in out.columns and pd.notna(out.loc[market_date, "sox"]):
                out.loc[market_date, "sox_ndx"] = float(out.loc[market_date, "sox"]) / ndx
    return out.sort_index()


def latest_input_snapshot(featured: pd.DataFrame, keys: Any = REQUIRED_COLUMNS) -> dict[str, dict[str, Any]]:
    if "date" in featured.columns:
        raise ValueError("featured data must use the market date index, not a date column")
    rows = featured.sort_index()
    snapshot: dict[str, dict[str, Any]] = {}
    for key in keys:
        if key not in rows.columns:
            raise ValueError(f"latest input column missing: {key}")
        dependency_dates = []
        for dependency in LATEST_INPUT_DEPENDENCIES.get(str(key), (str(key),)):
            if dependency not in rows.columns:
                raise ValueError(f"latest input dependency missing for {key}: {dependency}")
            dependency_values = _finite_series(rows[dependency])
            if dependency_values.empty:
                raise ValueError(f"latest input dependency has no finite values for {key}: {dependency}")
            dependency_dates.append(dependency_values.index[-1])
        latest_date = min(dependency_dates)
        if not isinstance(latest_date, pd.Timestamp):
            latest_date = pd.Timestamp(latest_date)
        value = float(pd.to_numeric(pd.Series([rows.at[latest_date, key]]), errors="coerce").iloc[0])
        if not math.isfinite(value):
            raise ValueError(f"latest input column has no finite value for {key} on {latest_date.strftime('%Y-%m-%d')}")
        snapshot[str(key)] = {
            "value": value,
            "as_of_date": latest_date.strftime("%Y-%m-%d"),
        }
    return snapshot


def latest_input_history(
    featured: pd.DataFrame,
    keys: Any = REQUIRED_COLUMNS,
    *,
    limit: int = 30,
) -> dict[str, list[dict[str, Any]]]:
    if "date" in featured.columns:
        raise ValueError("featured data must use the market date index, not a date column")
    if limit < 2:
        raise ValueError("latest input history limit must be at least 2")
    rows = featured.sort_index()
    history: dict[str, list[dict[str, Any]]] = {}
    for key in keys:
        if key not in rows.columns:
            raise ValueError(f"latest input column missing: {key}")
        dependencies = LATEST_INPUT_DEPENDENCIES.get(str(key), (str(key),))
        valid_mask = _finite_series(rows[key]).index
        valid_dates = set(valid_mask)
        for dependency in dependencies:
            if dependency not in rows.columns:
                raise ValueError(f"latest input dependency missing for {key}: {dependency}")
            valid_dates &= set(_finite_series(rows[dependency]).index)
        entries: list[dict[str, Any]] = []
        for date in [index for index in rows.index if index in valid_dates][-limit:]:
            value = float(pd.to_numeric(pd.Series([rows.at[date, key]]), errors="coerce").iloc[0])
            if not math.isfinite(value):
                raise ValueError(f"latest input history has no finite value for {key} on {date.strftime('%Y-%m-%d')}")
            timestamp = date if isinstance(date, pd.Timestamp) else pd.Timestamp(date)
            entries.append({"date": timestamp.strftime("%Y-%m-%d"), "value": value})
        if len(entries) < 2:
            raise ValueError(f"latest input history has fewer than 2 values: {key}")
        history[str(key)] = entries
    return history


def _finite_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric[numeric.apply(lambda value: pd.notna(value) and math.isfinite(float(value)))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--data-path", type=Path, default=DATA_PATH)
    parser.add_argument("--target-date")
    parser.add_argument("--latest-inputs-path", type=Path, default=DEFAULT_LATEST_INPUTS)
    parser.add_argument("--recommended-config-path", type=Path)
    args = parser.parse_args()
    config = None
    config_metadata = None
    if args.recommended_config_path is not None:
        config = load_recommended_config(args.recommended_config_path)
        config_metadata = load_recommendation_metadata(args.recommended_config_path)
    run_workflow(
        output_dir=args.output_dir,
        data_path=args.data_path,
        target_date=args.target_date,
        config=config,
        config_metadata=config_metadata,
        latest_inputs_path=args.latest_inputs_path,
    )
    print(f"Wrote market regime dashboard to {args.output_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
