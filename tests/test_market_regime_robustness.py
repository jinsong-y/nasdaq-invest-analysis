import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_market_regime_robustness import (
    EXTREME_DATE_EXPECTATIONS,
    GRID_VALUES,
    add_forward_metrics,
    build_misclassification_review,
    build_walk_forward_table,
    config_id,
    evaluate_config_result,
    generate_candidate_configs,
    score_extreme_dates,
    score_state_stability,
    write_outputs,
    write_recommended_config,
)
from src.market_regime.config import DashboardConfig


class MarketRegimeRobustnessGridTests(unittest.TestCase):
    def test_generate_candidate_configs_skips_invalid_threshold_orders(self):
        configs = list(generate_candidate_configs())
        self.assertGreater(len(configs), 0)
        self.assertLess(len(configs), 3 * 4 * 3 * 3 * 2 * 3 * 3 * 3 * 3 * 3)
        for config in configs:
            self.assertLess(config.top_risk_watch_threshold, config.top_risk_threshold)
            self.assertLess(config.warm_threshold, config.overheat_threshold)
            self.assertLess(config.recovery_top_risk_ceiling, config.top_risk_watch_threshold)

    def test_config_id_is_stable_and_includes_thresholds(self):
        config = DashboardConfig(
            stress_low_threshold=55.0,
            recovery_threshold=60.0,
            warm_threshold=60.0,
            overheat_threshold=70.0,
            top_risk_watch_threshold=70.0,
            top_risk_threshold=75.0,
            recovery_temperature_ceiling=65.0,
            recovery_top_risk_ceiling=55.0,
            recovery_overheat_ceiling=50.0,
            recovery_dist_sma_ceiling=0.08,
        )
        ident = config_id(config)
        self.assertIn("stress55", ident)
        self.assertIn("rec60", ident)
        self.assertIn("top75", ident)

    def test_grid_values_match_spec(self):
        self.assertEqual([50.0, 55.0, 60.0], GRID_VALUES["stress_low_threshold"])
        self.assertEqual([50.0, 55.0, 60.0, 65.0], GRID_VALUES["recovery_threshold"])
        self.assertEqual([0.06, 0.08, 0.10], GRID_VALUES["recovery_dist_sma_ceiling"])


class MarketRegimeRobustnessScoringTests(unittest.TestCase):
    def _daily(self):
        dates = pd.bdate_range("2026-01-01", periods=270)
        regimes = ["normal"] * len(dates)
        regimes[0:5] = ["panic_low"] * 5
        regimes[50:55] = ["top_risk"] * 5
        return pd.DataFrame(
            {
                "date": dates,
                "market_regime": regimes,
                "ndx": [100.0 + i for i in range(len(dates))],
                "temperature_score": [50.0] * len(dates),
                "undervaluation_score": [0.0] * len(dates),
                "overheat_score": [0.0] * len(dates),
                "top_risk_score": [0.0] * len(dates),
                "recovery_score": [0.0] * len(dates),
            }
        )

    def test_extreme_date_expectations_include_current_target(self):
        self.assertEqual({"warm_recovery"}, EXTREME_DATE_EXPECTATIONS["2026-04-30"])

    def test_add_forward_metrics_adds_returns_and_mdd(self):
        out = add_forward_metrics(self._daily())
        self.assertIn("fwd_1m", out.columns)
        self.assertIn("fwd_12m_mdd", out.columns)

    def test_add_forward_metrics_fails_fast_on_bad_ndx(self):
        daily = self._daily()
        daily["ndx"] = daily["ndx"].astype(object)
        daily.loc[0, "ndx"] = "bad"
        with self.assertRaises(ValueError):
            add_forward_metrics(daily)

    def test_state_stability_penalizes_churn(self):
        stable = self._daily()
        churn = stable.copy()
        churn["market_regime"] = ["normal", "warm"] * (len(churn) // 2)
        self.assertGreater(score_state_stability(stable), score_state_stability(churn))

    def test_extreme_dates_score_accepts_expected_regime(self):
        rows = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-04-30"]),
                "market_regime": ["warm_recovery"],
            }
        )
        score, table = score_extreme_dates(rows)
        latest = table[table["requested_date"] == "2026-04-30"].iloc[0]
        self.assertGreater(score, 0)
        self.assertEqual("pass", latest["result"])

    def test_evaluate_config_result_returns_robust_score(self):
        result = evaluate_config_result("sample", DashboardConfig(), self._daily())
        self.assertIn("robust_score", result)
        self.assertIn("low_zone_quality", result)
        self.assertIn("top_warning_quality", result)

    def test_walk_forward_table_scores_named_windows(self):
        table = build_walk_forward_table("sample", DashboardConfig(), self._daily())
        self.assertIn("window_name", table.columns)
        self.assertIn("robust_score", table.columns)

    def test_misclassification_review_marks_failed_extreme_dates(self):
        daily = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-04-30"]),
                "market_regime": ["normal"],
                "ndx": [100.0],
            }
        )
        review = build_misclassification_review("sample", daily)
        latest = review[review["requested_date"] == "2026-04-30"].iloc[0]
        self.assertEqual("2026-04-30", latest["requested_date"])
        self.assertEqual("fail", latest["result"])


