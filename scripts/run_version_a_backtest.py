#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.version_a.config import MAIN_START, BacktestParams, coarse_grid
from src.version_a.data import load_market_data
from src.version_a.engine import run_backtest, run_mechanical_baseline
from src.version_a.features import add_features
from src.version_a.grid import (
    add_lag_robustness,
    mark_sweet_spots,
    rank_summaries,
    refined_grid,
    robustness_grid,
    write_run_outputs,
)
from src.version_a.metrics import summarize_run
from src.version_a.report import build_report


DATA_PATH = ROOT / "data" / "processed" / "market_indicators.csv"
DEFAULT_OUTPUT = ROOT / "reports" / "version_a"


def summary_to_params(row: dict) -> BacktestParams:
    return BacktestParams(
        int(row["sma_period"]),
        float(row["sma_buffer_pct"]),
        float(row["overheat_ratio"]),
        float(row["vol_high_pctile"]),
        int(row["cnn_fear_threshold"]),
        int(row["cnn_greed_threshold"]),
        int(row["sentiment_lookback_days"]),
        int(row["repair_ma_days"]),
        int(row["divergence_weeks"]),
        int(row["lag_days"]),
        int(row["standard_buy_window_days"]),
        int(row["deep_buy_window_days"]),
        int(row["pause_window_days"]),
        str(row.get("strategy_family", "v2_full")),
        str(row.get("stage", "coarse")),
    )


def _sample_daily(daily: pd.DataFrame, *, points: int = 240) -> list[dict]:
    frame = daily.reset_index()
    if len(frame) > points:
        step = max(1, len(frame) // points)
        frame = pd.concat([frame.iloc[::step], frame.tail(1)]).drop_duplicates(subset=["date"])
    rows = frame.to_dict(orient="records")
    for row in rows:
        row["date"] = str(row["date"])[:10]
    return rows


def run_workflow(
    output_dir: Path = DEFAULT_OUTPUT,
    max_runs: int | None = None,
    *,
    detail_limit: int = 300,
    refined_seed_count: int = 300,
    robustness_seed_count: int = 100,
) -> None:
    started = time.time()
    raw = load_market_data(DATA_PATH)
    main = raw[raw.index >= pd.Timestamp(MAIN_START)].copy()
    baseline = run_mechanical_baseline(main.dropna(subset=["ndx"]), run_id="baseline")
    baseline_summary = summarize_run(baseline)

    summaries: list[dict] = []
    run_rows: list[dict] = []
    run_details: dict[str, list[dict]] = {"baseline": _sample_daily(baseline.daily)}
    stage_counts: dict[str, int] = {}
    feature_cache: dict[tuple[int, int, int], pd.DataFrame] = {}

    def featured_for(params: BacktestParams) -> pd.DataFrame:
        key = (params.sma_period, params.sentiment_lookback_days, params.repair_ma_days)
        if key not in feature_cache:
            feature_cache[key] = add_features(
                main,
                sma_period=params.sma_period,
                sentiment_lookback_days=params.sentiment_lookback_days,
                repair_ma_days=params.repair_ma_days,
            ).dropna(subset=["ndx", "sma", "vxn_pctile", "vix_pctile"])
        return feature_cache[key]

    def execute(params_list: list[BacktestParams], start_idx: int) -> list[dict]:
        local = []
        for offset, params in enumerate(params_list):
            idx = start_idx + offset
            if offset == 0 or (offset + 1) % 500 == 0 or offset + 1 == len(params_list):
                print(
                    f"[{params.stage}] {offset + 1}/{len(params_list)} "
                    f"(total run index {idx})",
                    flush=True,
                )
            run_id = f"run_{idx:05d}_{params.stable_key()}"
            result = run_backtest(featured_for(params), params, run_id=run_id)
            summary = summarize_run(result)
            summary.update(params.to_dict())
            summary["run_id"] = run_id
            summary["excess_return"] = summary["roi"] - baseline_summary["roi"]
            summary["cost_improvement"] = (
                baseline_summary["average_cost"] - summary["average_cost"]
            ) / baseline_summary["average_cost"]
            summary["lag_robustness"] = 1.0
            local.append(summary)
            run_rows.append(summary.copy())
            stage_counts[params.stage] = stage_counts.get(params.stage, 0) + 1
            if len(run_details) < detail_limit:
                run_details[run_id] = _sample_daily(result.daily)
        return local

    coarse_params = list(coarse_grid())
    if max_runs is not None:
        coarse_params = coarse_params[:max_runs]
    summaries.extend(execute(coarse_params, 1))

    if max_runs is None:
        ranked_coarse = rank_summaries(summaries)
        seed_count = min(refined_seed_count, max(1, int(len(ranked_coarse) * 0.05)))
        print(f"[refined] selected {seed_count} coarse seeds", flush=True)
        refined_params = refined_grid([summary_to_params(row) for row in ranked_coarse[:seed_count]])
        print(f"[refined] expanded to {len(refined_params)} unique combinations", flush=True)
        summaries.extend(execute(refined_params, len(summaries) + 1))

        refined_only = [row for row in summaries if row.get("stage") == "refined"]
        ranked_refined = rank_summaries(refined_only)
        robust_params = robustness_grid([summary_to_params(row) for row in ranked_refined[:robustness_seed_count]])
        print(f"[robustness] expanded to {len(robust_params)} combinations", flush=True)
        summaries.extend(execute(robust_params, len(summaries) + 1))

    ranked = mark_sweet_spots(add_lag_robustness(summaries))
    write_run_outputs(output_dir, ranked, run_rows)
    build_report(output_dir, summaries=ranked, run_details=run_details, baseline_summary=baseline_summary)
    _write_results(output_dir, ranked, stage_counts, started)


def _write_results(output_dir: Path, ranked: list[dict], stage_counts: dict[str, int], started: float) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    top = ranked[:3]
    lines = [
        "# Version A Backtest Results",
        "",
        f"- Run date: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "- Input data: `data/processed/market_indicators.csv`",
        f"- Evaluated combinations: {len(ranked)}",
        f"- Stage counts: {stage_counts}",
        f"- Sweet-spot candidate count: {sum(1 for row in ranked if row.get('sweet_spot'))}",
        f"- Elapsed seconds: {time.time() - started:.2f}",
        "",
        "## Top Composite Runs",
        "",
    ]
    for row in top:
        lines.append(
            f"- `{row['run_id']}`: score={float(row.get('composite_score', 0)):.2f}, "
            f"roi={float(row.get('roi', 0)):.2%}, mdd={float(row.get('max_drawdown', 0)):.2%}"
        )
    lines.append("")
    (output_dir / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-runs", type=int)
    parser.add_argument("--detail-limit", type=int, default=300)
    parser.add_argument("--refined-seed-count", type=int, default=300)
    parser.add_argument("--robustness-seed-count", type=int, default=100)
    args = parser.parse_args()
    run_workflow(
        output_dir=args.output_dir,
        max_runs=args.max_runs,
        detail_limit=args.detail_limit,
        refined_seed_count=args.refined_seed_count,
        robustness_seed_count=args.robustness_seed_count,
    )
    print(f"Wrote Version A report to {args.output_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
