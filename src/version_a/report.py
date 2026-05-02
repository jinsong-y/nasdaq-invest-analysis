from __future__ import annotations

from html import escape
from pathlib import Path


CSS = """
:root{--ink:#181713;--muted:#6f6a5f;--paper:#f8f4ea;--panel:#fffdf7;--line:#ddd5c4;--red:#9d2f22;--green:#1f6b4c;--blue:#245c9e}
*{box-sizing:border-box} body{font-family:ui-serif,Georgia,Cambria,serif;margin:0;background:var(--paper);color:var(--ink)}
main{max-width:1220px;margin:0 auto;padding:38px clamp(18px,4vw,48px) 56px}
h1{font-size:clamp(34px,5vw,64px);line-height:.98;margin:0 0 18px;letter-spacing:0}
h2{font-size:22px;margin:0 0 14px} h3{font-size:16px;margin:0 0 8px}
p{color:var(--muted);font-size:16px;line-height:1.55;margin:0}
a{color:var(--blue);text-decoration:none}
.hero{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(280px,.8fr);gap:28px;align-items:end;border-bottom:1px solid var(--line);padding-bottom:28px;margin-bottom:28px}
.verdict{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;text-transform:uppercase;letter-spacing:.08em;color:var(--red);font-weight:700;font-size:13px;margin-bottom:16px}
.summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:22px 0}
.metric{background:var(--panel);border:1px solid var(--line);padding:15px 16px;min-height:104px}
.metric .label{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}
.metric .value{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;font-size:28px;font-weight:750;margin-top:8px}
.metric.bad .value{color:var(--red)} .metric.good .value{color:var(--green)}
.card{background:var(--panel);border:1px solid var(--line);padding:18px;margin:16px 0;overflow:auto}
.subpanel{border-top:1px solid var(--line);padding-top:14px;margin-top:14px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.note{border-left:4px solid var(--red);padding:10px 0 10px 14px;color:var(--ink)}
table{border-collapse:collapse;width:100%;background:var(--panel);font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:9px 10px;text-align:right;white-space:nowrap}
th{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em;background:#fbf7ed}
th:first-child,td:first-child{text-align:left}
.pill{display:inline-block;border:1px solid var(--line);padding:4px 9px;background:var(--panel);font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;font-size:12px;margin:0 6px 6px 0}
@media (max-width:860px){.hero,.two{grid-template-columns:1fr}.summary-grid{grid-template-columns:1fr 1fr}h1{font-size:38px}}
@media (max-width:560px){.summary-grid{grid-template-columns:1fr}main{padding-inline:16px}}
"""


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{escape(title)}</title><style>{CSS}</style></head><body><main>{body}</main></body></html>"
    )


def _fmt_pct(value) -> str:
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return ""


def _fmt_num(value) -> str:
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return ""


def _truthy(value) -> bool:
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes"}
    return bool(value)


def _fmt_money(value) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return ""


