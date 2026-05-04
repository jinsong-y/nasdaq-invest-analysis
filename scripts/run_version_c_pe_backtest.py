#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_nasdaq100_pe import extract_pe_series, fetch_html
from src.version_c.config import DEFAULT_OUTPUT_DIR, MARKET_DATA_PATH, PE_DATA_PATH
from src.version_c.data import filter_date_range, load_market_data, load_pe_data, merge_market_with_pe
from src.version_c.engine import run_mechanical_baseline, run_pe_strategy
from src.version_c.metrics import summarize_run
from src.version_c.report import build_report


def run_workflow(
    *,
    market_path: Path = MARKET_DATA_PATH,
    pe_path: Path = PE_DATA_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    refresh_pe: bool = False,
    buy_budget: float = 200.0,
    double_buy_budget: float = 400.0,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    if refresh_pe:
        html = fetch_html()
        pe_df = extract_pe_series(html)
        pe_path.parent.mkdir(parents=True, exist_ok=True)
        pe_df.to_csv(pe_path, index=False)

    if not pe_path.exists():
        raise FileNotFoundError(f"missing PE data file: {pe_path}")

    market = load_market_data(market_path)
    pe = load_pe_data(pe_path)
    merged = merge_market_with_pe(market, pe)
    merged = filter_date_range(merged, start_date=start_date, end_date=end_date)

    strategy = run_pe_strategy(
        merged,
        run_id="pe_percentile_strategy",
        buy_budget=buy_budget,
        double_buy_budget=double_buy_budget,
    )
    baseline = run_mechanical_baseline(merged, run_id="mechanical_dca")
    strategy_summary = summarize_run(strategy)
    baseline_summary = summarize_run(baseline)

    comparison = pd.DataFrame(
        {
            "price": merged["ndx"],
            "pe_ratio": merged["pe_ratio"],
            "pe_pctile": merged["pe_pctile"],
            "state": strategy.daily["state"],
            "strategy_value": strategy.daily["portfolio_value"],
            "baseline_value": baseline.daily["portfolio_value"],
        }
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(output_dir / "daily_compare.csv", index_label="date")
    build_report(
        output_dir,
        strategy_summary=strategy_summary,
        baseline_summary=baseline_summary,
        comparison=comparison,
    )

    results_md = "\n".join(
        [
            "# Version C PE Backtest Results",
            "",
            f"- Data window: {merged.index.min().strftime('%Y-%m-%d')} to {merged.index.max().strftime('%Y-%m-%d')}",
            f"- Buy budget on trigger days: {buy_budget:.2f}",
            f"- Double-buy budget on deep trigger days: {double_buy_budget:.2f}",
            f"- Requested start date: {start_date or 'default'}",
            f"- Requested end date: {end_date or 'default'}",
            f"- Strategy terminal value: {strategy_summary['terminal_value']:.2f}",
            f"- Baseline terminal value: {baseline_summary['terminal_value']:.2f}",
            f"- Terminal value diff: {strategy_summary['terminal_value'] - baseline_summary['terminal_value']:.2f}",
            f"- Strategy ROI: {strategy_summary['roi']:.2%}",
            f"- Baseline ROI: {baseline_summary['roi']:.2%}",
            f"- ROI diff: {strategy_summary['roi'] - baseline_summary['roi']:.2%}",
        ]
    )
    (output_dir / "RESULTS.md").write_text(results_md, encoding="utf-8")
    return {
        "strategy": strategy_summary,
        "baseline": baseline_summary,
        "comparison_rows": len(comparison),
        "output_dir": str(output_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-path", type=Path, default=MARKET_DATA_PATH)
    parser.add_argument("--pe-path", type=Path, default=PE_DATA_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--refresh-pe", action="store_true")
    parser.add_argument("--buy-budget", type=float, default=200.0)
    parser.add_argument("--double-buy-budget", type=float, default=400.0)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    args = parser.parse_args()
    result = run_workflow(
        market_path=args.market_path,
        pe_path=args.pe_path,
        output_dir=args.output_dir,
        refresh_pe=args.refresh_pe,
        buy_budget=args.buy_budget,
        double_buy_budget=args.double_buy_budget,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
