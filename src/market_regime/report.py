from __future__ import annotations

import io
import json
import math
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

from .config import OUTPUT_COLUMNS


REGIME_BANDS = [
    ("panic_low", "Panic Low", 0, 12, "#7f1d1d", "Severe stress; prices and sentiment are deeply depressed."),
    ("stress_low", "Stress Low", 12, 26, "#c2410c", "Below-trend market with elevated stress."),
    ("recovery", "Recovery", 26, 42, "#d97706", "Repair signals improving after stress."),
    ("normal", "Normal", 42, 58, "#15803d", "Balanced market; no major extreme dominates."),
    ("warm_recovery", "Warm Recovery", 58, 68, "#84cc16", "Repair signals are strong, but conditions are already warm."),
    ("warm", "Warm", 68, 78, "#65a30d", "Above-trend market with warmer conditions."),
    ("overheated", "Overheated", 78, 88, "#dc2626", "Multiple overheat signals are active."),
    ("top_risk_watch", "Top Risk Watch", 88, 94, "#ea580c", "Top-risk evidence is elevated but below full risk."),
    ("top_risk", "Top Risk", 94, 100, "#7c2d12", "Overheat plus structural deterioration risk."),
]

REGIME_LABELS = {key: label for key, label, *_ in REGIME_BANDS}

GITHUB_REPO_URL = "https://github.com/jinsong-y/nasdaq-invest-analysis"


ZH_TEXT = {
    "Market Regime Dashboard": "市场状态仪表盘",
    "Finance-tech market monitor": "金融科技市场监测",
    "Market State Gauge": "市场状态指针",
    "Summary": "摘要",
    "How This Dashboard Works": "仪表说明",
    "Drivers": "主要驱动",
    "Risks": "风险",
    "Latest Inputs": "最新输入",
    "Config": "配置",
    "Recent Daily Regimes": "近期每日状态",
    "As of": "日期",
    "Regime": "状态",
    "Action": "动作",
    "Temperature": "温度",
    "Confidence": "置信度",
    "Data date": "数据日期",
    "GitHub": "GitHub",
    "current regime": "当前状态",
    "Panic Low": "恐慌低位",
    "Stress Low": "压力偏低",
    "Recovery": "修复期",
    "Normal": "正常",
    "Warm Recovery": "暖修复",
    "Warm": "偏热",
    "Overheated": "过热",
    "Top Risk Watch": "顶部风险观察",
    "Top Risk": "顶部风险",
    "Severe stress; prices and sentiment are deeply depressed.": "严重压力；价格和情绪明显低迷。",
    "Below-trend market with elevated stress.": "低于趋势且压力升高。",
    "Repair signals improving after stress.": "压力后修复信号改善。",
    "Balanced market; no major extreme dominates.": "市场均衡；没有主要极端信号。",
    "Repair signals are strong, but conditions are already warm.": "修复信号强，但市场已经偏热。",
    "Above-trend market with warmer conditions.": "高于趋势，市场温度偏暖。",
    "Multiple overheat signals are active.": "多个过热信号同时出现。",
    "Top-risk evidence is elevated but below full risk.": "顶部风险证据升高，但尚未达到完整风险状态。",
    "Overheat plus structural deterioration risk.": "过热叠加结构走弱风险。",
    "Severe stress with low-market evidence.": "严重压力，低位证据明显。",
    "Market stress and below-trend evidence.": "市场承压，且存在低于趋势的证据。",
    "No dominant extreme signal.": "没有主导性的极端信号。",
    "Required inputs missing.": "关键输入缺失。",
    "Current.": "当前。",
    "normal_dca": "正常定投",
    "add_strong": "强加仓",
    "add_light": "轻加仓",
    "reduce_light": "轻降节奏",
    "reduce": "降低节奏",
    "pause_new_buy": "暂停新买入",
    "pause": "暂停",
    "unavailable": "不可用",
    "undervaluation": "偏低",
    "overheat": "过热",
    "top_risk_watch": "顶部风险观察",
    "top_risk": "顶部风险",
    "recovery": "修复",
    "trend": "趋势",
    "volatility": "波动",
    "sentiment": "情绪",
    "breadth": "广度",
    "semiconductor": "半导体",
    "market_stress": "市场压力",
    "low_confidence": "低置信度",
    "no_major_extreme": "无主要极端",
}


