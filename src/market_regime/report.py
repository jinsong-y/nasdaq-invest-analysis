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
    ("panic_low", "Panic Low", 0, 14, "#7f1d1d", "Severe stress; prices and sentiment are deeply depressed."),
    ("stress_low", "Stress Low", 14, 28, "#c2410c", "Below-trend market with elevated stress."),
    ("recovery", "Recovery", 28, 44, "#d97706", "Repair signals improving after stress."),
    ("normal", "Normal", 44, 60, "#15803d", "Balanced market; no major extreme dominates."),
    ("warm", "Warm", 60, 74, "#65a30d", "Above-trend market with warmer conditions."),
    ("overheated", "Overheated", 74, 88, "#dc2626", "Multiple overheat signals are active."),
    ("top_risk", "Top Risk", 88, 100, "#7c2d12", "Overheat plus structural deterioration risk."),
]


CSS = """
:root {
  color-scheme: light;
  font-family: Arial, Helvetica, sans-serif;
  background: #f6f7f9;
  color: #18202a;
}

body {
  margin: 0;
  padding: 32px;
}

main {
  max-width: 1120px;
  margin: 0 auto;
}

h1,
h2 {
  margin: 0;
}

h1 {
  font-size: 28px;
}

h2 {
  margin-top: 28px;
  font-size: 18px;
}

.summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-top: 20px;
}

.metric {
  border: 1px solid #d8dee7;
  border-radius: 8px;
  background: #ffffff;
  padding: 14px;
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
}

.gauge-grid {
  display: grid;
  grid-template-columns: minmax(280px, 1.1fr) minmax(260px, 0.9fr);
  gap: 16px;
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
  border: 1px solid #d8dee7;
  border-radius: 8px;
  background: #ffffff;
  margin-top: 12px;
  padding: 16px;
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
  padding: 10px;
  text-align: left;
  white-space: nowrap;
}

th {
  background: #eef2f6;
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

  .gauge-grid {
    grid-template-columns: 1fr;
  }

  .legend-item {
    grid-template-columns: 14px minmax(82px, 0.32fr) 1fr;
  }
}
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
    rows = daily.tail(20)
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
            "<body>",
            "<main>",
            "<h1>Market Regime Dashboard</h1>",
            _summary_grid(summary),
            _section("Market State Gauge", _regime_gauge(summary)),
            _section("Summary", _paragraph(summary.get("summary", ""))),
            _section("Drivers", _list(summary.get("drivers", []))),
            _section("Risks", _list(summary.get("risks", []))),
            _section("Latest Inputs", _key_value_list(summary.get("inputs", {}))),
            _section("Recent Daily Regimes", _table(rows)),
            "</main>",
            "</body>",
            "</html>",
        ]
    )


def _summary_grid(summary: dict[str, Any]) -> str:
    metrics = [
        ("As of", summary.get("as_of_date", "")),
        ("Regime", summary.get("market_regime", "")),
        ("Action", summary.get("dashboard_action", "")),
        ("Temperature", summary.get("temperature_score", "")),
        ("Confidence", summary.get("confidence_score", "")),
    ]
    cards = [
        '<div class="metric">'
        f'<div class="label">{escape(label)}</div>'
        f'<div class="value">{escape(_format_value(value))}</div>'
        "</div>"
        for label, value in metrics
    ]
    return f'<section class="summary">{"".join(cards)}</section>'


def _regime_gauge(summary: dict[str, Any]) -> str:
    regime = _format_value(summary.get("market_regime", "normal"))
    active = _band_for_regime(regime)
    active_midpoint = (active[2] + active[3]) / 2.0
    needle_angle = 180.0 - active_midpoint * 1.8
    needle_x, needle_y = _polar(120.0, 116.0, 76.0, needle_angle)
    segments = "".join(_gauge_segment(band) for band in REGIME_BANDS)
    legend = "".join(_legend_item(band, regime) for band in REGIME_BANDS)
    active_label = escape(active[1])
    return (
        '<div class="gauge-grid">'
        '<svg class="regime-gauge" viewBox="0 0 240 145" role="img" '
        'aria-labelledby="gauge-title gauge-desc">'
        '<title id="gauge-title">Market regime gauge</title>'
        f'<desc id="gauge-desc">Current market regime is {active_label}.</desc>'
        '<path d="M 20 116 A 100 100 0 0 1 220 116" fill="none" stroke="#e3e8ef" '
        'stroke-width="18" stroke-linecap="round"/>'
        f"{segments}"
        f'<line x1="120" y1="116" x2="{needle_x:.2f}" y2="{needle_y:.2f}" '
        'stroke="#18202a" stroke-width="4" stroke-linecap="round"/>'
        '<circle cx="120" cy="116" r="7" fill="#18202a"/>'
        f'<text x="120" y="132" class="gauge-label">{active_label}</text>'
        '<text x="120" y="142" class="gauge-sub">current regime</text>'
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
    current = " Current." if key == current_regime else ""
    return (
        '<li class="legend-item">'
        f'<span class="swatch" style="background:{color}"></span>'
        f'<strong>{escape(label)}</strong>'
        f'<span>{start}-{end}: {escape(description)}{current}</span>'
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
    return f"<h2>{escape(title)}</h2><section class=\"panel\">{body}</section>"


def _paragraph(value: Any) -> str:
    return f"<p>{escape(_format_value(value))}</p>"


def _list(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "<p>None</p>"
    items = "".join(f"<li>{escape(_format_value(value))}</li>" for value in values)
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


def _format_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
