from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.market_regime.config import DashboardConfig, REQUIRED_RAW_COLUMNS
from src.market_regime.model import REQUIRED_COLUMNS
from src.version_a.data import load_market_data
from src.version_a.features import add_features


LATEST_INPUT_DEPENDENCIES = {
    "cnn_ma5": ("cnn_fear_greed",),
    "dist_sma": ("ndx",),
    "sma": ("ndx",),
    "vix_pctile": ("vix",),
    "vxn_pctile": ("vxn",),
    "ndxe_ma": ("ndxe_ndx",),
    "sox_ma": ("sox_ndx",),
}


@dataclass(frozen=True)
class DailyInputReadiness:
    featured: pd.DataFrame
    publishable_market_date: str
    latest_inputs: dict[str, dict[str, Any]]
    latest_input_history: dict[str, list[dict[str, Any]]]


def prepare_daily_input(
    data_path: Path,
    *,
    config: DashboardConfig,
    target_date: str | None = None,
    latest_inputs_path: Path | None = None,
    allow_latest_inputs_overlay: bool = False,
) -> DailyInputReadiness:
    raw = load_market_data(data_path)
    if allow_latest_inputs_overlay:
        raw = apply_latest_inputs_overlay(raw, latest_inputs_path)
    featured = add_features(
        raw,
        sma_period=config.sma_period,
        sentiment_lookback_days=config.sentiment_lookback_days,
        repair_ma_days=config.repair_ma_days,
    )
    publishable_date = find_publishable_market_date(data_path)
    if target_date is not None:
        target = pd.Timestamp(target_date)
        if target not in featured.index:
            raise ValueError(f"target date not found in market data: {target_date}")
    keys = REQUIRED_COLUMNS
    return DailyInputReadiness(
        featured=featured,
        publishable_market_date=publishable_date,
        latest_inputs=latest_input_snapshot(featured, keys),
        latest_input_history=latest_input_history(featured, keys),
    )


def find_publishable_market_date(data_path: Path) -> str:
    if not data_path.exists():
        raise ValueError(f"Daily Input CSV missing: {data_path}")
    dates: list[str] = []
    required = ("date", *sorted(REQUIRED_RAW_COLUMNS))
    with data_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [column for column in required if column not in fieldnames]
        if missing:
            raise ValueError(f"Daily Input missing required columns in {data_path}: {', '.join(missing)}")
        for row in reader:
            raw_date = (row.get("date") or "").strip()
            if not raw_date:
                continue
            market_date = parse_market_date(raw_date)
            complete = True
            for column in REQUIRED_RAW_COLUMNS:
                value = (row.get(column) or "").strip()
                if not value:
                    complete = False
                    continue
                try:
                    numeric_value = float(value)
                except ValueError:
                    raise ValueError(f"invalid Daily Input value for {column} on {market_date}: {value!r}")
                if not math.isfinite(numeric_value):
                    raise ValueError(f"invalid Daily Input value for {column} on {market_date}: {value!r}")
            if complete:
                dates.append(market_date)
    if not dates:
        raise ValueError(f"no Publishable Market Date found in {data_path}")
    return max(dates)


def parse_market_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"invalid date {value!r}: {exc}") from exc


def publishable_market_date(raw: pd.DataFrame) -> str:
    required = sorted(REQUIRED_RAW_COLUMNS)
    missing = [column for column in required if column not in raw.columns]
    if missing:
        raise ValueError(f"Daily Input missing required columns: {', '.join(missing)}")
    dates = []
    for date, row in raw.iterrows():
        complete = True
        for column in required:
            value = row.get(column)
            if _is_missing_or_invalid(value):
                complete = False
        if complete:
            dates.append(pd.Timestamp(date))
    if not dates:
        raise ValueError("no Publishable Market Date found")
    return max(dates).strftime("%Y-%m-%d")


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
        valid_dates = set(_finite_series(rows[key]).index)
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


def _is_missing_or_invalid(value: object) -> bool:
    if pd.isna(value):
        return True
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"invalid Daily Input value: {value!r}")
    return not math.isfinite(numeric_value)