CSS = """
:root {
  color-scheme: light;
  font-family: "Aptos", "Helvetica Neue", Arial, sans-serif;
  background: #f4f7fb;
  color: #142033;
}

body {
  margin: 0;
  padding: 40px 32px 56px;
  background:
    linear-gradient(180deg, rgba(226, 237, 247, 0.86) 0%, rgba(244, 247, 251, 0) 280px),
    #f4f7fb;
}

main {
  max-width: 1180px;
  margin: 0 auto;
}

h1,
h2 {
  margin: 0;
}

h1 {
  font-size: 30px;
  letter-spacing: 0;
  color: #102033;
}

.topbar {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-start;
  margin-bottom: 24px;
}

.brand-block {
  display: grid;
  gap: 6px;
}

.subtitle {
  margin: 0;
  color: #5d6b7a;
  font-size: 14px;
  line-height: 1.45;
}

.top-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.github-link {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 0 13px;
  border: 1px solid #c6d2df;
  border-radius: 999px;
  background: #102033;
  color: #ffffff;
  font-size: 13px;
  font-weight: 700;
  text-decoration: none;
}

.language-toggle {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid #d8dee7;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
}

.language-toggle button {
  appearance: none;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #3b4754;
  padding: 7px 12px;
  cursor: pointer;
  font-weight: 700;
}

body.lang-en .language-toggle [data-language="en"],
body.lang-zh .language-toggle [data-language="zh"] {
  background: #102033;
  color: #ffffff;
}

[data-lang="zh"] {
  display: none;
}

body.lang-zh [data-lang="en"] {
  display: none;
}

body.lang-zh [data-lang="zh"] {
  display: inline;
}

h2 {
  margin-top: 34px;
  font-size: 18px;
  color: #102033;
}

.summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
  margin-top: 0;
}

.metric {
  border: 1px solid #d5e0ea;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  padding: 17px;
  box-shadow: 0 10px 28px rgba(20, 32, 51, 0.05);
}

.label {
  color: #5d6b7a;
  font-size: 12px;
  text-transform: uppercase;
}

.value {
  margin-top: 8px;
  font-size: 22px;
  font-weight: 700;
  color: #102033;
}

.gauge-grid {
  display: grid;
  grid-template-columns: minmax(280px, 1.1fr) minmax(260px, 0.9fr);
  gap: 22px;
  align-items: center;
}

.regime-gauge {
  width: 100%;
  max-width: 520px;
  margin: 0 auto;
  display: block;
}

.gauge-label {
  text-anchor: middle;
  fill: #18202a;
  font-weight: 700;
  font-size: 14px;
}

.gauge-sub {
  text-anchor: middle;
  fill: #5d6b7a;
  font-size: 9px;
  text-transform: uppercase;
}

.legend-grid {
  display: grid;
  gap: 9px;
  margin: 0;
  padding: 0;
}

.legend-item {
  list-style: none;
  display: grid;
  grid-template-columns: 14px minmax(84px, 0.42fr) 1fr;
  gap: 8px;
  align-items: start;
  color: #3b4754;
  font-size: 13px;
}

.legend-item strong {
  color: #18202a;
}

.swatch {
  width: 14px;
  height: 14px;
  border-radius: 999px;
  margin-top: 2px;
  border: 1px solid rgba(24, 32, 42, 0.16);
}

.panel {
  border: 1px solid #d5e0ea;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.96);
  margin-top: 14px;
  padding: 20px;
  box-shadow: 0 12px 30px rgba(20, 32, 51, 0.045);
}

.panel-kicker {
  margin: 0 0 14px;
  color: #5d6b7a;
  font-size: 13px;
  font-weight: 700;
}

.methodology {
  display: grid;
  gap: 16px;
}

.methodology-intro,
.methodology-note {
  margin: 0;
  color: #3b4754;
  line-height: 1.55;
}

.methodology-group h3 {
  margin: 0 0 8px;
  color: #18202a;
  font-size: 14px;
}

.methodology-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
}

.methodology-list li {
  list-style: none;
  color: #3b4754;
  line-height: 1.45;
}

.methodology-list strong {
  color: #18202a;
}

ul {
  margin: 8px 0 0;
  padding-left: 20px;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 12px;
  background: #ffffff;
}

th,
td {
  border-bottom: 1px solid #e3e8ef;
  padding: 12px 10px;
  text-align: left;
  white-space: nowrap;
}

th {
  background: #edf4fa;
  color: #3b4754;
  font-size: 12px;
  text-transform: uppercase;
}

.table-wrap {
  overflow-x: auto;
  border: 1px solid #d8dee7;
  border-radius: 8px;
  margin-top: 12px;
}

@media (max-width: 780px) {
  body {
    padding: 18px;
  }

  .topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .top-actions {
    justify-content: flex-start;
  }

  .gauge-grid {
    grid-template-columns: 1fr;
  }

  .legend-item {
    grid-template-columns: 14px minmax(82px, 0.32fr) 1fr;
  }
}
"""


