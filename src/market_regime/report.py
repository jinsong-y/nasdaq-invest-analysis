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
    ("panic_low", "Panic Low", 0, 12, "#1d4ed8", "Severe stress; prices and sentiment are deeply depressed."),
    ("stress_low", "Stress Low", 12, 26, "#2563eb", "Below-trend market with elevated stress."),
    ("recovery", "Recovery", 26, 42, "#38bdf8", "Repair signals improving after stress."),
    ("normal", "Normal", 42, 58, "#14b8a6", "Balanced market; no major extreme dominates."),
    ("warm_recovery", "Warm Recovery", 58, 68, "#facc15", "Repair signals are strong, but conditions are already warm."),
    ("warm", "Warm", 68, 78, "#f97316", "Above-trend market with warmer conditions."),
    ("overheated", "Overheated", 78, 88, "#dc2626", "Multiple overheat signals are active."),
    ("top_risk_watch", "Top Risk Watch", 88, 94, "#b91c1c", "Top-risk evidence is elevated but below full risk."),
    ("top_risk", "Top Risk", 94, 100, "#7f1d1d", "Overheat plus structural deterioration risk."),
]

REGIME_LABELS = {key: label for key, label, *_ in REGIME_BANDS}

GITHUB_REPO_URL = "https://github.com/jinsong-y/nasdaq-invest-analysis"


ZH_TEXT = {
    "Nasdaq 100 Market Regime Dashboard": "纳指100市场状态仪表盘",
    "Finance-tech market monitor": "金融科技市场监测",
    "Market State Gauge": "市场状态指针",
    "Composite Score Trend": "综合评分曲线",
    "Summary": "摘要",
    "How This Dashboard Works": "仪表说明",
    "Drivers": "主要驱动",
    "Risks": "风险",
    "Latest Inputs": "最新输入",
    "Config": "配置",
    "Recent Daily Regimes": "近期每日状态",
    "As of": "日期",
    "Current Time": "当前天文时间",
    "Regime": "状态",
    "Action": "动作",
    "Temperature": "温度",
    "Confidence": "置信度",
    "Data date": "数据日期",
    "Dashboard data date": "仪表盘数据日期",
    "GitHub": "GitHub",
    "copy markdown": "复制 markdown",
    "Copied": "已复制",
    "Copy failed": "复制失败",
    "send this page info to your AI for further analysis": "将本页信息发送给你的 AI 继续分析",
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
    "Composite score": "综合评分",
    "Daily composite score": "每日综合评分",
    "Week": "周",
    "Month": "月",
    "Year": "年",
    "No score history available.": "暂无评分历史。",
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
  --background: #f8fafc;
  --foreground: #111827;
  --card: #ffffff;
  --card-foreground: #111827;
  --muted: #f1f5f9;
  --muted-foreground: #64748b;
  --border: #e2e8f0;
  --primary: #0f766e;
  --primary-foreground: #f8fafc;
  --accent: #b45309;
  --accent-soft: #fffbeb;
  --ring: rgba(15, 118, 110, 0.22);
  --shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
  --radius: 8px;
  font-family: "Aptos", "Helvetica Neue", Arial, sans-serif;
  background: var(--background);
  color: var(--foreground);
}

body {
  margin: 0;
  padding: 32px 28px 56px;
  background:
    linear-gradient(180deg, rgba(15, 118, 110, 0.08) 0%, rgba(248, 250, 252, 0) 340px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.035) 1px, transparent 1px),
    linear-gradient(180deg, rgba(15, 23, 42, 0.035) 1px, transparent 1px),
    var(--background);
  background-size: auto, 36px 36px, 36px 36px;
}

main {
  max-width: 1220px;
  margin: 0 auto;
}

h1,
h2 {
  margin: 0;
}

h1 {
  font-size: 32px;
  letter-spacing: 0;
  color: var(--foreground);
}

.topbar {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-start;
  margin-bottom: 22px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(255, 255, 255, 0.84);
  padding: 22px;
  box-shadow: var(--shadow);
  backdrop-filter: blur(14px);
}

.brand-block {
  display: grid;
  gap: 6px;
}

.subtitle {
  margin: 0;
  color: var(--muted-foreground);
  font-size: 14px;
  line-height: 1.45;
}

.top-actions {
  display: grid;
  gap: 8px;
  justify-items: end;
}

.copy-action {
  display: grid;
  gap: 6px;
  justify-items: stretch;
  min-width: min(100%, 292px);
  padding: 10px;
  border: 1px solid rgba(15, 118, 110, 0.18);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.72);
}

.secondary-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.github-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 0 13px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--card);
  color: var(--foreground);
  font-size: 13px;
  font-weight: 700;
  text-decoration: none;
  transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

.github-link:hover {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--ring);
  transform: translateY(-1px);
}

.copy-button {
  appearance: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 0 13px;
  border: 1px solid rgba(15, 118, 110, 0.26);
  border-radius: 6px;
  background: rgba(15, 118, 110, 0.08);
  color: var(--primary);
  cursor: pointer;
  font-size: 13px;
  font-weight: 800;
  text-transform: none;
  transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease, background 160ms ease;
}

.copy-helper {
  margin: 0;
  color: var(--muted-foreground);
  font-size: 11px;
  font-weight: 700;
  line-height: 1.35;
  text-align: left;
}

.copy-button:hover {
  border-color: var(--primary);
  background: rgba(15, 118, 110, 0.12);
  box-shadow: 0 0 0 3px var(--ring);
  transform: translateY(-1px);
}

.copy-button[data-copy-state="copied"] {
  border-color: rgba(15, 118, 110, 0.42);
  background: rgba(15, 118, 110, 0.14);
}

.copy-button[data-copy-state="failed"] {
  border-color: rgba(220, 38, 38, 0.34);
  background: rgba(220, 38, 38, 0.08);
  color: #b91c1c;
}

.language-toggle {
  display: inline-flex;
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--muted);
}

.language-toggle button {
  appearance: none;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--muted-foreground);
  padding: 7px 12px;
  cursor: pointer;
  font-weight: 700;
  transition: background 160ms ease, color 160ms ease, box-shadow 160ms ease;
}

body.lang-en .language-toggle [data-language="en"],
body.lang-zh .language-toggle [data-language="zh"] {
  background: var(--card);
  color: var(--foreground);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.12);
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
  margin-top: 30px;
  font-size: 18px;
  color: var(--foreground);
  display: flex;
  align-items: center;
  gap: 10px;
}

h2::before {
  content: "";
  width: 6px;
  height: 18px;
  border-radius: 999px;
  background: linear-gradient(180deg, var(--primary), var(--accent));
}

.summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 12px;
  margin-top: 0;
}

.metric {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card);
  padding: 16px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
  min-height: 86px;
}

.label {
  color: var(--muted-foreground);
  font-size: 12px;
  text-transform: uppercase;
  font-weight: 800;
}

.value {
  margin-top: 8px;
  font-size: 22px;
  font-weight: 700;
  color: var(--card-foreground);
  overflow-wrap: anywhere;
}

.metric-regime .value [data-lang],
.metric-action .value [data-lang] {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border: 1px solid rgba(15, 118, 110, 0.22);
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.08);
  color: var(--primary);
  font-size: 14px;
  font-weight: 800;
}

.metric-action .value [data-lang] {
  border-color: rgba(180, 83, 9, 0.24);
  background: var(--accent-soft);
  color: var(--accent);
}

body.lang-en .metric-regime .value [data-lang="zh"],
body.lang-en .metric-action .value [data-lang="zh"],
body.lang-zh .metric-regime .value [data-lang="en"],
body.lang-zh .metric-action .value [data-lang="en"] {
  display: none;
}

.gauge-grid {
  display: grid;
  grid-template-columns: minmax(300px, 1.05fr) minmax(280px, 0.95fr);
  gap: 24px;
  align-items: center;
}

.regime-gauge {
  width: 100%;
  max-width: 540px;
  margin: 0 auto;
  display: block;
}

.gauge-label {
  text-anchor: middle;
  fill: var(--foreground);
  font-weight: 700;
  font-size: 13px;
}

.gauge-sub {
  text-anchor: middle;
  fill: var(--muted-foreground);
  font-size: 9px;
  text-transform: uppercase;
}

.score-trend-header {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  margin-bottom: 14px;
}

.score-trend-title {
  display: grid;
  gap: 4px;
}

.score-trend-title strong {
  color: var(--foreground);
  font-size: 15px;
}

.score-trend-title span {
  color: var(--muted-foreground);
  font-size: 12px;
  font-weight: 700;
}

.score-range-toggle {
  display: inline-flex;
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--muted);
}

.score-range-toggle button {
  appearance: none;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--muted-foreground);
  min-width: 58px;
  padding: 7px 10px;
  cursor: pointer;
  font-weight: 800;
  transition: background 160ms ease, color 160ms ease, box-shadow 160ms ease;
}

.score-range-toggle button[aria-pressed="true"] {
  background: var(--card);
  color: var(--foreground);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.12);
}

.score-trend-panel[hidden] {
  display: none;
}

.score-trend-chart {
  display: block;
  width: 100%;
  min-height: 230px;
}

.score-trend-grid {
  stroke: #e2e8f0;
  stroke-width: 1;
}

.score-zone-panic {
  fill: rgba(29, 78, 216, 0.12);
}

.score-zone-recovery {
  fill: rgba(20, 184, 166, 0.10);
}

.score-zone-warm {
  fill: rgba(250, 204, 21, 0.12);
}

.score-zone-overheated {
  fill: rgba(220, 38, 38, 0.11);
}

.score-trend-axis {
  stroke: #94a3b8;
  stroke-width: 1.4;
}

.score-trend-line {
  fill: none;
  stroke: var(--primary);
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.score-trend-area {
  fill: rgba(15, 118, 110, 0.07);
}

.score-trend-point {
  fill: var(--card);
  stroke: var(--primary);
  stroke-width: 2;
}

.score-trend-label {
  fill: var(--muted-foreground);
  font-size: 11px;
  font-weight: 700;
}

.score-trend-value {
  fill: var(--foreground);
  font-size: 12px;
  font-weight: 800;
}

.legend-grid {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
}

.legend-item {
  list-style: none;
  display: grid;
  grid-template-columns: 14px minmax(84px, 0.42fr) 1fr;
  gap: 8px;
  align-items: start;
  color: var(--muted-foreground);
  font-size: 13px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(248, 250, 252, 0.68);
  padding: 9px;
}

.legend-item strong {
  color: var(--foreground);
}

.swatch {
  width: 14px;
  height: 14px;
  border-radius: 999px;
  margin-top: 2px;
  border: 1px solid rgba(15, 23, 42, 0.16);
}

.panel {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card);
  margin-top: 14px;
  padding: 20px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.055);
}

.panel-kicker {
  margin: 0 0 14px;
  color: var(--muted-foreground);
  font-size: 13px;
  font-weight: 700;
}

.pill-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  padding: 0;
}

.pill-list li {
  list-style: none;
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--muted);
  padding: 0 10px;
  color: var(--foreground);
  font-size: 13px;
  font-weight: 700;
}

.input-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(276px, 1fr));
  gap: 14px;
  margin: 0;
  padding: 0;
}

.input-card {
  list-style: none;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(248, 250, 252, 0.78)),
    var(--card);
  padding: 16px;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.055);
  display: grid;
  gap: 12px;
  min-height: 214px;
}

.input-card-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.input-title {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.input-title strong {
  color: var(--foreground);
  font-size: 16px;
  font-weight: 900;
  line-height: 1.18;
}

.input-code {
  color: var(--muted-foreground);
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0;
  text-transform: uppercase;
}

.input-status {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border: 1px solid rgba(100, 116, 139, 0.22);
  border-radius: 999px;
  background: rgba(100, 116, 139, 0.10);
  color: var(--muted-foreground);
  font-size: 12px;
  font-weight: 900;
  white-space: nowrap;
}

.status-low .input-status {
  border-color: rgba(37, 99, 235, 0.25);
  background: rgba(37, 99, 235, 0.08);
  color: #1d4ed8;
}

.status-normal .input-status {
  border-color: rgba(15, 118, 110, 0.26);
  background: rgba(15, 118, 110, 0.09);
  color: var(--primary);
}

.status-high .input-status {
  border-color: rgba(180, 83, 9, 0.30);
  background: rgba(245, 158, 11, 0.12);
  color: var(--accent);
}

.status-stress .input-status {
  border-color: rgba(220, 38, 38, 0.28);
  background: rgba(220, 38, 38, 0.09);
  color: #b91c1c;
}

.input-card-description {
  min-height: 38px;
  margin: 0;
  color: var(--muted-foreground);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.45;
}

.input-value {
  display: block;
  margin-top: 0;
  color: var(--foreground);
  font-size: 34px;
  font-weight: 900;
  letter-spacing: 0;
}

.input-value-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 6px;
}

.input-value-row .input-value {
  margin-top: 0;
}

.input-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--muted-foreground);
  font-size: 12px;
  font-weight: 800;
}

