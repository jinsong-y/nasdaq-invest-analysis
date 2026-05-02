#!/usr/bin/env python3
"""Fetch source data required by the NASDAQ DCA backtest notes.

The script is intentionally strict: every configured source must succeed, and
malformed or empty payloads stop the run instead of silently substituting data.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
RAW_FRED_DIR = ROOT / "data" / "raw" / "fred"
RAW_CNN_DIR = ROOT / "data" / "raw" / "cnn"
PROCESSED_DIR = ROOT / "data" / "processed"
DOCS_DIR = ROOT / "docs"
START_DATE = "2000-01-03"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass(frozen=True)
class FredSeries:
    series_id: str
    output_name: str
    description: str


FRED_SERIES = [
    FredSeries("NASDAQ100", "ndx", "Nasdaq 100 index level for SMA/trend gates"),
    FredSeries("VXNCLS", "vxn", "CBOE Nasdaq-100 volatility index"),
    FredSeries("VIXCLS", "vix", "CBOE S&P 500 volatility index"),
    FredSeries("NASDAQNDXE", "ndxe", "Nasdaq-100 equal weighted index"),
    FredSeries("NASDAQSOX", "sox", "PHLX semiconductor sector index"),
]

FRED_GRAPH_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FINHACKER_PAGE_URL = (
    "https://www.finhacker.cz/en/fear-and-greed-index-historical-data-and-chart/"
)
FINHACKER_DATA_URL = "https://www.finhacker.cz/wp-content/custom-api/fear-greed-data.php"
FINHACKER_LIVE_URL = "https://www.finhacker.cz/wp-content/data/fng-live.json"


def fail(message: str) -> None:
    raise RuntimeError(message)


def ensure_dirs() -> None:
    for directory in (RAW_FRED_DIR, RAW_CNN_DIR, PROCESSED_DIR, DOCS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def request_bytes(url: str, headers: dict[str, str] | None = None) -> bytes:
    args = ["curl", "-fsSL", "--max-time", "60"]
    for key, value in (headers or {}).items():
        args.extend(["-H", f"{key}: {value}"])
    args.append(url)
    result = subprocess.run(args, capture_output=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        fail(f"curl failed for {url}: {stderr or f'exit {result.returncode}'}")
    return result.stdout


def write_bytes(path: Path, payload: bytes) -> None:
    if not payload:
        fail(f"Refusing to write empty payload: {path}")
    path.write_bytes(payload)


def fetch_fred_series(series: FredSeries) -> list[dict[str, str | None]]:
    url = f"{FRED_GRAPH_URL}?{urlencode({'id': series.series_id, 'cosd': START_DATE})}"
    payload = request_bytes(url)
    path = RAW_FRED_DIR / f"{series.series_id}.csv"
    write_bytes(path, payload)

    text = payload.decode("utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    expected = ["observation_date", series.series_id]
    if reader.fieldnames != expected:
        fail(
            f"Unexpected FRED columns for {series.series_id}: "
            f"{reader.fieldnames!r}, expected {expected!r}"
        )

    rows: list[dict[str, str | None]] = []
    for row in reader:
        day = row["observation_date"]
        value = row[series.series_id]
        if not day:
            fail(f"Blank date in {series.series_id}")
        rows.append({"date": day, series.output_name: None if value == "." else value})

    if not rows:
        fail(f"No rows returned for FRED series {series.series_id}")
    return rows


def fetch_finhacker_data() -> tuple[dict, dict]:
    with NamedTemporaryFile() as cookie_file:
        page_args = [
            "curl",
            "-fsSL",
            "--max-time",
            "60",
            "-c",
            cookie_file.name,
            "-H",
            f"User-Agent: {USER_AGENT}",
            FINHACKER_PAGE_URL,
        ]
        page_result = subprocess.run(page_args, capture_output=True, check=False)
        if page_result.returncode != 0:
            stderr = page_result.stderr.decode("utf-8", errors="replace").strip()
            fail(f"curl failed for {FINHACKER_PAGE_URL}: {stderr or page_result.returncode}")

        data_args = [
            "curl",
            "-fsSL",
            "--max-time",
            "60",
            "-b",
            cookie_file.name,
            "-H",
            f"User-Agent: {USER_AGENT}",
            "-H",
            f"Referer: {FINHACKER_PAGE_URL}",
            FINHACKER_DATA_URL,
        ]
        data_result = subprocess.run(data_args, capture_output=True, check=False)
        if data_result.returncode != 0:
            stderr = data_result.stderr.decode("utf-8", errors="replace").strip()
            fail(f"curl failed for {FINHACKER_DATA_URL}: {stderr or data_result.returncode}")
        historical_payload = data_result.stdout

    live_payload = request_bytes(FINHACKER_LIVE_URL)

    write_bytes(RAW_CNN_DIR / "fear_greed_history.json", historical_payload)
    write_bytes(RAW_CNN_DIR / "fear_greed_live.json", live_payload)

    try:
        historical = json.loads(historical_payload)
        live = json.loads(live_payload)
    except json.JSONDecodeError as exc:
        fail(f"Invalid FinHacker JSON: {exc}")

    daily = historical.get("daily")
    if not isinstance(daily, list) or not daily:
        fail("FinHacker historical payload has no non-empty daily array")
    for row in daily:
        if "d" not in row or "fg" not in row:
            fail(f"Malformed FinHacker daily row: {row!r}")

    if "score" not in live or "timestamp" not in live:
        fail(f"Malformed FinHacker live payload: {live!r}")

    return historical, live


def parse_float(value: str | int | float | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def merge_by_date(
    fred_rows_by_series: dict[str, list[dict[str, str | None]]],
    cnn_history: dict,
) -> list[dict[str, str]]:
    merged: dict[str, dict[str, float | str | None]] = {}

    for series in FRED_SERIES:
        rows = fred_rows_by_series[series.series_id]
        for row in rows:
            day = str(row["date"])
            merged.setdefault(day, {"date": day})
            merged[day][series.output_name] = parse_float(row[series.output_name])

    for row in cnn_history["daily"]:
        day = row["d"]
        if day < START_DATE:
            continue
        merged.setdefault(day, {"date": day})
        merged[day]["cnn_fear_greed"] = parse_float(row.get("fg"))
        merged[day]["spx"] = parse_float(row.get("spx"))

    output_rows = []
    for day in sorted(day for day in merged if day >= START_DATE):
        item = merged[day]
        ndx = item.get("ndx")
        ndxe = item.get("ndxe")
        sox = item.get("sox")
        if isinstance(ndx, float) and ndx:
            if isinstance(ndxe, float):
                item["ndxe_ndx"] = ndxe / ndx
            if isinstance(sox, float):
                item["sox_ndx"] = sox / ndx
        output_rows.append(item)

    return [stringify_row(row) for row in output_rows]


def stringify_row(row: dict[str, float | str | None]) -> dict[str, str]:
    fields = [
        "date",
        "ndx",
        "vxn",
        "vix",
        "ndxe",
        "sox",
        "cnn_fear_greed",
        "spx",
        "ndxe_ndx",
        "sox_ndx",
    ]
    out: dict[str, str] = {}
    for field in fields:
        value = row.get(field)
        if value is None:
            out[field] = ""
        elif isinstance(value, float):
            out[field] = f"{value:.10g}"
        else:
            out[field] = str(value)
    return out


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        fail(f"No rows to write: {path}")
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def non_empty_count(rows: Iterable[dict[str, str]], field: str) -> int:
    return sum(1 for row in rows if row.get(field))


def min_max_date(rows: list[dict[str, str]], field: str) -> tuple[str | None, str | None]:
    dates = [row["date"] for row in rows if row.get(field)]
    return (dates[0], dates[-1]) if dates else (None, None)


def write_manifest(rows: list[dict[str, str]], live: dict) -> None:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    fields = [
        "ndx",
        "vxn",
        "vix",
        "ndxe",
        "sox",
        "cnn_fear_greed",
        "spx",
        "ndxe_ndx",
        "sox_ndx",
    ]
    coverage = {
        field: {
            "rows": non_empty_count(rows, field),
            "start": min_max_date(rows, field)[0],
            "end": min_max_date(rows, field)[1],
        }
        for field in fields
    }
    manifest = {
        "generated_at_utc": generated_at,
        "sample_start_date": START_DATE,
        "source_urls": {
            "fred_graph_csv": FRED_GRAPH_URL,
            "finhacker_page": FINHACKER_PAGE_URL,
            "finhacker_history_api": FINHACKER_DATA_URL,
            "finhacker_live_json": FINHACKER_LIVE_URL,
        },
        "fred_series": [series.__dict__ for series in FRED_SERIES],
        "outputs": {
            "raw_fred_dir": str(RAW_FRED_DIR.relative_to(ROOT)),
            "raw_cnn_dir": str(RAW_CNN_DIR.relative_to(ROOT)),
            "merged_indicators": "data/processed/market_indicators.csv",
            "manifest": "data/processed/data_manifest.json",
            "inventory": "docs/DATA_INVENTORY.md",
        },
        "coverage": coverage,
        "finhacker_live": live,
        "known_missing": {
            "fund_nav": (
                "The notes require actual QDII fund NAV for Version B, but no "
                "specific fund code/name is present in the repository."
            )
        },
    }
    (PROCESSED_DIR / "data_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_inventory_doc(manifest)


def write_inventory_doc(manifest: dict) -> None:
    lines = [
        "# 数据清单",
        "",
        f"- 统一样本起点：`{manifest['sample_start_date']}`",
        f"- 生成时间 UTC：`{manifest['generated_at_utc']}`",
        "- 原始 FRED 数据：`data/raw/fred/*.csv`",
        "- 原始 CNN/FinHacker 数据：`data/raw/cnn/*.json`",
        "- 合并日频指标表：`data/processed/market_indicators.csv`",
        "- 机器可读 manifest：`data/processed/data_manifest.json`",
        "",
        "## 已获取字段覆盖",
        "",
        "| 字段 | 行数 | 起始日期 | 截止日期 |",
        "| :--- | ---: | :--- | :--- |",
    ]
    for field, info in manifest["coverage"].items():
        lines.append(
            f"| `{field}` | {info['rows']} | {info['start'] or ''} | {info['end'] or ''} |"
        )
    lines.extend(
        [
            "",
            "## 数据源",
            "",
            f"- FRED graph CSV：{manifest['source_urls']['fred_graph_csv']}",
            f"- FinHacker 页面：{manifest['source_urls']['finhacker_page']}",
            f"- FinHacker 历史数据接口：{manifest['source_urls']['finhacker_history_api']}",
            f"- FinHacker 实时 JSON：{manifest['source_urls']['finhacker_live_json']}",
            "",
            "## 尚缺数据",
            "",
            "- CNN Fear & Greed 源数据从 2011-01-03 开始；2000-01-03 到 2010 年末"
            "的合并表中该字段为空。",
            "- `fund_nav`：文档的真实执行回测 Version B 需要具体 QDII 基金历史净值，"
            "但当前仓库没有基金代码或名称；按 fall-fast 原则未替换成任意基金或 ETF。",
        ]
    )
    (DOCS_DIR / "DATA_INVENTORY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ensure_dirs()
    fred_rows: dict[str, list[dict[str, str | None]]] = {}
    for series in FRED_SERIES:
        fred_rows[series.series_id] = fetch_fred_series(series)

    cnn_history, cnn_live = fetch_finhacker_data()
    merged_rows = merge_by_date(fred_rows, cnn_history)
    write_csv(PROCESSED_DIR / "market_indicators.csv", merged_rows)
    write_manifest(merged_rows, cnn_live)

    print("Fetched data successfully.")
    print(f"Rows in merged indicators: {len(merged_rows)}")
    print(f"Latest merged date: {merged_rows[-1]['date']}")
    print(f"Latest FinHacker live score: {cnn_live['score']} at {cnn_live['timestamp']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"fetch_data failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