def _conclusion_block(summaries: list[dict], baseline_summary: dict | None) -> str:
    if not summaries:
        return "<h1>Version A Grid Backtest</h1>"

    best_composite = summaries[0]
    best_excess = max(summaries, key=lambda row: float(row.get("excess_return", 0) or 0))
    sweet_count = sum(1 for row in summaries if _truthy(row.get("sweet_spot")))
    positive_excess = sum(1 for row in summaries if float(row.get("excess_return", 0) or 0) > 0)
    baseline_roi = baseline_summary.get("roi") if baseline_summary else None
    baseline_invested = baseline_summary.get("total_invested") if baseline_summary else None
    best_invested = best_composite.get("total_invested")
    funding_gap = ""
    if baseline_invested is not None and best_invested not in (None, ""):
        funding_gap = _fmt_money(float(baseline_invested) - float(best_invested))

    return (
        "<section class='hero'>"
        "<div>"
        "<div class='verdict'>Result: failed the enhancement test</div>"
        "<h1>机械定投仍是这批参数的强基准</h1>"
        "<p class='note'>当前 Version A 的核心结论是：33648 组参数都没有跑赢机械定投。"
        "这些信号可以继续作为风控和节奏参考，但在本轮数据与资金规则下，不能证明它们能增强收益。</p>"
        "</div>"
        "<div class='card'>"
        "<h2>为什么结论这么硬</h2>"
        "<p>2011-2026 是纳指长牛样本，机械定投每天持续买入，没有暂停和等待确认。"
        "策略虽然会避开部分高位，但也降低了长期持仓暴露，补仓收益不足以弥补少买造成的差距。</p>"
        "</div>"
        "</section>"
        "<section class='summary-grid'>"
        f"<div class='metric good'><div class='label'>机械定投 ROI</div><div class='value'>{_fmt_pct(baseline_roi)}</div></div>"
        f"<div class='metric bad'><div class='label'>最佳超额收益</div><div class='value'>{_fmt_pct(best_excess.get('excess_return'))}</div></div>"
        f"<div class='metric bad'><div class='label'>严格甜品区间</div><div class='value'>{sweet_count}</div></div>"
        f"<div class='metric'><div class='label'>正超额组合数</div><div class='value'>{positive_excess}</div></div>"
        "</section>"
        "<section class='two'>"
        "<div class='card'><h2>资金口径</h2>"
        f"<p>机械定投总投入约 <strong>{_fmt_money(baseline_invested)}</strong>；"
        f"Top 综合组合总投入约 <strong>{_fmt_money(best_invested)}</strong>，少投入约 <strong>{funding_gap}</strong>。"
        "当前报告已把策略剩余现金计入期末资产，但仍未超过机械定投。</p></div>"
        "<div class='card'><h2>Top 组合也没有越线</h2>"
        f"<p>最高综合评分组合 ROI 为 <strong>{_fmt_pct(best_composite.get('roi'))}</strong>，"
        f"最大回撤为 <strong>{_fmt_pct(best_composite.get('max_drawdown'))}</strong>，"
        f"相对机械定投超额为 <strong>{_fmt_pct(best_composite.get('excess_return'))}</strong>。</p></div>"
        "</section>"
    )


def _version_b_block(output_dir: Path) -> str:
    path = output_dir.parent / "version_b_funds" / "summary.json"
    if not path.exists():
        return ""
    import json

    rows = json.loads(path.read_text(encoding="utf-8"))
    if not rows:
        return ""
    positive = sum(1 for row in rows if float(row.get("excess_return", 0) or 0) > 0)
    best = max(rows, key=lambda row: float(row.get("excess_return", 0) or 0))
    worst = min(rows, key=lambda row: float(row.get("excess_return", 0) or 0))
    positive_class = "good" if positive else "bad"
    best_class = "good" if float(best["excess_return"]) > 0 else "bad"
    table_rows = "".join(
        "<tr>"
        f"<td>{escape(str(row['code']))}</td>"
        f"<td>{escape(str(row['name']))}</td>"
        f"<td>{escape(str(row['start']))}</td>"
        f"<td>{escape(str(row['end']))}</td>"
        f"<td>{_fmt_pct(row['baseline_roi'])}</td>"
        f"<td>{_fmt_pct(row['strategy_roi'])}</td>"
        f"<td>{_fmt_pct(row['excess_return'])}</td>"
        f"<td>{_fmt_pct(row['baseline_mdd'])}</td>"
        f"<td>{_fmt_pct(row['strategy_mdd'])}</td>"
        "</tr>"
        for row in sorted(rows, key=lambda item: float(item.get("excess_return", 0) or 0), reverse=True)
    )
    return (
        "<section class='card'>"
        "<h2>Version B：10 只基金真实净值测算</h2>"
        "<p>信号沿用 Version A 最高综合评分参数，成交价格改为基金历史单位净值。"
        "结果比指数代理温和：部分基金小幅跑赢，但优势非常薄。</p>"
        "<section class='summary-grid'>"
        f"<div class='metric'><div class='label'>基金数量</div><div class='value'>{len(rows)}</div></div>"
        f"<div class='metric {positive_class}'><div class='label'>正超额基金数</div><div class='value'>{positive}</div></div>"
        f"<div class='metric {best_class}'><div class='label'>最佳超额</div><div class='value'>{_fmt_pct(best['excess_return'])}</div></div>"
        f"<div class='metric'><div class='label'>最佳基金</div><div class='value' style='font-size:18px'>{escape(str(best['code']))}</div></div>"
        "</section>"
        "<section class='two'>"
        f"<div class='subpanel'><h3>最好结果</h3><p>{escape(best['name'])}：策略 ROI {_fmt_pct(best['strategy_roi'])}，"
        f"机械 ROI {_fmt_pct(best['baseline_roi'])}，超额 {_fmt_pct(best['excess_return'])}。</p></div>"
        f"<div class='subpanel'><h3>最弱结果</h3><p>{escape(worst['name'])}：超额 {_fmt_pct(worst['excess_return'])}。"
        "这说明真实基金净值下仍没有形成稳定优势。</p></div>"
        "</section>"
        "<p><a href='../version_b_funds/index.html'>打开独立 Version B 报告</a></p>"
        "<div class='subpanel'><table><thead><tr><th>Code</th><th>Name</th><th>Start</th><th>End</th>"
        "<th>Baseline ROI</th><th>Strategy ROI</th><th>Excess</th><th>Base MDD</th><th>Strategy MDD</th></tr></thead>"
        f"<tbody>{table_rows}</tbody></table></div>"
        "</section>"
    )