LANGUAGE_SCRIPT = """
<script>
function setLanguage(language) {
  const isChinese = language === "zh";
  document.body.classList.toggle("lang-zh", isChinese);
  document.body.classList.toggle("lang-en", !isChinese);
  document.documentElement.lang = isChinese ? "zh-CN" : "en";
  for (const button of document.querySelectorAll("[data-language]")) {
    button.setAttribute("aria-pressed", button.dataset.language === language ? "true" : "false");
  }
}

document.addEventListener("DOMContentLoaded", function () {
  setLanguage("en");
  for (const button of document.querySelectorAll("[data-language]")) {
    button.addEventListener("click", function () {
      setLanguage(button.dataset.language);
    });
  }
});
</script>
"""


def write_dashboard_outputs(output_dir: Path, daily: pd.DataFrame, summary: dict[str, Any]) -> None:
    missing_columns = [column for column in OUTPUT_COLUMNS if column not in daily.columns]
    if missing_columns:
        raise ValueError(f"daily is missing output columns: {', '.join(missing_columns)}")

    csv_buffer = io.StringIO()
    daily.to_csv(csv_buffer, index=False, columns=OUTPUT_COLUMNS)
    json_text = json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False)
    html_text = _html_page(daily, summary)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "daily_regimes.csv").write_text(csv_buffer.getvalue(), encoding="utf-8")
    (output_dir / "latest.json").write_text(json_text, encoding="utf-8")
    (output_dir / "index.html").write_text(html_text, encoding="utf-8")


def _html_page(daily: pd.DataFrame, summary: dict[str, Any]) -> str:
    rows = _recent_rows(daily)
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>Market Regime Dashboard</title>",
            f"<style>{CSS}</style>",
            "</head>",
            '<body class="lang-en">',
            "<main>",
            '<div class="topbar">',
            '<div class="brand-block">',
            f"<h1>{_localized('Market Regime Dashboard')}</h1>",
            f'<p class="subtitle">{_localized("Finance-tech market monitor")}</p>',
            "</div>",
            '<div class="top-actions">',
            _github_link(),
            _language_toggle(),
            "</div>",
            "</div>",
            _summary_grid(summary),
            _config_metadata_html(summary),
            _section("Market State Gauge", _regime_gauge(summary)),
            _section("Summary", _summary_paragraph(summary)),
            _section("How This Dashboard Works", _methodology_html()),
            _section("Drivers", _list(summary.get("drivers", []))),
            _section("Risks", _list(summary.get("risks", []))),
            _section("Latest Inputs", _latest_inputs_html(summary)),
            _section("Recent Daily Regimes", _table(rows)),
            "</main>",
            LANGUAGE_SCRIPT,
            "</body>",
            "</html>",
        ]
    )


def _summary_grid(summary: dict[str, Any]) -> str:
    metrics = [
        ("As of", summary.get("as_of_date", "")),
        ("Regime", _translated_regime_value(summary.get("market_regime", ""))),
        ("Action", _translated_value(summary.get("dashboard_action", ""))),
        ("Temperature", summary.get("temperature_score", "")),
        ("Confidence", summary.get("confidence_score", "")),
    ]
    cards = [
        '<div class="metric">'
        f'<div class="label">{_localized(label)}</div>'
        f'<div class="value">{_format_display_value(value)}</div>'
        "</div>"
        for label, value in metrics
    ]
    return f'<section class="summary">{"".join(cards)}</section>'


