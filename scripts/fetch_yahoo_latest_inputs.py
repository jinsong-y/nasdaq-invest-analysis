#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
RAW_OUTPUT = ROOT / "data" / "raw" / "yahoo" / "latest_quotes.json"
PROCESSED_OUTPUT = ROOT / "data" / "processed" / "latest_intraday_inputs.json"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1m"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

YAHOO_SYMBOLS = {
    "ndx": "^NDX",
    "vix": "^VIX",
    "vxn": "^VXN",
    "ndxe": "^NDXE",
    "sox": "^SOX",
}


def fail(message: str) -> None:
    raise RuntimeError(message)


def request_chart(symbol: str) -> dict[str, Any]:
    url = YAHOO_CHART_URL.format(symbol=quote(symbol, safe=""))
    result = subprocess.run(
        [
            "curl",
            "-fsSL",
            "--max-time",
            "60",
            "-H",
            f"User-Agent: {USER_AGENT}",
            "-H",
            "Accept: application/json",
            url,
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        fail(f"curl failed for Yahoo {symbol}: {stderr or f'exit {result.returncode}'}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        fail(f"invalid Yahoo JSON for {symbol}: {exc}")
    raise AssertionError("unreachable")


def fetch_payloads() -> dict[str, dict[str, Any]]:
    return {symbol: request_chart(symbol) for symbol in YAHOO_SYMBOLS.values()}


def build_latest_inputs_snapshot(payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    raw_inputs: dict[str, dict[str, Any]] = {}
    market_dates: list[str] = []
    source_times: list[str] = []
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    for output_name, symbol in YAHOO_SYMBOLS.items():
        quote_data = parse_chart_payload(symbol, payloads[symbol])
        raw_inputs[output_name] = quote_data
        market_dates.append(str(quote_data["as_of_date"]))
        source_times.append(str(quote_data["source_time_utc"]))

    ndx = _value(raw_inputs["ndx"])
    ndxe = _value(raw_inputs["ndxe"])
    sox = _value(raw_inputs["sox"])
    raw_inputs["ndxe_ndx"] = {
        "value": ndxe / ndx,
        "as_of_date": min(raw_inputs["ndxe"]["as_of_date"], raw_inputs["ndx"]["as_of_date"]),
        "source_time_utc": min(raw_inputs["ndxe"]["source_time_utc"], raw_inputs["ndx"]["source_time_utc"]),
        "symbol": "^NDXE/^NDX",
        "source": "yahoo_finance_chart",
    }
    raw_inputs["sox_ndx"] = {
        "value": sox / ndx,
        "as_of_date": min(raw_inputs["sox"]["as_of_date"], raw_inputs["ndx"]["as_of_date"]),
        "source_time_utc": min(raw_inputs["sox"]["source_time_utc"], raw_inputs["ndx"]["source_time_utc"]),
        "symbol": "^SOX/^NDX",
        "source": "yahoo_finance_chart",
    }

    return {
        "generated_at_utc": generated_at,
        "source": "yahoo_finance_chart",
        "market_date": max(market_dates),
        "latest_source_time_utc": max(source_times),
        "raw_inputs": raw_inputs,
    }


def parse_chart_payload(symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        fail(f"Yahoo payload missing chart for {symbol}")
    if chart.get("error"):
        fail(f"Yahoo chart error for {symbol}: {chart['error']}")
    results = chart.get("result")
    if not isinstance(results, list) or not results:
        fail(f"Yahoo payload missing result for {symbol}")
    result = results[0]
    if not isinstance(result, dict):
        fail(f"Yahoo result malformed for {symbol}")
    meta = result.get("meta")
    if not isinstance(meta, dict):
        fail(f"Yahoo payload missing meta for {symbol}")

    timestamp = latest_timestamp(result, meta, symbol)
    value = latest_close_value(result)
    if value is None:
        value = meta.get("regularMarketPrice")
    value = float(value)
    if not math.isfinite(value):
        fail(f"Yahoo value is not finite for {symbol}: {value!r}")
    source_time = datetime.fromtimestamp(int(timestamp), timezone.utc)
    exchange_tz = str(meta.get("exchangeTimezoneName") or "America/New_York")
    market_date = source_time.astimezone(ZoneInfo(exchange_tz)).date().isoformat()
    return {
        "value": value,
        "as_of_date": market_date,
        "source_time_utc": source_time.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "symbol": symbol,
        "source": "yahoo_finance_chart",
    }


def latest_timestamp(result: dict[str, Any], meta: dict[str, Any], symbol: str) -> int:
    timestamps = result.get("timestamp")
    if isinstance(timestamps, list) and timestamps:
        for value in reversed(timestamps):
            if value is not None:
                return int(value)
    value = meta.get("regularMarketTime")
    if value is None:
        fail(f"Yahoo payload has no timestamp for {symbol}")
    return int(value)


def latest_close_value(result: dict[str, Any]) -> float | None:
    indicators = result.get("indicators")
    if not isinstance(indicators, dict):
        return None
    quotes = indicators.get("quote")
    if not isinstance(quotes, list) or not quotes:
        return None
    close_values = quotes[0].get("close") if isinstance(quotes[0], dict) else None
    if not isinstance(close_values, list):
        return None
    for value in reversed(close_values):
        if value is not None:
            numeric = float(value)
            if math.isfinite(numeric):
                return numeric
    return None


def _value(entry: dict[str, Any]) -> float:
    value = float(entry["value"])
    if not math.isfinite(value):
        fail(f"snapshot value is not finite: {entry!r}")
    return value


def write_snapshot(root: Path, snapshot: dict[str, Any], raw_payloads: dict[str, dict[str, Any]]) -> None:
    root = Path(root)
    processed_path = root / "data" / "processed" / "latest_intraday_inputs.json"
    raw_path = root / "data" / "raw" / "yahoo" / "latest_quotes.json"
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    processed_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    raw_path.write_text(
        json.dumps(
            {
                "generated_at_utc": snapshot["generated_at_utc"],
                "source": "yahoo_finance_chart",
                "payloads": raw_payloads,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        payloads = fetch_payloads()
        snapshot = build_latest_inputs_snapshot(payloads)
        write_snapshot(args.root, snapshot, payloads)
        print(
            "Fetched Yahoo latest inputs for "
            f"{snapshot['market_date']} at {snapshot['latest_source_time_utc']}"
        )
    except Exception as exc:
        print(f"fetch_yahoo_latest_inputs failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
