#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from html import escape
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_fund_nav import FUNDS
from src.version_a.config import MAIN_START
from src.version_a.data import load_market_data
from src.version_a.engine import run_backtest, run_mechanical_baseline
from src.version_a.features import add_features
from src.version_a.metrics import summarize_run
from scripts.run_version_a_backtest import summary_to_params


DEFAULT_OUTPUT = ROOT / "reports" / "version_b_funds"
FUND_DIR = ROOT / "data" / "processed" / "funds"


def load_top_params():
    with (ROOT / "reports" / "version_a" / "summary.csv").open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    return summary_to_params(row), row


def load_fund_nav(code: str) -> pd.DataFrame:
    path = FUND_DIR / f"{code}.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing fund NAV file: {path}")
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df["fund_nav"] = pd.to_numeric(df["nav"], errors="coerce")
    return df.dropna(subset=["fund_nav"]).sort_values("date")


def align_fund_with_signals(fund: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    left = fund[fund["date"] >= pd.Timestamp(MAIN_START)].copy()
    right = signals.reset_index().rename(columns={"date": "signal_date"}).sort_values("signal_date")
    merged = pd.merge_asof(left.sort_values("date"), right, left_on="date", right_on="signal_date", direction="backward")
    merged = merged.dropna(subset=["fund_nav", "ndx", "sma", "vxn_pctile", "vix_pctile"])
    return merged.set_index("date")


def run_version_b(output_dir: Path = DEFAULT_OUTPUT) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    params, params_row = load_top_params()
    raw = load_market_data(ROOT / "data" / "processed" / "market_indicators.csv")
    main = raw[raw.index >= pd.Timestamp(MAIN_START)].copy()
    signals = add_features(
        main,
        sma_period=params.sma_period,
        sentiment_lookback_days=params.sentiment_lookback_days,
        repair_ma_days=params.repair_ma_days,
    )
    rows = []
    detail = {}
    fund_names = dict(FUNDS)
    for code, name in FUNDS:
        aligned = align_fund_with_signals(load_fund_nav(code), signals)
        if aligned.empty:
            raise RuntimeError(f"no aligned NAV/signal rows for {code}")
        baseline = run_mechanical_baseline(aligned, run_id=f"{code}_baseline", price_column="fund_nav")
        strategy = run_backtest(aligned, params, run_id=f"{code}_strategy", price_column="fund_nav")
        base_summary = summarize_run(baseline)
        strat_summary = summarize_run(strategy)
        row = {
            "code": code,
            "name": name,
            "start": str(aligned.index.min().date()),
            "end": str(aligned.index.max().date()),
            "nav_rows": len(aligned),
            "baseline_roi": base_summary["roi"],
            "strategy_roi": strat_summary["roi"],
            "excess_return": strat_summary["roi"] - base_summary["roi"],
            "baseline_mdd": base_summary["max_drawdown"],
            "strategy_mdd": strat_summary["max_drawdown"],
            "baseline_total_invested": base_summary["total_invested"],
            "strategy_total_invested": strat_summary["total_invested"],
            "baseline_terminal_value": base_summary["terminal_value"],
            "strategy_terminal_value": strat_summary["terminal_value"],
            "strategy_average_cost": strat_summary["average_cost"],
            "baseline_average_cost": base_summary["average_cost"],
        }
        rows.append(row)
        sample = strategy.daily.reset_index()
        if len(sample) > 240:
            step = max(1, len(sample) // 240)
            sample = pd.concat([sample.iloc[::step], sample.tail(1)]).drop_duplicates(subset=["date"])
        detail[code] = sample.assign(date=lambda x: x["date"].astype(str).str.slice(0, 10)).to_dict(orient="records")
    write_outputs(output_dir, rows, detail, params_row)
    return rows


def fmt_pct(value) -> str:
    return f"{float(value):.2%}"


def fmt_money(value) -> str:
    return f"{float(value):,.0f}"


def write_outputs(output_dir: Path, rows: list[dict], detail: dict, params_row: dict) -> None:
    fields = list(rows[0])
    with (output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    body_rows = []
    for row in sorted(rows, key=lambda item: item["excess_return"], reverse=True):
        body_rows.append(
            "<tr>"
            f"<td>{escape(row['code'])}</td><td>{escape(row['name'])}</td><td>{escape(row['start'])}</td><td>{escape(row['end'])}</td>"
            f"<td>{fmt_pct(row['baseline_roi'])}</td><td>{fmt_pct(row['strategy_roi'])}</td><td>{fmt_pct(row['excess_return'])}</td>"
            f"<td>{fmt_pct(row['baseline_mdd'])}</td><td>{fmt_pct(row['strategy_mdd'])}</td>"
            f"<td>{fmt_money(row['baseline_total_invested'])}</td><td>{fmt_money(row['strategy_total_invested'])}</td>"
            "</tr>"
        )
    positive = sum(1 for row in rows if row["excess_return"] > 0)
    best = max(rows, key=lambda row: row["excess_return"])
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Version B Fund Backtest</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#f8f4ea;color:#181713;margin:0}}
main{{max-width:1240px;margin:0 auto;padding:36px}} h1{{font-size:44px;margin:0 0 12px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}} .metric{{background:#fffdf7;border:1px solid #ddd5c4;padding:16px}}
.label{{font-size:12px;color:#6f6a5f;text-transform:uppercase;letter-spacing:.06em}} .value{{font-size:28px;font-weight:750;margin-top:8px}}
table{{border-collapse:collapse;width:100%;background:#fffdf7;font-size:13px}} th,td{{border-bottom:1px solid #ddd5c4;padding:8px;text-align:right;white-space:nowrap}} th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){{text-align:left}}
.card{{background:#fffdf7;border:1px solid #ddd5c4;padding:18px;margin:18px 0;overflow:auto}} .bad{{color:#9d2f22}} .good{{color:#1f6b4c}}
</style></head><body><main>
<h1>Version B: 10 只纳指100基金真实净值测算</h1>
<p>信号使用 Version A 最高综合评分参数，成交价格使用东方财富历史单位净值。对照组为同一基金净值上的机械定投。</p>
<section class="grid">
<div class="metric"><div class="label">基金数量</div><div class="value">{len(rows)}</div></div>
<div class="metric"><div class="label">正超额基金数</div><div class="value {'good' if positive else 'bad'}">{positive}</div></div>
<div class="metric"><div class="label">最佳超额</div><div class="value {'good' if best['excess_return'] > 0 else 'bad'}">{fmt_pct(best['excess_return'])}</div></div>
<div class="metric"><div class="label">最佳基金</div><div class="value" style="font-size:18px">{escape(best['code'])}</div></div>
</section>
<div class="card"><h2>测算口径</h2><p>基金申购状态未做额度约束，只使用有净值日期执行；QDII 时差、汇率和费用已隐含在基金净值表现中，但申购费/赎回费未另行扣除。</p>
<p>信号参数来自：{escape(str(params_row.get('run_id','')))}</p></div>
<div class="card"><table><thead><tr><th>Code</th><th>Name</th><th>Start</th><th>End</th><th>Baseline ROI</th><th>Strategy ROI</th><th>Excess</th><th>Base MDD</th><th>Strategy MDD</th><th>Base Invested</th><th>Strategy Invested</th></tr></thead><tbody>
{''.join(body_rows)}
</tbody></table></div>
</main></body></html>"""
    (output_dir / "index.html").write_text(html, encoding="utf-8")
    (output_dir / "details.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    rows = run_version_b(args.output_dir)
    print(f"Wrote Version B report to {args.output_dir / 'index.html'}")
    for row in rows:
        print(row["code"], row["name"], fmt_pct(row["excess_return"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