def _config_metadata_html(summary: dict[str, Any]) -> str:
    metadata = summary.get("config_metadata")
    if not metadata:
        return ""
    if not isinstance(metadata, dict):
        raise ValueError("config_metadata must be a dict")
    return _section("Config", _key_value_list(metadata))


def _regime_gauge(summary: dict[str, Any]) -> str:
    regime = _format_value(summary.get("market_regime", "normal"))
    active = _band_for_regime(regime)
    active_midpoint = (active[2] + active[3]) / 2.0
    needle_angle = 180.0 - active_midpoint * 1.8
    needle_x, needle_y = _polar(120.0, 116.0, 76.0, needle_angle)
    segments = "".join(_gauge_segment(band) for band in REGIME_BANDS)
    legend = "".join(_legend_item(band, regime) for band in REGIME_BANDS)
    active_label = escape(active[1])
    active_label_zh = escape(ZH_TEXT.get(active[1], active[1]))
    return (
        '<div class="gauge-grid">'
        '<svg class="regime-gauge" viewBox="0 0 240 145" role="img" '
        'aria-labelledby="gauge-title gauge-desc">'
        '<title id="gauge-title">Market regime gauge</title>'
        f'<desc id="gauge-desc">Current market regime is {active_label} / {active_label_zh}.</desc>'
        '<path d="M 20 116 A 100 100 0 0 1 220 116" fill="none" stroke="#e3e8ef" '
        'stroke-width="18" stroke-linecap="round"/>'
        f"{segments}"
        f'<line x1="120" y1="116" x2="{needle_x:.2f}" y2="{needle_y:.2f}" '
        'stroke="#18202a" stroke-width="4" stroke-linecap="round"/>'
        '<circle cx="120" cy="116" r="7" fill="#18202a"/>'
        f'{_localized_svg_text(active[1], x=120, y=132, class_name="gauge-label")}'
        f'{_localized_svg_text("current regime", x=120, y=142, class_name="gauge-sub")}'
        "</svg>"
        f'<ul class="legend-grid">{legend}</ul>'
        "</div>"
    )


def _band_for_regime(regime: str) -> tuple[str, str, int, int, str, str]:
    for band in REGIME_BANDS:
        if band[0] == regime:
            return band
    for band in REGIME_BANDS:
        if band[0] == "normal":
            return band
    raise ValueError("normal regime band is not configured")


def _gauge_segment(band: tuple[str, str, int, int, str, str]) -> str:
    _, label, start, end, color, _ = band
    start_angle = 180.0 - start * 1.8
    end_angle = 180.0 - end * 1.8
    d = _arc_path(120.0, 116.0, 100.0, start_angle, end_angle)
    return (
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="18" '
        f'stroke-linecap="butt" aria-label="{escape(label)}"/>'
    )


def _legend_item(band: tuple[str, str, int, int, str, str], current_regime: str) -> str:
    key, label, start, end, color, description = band
    current = _localized("Current.") if key == current_regime else ""
    return (
        '<li class="legend-item">'
        f'<span class="swatch" style="background:{color}"></span>'
        f"<strong>{_localized(label)}</strong>"
        f"<span>{start}-{end}: {_localized(description)}{current}</span>"
        "</li>"
    )


def _arc_path(cx: float, cy: float, radius: float, start_angle: float, end_angle: float) -> str:
    start_x, start_y = _polar(cx, cy, radius, start_angle)
    end_x, end_y = _polar(cx, cy, radius, end_angle)
    large_arc = 1 if abs(end_angle - start_angle) > 180 else 0
    return f"M {start_x:.2f} {start_y:.2f} A {radius:.2f} {radius:.2f} 0 {large_arc} 1 {end_x:.2f} {end_y:.2f}"


def _polar(cx: float, cy: float, radius: float, angle: float) -> tuple[float, float]:
    radians = math.radians(angle)
    return cx + radius * math.cos(radians), cy - radius * math.sin(radians)


