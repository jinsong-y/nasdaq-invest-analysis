from __future__ import annotations

import json
from html import escape
from pathlib import Path

import pandas as pd


CSS = """
:root{--ink:#181713;--muted:#6f6a5f;--paper:#f8f4ea;--panel:#fffdf7;--line:#ddd5c4;--good:#1f6b4c;--bad:#9d2f22}
*{box-sizing:border-box} body{font-family:ui-serif,Georgia,Cambria,serif;margin:0;background:var(--paper);color:var(--ink)}
main{max-width:1080px;margin:0 auto;padding:32px 20px 64px} h1,h2{margin:0 0 12px} p{line-height:1.6}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:24px 0}
.metric{background:var(--panel);border:1px solid var(--line);padding:16px}.label{font-size:12px;color:var(--muted);text-transform:uppercase}.value{font-size:28px;font-weight:700;margin-top:8px}
table{width:100%;border-collapse:collapse;margin-top:20px;background:var(--panel)} th,td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left} th{font-size:12px;color:var(--muted);text-transform:uppercase}
"""


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}"


def _fmt_pct(value: float) -> str:
    return f"{value:.2%}"


def build_report(
    output_dir: Path,
    *,
    strategy_summary: dict,
    baseline_summary: dict,
    comparison: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    excess_value = float(strategy_summary["terminal_value"] - baseline_summary["terminal_value"])
    excess_roi = float(strategy_summary["roi"] - baseline_summary["roi"])
    verdict_class = "good" if excess_value >= 0 else "bad"
    verdict = "PE 策略跑赢机械定投" if excess_value >= 0 else "机械定投仍然更强"

    body = f"""
    <h1>Version C: PE Percentile Backtest</h1>
    <p>规则口径：每天现金流固定 200；PE 历史值使用截至当日的扩展分位数；低于 40% 买入，低于 20% 双倍买入，高于 40% 停买，高于 80% 开始卖出。</p>
    <p class="{verdict_class}"><strong>{escape(verdict)}</strong>。终值差额 {escape(_fmt_money(excess_value))}，ROI 差额 {escape(_fmt_pct(excess_roi))}。</p>
    <div class="grid">
      <div class="metric"><div class="label">PE 策略终值</div><div class="value">{escape(_fmt_money(strategy_summary["terminal_value"]))}</div></div>
      <div class="metric"><div class="label">机械定投终值</div><div class="value">{escape(_fmt_money(baseline_summary["terminal_value"]))}</div></div>
      <div class="metric"><div class="label">PE 策略 ROI</div><div class="value">{escape(_fmt_pct(strategy_summary["roi"]))}</div></div>
      <div class="metric"><div class="label">机械定投 ROI</div><div class="value">{escape(_fmt_pct(baseline_summary["roi"]))}</div></div>
    </div>
    <h2>最近 12 个交易日</h2>
    <table>
      <thead><tr><th>Date</th><th>PE</th><th>PE Pctile</th><th>Strategy</th><th>Baseline</th><th>State</th></tr></thead>
      <tbody>
        {''.join(
            f"<tr><td>{escape(str(idx)[:10])}</td><td>{row['pe_ratio']:.2f}</td><td>{row['pe_pctile']:.2%}</td><td>{row['strategy_value']:.2f}</td><td>{row['baseline_value']:.2f}</td><td>{escape(str(row['state']))}</td></tr>"
            for idx, row in comparison.tail(12).iterrows()
        )}
      </tbody>
    </table>
    """
    html = f"<!doctype html><html><head><meta charset='utf-8'><title>Version C PE Backtest</title><style>{CSS}</style></head><body><main>{body}</main></body></html>"
    (output_dir / "index.html").write_text(html, encoding="utf-8")
    (output_dir / "summary.json").write_text(
        json.dumps(
            {
                "strategy": strategy_summary,
                "baseline": baseline_summary,
                "terminal_value_diff": excess_value,
                "roi_diff": excess_roi,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