.input-scale {
  display: grid;
  gap: 7px;
}

.input-scale-track {
  position: relative;
  height: 12px;
  border-radius: 999px;
  background: linear-gradient(90deg, #bfdbfe 0 24%, #99f6e4 24% 56%, #fde68a 56% 76%, #fecaca 76% 100%);
  overflow: visible;
}

.input-scale-marker {
  position: absolute;
  top: 50%;
  left: var(--marker);
  width: 14px;
  height: 14px;
  border: 2px solid var(--card);
  border-radius: 999px;
  background: var(--foreground);
  box-shadow: 0 3px 8px rgba(15, 23, 42, 0.22);
  transform: translate(-50%, -50%);
}

.status-low .input-scale-marker {
  background: #2563eb;
}

.status-normal .input-scale-marker {
  background: var(--primary);
}

.status-high .input-scale-marker {
  background: var(--accent);
}

.status-stress .input-scale-marker {
  background: #dc2626;
}

.input-scale-labels {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  color: var(--muted-foreground);
  font-size: 11px;
  font-weight: 900;
}

.input-trend {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 26px;
  height: 24px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 900;
}

.trend-up {
  background: rgba(15, 118, 110, 0.11);
  color: #0f766e;
}

.trend-down {
  background: rgba(220, 38, 38, 0.1);
  color: #b91c1c;
}

.trend-flat {
  background: rgba(100, 116, 139, 0.12);
  color: var(--muted-foreground);
}

.methodology {
  display: grid;
  gap: 12px;
}

.methodology-intro,
.methodology-note {
  margin: 0;
  color: var(--muted-foreground);
  line-height: 1.55;
}

.methodology-group {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(248, 250, 252, 0.74);
  overflow: hidden;
}

.methodology-group summary {
  cursor: pointer;
  padding: 12px 14px;
  color: var(--foreground);
  font-size: 14px;
  font-weight: 800;
}

.methodology-group summary:focus-visible {
  outline: 3px solid var(--ring);
  outline-offset: -3px;
}

.methodology-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0 14px 14px;
}

.methodology-list li {
  list-style: none;
  color: var(--muted-foreground);
  line-height: 1.45;
}

.methodology-list strong {
  color: var(--foreground);
}

ul {
  margin: 8px 0 0;
  padding-left: 20px;
}

table {
  width: 100%;
  border-collapse: collapse;
  background: var(--card);
  font-size: 13px;
}

th,
td {
  border-bottom: 1px solid var(--border);
  padding: 11px 10px;
  text-align: left;
  white-space: nowrap;
}

th {
  position: sticky;
  top: 0;
  background: var(--muted);
  color: var(--muted-foreground);
  font-size: 12px;
  text-transform: uppercase;
  font-weight: 800;
}

tbody tr:hover {
  background: rgba(15, 118, 110, 0.045);
}