def _section(title: str, body: str) -> str:
    return f"<h2>{_localized(title)}</h2><section class=\"panel\">{body}</section>"


def _paragraph(value: Any) -> str:
    return f"<p>{escape(_format_value(value))}</p>"


def _summary_paragraph(summary: dict[str, Any]) -> str:
    return f"<p>{_localized(_format_value(summary.get('summary', '')))}</p>"


def _latest_inputs_html(summary: dict[str, Any]) -> str:
    as_of = _format_value(summary.get("as_of_date", ""))
    return (
        f'<p class="panel-kicker">{_localized("Data date")}: {escape(as_of)}</p>'
        f'{_key_value_list(summary.get("inputs", {}))}'
    )


def _methodology_html() -> str:
    inputs = [
        (
            "NDX price and 180-day SMA",
            "Shows trend direction and how far price is above or below its long-term baseline.",
            "纳指价格与 180 日均线",
            "判断趋势方向，以及价格相对长期基准的偏离程度。",
        ),
        (
            "VIX / VXN volatility",
            "Measures market stress; high volatility raises low-zone or risk signals depending on price context.",
            "VIX / VXN 波动率",
            "衡量市场压力；高波动会结合价格位置影响低位或风险判断。",
        ),
        (
            "CNN Fear & Greed",
            "Tracks sentiment and short-term emotional temperature.",
            "CNN 恐惧贪婪指数",
            "衡量市场情绪和短期情绪温度。",
        ),
        (
            "NDXE / NDX breadth",
            "Compares equal-weighted Nasdaq 100 with cap-weighted Nasdaq 100 to see whether strength is broad.",
            "NDXE / NDX 市场广度",
            "比较等权纳指与市值加权纳指，观察上涨是否足够广泛。",
        ),
        (
            "SOX / NDX semiconductor leadership",
            "Checks whether the semiconductor core of the tech cycle is confirming or weakening.",
            "SOX / NDX 半导体主线强弱",
            "观察半导体这个科技周期核心主线是在确认还是走弱。",
        ),
    ]
    scores = [
        (
            "Scores",
            "The model combines temperature, low-zone, overheat, trend, recovery, and confidence scores.",
            "评分",
            "模型合成温度、低位、过热、趋势、修复和置信度评分。",
        ),
        (
            "Regime",
            "Those scores map to regimes such as panic low, stress low, recovery, normal, warm, overheated, and top risk.",
            "状态",
            "这些评分会映射为恐慌低位、压力偏低、修复、正常、偏热、过热和顶部风险等状态。",
        ),
        (
            "Action",
            "The action is a DCA pacing reference: add, keep normal, reduce, or pause new buying.",
            "动作",
            "动作是定投节奏参考：加仓、正常定投、降速或暂停新买入。",
        ),
    ]
    validation = [
        (
            "Robustness check: 9 of 9 known stress or top-risk dates passed.",
            "历史校验：9 个已知压力或顶部风险日期全部通过。",
        ),
        (
            "Threshold grid score improved from 113.72 to 116.59 after robustness tuning.",
            "阈值网格评分从 113.72 提升到 116.59。",
        ),
        (
            "Walk-forward windows were checked across 2011-2015, 2016-2020, 2021-2026, and multiple stress periods.",
            "已在 2011-2015、2016-2020、2021-2026 以及多个压力时期做 walk-forward 校验。",
        ),
    ]
    return (
        '<div class="methodology">'
        f'<p class="methodology-intro">{_localized_pair("This dashboard is a Nasdaq 100 market-regime classifier. It is built to explain market condition and DCA pacing, not to forecast returns.", "这个仪表盘是纳指 100 市场状态分类器，用来解释市场环境和定投节奏，不是收益预测。")}</p>'
        f'{_methodology_group("Inputs", "指标", inputs)}'
        f'{_methodology_group("Scoring and output", "评分与输出", scores)}'
        f'{_methodology_validation(validation)}'
        f'<p class="methodology-note">{_localized_pair("This is a regime and DCA pacing reference, not a return forecast.", "这是市场状态与定投节奏参考，不是收益预测。")}</p>'
        "</div>"
    )


