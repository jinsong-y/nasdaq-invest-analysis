import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market_regime.config import DashboardConfig, OUTPUT_COLUMNS, REQUIRED_DERIVED_COLUMNS, REQUIRED_RAW_COLUMNS
from src.market_regime.report import REGIME_BANDS, ZH_TEXT


class MarketRegimeConfigTests(unittest.TestCase):
    def test_required_columns_are_explicit(self):
        self.assertEqual(
            {
                "ndx",
                "vxn",
                "vix",
                "cnn_fear_greed",
                "ndxe_ndx",
                "sox_ndx",
            },
            REQUIRED_RAW_COLUMNS,
        )
        self.assertEqual(
            {
                "sma",
                "dist_sma",
                "vxn_pctile",
                "vix_pctile",
                "cnn_ma5",
                "ndxe_ma",
                "sox_ma",
            },
            REQUIRED_DERIVED_COLUMNS,
        )

    def test_default_config_matches_design(self):
        config = DashboardConfig()
        self.assertEqual(180, config.sma_period)
        self.assertEqual(1260, config.sentiment_lookback_days)
        self.assertEqual(50, config.repair_ma_days)
        self.assertEqual(252, config.rolling_high_days)
        self.assertEqual(75.0, config.panic_low_threshold)
        self.assertEqual(55.0, config.stress_low_threshold)
        self.assertEqual(55.0, config.recovery_threshold)
        self.assertEqual(60.0, config.warm_threshold)
        self.assertEqual(70.0, config.overheat_threshold)
        self.assertEqual(75.0, config.top_risk_threshold)
        self.assertEqual(70.0, config.top_risk_watch_threshold)
        self.assertEqual(65.0, config.recovery_temperature_ceiling)
        self.assertEqual(55.0, config.recovery_top_risk_ceiling)
        self.assertEqual(50.0, config.recovery_overheat_ceiling)
        self.assertEqual(0.08, config.recovery_dist_sma_ceiling)
        self.assertEqual(45.0, config.low_confidence_threshold)
        self.assertGreater(config.top_risk_threshold, config.warm_threshold)
        self.assertLess(config.top_risk_watch_threshold, config.top_risk_threshold)


class MarketRegimeReportTextTests(unittest.TestCase):
    def test_report_knows_new_regime_labels(self):
        labels = {band[0]: band[1] for band in REGIME_BANDS}
        self.assertEqual("Warm Recovery", labels["warm_recovery"])
        self.assertEqual("Top Risk Watch", labels["top_risk_watch"])
        self.assertEqual("暖修复", ZH_TEXT["Warm Recovery"])
        self.assertEqual("顶部风险观察", ZH_TEXT["Top Risk Watch"])
        self.assertEqual("暂停新买入", ZH_TEXT["pause_new_buy"])
        self.assertEqual("轻降节奏", ZH_TEXT["reduce_light"])


import pandas as pd

from src.market_regime.model import classify_daily, classify_latest, latest_summary, missing_inputs_for_row


class MarketRegimeValidationTests(unittest.TestCase):
    def _valid_row(self):
        return {
            "ndx": 100.0,
            "sma": 100.0,
            "dist_sma": 0.0,
            "vxn": 20.0,
            "vix": 18.0,
            "vxn_pctile": 0.50,
            "vix_pctile": 0.50,
            "cnn_fear_greed": 50.0,
            "cnn_ma5": 50.0,
            "ndxe_ndx": 0.35,
            "ndxe_ma": 0.35,
            "sox_ndx": 0.25,
            "sox_ma": 0.25,
        }

    def test_missing_inputs_for_row_lists_nan_fields(self):
        row = pd.Series(self._valid_row())
        row["vix"] = float("nan")
        row["vxn"] = None
        self.assertEqual(["vix", "vxn"], missing_inputs_for_row(row))

    def test_latest_classification_fails_when_required_latest_inputs_missing(self):
        frame = pd.DataFrame([self._valid_row()], index=pd.to_datetime(["2026-05-01"]))
        frame.loc[pd.Timestamp("2026-05-01"), "vix"] = float("nan")
        with self.assertRaisesRegex(ValueError, "2026-05-01.*vix"):
            classify_latest(frame)

    def test_latest_classification_fails_when_required_latest_inputs_invalid(self):
        frame = pd.DataFrame([self._valid_row()], index=pd.to_datetime(["2026-05-01"]))
        frame["vix"] = frame["vix"].astype(object)
        frame.loc[pd.Timestamp("2026-05-01"), "vix"] = "bad"
        with self.assertRaisesRegex(ValueError, "2026-05-01.*vix"):
            classify_latest(frame)

    def test_latest_classification_fails_when_required_latest_inputs_infinite(self):
        for value in [float("inf"), float("-inf")]:
            with self.subTest(value=value):
                frame = pd.DataFrame([self._valid_row()], index=pd.to_datetime(["2026-05-01"]))
                frame.loc[pd.Timestamp("2026-05-01"), "vix"] = value
                with self.assertRaisesRegex(ValueError, "2026-05-01.*vix"):
                    classify_latest(frame)

    def test_latest_classification_fails_when_denominator_is_zero(self):
        frame = pd.DataFrame([self._valid_row()], index=pd.to_datetime(["2026-05-01"]))
        frame.loc[pd.Timestamp("2026-05-01"), "ndxe_ma"] = 0.0
        with self.assertRaisesRegex(ValueError, "2026-05-01.*ndxe_ma"):
            classify_latest(frame)