.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-top: 12px;
  max-height: 620px;
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
    justify-items: start;
  }

  .copy-action {
    justify-items: stretch;
    width: 100%;
  }

  .copy-helper {
    text-align: left;
  }

  .secondary-actions {
    justify-content: flex-start;
  }

  .gauge-grid {
    grid-template-columns: 1fr;
  }

  .legend-item {
    grid-template-columns: 14px 1fr;
  }

  .legend-item > span:last-child {
    grid-column: 2;
  }

  .score-trend-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .score-range-toggle {
    width: 100%;
  }

  .score-range-toggle button {
    flex: 1;
    min-width: 0;
  }

  .value {
    font-size: 19px;
  }

  .input-grid {
    grid-template-columns: 1fr;
  }

  .input-card {
    min-height: 0;
  }

  .input-value {
    font-size: 30px;
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

function updateCurrentTime() {
  const now = new Date();
  const options = {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short"
  };
  const values = {
    en: new Intl.DateTimeFormat("en-US", options).format(now),
    zh: new Intl.DateTimeFormat("zh-CN", options).format(now)
  };
  for (const element of document.querySelectorAll("[data-current-time]")) {
    element.textContent = values[element.dataset.lang] || values.en;
  }
}

function setScoreTrendRange(range) {
  for (const panel of document.querySelectorAll("[data-score-panel]")) {
    panel.hidden = panel.dataset.scorePanel !== range;
  }
  for (const button of document.querySelectorAll("[data-score-range]")) {
    button.setAttribute("aria-pressed", button.dataset.scoreRange === range ? "true" : "false");
  }
}

function visibleText(element) {
  if (!element) {
    return "";
  }
  if (element.nodeType === Node.TEXT_NODE) {
    return element.textContent || "";
  }
  if (element.nodeType !== Node.ELEMENT_NODE) {
    return "";
  }
  const style = window.getComputedStyle(element);
  if (style.display === "none" || style.visibility === "hidden") {
    return "";
  }
  return Array.from(element.childNodes).map(visibleText).join(" ");
}

function normalizeMarkdownText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function escapeMarkdownCell(value) {
  return normalizeMarkdownText(value).replace(/\|/g, "\\|");
}

function tableToMarkdown(table) {
  const rows = Array.from(table.querySelectorAll("tr")).map(function (row) {
    return Array.from(row.children).map(function (cell) {
      return escapeMarkdownCell(visibleText(cell));
    });
  }).filter(function (cells) {
    return cells.length > 0;
  });
  if (!rows.length) {
    return "";
  }
  const header = rows[0];
  const divider = header.map(function () {
    return "---";
  });
  const body = rows.slice(1);
  return [
    "| " + header.join(" | ") + " |",
    "| " + divider.join(" | ") + " |"
  ].concat(body.map(function (cells) {
    return "| " + cells.join(" | ") + " |";
  })).join("\\n");
}

function panelToMarkdown(panel) {
  const table = panel.querySelector("table");
  if (table) {
    return tableToMarkdown(table);
  }
  const listItems = Array.from(panel.querySelectorAll(":scope > ul > li, .pill-list > li, .input-grid > li"));
  if (listItems.length) {
    return listItems.map(function (item) {
      return "- " + normalizeMarkdownText(visibleText(item));
    }).join("\\n");
  }
  const detailBlocks = Array.from(panel.querySelectorAll("details"));
  if (detailBlocks.length) {
    return detailBlocks.map(function (detail) {
      const summary = normalizeMarkdownText(visibleText(detail.querySelector("summary")));
      const items = Array.from(detail.querySelectorAll("li")).map(function (item) {
        return "- " + normalizeMarkdownText(visibleText(item));
      }).join("\\n");
      return "### " + summary + "\\n" + items;
    }).join("\\n\\n");
  }
  return normalizeMarkdownText(visibleText(panel));
}

function buildDashboardMarkdown() {
  const lines = [];
  const title = normalizeMarkdownText(visibleText(document.querySelector("h1")));
  if (title) {
    lines.push("# " + title);
  }
  const subtitle = normalizeMarkdownText(visibleText(document.querySelector(".subtitle")));
  if (subtitle) {
    lines.push("", subtitle);
  }
  lines.push("", "Source: " + window.location.href);
  lines.push("Copied at: " + new Date().toISOString());

  const metrics = Array.from(document.querySelectorAll(".summary .metric")).map(function (metric) {
    return [
      escapeMarkdownCell(visibleText(metric.querySelector(".label"))),
      escapeMarkdownCell(visibleText(metric.querySelector(".value")))
    ];
  }).filter(function (row) {
    return row[0] || row[1];
  });
  if (metrics.length) {
    lines.push("", "## Snapshot", "", "| Metric | Value |", "| --- | --- |");
    for (const row of metrics) {
      lines.push("| " + row[0] + " | " + row[1] + " |");
    }
  }

  for (const heading of document.querySelectorAll("main > h2")) {
    const title = normalizeMarkdownText(visibleText(heading));
    const panel = heading.nextElementSibling;
    if (!title || !panel || !panel.classList.contains("panel")) {
      continue;
    }
    const body = panelToMarkdown(panel);
    lines.push("", "## " + title);
    if (body) {
      lines.push("", body);
    }
  }
  return lines.join("\\n").replace(/\\n{3,}/g, "\\n\\n").trim() + "\\n";
}

async function copyDashboardMarkdown() {
  const button = document.querySelector("[data-copy-markdown]");
  const markdown = buildDashboardMarkdown();
  try {
    await navigator.clipboard.writeText(markdown);
    button.dataset.copyState = "copied";
    button.querySelector('[data-lang="en"]').textContent = "Copied";
    button.querySelector('[data-lang="zh"]').textContent = "已复制";
  } catch (error) {
    button.dataset.copyState = "failed";
    button.querySelector('[data-lang="en"]').textContent = "Copy failed";
    button.querySelector('[data-lang="zh"]').textContent = "复制失败";
  }
  window.setTimeout(function () {
    button.dataset.copyState = "";
    button.querySelector('[data-lang="en"]').textContent = "copy markdown";
    button.querySelector('[data-lang="zh"]').textContent = "复制 markdown";
  }, 1800);
}

document.addEventListener("DOMContentLoaded", function () {
  setLanguage("en");
  setScoreTrendRange("week");
  updateCurrentTime();
  window.setInterval(updateCurrentTime, 1000);
  for (const button of document.querySelectorAll("[data-language]")) {
    button.addEventListener("click", function () {
      setLanguage(button.dataset.language);
    });
  }
  for (const button of document.querySelectorAll("[data-score-range]")) {
    button.addEventListener("click", function () {
      setScoreTrendRange(button.dataset.scoreRange);
    });
  }
  const copyButton = document.querySelector("[data-copy-markdown]");
  if (copyButton) {
    copyButton.addEventListener("click", copyDashboardMarkdown);
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
            "<title>Nasdaq 100 Market Regime Dashboard</title>",
            f"<style>{CSS}</style>",
            "</head>",
            '<body class="lang-en">',
            "<main>",
            '<div class="topbar">',
            '<div class="brand-block">',
            f"<h1>{_localized('Nasdaq 100 Market Regime Dashboard')}</h1>",
            f'<p class="subtitle">{_localized("Finance-tech market monitor")}</p>',
            "</div>",
            '<div class="top-actions">',
            _copy_markdown_button(),
            '<div class="secondary-actions">',
            _github_link(),
            _language_toggle(),
            "</div>",
            "</div>",
            "</div>",
            _summary_grid(summary),
            _section("Latest Inputs", _latest_inputs_html(summary, daily)),
            _section("Market State Gauge", _regime_gauge(summary)),
            _section("Composite Score Trend", _score_trend_html(daily, summary)),
            _section("Drivers", _list(summary.get("drivers", []))),
            _section("Risks", _list(summary.get("risks", []))),
            _section("Summary", _summary_paragraph(summary)),
            _config_metadata_html(summary),
            _section("Recent Daily Regimes", _table(rows)),
            _section("How This Dashboard Works", _methodology_html()),
            "</main>",
            LANGUAGE_SCRIPT,
            "</body>",
            "</html>",
        ]
    )


def _summary_grid(summary: dict[str, Any]) -> str:
    metrics = [
        ("Current Time", _current_time_value(), "metric-time"),
        ("Regime", _translated_regime_value(summary.get("market_regime", "")), "metric-regime"),
        ("Action", _translated_value(summary.get("dashboard_action", "")), "metric-action"),
        ("Temperature", summary.get("temperature_score", ""), "metric-temperature"),
        ("Confidence", summary.get("confidence_score", ""), "metric-confidence"),
    ]
    cards = [
        f'<div class="metric {class_name}">'
        f'<div class="label">{_localized(label)}</div>'
        f'<div class="value">{_format_display_value(value)}</div>'
        "</div>"
        for label, value, class_name in metrics
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
        '<svg class="regime-gauge" viewBox="0 0 240 172" role="img" '
        'aria-labelledby="gauge-title gauge-desc">'
        '<title id="gauge-title">Market regime gauge</title>'
        f'<desc id="gauge-desc">Current market regime is {active_label} / {active_label_zh}.</desc>'
        '<path d="M 20 116 A 100 100 0 0 1 220 116" fill="none" stroke="#e3e8ef" '
        'stroke-width="18" stroke-linecap="round"/>'
        f"{segments}"
        f'<line x1="120" y1="116" x2="{needle_x:.2f}" y2="{needle_y:.2f}" '
        'stroke="#18202a" stroke-width="4" stroke-linecap="round"/>'
        '<circle cx="120" cy="116" r="7" fill="#18202a"/>'
        f'{_localized_svg_text(active[1], x=120, y=154, class_name="gauge-label")}'
        f'{_localized_svg_text("current regime", x=120, y=166, class_name="gauge-sub")}'
        "</svg>"
        f'<ul class="legend-grid">{legend}</ul>'
        "</div>"
    )


def _score_trend_html(daily: pd.DataFrame, summary: dict[str, Any]) -> str:
    if "date" not in daily.columns or "temperature_score" not in daily.columns:
        return f"<p>{_localized('No score history available.')}</p>"

    panels = "".join(
        _score_trend_panel(daily, summary, key, days)
        for key, days in [("week", 7), ("month", 31), ("year", 366)]
    )
    if not panels:
        return f"<p>{_localized('No score history available.')}</p>"
    return (
        '<div class="score-trend">'
        '<div class="score-trend-header">'
        '<div class="score-trend-title">'
        f'<strong>{_localized("Daily composite score")}</strong>'
        f'<span>{_localized("Composite score")}: temperature_score</span>'
        "</div>"
        '<div class="score-range-toggle" aria-label="Score trend range">'
        '<button type="button" data-score-range="week" aria-pressed="true">'
        f'{_localized("Week")}</button>'
        '<button type="button" data-score-range="month" aria-pressed="false">'
        f'{_localized("Month")}</button>'
        '<button type="button" data-score-range="year" aria-pressed="false">'
        f'{_localized("Year")}</button>'
        "</div>"
        "</div>"
        f"{panels}"
        "</div>"
    )


def _score_trend_panel(daily: pd.DataFrame, summary: dict[str, Any], key: str, days: int) -> str:
    rows = _score_trend_rows(daily, summary, days)
    if rows.empty:
        return ""
    return (
        f'<div class="score-trend-panel" data-score-panel="{key}"'
        f'{" hidden" if key != "week" else ""}>'
        f"{_score_trend_svg(rows, key)}"
        "</div>"
    )


def _score_trend_rows(daily: pd.DataFrame, summary: dict[str, Any], days: int) -> pd.DataFrame:
    columns = ["date", "temperature_score"]
    optional_columns = [column for column in ["market_regime", "dashboard_action"] if column in daily.columns]
    rows = daily[columns + optional_columns].copy()
    rows["_date"] = pd.to_datetime(rows["date"], errors="coerce")
    rows["_score"] = pd.to_numeric(rows["temperature_score"], errors="coerce")
    rows = rows.dropna(subset=["_date", "_score"]).sort_values("_date")
    rows = rows[(rows["_score"] > 0.0) & (rows["_score"] <= 100.0)]
    if "market_regime" in rows.columns:
        rows = rows[rows["market_regime"].astype(str) != "unscorable"]
    if "dashboard_action" in rows.columns:
        rows = rows[rows["dashboard_action"].astype(str) != "unavailable"]
    if rows.empty:
        return rows

    as_of = pd.to_datetime(summary.get("as_of_date"), errors="coerce")
    end_date = rows["_date"].max() if pd.isna(as_of) else as_of
    start_date = end_date - pd.Timedelta(days=days - 1)
    return rows[(rows["_date"] >= start_date) & (rows["_date"] <= end_date)].tail(260)


def _score_trend_svg(rows: pd.DataFrame, range_key: str) -> str:
    width = 920.0
    height = 260.0
    left = 54.0
    right = 20.0
    top = 22.0
    bottom = 38.0
    plot_width = width - left - right
    plot_height = height - top - bottom
    count = len(rows)

    points = []
    for idx, (_, row) in enumerate(rows.iterrows()):
        score = min(100.0, max(0.0, float(row["_score"])))
        x = left + (plot_width * idx / max(count - 1, 1))
        y = top + (plot_height * (100.0 - score) / 100.0)
        points.append((x, y, row["_date"], score))

    path = _svg_line_path([(x, y) for x, y, _, _ in points])
    area = _svg_area_path([(x, y) for x, y, _, _ in points], top + plot_height)
    circles = "".join(
        f'<circle class="score-trend-point" cx="{x:.2f}" cy="{y:.2f}" r="3.2">'
        f"<title>{date.date().isoformat()}: {score:.2f}</title>"
        "</circle>"
        for x, y, date, score in _sample_points(points)
    )
    y_grid = "".join(
        f'<line class="score-trend-grid" x1="{left:.0f}" y1="{y:.2f}" x2="{width - right:.0f}" y2="{y:.2f}"/>'
        f'<text class="score-trend-label" x="14" y="{y + 4:.2f}">{label}</text>'
        for label, y in [
            ("100", top),
            ("75", top + plot_height * 0.25),
            ("50", top + plot_height * 0.50),
            ("25", top + plot_height * 0.75),
            ("0", top + plot_height),
        ]
    )
    zones = "".join(
        _score_zone_rect(class_name, start, end, left, width - right, top, plot_height)
        for class_name, start, end in [
            ("score-zone-panic", 0.0, 35.0),
            ("score-zone-recovery", 35.0, 65.0),
            ("score-zone-warm", 65.0, 78.0),
            ("score-zone-overheated", 78.0, 100.0),
        ]
    )
    first = points[0]
    last = points[-1]
    x_labels = (
        f'<text class="score-trend-label" x="{first[0]:.2f}" y="{height - 12:.0f}" text-anchor="start">'
        f"{first[2].date().isoformat()}</text>"
        f'<text class="score-trend-label" x="{last[0]:.2f}" y="{height - 12:.0f}" text-anchor="end">'
        f"{last[2].date().isoformat()}</text>"
    )
    value_label = (
        f'<text class="score-trend-value" x="{last[0]:.2f}" y="{max(top + 12, last[1] - 10):.2f}" '
        f'text-anchor="end">{last[3]:.2f}</text>'
    )
    title = escape(f"{range_key} composite score trend")
    return (
        f'<svg class="score-trend-chart" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'role="img" aria-label="{title}">'
        f"<title>{title}</title>"
        f"{zones}"
        f"{y_grid}"
        f'<line class="score-trend-axis" x1="{left:.0f}" y1="{top + plot_height:.0f}" '
        f'x2="{width - right:.0f}" y2="{top + plot_height:.0f}"/>'
        f'<path class="score-trend-area" d="{area}"/>'
        f'<path class="score-trend-line" d="{path}"/>'
        f"{circles}{value_label}{x_labels}"
        "</svg>"
    )


def _score_zone_rect(
    class_name: str,
    start_score: float,
    end_score: float,
    left: float,
    right: float,
    top: float,
    plot_height: float,
) -> str:
    y_top = top + plot_height * (100.0 - end_score) / 100.0
    y_bottom = top + plot_height * (100.0 - start_score) / 100.0
    return (
        f'<rect class="{class_name}" x="{left:.0f}" y="{y_top:.2f}" '
        f'width="{right - left:.0f}" height="{y_bottom - y_top:.2f}"/>'
    )


def _svg_line_path(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    if len(points) == 1:
        x, y = points[0]
        return f"M {x:.2f} {y:.2f} L {x + 0.01:.2f} {y:.2f}"
    start = points[0]
    rest = " ".join(f"L {x:.2f} {y:.2f}" for x, y in points[1:])
    return f"M {start[0]:.2f} {start[1]:.2f} {rest}"


def _svg_area_path(points: list[tuple[float, float]], baseline: float) -> str:
    if not points:
        return ""
    line = _svg_line_path(points)
    first_x = points[0][0]
    last_x = points[-1][0]
    return f"{line} L {last_x:.2f} {baseline:.2f} L {first_x:.2f} {baseline:.2f} Z"


def _sample_points(points: list[tuple[float, float, pd.Timestamp, float]]) -> list[tuple[float, float, pd.Timestamp, float]]:
    if len(points) <= 32:
        return points
    indexes = {0, len(points) - 1}
    step = max(1, len(points) // 30)
    indexes.update(range(0, len(points), step))
    return [points[index] for index in sorted(indexes)]


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
    _, label, start, end, color, description = band
    return (
        '<li class="legend-item">'
        f'<span class="swatch" style="background:{color}"></span>'
        f"<strong>{_localized(label)}</strong>"
        f"<span>{start}-{end}: {_localized(description)}</span>"
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


def _latest_inputs_html(summary: dict[str, Any], daily: pd.DataFrame) -> str:
    as_of = _format_value(summary.get("as_of_date", ""))
    inputs = _latest_input_values(summary)
    context_values = _current_input_values(daily, as_of)
    if isinstance(inputs, dict):
        context_values.update(inputs)
    previous_values = _previous_latest_input_values(daily, summary, as_of)
    as_of_by_key = _latest_input_dates(summary, as_of)
    return (
        f'<p class="panel-kicker">{_localized("Dashboard data date")}: {escape(as_of)}</p>'
        f'{_input_grid(inputs, previous_values, as_of, context_values, as_of_by_key)}'
    )


def _latest_input_values(summary: dict[str, Any]) -> dict[str, Any]:
    latest_inputs = summary.get("latest_inputs")
    if isinstance(latest_inputs, dict) and latest_inputs:
        values: dict[str, Any] = {}
        for key, entry in latest_inputs.items():
            if not isinstance(entry, dict) or "value" not in entry:
                raise ValueError(f"latest_inputs[{key!r}] must contain value")
            values[str(key)] = entry["value"]
        return values
    inputs = summary.get("inputs", {})
    return inputs if isinstance(inputs, dict) else {}


def _latest_input_dates(summary: dict[str, Any], default_as_of: str) -> dict[str, str]:
    latest_inputs = summary.get("latest_inputs")
    if not isinstance(latest_inputs, dict):
        return {}
    dates: dict[str, str] = {}
    for key, entry in latest_inputs.items():
        if not isinstance(entry, dict):
            raise ValueError(f"latest_inputs[{key!r}] must be a dict")
        dates[str(key)] = _format_value(entry.get("as_of_date", default_as_of))
    return dates


def _previous_latest_input_values(
    daily: pd.DataFrame,
    summary: dict[str, Any],
    default_as_of: str,
) -> dict[str, Any]:
    latest_inputs = summary.get("latest_inputs")
    if not isinstance(latest_inputs, dict):
        return _previous_input_values(daily, default_as_of)
    previous: dict[str, Any] = {}
    for key, entry in latest_inputs.items():
        if not isinstance(entry, dict):
            continue
        previous[str(key)] = _previous_input_value(daily, str(key), _format_value(entry.get("as_of_date", default_as_of)))
    return previous


def _current_time_value() -> tuple[str, str]:
    fallback = "--"
    return (
        f'<span data-current-time data-lang="en">{fallback}</span>',
        f'<span data-current-time data-lang="zh">{fallback}</span>',
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
        '<details class="methodology-group" open>'
        f"<summary>{_localized_pair(title_en, title_zh)}</summary>"
        f'<ul class="methodology-list">{items}</ul>'
        "</details>"
    )


def _methodology_validation(rows: list[tuple[str, str]]) -> str:
    items = "".join(f"<li>{_localized_pair(english, chinese)}</li>" for english, chinese in rows)
    return (
        '<details class="methodology-group" open>'
        f"<summary>{_localized_pair('Backtest validation', '回测验证')}</summary>"
        f'<ul class="methodology-list">{items}</ul>'
        "</details>"
    )


def _list(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "<p>None</p>"
    items = "".join(f"<li>{_localized(_format_value(value))}</li>" for value in values)
    return f'<ul class="pill-list">{items}</ul>'


def _key_value_list(values: Any) -> str:
    if not isinstance(values, dict) or not values:
        return "<p>None</p>"
    items = "".join(
        f"<li><strong>{escape(str(key))}</strong>: {escape(_format_value(value))}</li>"
        for key, value in values.items()
    )
    return f"<ul>{items}</ul>"


INPUT_CARD_META = {
    "cnn_fear_greed": (
        "Fear & Greed",
        "恐惧贪婪",
        "CNN sentiment gauge for crowd fear versus risk appetite.",
        "CNN 情绪温度计，观察恐惧与风险偏好。",
        "0",
        "25",
        "45",
        "56",
        "76",
        "100",
    ),
    "cnn_ma5": (
        "Fear & Greed MA5",
        "恐惧贪婪 5 日均值",
        "Short-term sentiment average; smoother than the daily reading.",
        "短期情绪均值，比单日读数更平滑。",
        "0",
        "25",
        "45",
        "56",
        "76",
        "100",
    ),
    "ndx": (
        "NASDAQ 100",
        "纳指 100",
        "Price level; status uses distance from the 180-day SMA.",
        "价格位置；状态按相对 180 日均线距离判断。",
        "-15%",
        "0",
        "+8%",
        "+15%",
        "+20%",
    ),
    "sma": (
        "180D SMA",
        "180 日均线",
        "Long-term trend baseline for the Nasdaq 100.",
        "纳指 100 长期趋势基准线。",
        "-15%",
        "0",
        "+8%",
        "+15%",
        "+20%",
    ),
    "dist_sma": (
        "Distance to SMA",
        "均线偏离",
        "How stretched price is versus the 180-day baseline.",
        "价格相对 180 日均线的拉伸程度。",
        "-15%",
        "0",
        "+8%",
        "+15%",
        "+20%",
    ),
    "vix": (
        "VIX",
        "VIX 标普波动率",
        "S&P 500 implied-volatility stress gauge.",
        "标普 500 隐含波动率压力表。",
        "0",
        "12",
        "20",
        "30",
        "50",
    ),
    "vxn": (
        "VXN",
        "VXN 纳指波动率",
        "Nasdaq 100 implied-volatility stress gauge.",
        "纳指 100 隐含波动率压力表。",
        "0",
        "15",
        "22",
        "32",
        "55",
    ),
    "vix_pctile": (
        "VIX Percentile",
        "VIX 分位",
        "VIX rank inside the rolling history window.",
        "VIX 在滚动历史窗口中的相对位置。",
        "0",
        ".20",
        ".60",
        ".80",
        "1.00",
    ),
    "vxn_pctile": (
        "VXN Percentile",
        "VXN 分位",
        "VXN rank inside the rolling history window.",
        "VXN 在滚动历史窗口中的相对位置。",
        "0",
        ".20",
        ".60",
        ".80",
        "1.00",
    ),
    "ndxe_ndx": (
        "NDXE / NDX",
        "等权 / 市值加权",
        "Breadth ratio; higher means gains are more broadly shared.",
        "市场广度比率；越高代表上涨更分散。",
        ".25",
        ".32",
        ".36",
        ".42",
        ".45",
    ),
    "ndxe_ma": (
        "NDXE / NDX MA",
        "广度均值",
        "Smoothed breadth ratio for trend confirmation.",
        "平滑后的广度比率，用于确认趋势。",
        ".25",
        ".32",
        ".36",
        ".42",
        ".45",
    ),
    "sox_ndx": (
        "SOX / NDX",
        "半导体 / 纳指",
        "Semiconductor leadership versus the Nasdaq 100.",
        "半导体相对纳指 100 的主线强度。",
        ".25",
        ".32",
        ".36",
        ".42",
        ".45",
    ),
    "sox_ma": (
        "SOX / NDX MA",
        "半导体均值",
        "Smoothed semiconductor leadership signal.",
        "平滑后的半导体主线强度。",
        ".25",
        ".32",
        ".36",
        ".42",
        ".45",
    ),
}


def _input_grid(
    values: Any,
    previous_values: dict[str, Any] | None = None,
    as_of: str = "",
    context_values: dict[str, Any] | None = None,
    as_of_by_key: dict[str, str] | None = None,
) -> str:
    if not isinstance(values, dict) or not values:
        return "<p>None</p>"
    previous_values = previous_values or {}
    context_values = context_values or values
    as_of_by_key = as_of_by_key or {}
    items = "".join(
        _input_card_html(str(key), value, context_values, previous_values, as_of_by_key.get(str(key), as_of))
        for key, value in values.items()
    )
    return f'<ul class="input-grid">{items}</ul>'


def _input_card_html(
    key: str,
    value: Any,
    values: dict[str, Any],
    previous_values: dict[str, Any],
    as_of: str,
) -> str:
    if key not in INPUT_CARD_META:
        raise ValueError(f"unknown latest input key: {key}")
    title_en, title_zh, desc_en, desc_zh, *scale_labels = INPUT_CARD_META[key]
    status_class, status_en, status_zh = _input_status(key, value, values, previous_values)
    marker = _input_marker_percent(key, value, values)
    trend = _input_trend_html(value, previous_values.get(key))
    scale = "".join(f"<span>{escape(label)}</span>" for label in scale_labels)
    return (
        f'<li class="input-card status-{status_class}" aria-label="{escape(title_en)} status {escape(status_en)}">'
        '<div class="input-card-header">'
        '<div class="input-title">'
        f"<strong>{_localized_pair(title_en, title_zh)}</strong>"
        f'<span class="input-code">{escape(key)}</span>'
        "</div>"
        f'<span class="input-status"><span class="input-status-label">{_localized_pair(status_en, status_zh)}</span></span>'
        "</div>"
        f'<p class="input-card-description">{_localized_pair(desc_en, desc_zh)}</p>'
        '<div class="input-value-row">'
        f'<span class="input-value">{escape(_input_display_value(key, value))}</span>'
        f"{trend}"
        "</div>"
        '<div class="input-scale">'
        f'<div class="input-scale-track" style="--marker: {marker:.2f}%;">'
        '<span class="input-scale-marker" aria-hidden="true"></span>'
        "</div>"
        f'<div class="input-scale-labels">{scale}</div>'
        "</div>"
        f'<div class="input-meta"><span>{_localized_pair(f"Updated {as_of}", f"更新 {as_of}")}</span></div>'
        "</li>"
    )


def _input_status(
    key: str,
    value: Any,
    values: dict[str, Any],
    previous_values: dict[str, Any],
) -> tuple[str, str, str]:
    numeric = _float_value(value)
    if key in {"cnn_fear_greed", "cnn_ma5"}:
        return _band_status(
            numeric,
            [
                (25.0, "stress", "Extreme Fear", "极恐"),
                (45.0, "low", "Fear", "恐惧"),
                (56.0, "normal", "Neutral", "中性"),
                (76.0, "high", "Greed", "贪婪"),
                (math.inf, "stress", "Extreme Greed", "极贪"),
            ],
        )
    if key in {"ndx", "sma", "dist_sma"}:
        distance = _distance_value(values)
        if key == "sma":
            trend = _input_trend(value, previous_values.get(key))
            if trend == "down":
                return "low", "Falling", "下行"
            if trend == "up":
                return "normal", "Rising", "上行"
        return _band_status(
            distance,
            [
                (-0.08, "low", "Below Trend", "趋势下方"),
                (0.0, "low", "Soft", "偏弱"),
                (0.08, "normal", "Normal", "正常"),
                (0.15, "high", "High", "偏高"),
                (math.inf, "stress", "Extended", "过度拉伸"),
            ],
        )
    if key == "vix":
        return _volatility_status(numeric, normal_high=20.0, elevated_high=30.0, panic_high=50.0)
    if key == "vxn":
        return _volatility_status(numeric, normal_high=22.0, elevated_high=32.0, panic_high=55.0)
    if key in {"vix_pctile", "vxn_pctile"}:
        return _band_status(
            numeric,
            [
                (0.20, "low", "Low", "偏低"),
                (0.60, "normal", "Normal", "正常"),
                (0.80, "high", "Elevated", "偏高"),
                (math.inf, "stress", "High Stress", "高压力"),
            ],
        )
    if key in {"ndxe_ndx", "ndxe_ma", "sox_ndx", "sox_ma"}:
        return _band_status(
            numeric,
            [
                (0.32, "low", "Weak", "偏弱"),
                (0.36, "normal", "Neutral", "中性"),
                (0.42, "high", "Strong", "偏强"),
                (math.inf, "stress", "Crowded", "拥挤"),
            ],
        )
    raise ValueError(f"unknown latest input key: {key}")


def _band_status(value: float, bands: list[tuple[float, str, str, str]]) -> tuple[str, str, str]:
    if pd.isna(value):
        raise ValueError("latest input status cannot be computed from NaN")
    for upper, status_class, english, chinese in bands:
        if value < upper:
            return status_class, english, chinese
    raise ValueError(f"latest input status bands exhausted for {value}")


def _volatility_status(value: float, *, normal_high: float, elevated_high: float, panic_high: float) -> tuple[str, str, str]:
    return _band_status(
        value,
        [
            (normal_high * 0.6, "low", "Calm", "低波动"),
            (normal_high, "normal", "Normal", "正常"),
            (elevated_high, "high", "Elevated", "略升"),
            (panic_high, "stress", "Stress", "压力"),
            (math.inf, "stress", "Panic", "恐慌"),
        ],
    )


def _input_marker_percent(key: str, value: Any, values: dict[str, Any]) -> float:
    if key in {"ndx", "sma", "dist_sma"}:
        return _scale_percent(_distance_value(values), -0.15, 0.20)
    numeric = _float_value(value)
    if key in {"cnn_fear_greed", "cnn_ma5"}:
        return _scale_percent(numeric, 0.0, 100.0)
    if key == "vix":
        return _scale_percent(numeric, 0.0, 50.0)
    if key == "vxn":
        return _scale_percent(numeric, 0.0, 55.0)
    if key in {"vix_pctile", "vxn_pctile"}:
        return _scale_percent(numeric, 0.0, 1.0)
    if key in {"ndxe_ndx", "ndxe_ma", "sox_ndx", "sox_ma"}:
        return _scale_percent(numeric, 0.25, 0.45)
    raise ValueError(f"unknown latest input key: {key}")


def _input_display_value(key: str, value: Any) -> str:
    if key == "dist_sma":
        return f"{_float_value(value) * 100:.2f}%"
    return _format_value(value)


def _distance_value(values: dict[str, Any]) -> float:
    if "dist_sma" in values and values.get("dist_sma") not in ("", None):
        return _float_value(values.get("dist_sma"))
    ndx = _float_value(values.get("ndx"))
    sma = _float_value(values.get("sma"))
    if math.isclose(sma, 0.0):
        raise ValueError("dist_sma is required to classify price trend inputs")
    return (ndx - sma) / sma


def _float_value(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"latest input must be numeric: {value!r}") from None
    if not math.isfinite(numeric):
        raise ValueError(f"latest input must be finite: {value!r}")
    return numeric


def _scale_percent(value: float, lower: float, upper: float) -> float:
    if upper <= lower:
        raise ValueError("scale upper bound must be greater than lower bound")
    return max(0.0, min(100.0, (value - lower) / (upper - lower) * 100.0))


def _previous_input_values(daily: pd.DataFrame, as_of: str) -> dict[str, Any]:
    if "date" not in daily.columns:
        return {}
    target = pd.to_datetime(as_of, errors="coerce")
    if pd.isna(target):
        return {}
    rows = daily.copy()
    rows["_date"] = pd.to_datetime(rows["date"], errors="coerce")
    previous = rows[rows["_date"] < target].sort_values("_date", ascending=False)
    if previous.empty:
        return {}
    return previous.iloc[0].drop(labels=["_date"]).to_dict()


def _previous_input_value(daily: pd.DataFrame, key: str, as_of: str) -> Any:
    if "date" not in daily.columns or key not in daily.columns:
        return None
    target = pd.to_datetime(as_of, errors="coerce")
    if pd.isna(target):
        return None
    rows = daily.copy()
    rows["_date"] = pd.to_datetime(rows["date"], errors="coerce")
    previous = rows[rows["_date"] < target].sort_values("_date", ascending=False)
    for _, row in previous.iterrows():
        value = row.get(key)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric):
            return value
    return None


def _current_input_values(daily: pd.DataFrame, as_of: str) -> dict[str, Any]:
    if "date" not in daily.columns:
        return {}
    target = pd.to_datetime(as_of, errors="coerce")
    if pd.isna(target):
        return {}
    rows = daily.copy()
    rows["_date"] = pd.to_datetime(rows["date"], errors="coerce")
    current = rows[rows["_date"] == target]
    if current.empty:
        return {}
    return current.iloc[0].drop(labels=["_date"]).to_dict()


def _input_trend_html(current: Any, previous: Any) -> str:
    trend = _input_trend(current, previous)
    if trend is None:
        return ""
    labels = {
        "up": ("↑", "Up from prior market day"),
        "down": ("↓", "Down from prior market day"),
        "flat": ("→", "Flat from prior market day"),
    }
    arrow, label = labels[trend]
    return (
        f'<span class="input-trend trend-{trend}" aria-label="{label}" '
        f'title="{label}">{arrow}</span>'
    )


def _input_trend(current: Any, previous: Any) -> str | None:
    try:
        current_value = float(current)
        previous_value = float(previous)
    except (TypeError, ValueError):
        return None
    if pd.isna(current_value) or pd.isna(previous_value):
        return None
    current_rounded = round(current_value, 2)
    previous_rounded = round(previous_value, 2)
    if math.isclose(current_rounded, previous_rounded, abs_tol=0.0):
        return "flat"
    if current_rounded > previous_rounded:
        return "up"
    return "down"


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
    return f'<div class="table-wrap"><table class="data-table"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>'


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
        if _is_trusted_localized_html(english, chinese):
            return f"{english}{chinese}"
        return f'<span data-lang="en">{escape(english)}</span><span data-lang="zh">{escape(chinese)}</span>'
    return escape(_format_value(value))


def _is_trusted_localized_html(english: str, chinese: str) -> bool:
    return (
        english.startswith('<span data-current-time data-lang="en">')
        and chinese.startswith('<span data-current-time data-lang="zh">')
    )


def _language_toggle() -> str:
    return (
        '<div class="language-toggle" aria-label="Language switch">'
        '<button type="button" data-language="en" aria-pressed="true">English</button>'
        '<button type="button" data-language="zh" aria-pressed="false">中文</button>'
        "</div>"
    )


def _copy_markdown_button() -> str:
    return (
        '<div class="copy-action">'
        f'<p class="copy-helper">{_localized("send this page info to your AI for further analysis")}</p>'
        '<button type="button" class="copy-button" data-copy-markdown data-copy-state="">'
        f'{_localized("copy markdown")}'
        "</button>"
        "</div>"
    )


def _github_link() -> str:
    return (
        f'<a class="github-link" href="{GITHUB_REPO_URL}" target="_blank" '
        f'rel="noopener noreferrer">{_localized("GitHub")}</a>'
    )