def _methodology_group(title_en: str, title_zh: str, rows: list[tuple[str, str, str, str]]) -> str:
    items = "".join(
        "<li>"
        f"<strong>{_localized_pair(label_en, label_zh)}</strong>: "
        f"{_localized_pair(description_en, description_zh)}"
        "</li>"
        for label_en, description_en, label_zh, description_zh in rows
    )
    return (
        '<div class="methodology-group">'
        f"<h3>{_localized_pair(title_en, title_zh)}</h3>"
        f'<ul class="methodology-list">{items}</ul>'
        "</div>"
    )


def _methodology_validation(rows: list[tuple[str, str]]) -> str:
    items = "".join(f"<li>{_localized_pair(english, chinese)}</li>" for english, chinese in rows)
    return (
        '<div class="methodology-group">'
        f"<h3>{_localized_pair('Backtest validation', '回测验证')}</h3>"
        f'<ul class="methodology-list">{items}</ul>'
        "</div>"
    )


def _list(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "<p>None</p>"
    items = "".join(f"<li>{_localized(_format_value(value))}</li>" for value in values)
    return f"<ul>{items}</ul>"


def _key_value_list(values: Any) -> str:
    if not isinstance(values, dict) or not values:
        return "<p>None</p>"
    items = "".join(
        f"<li><strong>{escape(str(key))}</strong>: {escape(_format_value(value))}</li>"
        for key, value in values.items()
    )
    return f"<ul>{items}</ul>"


def _table(frame: pd.DataFrame) -> str:
    columns = [column for column in OUTPUT_COLUMNS if column in frame.columns]
    if not columns:
        return "<p>No daily regime rows available.</p>"

    header = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body_rows = []
    for _, row in frame[columns].iterrows():
        cells = "".join(f"<td>{escape(_format_value(row[column]))}</td>" for column in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    body = "".join(body_rows) or f'<tr><td colspan="{len(columns)}">No daily regime rows available.</td></tr>'
    return f'<div class="table-wrap"><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>'


def _recent_rows(daily: pd.DataFrame) -> pd.DataFrame:
    rows = daily.tail(20).copy()
    if "date" not in rows.columns:
        return rows
    rows["_sort_date"] = pd.to_datetime(rows["date"], errors="coerce")
    rows = rows.sort_values("_sort_date", ascending=False, na_position="last")
    return rows.drop(columns=["_sort_date"])


def _format_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _localized(english: str) -> str:
    chinese = ZH_TEXT.get(english, english)
    return f'<span data-lang="en">{escape(english)}</span><span data-lang="zh">{escape(chinese)}</span>'


def _localized_pair(english: str, chinese: str) -> str:
    return f'<span data-lang="en">{escape(english)}</span><span data-lang="zh">{escape(chinese)}</span>'


def _localized_svg_text(english: str, *, x: int, y: int, class_name: str) -> str:
    chinese = ZH_TEXT.get(english, english)
    return (
        f'<text x="{x}" y="{y}" class="{escape(class_name)}" data-lang="en">{escape(english)}</text>'
        f'<text x="{x}" y="{y}" class="{escape(class_name)}" data-lang="zh">{escape(chinese)}</text>'
    )


def _translated_value(value: Any) -> tuple[str, str]:
    text = _format_value(value)
    return text, ZH_TEXT.get(text, text)


def _translated_regime_value(value: Any) -> tuple[str, str]:
    code = _format_value(value)
    english = REGIME_LABELS.get(code, code)
    return english, ZH_TEXT.get(english, english)


def _format_display_value(value: Any) -> str:
    if isinstance(value, tuple):
        english, chinese = value
        return f'<span data-lang="en">{escape(english)}</span><span data-lang="zh">{escape(chinese)}</span>'
    return escape(_format_value(value))


def _language_toggle() -> str:
    return (
        '<div class="language-toggle" aria-label="Language switch">'
        '<button type="button" data-language="en" aria-pressed="true">English</button>'
        '<button type="button" data-language="zh" aria-pressed="false">中文</button>'
        "</div>"
    )


def _github_link() -> str:
    return (
        f'<a class="github-link" href="{GITHUB_REPO_URL}" target="_blank" '
        f'rel="noopener noreferrer">{_localized("GitHub")}</a>'
    )
