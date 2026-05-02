import csv
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.version_a.config import BacktestParams, BASELINE_START, MAIN_START, coarse_grid
from src.version_a.data import load_market_data
from src.version_a.engine import run_backtest, run_mechanical_baseline
from src.version_a.features import add_features
from src.version_a.grid import (
    add_lag_robustness,
    mark_sweet_spots,
    rank_summaries,
    refined_grid,
    robustness_grid,
    write_run_outputs,
)
from src.version_a.metrics import summarize_run
from src.version_a.report import build_report


class VersionAConfigTests(unittest.TestCase):
    def test_coarse_grid_has_expected_size_and_defaults(self):
        grid = list(coarse_grid())
        self.assertEqual(8748, len(grid))
        self.assertTrue(all(isinstance(item, BacktestParams) for item in grid))
        self.assertEqual({2}, {item.lag_days for item in grid})
        self.assertEqual({10}, {item.standard_buy_window_days for item in grid})
        self.assertEqual({20}, {item.deep_buy_window_days for item in grid})
        self.assertEqual({15}, {item.pause_window_days for item in grid})

    def test_required_windows_are_explicit(self):
        self.assertEqual("2000-01-03", BASELINE_START)
        self.assertEqual("2011-01-03", MAIN_START)


class VersionADataFeatureTests(unittest.TestCase):
    def test_load_market_data_filters_start_and_validates_columns(self):
        df = load_market_data(ROOT / "data" / "processed" / "market_indicators.csv")
        self.assertEqual("2000-01-03", df.index.min().strftime("%Y-%m-%d"))
        self.assertIn("ndx", df.columns)
        self.assertIn("cnn_fear_greed", df.columns)

    def test_add_features_creates_expected_columns(self):
        df = pd.DataFrame(
            {
                "ndx": [100.0, 101.0, 99.0, 103.0, 105.0],
                "vxn": [20.0, 22.0, 25.0, 23.0, 21.0],
                "vix": [18.0, 19.0, 24.0, 21.0, 20.0],
                "ndxe_ndx": [0.30, 0.31, 0.29, 0.32, 0.33],
                "sox_ndx": [0.20, 0.21, 0.19, 0.22, 0.23],
                "cnn_fear_greed": [40.0, 35.0, 20.0, 25.0, 30.0],
            },
            index=pd.to_datetime(
                ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
            ),
        )
        out = add_features(df, sma_period=3, sentiment_lookback_days=3, repair_ma_days=2)
        for column in ["sma", "dist_sma", "vxn_pctile", "vix_pctile", "cnn_ma5", "ndxe_ma", "sox_ma"]:
            self.assertIn(column, out.columns)


class VersionAEngineTests(unittest.TestCase):
    def test_run_backtest_records_daily_states_and_metrics(self):
        index = pd.date_range("2020-01-01", periods=8, freq="B")
        df = pd.DataFrame(
            {
                "ndx": [100, 98, 96, 99, 102, 103, 101, 104],
                "sma": [100] * 8,
                "dist_sma": [0, -0.02, -0.04, -0.01, 0.02, 0.03, 0.01, 0.04],
                "vxn_pctile": [0.5, 0.8, 0.9, 0.7, 0.5, 0.4, 0.3, 0.2],
                "vix_pctile": [0.5, 0.8, 0.9, 0.7, 0.5, 0.4, 0.3, 0.2],
                "vxn": [20, 30, 35, 28, 22, 20, 19, 18],
                "vix": [18, 25, 30, 24, 20, 18, 17, 16],
                "cnn_fear_greed": [50, 20, 18, 25, 30, 40, 60, 80],
                "cnn_ma5": [50, 35, 29, 28, 29, 31, 35, 47],
                "ndxe_ndx": [0.3, 0.29, 0.28, 0.30, 0.31, 0.32, 0.31, 0.30],
                "sox_ndx": [0.2, 0.19, 0.18, 0.20, 0.21, 0.22, 0.21, 0.20],
                "ndxe_ma": [0.3, 0.295, 0.285, 0.29, 0.305, 0.315, 0.315, 0.305],
                "sox_ma": [0.2, 0.195, 0.185, 0.19, 0.205, 0.215, 0.215, 0.205],
            },
            index=index,
        )
        params = BacktestParams(200, 0.05, 1.2, 0.75, 25, 75, 756, 20, 2, 1, 3, 5, 3)
        result = run_backtest(df, params, run_id="test_run")
        summary = summarize_run(result)
        self.assertEqual("test_run", result.run_id)
        self.assertEqual(len(df), len(result.daily))
        self.assertGreater(summary["total_invested"], 0)
        self.assertIn("roi", summary)

    def test_mechanical_baseline_invests_fixed_budget(self):
        index = pd.date_range("2020-01-01", periods=4, freq="B")
        df = pd.DataFrame({"ndx": [100.0, 101.0, 102.0, 103.0]}, index=index)
        result = run_mechanical_baseline(df, run_id="baseline")
        summary = summarize_run(result)
        self.assertEqual(400.0, summary["total_invested"])
        self.assertEqual({"baseline"}, set(result.daily["state"]))


