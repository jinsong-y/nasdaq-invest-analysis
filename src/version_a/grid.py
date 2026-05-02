from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

from .config import BacktestParams


def _percent_rank(values: pd.Series) -> pd.Series:
    return values.rank(pct=True, method="average").fillna(0.0)


def rank_summaries(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    df = pd.DataFrame(rows)
    for column in ["roi", "calmar", "excess_return", "cost_improvement", "lag_robustness"]:
        if column not in df:
            df[column] = 0.0
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    df["composite_score"] = (
        30 * _percent_rank(df["roi"])
        + 25 * _percent_rank(df["calmar"])
        + 20 * _percent_rank(df["excess_return"])
        + 15 * _percent_rank(df["cost_improvement"])
        + 10 * _percent_rank(df["lag_robustness"])
    )
    df = df.sort_values(["composite_score", "roi"], ascending=False)
    return df.to_dict(orient="records")


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_run_outputs(output_dir: Path, summary_rows: list[dict], run_rows: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ranked = rank_summaries(summary_rows)
    _write_csv(output_dir / "summary.csv", ranked)
    _write_csv(output_dir / "runs.csv", run_rows)
    (output_dir / "summary.json").write_text(json.dumps(ranked, indent=2, default=str), encoding="utf-8")
    (output_dir / "runs.json").write_text(json.dumps(run_rows, indent=2, default=str), encoding="utf-8")


def refined_grid(seeds: list[BacktestParams]) -> list[BacktestParams]:
    out: dict[str, BacktestParams] = {}
    for seed in seeds:
        for standard_buy_window_days in [5, 10, 15]:
            for deep_buy_window_days in [15, 20, 30]:
                for pause_window_days in [10, 15, 20]:
                    for divergence_weeks in [1, 2, 3]:
                        item = BacktestParams(
                            seed.sma_period,
                            seed.sma_buffer_pct,
                            seed.overheat_ratio,
                            seed.vol_high_pctile,
                            seed.cnn_fear_threshold,
                            seed.cnn_greed_threshold,
                            seed.sentiment_lookback_days,
                            seed.repair_ma_days,
                            divergence_weeks,
                            seed.lag_days,
                            standard_buy_window_days,
                            deep_buy_window_days,
                            pause_window_days,
                            "v2_full",
                            "refined",
                        )
                        out[item.stable_key()] = item
    return list(out.values())


def robustness_grid(seeds: list[BacktestParams]) -> list[BacktestParams]:
    out: dict[str, BacktestParams] = {}
    for seed in seeds:
        for lag_days in [1, 2, 3]:
            for strategy_family in ["v1_no_cnn", "v2_full"]:
                item = BacktestParams(
                    seed.sma_period,
                    seed.sma_buffer_pct,
                    seed.overheat_ratio,
                    seed.vol_high_pctile,
                    seed.cnn_fear_threshold,
                    seed.cnn_greed_threshold,
                    seed.sentiment_lookback_days,
                    seed.repair_ma_days,
                    seed.divergence_weeks,
                    lag_days,
                    seed.standard_buy_window_days,
                    seed.deep_buy_window_days,
                    seed.pause_window_days,
                    strategy_family,
                    "robustness",
                )
                out[item.stable_key()] = item
    return list(out.values())


def _param_key_without_lag(row: dict) -> tuple:
    keys = [
        "strategy_family",
        "sma_period",
        "sma_buffer_pct",
        "overheat_ratio",
        "vol_high_pctile",
        "cnn_fear_threshold",
        "cnn_greed_threshold",
        "sentiment_lookback_days",
        "repair_ma_days",
        "divergence_weeks",
        "standard_buy_window_days",
        "deep_buy_window_days",
        "pause_window_days",
    ]
    return tuple(row.get(key) for key in keys)


def add_lag_robustness(rows: list[dict]) -> list[dict]:
    by_key: dict[tuple, dict[int, float]] = {}
    for row in rows:
        by_key.setdefault(_param_key_without_lag(row), {})[int(row.get("lag_days", 0))] = float(row.get("roi", 0))
    out = []
    for row in rows:
        lag_map = by_key.get(_param_key_without_lag(row), {})
        lag1 = lag_map.get(1)
        lag3 = lag_map.get(3)
        item = dict(row)
        if lag1 is None or lag1 == 0 or lag3 is None:
            item["lag_robustness"] = float(item.get("lag_robustness", 1.0))
        else:
            item["lag_robustness"] = max(0.0, min(1.0, 1.0 - abs(lag1 - lag3) / abs(lag1)))
        out.append(item)
    return out


def mark_sweet_spots(rows: list[dict]) -> list[dict]:
    ranked = rank_summaries(rows)
    if not ranked:
        return []
    threshold = ranked[max(0, int(len(ranked) * 0.10) - 1)]["composite_score"]
    out = []
    for row in ranked:
        item = dict(row)
        item["sweet_spot"] = bool(
            item.get("composite_score", 0) >= threshold
            and item.get("excess_return", 0) > 0
            and item.get("lag_robustness", 0) >= 0.85
        )
        out.append(item)
    return out