class MarketRegimeClassificationTests(unittest.TestCase):
    def _row(
        self,
        *,
        ndx=100.0,
        sma=100.0,
        dist_sma=0.0,
        vxn=20.0,
        vix=18.0,
        vxn_pctile=0.50,
        vix_pctile=0.50,
        cnn_fear_greed=50.0,
        cnn_ma5=50.0,
        ndxe_ndx=0.35,
        ndxe_ma=0.35,
        sox_ndx=0.25,
        sox_ma=0.25,
    ):
        return pd.Series(
            {
                "ndx": ndx,
                "sma": sma,
                "dist_sma": dist_sma,
                "vxn": vxn,
                "vix": vix,
                "vxn_pctile": vxn_pctile,
                "vix_pctile": vix_pctile,
                "cnn_fear_greed": cnn_fear_greed,
                "cnn_ma5": cnn_ma5,
                "ndxe_ndx": ndxe_ndx,
                "ndxe_ma": ndxe_ma,
                "sox_ndx": sox_ndx,
                "sox_ma": sox_ma,
            }
        )

    def _classify(self, row):
        from src.market_regime.model import classify_row

        return classify_row(row, date=pd.Timestamp("2026-04-30"), strict=True)

    def test_panic_low_fixture(self):
        result = self._classify(
            self._row(
                ndx=78.0,
                sma=100.0,
                dist_sma=-0.22,
                vxn=55.0,
                vix=48.0,
                vxn_pctile=0.98,
                vix_pctile=0.97,
                cnn_fear_greed=8.0,
                cnn_ma5=10.0,
                ndxe_ndx=0.30,
                ndxe_ma=0.36,
                sox_ndx=0.18,
                sox_ma=0.25,
            )
        )
        self.assertEqual("panic_low", result.market_regime)
        self.assertEqual("add_strong", result.dashboard_action)
        self.assertGreaterEqual(result.undervaluation_score, 75.0)

    def test_stress_low_fixture(self):
        result = self._classify(
            self._row(
                ndx=90.0,
                sma=100.0,
                dist_sma=-0.10,
                vxn_pctile=0.82,
                vix_pctile=0.80,
                cnn_fear_greed=22.0,
                cnn_ma5=24.0,
            )
        )
        self.assertEqual("stress_low", result.market_regime)
        self.assertEqual("add_light", result.dashboard_action)

    def test_recovery_fixture(self):
        result = self._classify(
            self._row(
                ndx=99.0,
                sma=100.0,
                dist_sma=-0.01,
                vxn=21.0,
                vix=18.0,
                vxn_pctile=0.55,
                vix_pctile=0.50,
                cnn_fear_greed=42.0,
                cnn_ma5=35.0,
                ndxe_ndx=0.37,
                ndxe_ma=0.35,
                sox_ndx=0.27,
                sox_ma=0.25,
            )
        )
        self.assertEqual("recovery", result.market_regime)
        self.assertEqual("normal_dca", result.dashboard_action)

    def test_recovery_requires_current_sentiment_above_moving_average(self):
        falling_sentiment = self._classify(
            self._row(
                dist_sma=-0.02,
                cnn_fear_greed=10.0,
                cnn_ma5=45.0,
                ndxe_ndx=0.35,
                ndxe_ma=0.35,
                sox_ndx=0.25,
                sox_ma=0.25,
            )
        )
        rising_sentiment = self._classify(
            self._row(
                dist_sma=-0.02,
                cnn_fear_greed=45.0,
                cnn_ma5=10.0,
                ndxe_ndx=0.35,
                ndxe_ma=0.35,
                sox_ndx=0.25,
                sox_ma=0.25,
            )
        )

        self.assertNotEqual("recovery", falling_sentiment.market_regime)
        self.assertGreater(rising_sentiment.recovery_score, falling_sentiment.recovery_score)

    def test_warm_recovery_when_repair_is_high_but_price_extended(self):
        result = self._classify(
            self._row(
                ndx=110.0,
                sma=100.0,
                dist_sma=0.10,
                vxn_pctile=0.40,
                vix_pctile=0.38,
                cnn_fear_greed=66.0,
                cnn_ma5=48.0,
                ndxe_ndx=0.39,
                ndxe_ma=0.35,
                sox_ndx=0.29,
                sox_ma=0.25,
            )
        )
        self.assertEqual("warm_recovery", result.market_regime)
        self.assertEqual("normal_dca", result.dashboard_action)
        self.assertGreaterEqual(result.recovery_score, 55.0)
        self.assertGreaterEqual(result.inputs["dist_sma"], 0.08)

    def test_recovery_when_repair_is_high_and_gates_pass(self):
        result = self._classify(
            self._row(
                ndx=104.0,
                sma=100.0,
                dist_sma=0.04,
                vxn_pctile=0.45,
                vix_pctile=0.42,
                cnn_fear_greed=58.0,
                cnn_ma5=42.0,
                ndxe_ndx=0.38,
                ndxe_ma=0.35,
                sox_ndx=0.28,
                sox_ma=0.25,
            )
        )
        self.assertEqual("recovery", result.market_regime)
        self.assertEqual("normal_dca", result.dashboard_action)
        self.assertLess(result.temperature_score, 65.0)
        self.assertLess(result.top_risk_score, 55.0)
        self.assertLess(result.overheat_score, 50.0)

    def test_normal_fixture(self):
        result = self._classify(self._row())
        self.assertEqual("normal", result.market_regime)
        self.assertEqual("normal_dca", result.dashboard_action)

    def test_warm_fixture(self):
        result = self._classify(
            self._row(
                ndx=109.0,
                sma=100.0,
                dist_sma=0.09,
                vxn_pctile=0.30,
                vix_pctile=0.28,
                cnn_fear_greed=66.0,
                cnn_ma5=64.0,
                ndxe_ndx=0.35,
                ndxe_ma=0.35,
                sox_ndx=0.25,
                sox_ma=0.25,
            )
        )
        self.assertEqual("warm", result.market_regime)
        self.assertEqual("reduce_light", result.dashboard_action)
        self.assertLess(result.recovery_score, 55.0)

    def test_overheated_fixture(self):
        result = self._classify(
            self._row(
                ndx=118.0,
                sma=100.0,
                dist_sma=0.18,
                vxn_pctile=0.12,
                vix_pctile=0.10,
                cnn_fear_greed=82.0,
                cnn_ma5=80.0,
                ndxe_ndx=0.36,
                ndxe_ma=0.35,
                sox_ndx=0.26,
                sox_ma=0.25,
            )
        )
        self.assertEqual("overheated", result.market_regime)
        self.assertEqual("reduce", result.dashboard_action)

    def test_top_risk_fixture(self):
        result = self._classify(
            self._row(
                ndx=124.0,
                sma=100.0,
                dist_sma=0.24,
                vxn_pctile=0.08,
                vix_pctile=0.06,
                cnn_fear_greed=88.0,
                cnn_ma5=84.0,
                ndxe_ndx=0.32,
                ndxe_ma=0.36,
                sox_ndx=0.21,
                sox_ma=0.25,
            )
        )
        self.assertEqual("top_risk", result.market_regime)
        self.assertEqual("pause", result.dashboard_action)
        self.assertGreaterEqual(result.top_risk_score, 75.0)

    def test_top_risk_watch_between_watch_and_full_threshold(self):
        result = self._classify(
            self._row(
                ndx=118.0,
                sma=100.0,
                dist_sma=0.18,
                vxn_pctile=0.10,
                vix_pctile=0.10,
                cnn_fear_greed=75.0,
                cnn_ma5=72.0,
                ndxe_ndx=0.3528,
                ndxe_ma=0.36,
                sox_ndx=0.245,
                sox_ma=0.25,
            )
        )
        self.assertEqual("top_risk_watch", result.market_regime)
        self.assertEqual("pause_new_buy", result.dashboard_action)
        self.assertGreaterEqual(result.top_risk_score, 70.0)
        self.assertLess(result.top_risk_score, 75.0)


