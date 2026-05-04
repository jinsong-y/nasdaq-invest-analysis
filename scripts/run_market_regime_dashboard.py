#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market_regime.config import DashboardConfig
from src.market_regime.model import classify_daily, latest_summary
from src.market_regime.report import write_dashboard_outputs
from src.version_a.data import load_market_data
from src.version_a.features import add_features


DATA_PATH = ROOT / "data" / "processed" / "market_indicators.csv"
DEFAULT_OUTPUT = ROOT / "reports" / "market_regime"


def load_recommended_config(path: Path) -> DashboardConfig:
    spec = importlib.util.spec_from_file_location("recommended_market_regime_config", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load recommended config: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "recommended_config"):
        raise ValueError(f"recommended config module missing recommended_config(): {path}")
    config = module.recommended_config()
    if not isinstance(config, DashboardConfig):
        raise ValueError(f"recommended_config() must return DashboardConfig: {path}")
    return config


def load_recommendation_metadata(path: Path) -> dict[str, Any]:
    recommendation_path = path.parent / "recommendation.json"
    recommendation = json.loads(recommendation_path.read_text(encoding="utf-8"))
    return {
        "config_source": "recommended robustness config",
        "recommendation_generated_at": recommendation["generated_at"],
        "robustness_report_path": str(path.parent / "index.html"),
    }


def run_workflow(
    output_dir: Path = DEFAULT_OUTPUT,
    *,
    data_path: Path = DATA_PATH,
    target_date: str | None = None,
    config: DashboardConfig | None = None,
    config_metadata: dict[str, Any] | None = None,
) -> None:
    config = config or DashboardConfig()
    raw = load_market_data(data_path)
    featured = add_features(
        raw,
        sma_period=config.sma_period,
        sentiment_lookback_days=config.sentiment_lookback_days,
        repair_ma_days=config.repair_ma_days,
    )
    if target_date is not None:
        target = pd.Timestamp(target_date)
        if target not in featured.index:
            raise ValueError(f"target date not found in market data: {target_date}")
        featured_for_summary = featured.loc[:target]
    else:
        featured_for_summary = featured
    daily = classify_daily(featured_for_summary, config=config)
    summary = latest_summary(featured_for_summary, config=config)
    if config_metadata is not None:
        summary["config_metadata"] = config_metadata
    write_dashboard_outputs(output_dir, daily, summary)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--data-path", type=Path, default=DATA_PATH)
    parser.add_argument("--target-date")
    parser.add_argument("--recommended-config-path", type=Path)
    args = parser.parse_args()
    config = None
    config_metadata = None
    if args.recommended_config_path is not None:
        config = load_recommended_config(args.recommended_config_path)
        config_metadata = load_recommendation_metadata(args.recommended_config_path)
    run_workflow(
        output_dir=args.output_dir,
        data_path=args.data_path,
        target_date=args.target_date,
        config=config,
        config_metadata=config_metadata,
    )
    print(f"Wrote market regime dashboard to {args.output_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