class MarketRegimeRobustnessOutputTests(unittest.TestCase):
    def _sample(self):
        dates = pd.bdate_range("2026-01-01", periods=270)
        return pd.DataFrame(
            {
                "date": dates,
                "market_regime": ["normal"] * len(dates),
                "ndx": [100.0 + i for i in range(len(dates))],
            }
        )

    def test_write_recommended_config_creates_importable_factory(self):
        config = DashboardConfig(stress_low_threshold=60.0, recovery_threshold=65.0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "recommended_config.py"
            write_recommended_config(path, config)
            text = path.read_text()
            self.assertIn("from src.market_regime.config import DashboardConfig", text)
            self.assertIn("def recommended_config() -> DashboardConfig:", text)
            self.assertIn("stress_low_threshold=60.0", text)
            self.assertIn("recovery_threshold=65.0", text)

    def test_write_outputs_creates_required_files_and_html_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            current = DashboardConfig()
            recommended = DashboardConfig(stress_low_threshold=60.0, recovery_threshold=65.0)
            grid = pd.DataFrame(
                [
                    evaluate_config_result("current", current, self._sample()),
                    evaluate_config_result("recommended", recommended, self._sample()),
                ]
            )
            top = grid.sort_values("robust_score", ascending=False).head(1)
            extreme = pd.DataFrame(
                [{"requested_date": "2026-04-30", "market_regime": "warm_recovery", "result": "pass"}]
            )
            write_outputs(out, grid, top, pd.DataFrame(), extreme, pd.DataFrame(), current, recommended)
            for name in [
                "grid_results.csv",
                "top_configs.csv",
                "walk_forward.csv",
                "extreme_dates.csv",
                "misclassification_review.csv",
                "recommendation.json",
                "recommended_config.py",
                "index.html",
            ]:
                self.assertTrue((out / name).exists(), name)
            payload = json.loads((out / "recommendation.json").read_text())
            self.assertIn("recommended_config", payload)
            html = (out / "index.html").read_text()
            self.assertIn("Current config", html)
            self.assertIn("Recommended config", html)
            self.assertIn("Changed params", html)
            self.assertIn("Score comparison", html)
            self.assertIn("Extreme-date pass/fail", html)
            self.assertIn("Copyable config snippet", html)

    def test_write_outputs_fails_fast_on_empty_recommendation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                write_outputs(
                    Path(tmp),
                    pd.DataFrame(),
                    pd.DataFrame(),
                    pd.DataFrame(),
                    pd.DataFrame(),
                    pd.DataFrame(),
                    DashboardConfig(),
                    DashboardConfig(),
                )

    def test_run_workflow_scores_only_through_target_date(self):
        from scripts.run_market_regime_robustness import run_workflow

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "robustness"
            dashboard = Path(tmp) / "dashboard"
            run_workflow(output_dir=out, dashboard_output_dir=dashboard, target_date="2026-04-30", max_configs=5)

            top = pd.read_csv(out / "top_configs.csv")
            self.assertEqual(0.0, top.iloc[0]["latest_target_penalty"])
            latest = json.loads((dashboard / "latest.json").read_text())
            self.assertEqual("2026-04-30", latest["as_of_date"])


if __name__ == "__main__":
    unittest.main()
