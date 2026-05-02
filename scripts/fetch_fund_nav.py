#!/usr/bin/env python3
from __future__ import annotations

import csv
import html
import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "funds"
PROCESSED_DIR = ROOT / "data" / "processed" / "funds"


FUNDS = [
    ("270042", "广发纳斯达克100ETF联接人民币(QDII)A"),
    ("000834", "大成纳斯达克100ETF联接(QDII)A"),
    ("016452", "南方纳斯达克100指数发起(QDII)A"),
    ("161130", "易方达纳斯达克100ETF联接(QDII-LOF)A人民币"),
    ("040046", "华安纳斯达克100ETF联接(QDII)A"),
    ("160213", "国泰纳斯达克100指数"),
    ("539001", "建信纳斯达克100指数(QDII)A人民币"),
    ("015299", "华夏纳斯达克100ETF发起式联接(QDII)A"),
    ("016055", "博时纳斯达克100ETF发起式联接(QDII)A人民币"),
    ("016532", "嘉实纳斯达克100ETF发起联接(QDII)A人民币"),
]


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "curl/8.7.1"})
    with urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def parse_rows(payload: str) -> list[dict[str, str]]:
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", payload, flags=re.S):
        cells = [strip_tags(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
        if len(cells) < 6 or not re.match(r"\d{4}-\d{2}-\d{2}", cells[0]):
            continue
        rows.append(
            {
                "date": cells[0],
                "nav": cells[1],
                "accum_nav": cells[2],
                "daily_growth": cells[3],
                "purchase_status": cells[4],
                "redeem_status": cells[5],
            }
        )
    return rows


def fetch_nav(code: str) -> list[dict[str, str]]:
    first_url = f"https://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page=1&per=20&sdate=&edate="
    first_payload = fetch_text(first_url)
    match = re.search(r"pages:(\d+)", first_payload)
    if not match:
        raise RuntimeError(f"cannot find page count for {code}")
    pages = int(match.group(1))
    rows = parse_rows(first_payload)
    for page in range(2, pages + 1):
        url = f"https://fund.eastmoney.com/f10/F10DataApi.aspx?type=lsjz&code={code}&page={page}&per=20&sdate=&edate="
        rows.extend(parse_rows(fetch_text(url)))
    if not rows:
        raise RuntimeError(f"no NAV rows parsed for {code}")
    unique = {row["date"]: row for row in rows}
    return sorted(unique.values(), key=lambda row: row["date"])


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for code, name in FUNDS:
        rows = fetch_nav(code)
        out = PROCESSED_DIR / f"{code}.csv"
        with out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["date", "nav", "accum_nav", "daily_growth", "purchase_status", "redeem_status"])
            writer.writeheader()
            writer.writerows(rows)
        manifest.append({"code": code, "name": name, "rows": len(rows), "start": rows[0]["date"], "end": rows[-1]["date"], "path": str(out.relative_to(ROOT))})
        print(code, name, len(rows), rows[0]["date"], rows[-1]["date"])
    (PROCESSED_DIR / "funds_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"fetch_fund_nav failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