class MarketRegimeSummaryTests(unittest.TestCase):
    def _summary_for_row(self, row, *, config=None):
        frame = pd.DataFrame([row], index=pd.to_datetime(["2026-04-30"]))
        return latest_summary(frame, config=config)

    def _frame(self):
        rows = [
            {
                "ndx": 100.0,
                "sma": 100.0,
                "dist_sma": 0.0,
                "vxn": 20.0,
                "vix": 18.0,
                "vxn_pctile": 0.50,
                "vix_pctile": 0.50,
                "cnn_fear_greed": 50.0,
                "cnn_ma5": 50.0,
                "ndxe_ndx": 0.35,
                "ndxe_ma": 0.35,
                "sox_ndx": 0.25,
                "sox_ma": 0.25,
            },
            {
                "ndx": 118.0,
                "sma": 100.0,
                "dist_sma": 0.18,
                "vxn": 14.0,
                "vix": 12.0,
                "vxn_pctile": 0.12,
                "vix_pctile": 0.10,
                "cnn_fear_greed": 82.0,
                "cnn_ma5": 80.0,
                "ndxe_ndx": 0.36,
                "ndxe_ma": 0.35,
                "sox_ndx": 0.26,
                "sox_ma": 0.25,
            },
        ]
        return pd.DataFrame(rows, index=pd.to_datetime(["2026-04-29", "2026-04-30"]))

    def test_classify_daily_marks_historical_missing_as_unscorable(self):
        frame = self._frame()
        frame.loc[pd.Timestamp("2026-04-29"), "vix"] = float("nan")
        out = classify_daily(frame)
        self.assertEqual("unscorable", out.iloc[0]["market_regime"])
        self.assertEqual("overheated", out.iloc[1]["market_regime"])
        self.assertEqual(0.0, out.iloc[0]["confidence_score"])

    def test_classify_daily_marks_historical_zero_denominator_as_unscorable(self):
        frame = self._frame()
        frame.loc[pd.Timestamp("2026-04-29"), "ndxe_ma"] = 0.0
        out = classify_daily(frame)
        self.assertEqual("unscorable", out.iloc[0]["market_regime"])
        self.assertIn("ndxe_ma", out.iloc[0]["missing_inputs"])
        self.assertEqual("overheated", out.iloc[1]["market_regime"])

    def test_latest_summary_contains_drivers_risks_inputs(self):
        summary = latest_summary(self._frame())
        self.assertEqual("2026-04-30", summary["as_of_date"])
        self.assertEqual("overheated", summary["market_regime"])
        self.assertIn("drivers", summary)
        self.assertIn("risks", summary)
        self.assertIn("inputs", summary)
        self.assertIn("dashboard_action", summary)
        json.dumps(summary, allow_nan=False)

    def test_latest_summary_uses_max_date_for_unsorted_frame(self):
        frame = self._frame()
        frame.index = pd.to_datetime(["2026-05-02", "2026-05-01"])
        summary = latest_summary(frame)
        self.assertEqual("2026-05-02", summary["as_of_date"])

    def test_latest_summary_reports_warm_recovery(self):
        summary = self._summary_for_row(
            {
                "ndx": 110.0,
                "sma": 100.0,
                "dist_sma": 0.10,
                "vxn": 20.0,
                "vix": 18.0,
                "vxn_pctile": 0.40,
                "vix_pctile": 0.38,
                "cnn_fear_greed": 66.0,
                "cnn_ma5": 48.0,
                "ndxe_ndx": 0.39,
                "ndxe_ma": 0.35,
                "sox_ndx": 0.29,
                "sox_ma": 0.25,
            }
        )

        self.assertEqual("warm_recovery", summary["market_regime"])
        self.assertEqual("normal_dca", summary["dashboard_action"])
        self.assertEqual("Repair signals are strong, but conditions are already warm.", summary["summary"])

    def test_latest_summary_reports_top_risk_watch(self):
        summary = self._summary_for_row(
            {
                "ndx": 118.0,
                "sma": 100.0,
                "dist_sma": 0.18,
                "vxn": 20.0,
                "vix": 18.0,
                "vxn_pctile": 0.10,
                "vix_pctile": 0.10,
                "cnn_fear_greed": 75.0,
                "cnn_ma5": 72.0,
                "ndxe_ndx": 0.3528,
                "ndxe_ma": 0.36,
                "sox_ndx": 0.245,
                "sox_ma": 0.25,
            }
        )

        self.assertEqual("top_risk_watch", summary["market_regime"])
        self.assertEqual("pause_new_buy", summary["dashboard_action"])
        self.assertIn("top_risk_watch", summary["risks"])

    def test_latest_summary_risks_use_custom_top_risk_threshold(self):
        summary = self._summary_for_row(
            {
                "ndx": 118.0,
                "sma": 100.0,
                "dist_sma": 0.18,
                "vxn": 20.0,
                "vix": 18.0,
                "vxn_pctile": 0.10,
                "vix_pctile": 0.10,
                "cnn_fear_greed": 75.0,
                "cnn_ma5": 72.0,
                "ndxe_ndx": 0.3528,
                "ndxe_ma": 0.36,
                "sox_ndx": 0.245,
                "sox_ma": 0.25,
            },
            config=DashboardConfig(top_risk_threshold=72.0),
        )

        self.assertEqual("top_risk", summary["market_regime"])
        self.assertIn("top_risk", summary["risks"])
        self.assertNotIn("top_risk_watch", summary["risks"])

    def test_latest_summary_risks_use_custom_overheat_threshold(self):
        summary = self._summary_for_row(
            {
                "ndx": 118.0,
                "sma": 100.0,
                "dist_sma": 0.18,
                "vxn": 20.0,
                "vix": 18.0,
                "vxn_pctile": 0.40,
                "vix_pctile": 0.40,
                "cnn_fear_greed": 76.0,
                "cnn_ma5": 74.0,
                "ndxe_ndx": 0.35,
                "ndxe_ma": 0.35,
                "sox_ndx": 0.25,
                "sox_ma": 0.25,
            },
            config=DashboardConfig(overheat_threshold=50.0),
        )

        self.assertEqual("overheated", summary["market_regime"])
        self.assertIn("overheat", summary["risks"])

    def test_latest_summary_risks_use_stress_low_threshold(self):
        summary = self._summary_for_row(
            {
                "ndx": 90.0,
                "sma": 100.0,
                "dist_sma": -0.10,
                "vxn": 20.0,
                "vix": 18.0,
                "vxn_pctile": 0.80,
                "vix_pctile": 0.78,
                "cnn_fear_greed": 25.0,
                "cnn_ma5": 26.0,
                "ndxe_ndx": 0.35,
                "ndxe_ma": 0.35,
                "sox_ndx": 0.25,
                "sox_ma": 0.25,
            }
        )

        self.assertEqual("stress_low", summary["market_regime"])
        self.assertIn("market_stress", summary["risks"])

    def test_latest_summary_risks_use_custom_low_confidence_threshold(self):
        summary = self._summary_for_row(
            {
                "ndx": 100.0,
                "sma": 100.0,
                "dist_sma": 0.0,
                "vxn": 20.0,
                "vix": 18.0,
                "vxn_pctile": 0.50,
                "vix_pctile": 0.50,
                "cnn_fear_greed": 50.0,
                "cnn_ma5": 50.0,
                "ndxe_ndx": 0.35,
                "ndxe_ma": 0.35,
                "sox_ndx": 0.25,
                "sox_ma": 0.25,
            },
            config=DashboardConfig(low_confidence_threshold=65.0),
        )

        self.assertEqual("normal", summary["market_regime"])
        self.assertIn("low_confidence", summary["risks"])


