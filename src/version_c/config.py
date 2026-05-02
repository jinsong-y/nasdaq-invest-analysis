from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

MARKET_DATA_PATH = ROOT / "data" / "processed" / "market_indicators.csv"
PE_DATA_PATH = ROOT / "data" / "processed" / "nasdaq100_pe.csv"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "version_c_pe"

START_DATE = "2000-01-03"
DAILY_BUDGET = 200.0
DOUBLE_BUY_BUDGET = 400.0

BUY_THRESHOLD = 0.40
DOUBLE_BUY_THRESHOLD = 0.20
SELL_THRESHOLD = 0.80
FULL_EXIT_THRESHOLD = 0.90
NEAR_PEAK_RATIO = 0.98
