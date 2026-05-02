import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_nasdaq100_pe import extract_pe_series
from src.version_c.data import merge_market_with_pe
from src.version_c.engine import run_mechanical_baseline, run_pe_strategy


class VersionCFetchTests(unittest.TestCase):
    def test_extract_pe_series_parses_worldperatio_script_block(self):
        html = """
        <html><body>
        <script>
        detailPE_data[0] = [
            [Date.UTC(2024, 0, 1), 25.0],
            [Date.UTC(2024, 1, 1), 30.0],
            [Date.UTC(2024, 2, 1), 27.0]
        ];
        </script>
        </body></html>
        """
        out = extract_pe_series(html)
        self.assertEqual(["date", "pe_ratio"], list(out.columns))
        self.assertEqual(["2024-01-01", "2024-02-01", "2024-03-01"], out["date"].dt.strftime("%Y-%m-%d").tolist())
        self.assertEqual([25.0, 30.0, 27.0], out["pe_ratio"].round(2).tolist())


class VersionCDataTests(unittest.TestCase):
    def test_merge_market_with_pe_forward_fills_and_adds_expanding_pctile(self):
        market = pd.DataFrame(
            {"date": pd.to_datetime(["2024-01-02", "2024-01-15", "2024-02-05", "2024-03-05"]), "ndx": [100.0, 101.0, 102.0, 103.0]}
        )
        pe = pd.DataFrame(
            {"date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]), "pe_ratio": [25.0, 30.0, 27.0]}
        )
        merged = merge_market_with_pe(market, pe)
        self.assertEqual([25.0, 25.0, 30.0, 27.0], merged["pe_ratio"].round(2).tolist())
        self.assertEqual([1.0, 1.0, 1.0, 2.0 / 3.0], merged["pe_pctile"].tolist())


class VersionCEngineTests(unittest.TestCase):
    def test_run_pe_strategy_applies_pause_double_buy_and_staged_sells(self):
        index = pd.date_range("2024-01-01", periods=8, freq="B")
        df = pd.DataFrame(
            {
                "ndx": [100.0] * 8,
                "pe_ratio": [30.0, 30.0, 15.0, 18.0, 35.0, 38.0, 38.0, 16.0],
                "pe_pctile": [0.45, 0.45, 0.15, 0.35, 0.85, 0.92, 0.92, 0.18],
            },
            index=index,
        )
        result = run_pe_strategy(df, run_id="pe_cycle")
        daily = result.daily

        self.assertEqual(
            ["pause", "pause", "double_buy", "normal_buy", "trim_80", "trim_90", "clear_90", "double_buy"],
            daily["state"].tolist(),
        )
        self.assertEqual([0.0, 0.0, 400.0, 200.0, 0.0, 0.0, 0.0, 400.0], daily["invested"].tolist())
        self.assertEqual([0.0, 0.0, 0.0, 0.0, 180.0, 126.0, 294.0, 0.0], daily["sold_value"].round(2).tolist())
        self.assertEqual(4.0, round(float(daily["shares"].iloc[-1]), 4))
        self.assertEqual(1200.0, round(float(daily["cash"].iloc[-1]), 2))

    def test_mechanical_baseline_uses_daily_200_budget(self):
        index = pd.date_range("2024-01-01", periods=3, freq="B")
        df = pd.DataFrame({"ndx": [100.0, 100.0, 100.0]}, index=index)
        result = run_mechanical_baseline(df, run_id="baseline")
        self.assertEqual([200.0, 200.0, 200.0], result.daily["invested"].tolist())
        self.assertEqual(600.0, float(result.daily["invested"].sum()))
        self.assertEqual(6.0, float(result.daily["shares"].iloc[-1]))


if __name__ == "__main__":
    unittest.main()