def _detail_page(run_id: str, summary: dict, rows: list[dict]) -> str:
    metric_rows = "".join(
        f"<tr><td>{escape(str(key))}</td><td>{escape(str(value))}</td></tr>"
        for key, value in summary.items()
        if key != "run_id"
    )
    detail_rows = "".join(
        f"<tr><td>{escape(str(row.get('date','')))}</td><td>{escape(str(row.get('state','')))}</td>"
        f"<td>{_fmt_num(row.get('portfolio_value', 0))}</td><td>{_fmt_num(row.get('invested', 0))}</td></tr>"
        for row in rows[:500]
    )
    body = (
        "<p><a href='../index.html'>Back to overview</a></p>"
        f"<h1>{escape(run_id)}</h1>"
        "<div class='card'><h2>Metrics And Parameters</h2><table><tbody>"
        f"{metric_rows}</tbody></table></div>"
    )
    if detail_rows:
        body += (
            "<div class='card'><h2>Daily Sample</h2><table><thead>"
            "<tr><th>Date</th><th>State</th><th>Portfolio Value</th><th>Invested</th></tr>"
            f"</thead><tbody>{detail_rows}</tbody></table></div>"
        )
    return _page(run_id, body)


def build_report(
    output_dir: Path,
    *,
    summaries: list[dict],
    run_details: dict[str, list[dict]],
    baseline_summary: dict | None = None,
    write_details: bool = True,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_dir = output_dir / "runs"
    detail_dir.mkdir(exist_ok=True)
    rows = []
    table_limit = min(len(summaries), 1000)
    for item in summaries[:table_limit]:
        run_id = str(item["run_id"])
        rows.append(
            "<tr>"
            f"<td><a href='runs/{escape(run_id)}.html'>{escape(run_id)}</a></td>"
            f"<td>{escape(str(item.get('stage', '')))}</td>"
            f"<td>{'Yes' if _truthy(item.get('sweet_spot')) else 'No'}</td>"
            f"<td>{_fmt_num(item.get('composite_score', 0))}</td>"
            f"<td>{_fmt_pct(item.get('roi', 0))}</td>"
            f"<td>{_fmt_pct(item.get('max_drawdown', 0))}</td>"
            f"<td>{_fmt_pct(item.get('excess_return', 0))}</td>"
            "</tr>"
        )
        if write_details:
            (detail_dir / f"{run_id}.html").write_text(
                _detail_page(run_id, item, run_details.get(run_id, [])),
                encoding="utf-8",
            )
    sweet_count = sum(1 for row in summaries if _truthy(row.get("sweet_spot")))
    body = (
        _conclusion_block(summaries, baseline_summary)
        + _version_b_block(output_dir)
        +
        f"<p><span class='pill'>Runs: {len(summaries)}</span> "
        f"<span class='pill'>Sweet spots: {sweet_count}</span></p>"
        "<div class='card'><h2>参数排行</h2>"
        f"<p>页面展示前 {table_limit} 组；完整 {len(summaries)} 组参数记录保存在 summary.csv 和 summary.json。</p>"
        "<div class='card'><table><thead><tr><th>Run</th><th>Stage</th><th>Sweet Spot</th>"
        "<th>Composite</th><th>ROI</th><th>MDD</th><th>Excess</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></div>"
    )
    (output_dir / "index.html").write_text(_page("Version A Grid Backtest", body), encoding="utf-8")
