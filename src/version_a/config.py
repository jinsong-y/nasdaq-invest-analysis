from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
from typing import Iterable


BASELINE_START = "2000-01-03"
MAIN_START = "2011-01-03"
BASE_DAILY_BUDGET = 100.0
MAX_BUY_DAILY_BUDGET = 200.0

SEGMENTS = {
    "diagnostic_2000_2010": ("2000-01-03", "2010-12-31"),
    "main_2011_2019": ("2011-01-03", "2019-12-31"),
    "shock_2020": ("2020-01-01", "2020-12-31"),
    "bear_2022": ("2022-01-01", "2022-12-31"),
    "recent_2023_present": ("2023-01-01", None),
}


@dataclass(frozen=True)
class BacktestParams:
    sma_period: int
    sma_buffer_pct: float
    overheat_ratio: float
    vol_high_pctile: float
    cnn_fear_threshold: int
    cnn_greed_threshold: int
    sentiment_lookback_days: int
    repair_ma_days: int
    divergence_weeks: int
    lag_days: int
    standard_buy_window_days: int
    deep_buy_window_days: int
    pause_window_days: int
    strategy_family: str = "v2_full"
    stage: str = "coarse"

    def to_dict(self) -> dict:
        return asdict(self)

    def stable_key(self) -> str:
        values = [
            self.strategy_family,
            self.stage,
            self.sma_period,
            self.sma_buffer_pct,
            self.overheat_ratio,
            self.vol_high_pctile,
            self.cnn_fear_threshold,
            self.cnn_greed_threshold,
            self.sentiment_lookback_days,
            self.repair_ma_days,
            self.divergence_weeks,
            self.lag_days,
            self.standard_buy_window_days,
            self.deep_buy_window_days,
            self.pause_window_days,
        ]
        return "_".join(str(value).replace(".", "p") for value in values)


def coarse_grid() -> Iterable[BacktestParams]:
    for values in product(
        [180, 200, 220],
        [0.03, 0.05, 0.07],
        [1.15, 1.20, 1.25],
        [0.75, 0.80, 0.85, 0.90],
        [20, 25, 30],
        [70, 75, 80],
        [504, 756, 1260],
        [10, 20, 50],
    ):
        yield BacktestParams(
            sma_period=values[0],
            sma_buffer_pct=values[1],
            overheat_ratio=values[2],
            vol_high_pctile=values[3],
            cnn_fear_threshold=values[4],
            cnn_greed_threshold=values[5],
            sentiment_lookback_days=values[6],
            repair_ma_days=values[7],
            divergence_weeks=2,
            lag_days=2,
            standard_buy_window_days=10,
            deep_buy_window_days=20,
            pause_window_days=15,
        )