class VersionAGridTests(unittest.TestCase):
    def test_rank_summaries_adds_composite_score(self):
        rows = [
            {"run_id": "a", "roi": 0.10, "calmar": 0.2, "excess_return": 0.03, "cost_improvement": 0.02, "lag_robustness": 0.9},
            {"run_id": "b", "roi": 0.20, "calmar": 0.1, "excess_return": 0.01, "cost_improvement": 0.01, "lag_robustness": 0.7},
        ]
        ranked = rank_summaries(rows)
        self.assertIn("composite_score", ranked[0])
        self.assertEqual(2, len(ranked))

    def test_write_run_outputs_creates_csv_and_json(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_run_outputs(out, [{"run_id": "x", "roi": 0.1}], [{"run_id": "x", "date": "2020-01-01", "state": "normal"}])
            self.assertTrue((out / "summary.csv").exists())
            self.assertTrue((out / "summary.json").exists())
            self.assertTrue((out / "runs.csv").exists())
            self.assertTrue((out / "runs.json").exists())

    def test_refined_and_robustness_grids_expand_seed_parameters(self):
        seed = BacktestParams(200, 0.05, 1.2, 0.8, 25, 75, 756, 20, 2, 2, 10, 20, 15)
        refined = list(refined_grid([seed]))
        robust = list(robustness_grid(refined[:1]))
        self.assertGreater(len(refined), 1)
        self.assertEqual({"refined"}, {item.stage for item in refined})
        self.assertEqual({1, 2, 3}, {item.lag_days for item in robust})
        self.assertEqual({"v1_no_cnn", "v2_full"}, {item.strategy_family for item in robust})

    def test_lag_robustness_and_sweet_spot_markers_are_added(self):
        rows = [
            {
                "run_id": "a1",
                "stage": "robustness",
                "lag_days": 1,
                "strategy_family": "v2_full",
                "sma_period": 200,
                "sma_buffer_pct": 0.05,
                "overheat_ratio": 1.2,
                "vol_high_pctile": 0.8,
                "cnn_fear_threshold": 25,
                "cnn_greed_threshold": 75,
                "sentiment_lookback_days": 756,
                "repair_ma_days": 20,
                "divergence_weeks": 2,
                "standard_buy_window_days": 10,
                "deep_buy_window_days": 20,
                "pause_window_days": 15,
                "roi": 0.30,
                "calmar": 1.0,
                "excess_return": 0.1,
                "cost_improvement": 0.1,
            },
            {
                "run_id": "a3",
                "stage": "robustness",
                "lag_days": 3,
                "strategy_family": "v2_full",
                "sma_period": 200,
                "sma_buffer_pct": 0.05,
                "overheat_ratio": 1.2,
                "vol_high_pctile": 0.8,
                "cnn_fear_threshold": 25,
                "cnn_greed_threshold": 75,
                "sentiment_lookback_days": 756,
                "repair_ma_days": 20,
                "divergence_weeks": 2,
                "standard_buy_window_days": 10,
                "deep_buy_window_days": 20,
                "pause_window_days": 15,
                "roi": 0.27,
                "calmar": 1.0,
                "excess_return": 0.1,
                "cost_improvement": 0.1,
            },
        ]
        marked = mark_sweet_spots(add_lag_robustness(rows))
        self.assertIn("lag_robustness", marked[0])
        self.assertIn("sweet_spot", marked[0])


class VersionAReportTests(unittest.TestCase):
    def test_build_report_writes_overview_and_detail_pages(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            build_report(
                out,
                summaries=[{"run_id": "run_a", "composite_score": 91.2, "roi": 0.2, "max_drawdown": -0.1}],
                run_details={"run_a": [{"date": "2020-01-01", "portfolio_value": 1000, "state": "normal"}]},
            )
            self.assertTrue((out / "index.html").exists())
            self.assertTrue((out / "runs" / "run_a.html").exists())
            self.assertIn("run_a", (out / "index.html").read_text(encoding="utf-8"))


class VersionAWorkflowTests(unittest.TestCase):
    def test_run_workflow_smoke_writes_report(self):
        from scripts.run_version_a_backtest import run_workflow

        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            run_workflow(output_dir=out, max_runs=3)
            self.assertTrue((out / "summary.csv").exists())
            self.assertTrue((out / "runs.csv").exists())
            self.assertTrue((out / "index.html").exists())
            with (out / "summary.csv").open(newline="", encoding="utf-8") as handle:
                self.assertGreater(len(list(csv.DictReader(handle))), 0)


if __name__ == "__main__":
    unittest.main()
