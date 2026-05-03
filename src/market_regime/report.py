from __future__ import annotations

import io
import json
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

from .config import OUTPUT_COLUMNS


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