from tempfile import TemporaryDirectory

from src.market_regime.report import write_dashboard_outputs


class MarketRegimeReportTests(unittest.TestCase):
    def _daily(self):
        return pd.DataFrame(
            [
                {
                    "date": "2026-04-30",
                    "market_regime": "normal",
                    "temperature_score": 50.0,
                    "undervaluation_score": 0.0,
                    "overheat_score": 0.0,
                    "trend_score": 50.0,
                    "volatility_score": 50.0,
                    "sentiment_score": 50.0,
                    "breadth_score": 50.0,
                    "semiconductor_score": 50.0,
                    "top_risk_score": 0.0,
                    "recovery_score": 0.0,
                    "confidence_score": 60.0,
                    "dashboard_action": "normal_dca",
                    "missing_inputs": "",
                    "ndx": 100.0,
                    "sma": 100.0,
                    "dist_sma": 0.0,
                    "vxn": 20.0,
                    "vix": 18.0,
                    "vxn_pctile": 0.5,
                    "vix_pctile": 0.5,
                    "cnn_fear_greed": 50.0,
                    "cnn_ma5": 50.0,
                    "ndxe_ndx": 0.35,
                    "ndxe_ma": 0.35,
                    "sox_ndx": 0.25,
                    "sox_ma": 0.25,
                }
            ]
        )

    def _summary(self):
        return {
            "as_of_date": "2026-04-30",
            "market_regime": "normal",
            "temperature_score": 50.0,
            "confidence_score": 60.0,
            "dashboard_action": "normal_dca",
            "summary": "No dominant extreme signal.",
            "drivers": ["trend", "volatility", "sentiment"],
            "risks": ["no_major_extreme"],
            "inputs": {"ndx": 100.0},
        }

    def test_write_dashboard_outputs_creates_csv_json_html(self):
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            write_dashboard_outputs(output_dir, self._daily(), self._summary())
            self.assertTrue((output_dir / "daily_regimes.csv").exists())
            self.assertTrue((output_dir / "latest.json").exists())
            self.assertTrue((output_dir / "index.html").exists())
            csv_header = (output_dir / "daily_regimes.csv").read_text(encoding="utf-8").splitlines()[0]
            self.assertEqual(OUTPUT_COLUMNS, csv_header.split(","))
            self.assertIn("normal", (output_dir / "index.html").read_text(encoding="utf-8"))

    def test_write_dashboard_outputs_fails_when_daily_missing_output_column(self):
        with TemporaryDirectory() as tmp:
            daily = self._daily().drop(columns=["sox_ma"])
            with self.assertRaisesRegex(ValueError, "sox_ma"):
                write_dashboard_outputs(Path(tmp), daily, self._summary())

    def test_write_dashboard_outputs_fails_when_summary_has_nan(self):
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            summary = self._summary()
            summary["temperature_score"] = float("nan")
            with self.assertRaises(ValueError):
                write_dashboard_outputs(output_dir, self._daily(), summary)
            self.assertEqual([], list(output_dir.iterdir()))
            self.assertFalse((output_dir / "daily_regimes.csv").exists())

    def test_write_dashboard_outputs_escapes_summary_html(self):
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            summary = self._summary()
            summary["market_regime"] = "<script>alert(1)</script>"
            summary["drivers"] = ["<img src=x onerror=alert(1)>"]
            write_dashboard_outputs(output_dir, self._daily(), summary)

            html = (output_dir / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertNotIn("<img src=x onerror=alert(1)>", html)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
            self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)

    def test_write_dashboard_outputs_renders_regime_gauge_and_legend(self):
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            summary = self._summary()
            summary["market_regime"] = "recovery"
            write_dashboard_outputs(output_dir, self._daily(), summary)

            html = (output_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn('class="regime-gauge"', html)
            self.assertIn("Market State Gauge", html)
            for label in [
                "Panic Low",
                "Stress Low",
                "Recovery",
                "Normal",
                "Warm",
                "Overheated",
                "Top Risk",
            ]:
                self.assertIn(label, html)

    def test_write_dashboard_outputs_renders_language_toggle(self):
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            write_dashboard_outputs(output_dir, self._daily(), self._summary())

            html = (output_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn('class="language-toggle"', html)
            self.assertIn('data-language="en"', html)
            self.assertIn('data-language="zh"', html)
            self.assertIn('data-lang="en"', html)
            self.assertIn('data-lang="zh"', html)
            self.assertIn("Market Regime Dashboard", html)
            self.assertIn("市场状态仪表盘", html)
            self.assertIn("市场状态指针", html)


class MarketRegimeWorkflowTests(unittest.TestCase):
    def test_run_workflow_writes_outputs_for_complete_target_date(self):
        from scripts.run_market_regime_dashboard import run_workflow

        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            run_workflow(output_dir=output_dir, target_date="2026-04-30")
            self.assertTrue((output_dir / "daily_regimes.csv").exists())
            self.assertTrue((output_dir / "latest.json").exists())
            self.assertTrue((output_dir / "index.html").exists())
            self.assertIn("market_regime", (output_dir / "latest.json").read_text(encoding="utf-8"))

    def test_run_workflow_fails_fast_for_latest_missing_volatility(self):
        from scripts.run_market_regime_dashboard import run_workflow

        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "2026-05-01.*vix.*vxn"):
                run_workflow(output_dir=Path(tmp), target_date="2026-05-01")
