from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import BASE_DAILY_BUDGET, MAX_BUY_DAILY_BUDGET, BacktestParams


STATE_NORMAL = 0
STATE_LIGHT_BUY = 1
STATE_STANDARD_BUY = 2
STATE_DEEP_BUY = 3
STATE_SLOWDOWN = 4
STATE_PAUSE = 5

STATE_NAMES = {
    STATE_NORMAL: "normal",
    STATE_LIGHT_BUY: "light_buy",
    STATE_STANDARD_BUY: "standard_buy",
    STATE_DEEP_BUY: "deep_buy",
    STATE_SLOWDOWN: "slowdown",
    STATE_PAUSE: "pause",
}


@dataclass
class BacktestResult:
    run_id: str
    params: BacktestParams
    daily: pd.DataFrame
    triggers: pd.DataFrame


def _safe_array(df: pd.DataFrame, column: str) -> np.ndarray:
    return pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float)


def _prev(values: np.ndarray) -> np.ndarray:
    out = np.empty_like(values)
    out[0] = np.nan
    out[1:] = values[:-1]
    return out


def _rolling_high(values: np.ndarray, window: int) -> np.ndarray:
    series = pd.Series(values)
    return series.rolling(window, min_periods=1).max().to_numpy(dtype=float)


def _score_arrays(df: pd.DataFrame, params: BacktestParams) -> tuple[np.ndarray, np.ndarray]:
    ndx = _safe_array(df, "ndx")
    sma = _safe_array(df, "sma")
    vxn = _safe_array(df, "vxn")
    vix = _safe_array(df, "vix")
    vxn_pctile = _safe_array(df, "vxn_pctile")
    vix_pctile = _safe_array(df, "vix_pctile")
    cnn = _safe_array(df, "cnn_fear_greed")
    cnn_ma5 = _safe_array(df, "cnn_ma5")
    ndxe_ndx = _safe_array(df, "ndxe_ndx")
    sox_ndx = _safe_array(df, "sox_ndx")
    ndxe_ma = _safe_array(df, "ndxe_ma")
    sox_ma = _safe_array(df, "sox_ma")

    vxn_prev = _prev(vxn)
    vix_prev = _prev(vix)
    cnn_ma5_prev = _prev(cnn_ma5)
    ndxe_prev = _prev(ndxe_ndx)
    sox_prev = _prev(sox_ndx)
    high = _rolling_high(ndx, max(5, params.divergence_weeks * 5))

    buy = np.zeros(len(df), dtype=np.int16)
    sell = np.zeros(len(df), dtype=np.int16)

    vol_panic = (vxn_pctile >= params.vol_high_pctile) | (vix_pctile >= params.vol_high_pctile)
    vol_turn = (vxn < vxn_prev) | (vix < vix_prev)
    buy += np.where(vol_panic, 15, 0)
    buy += np.where(vol_turn, 15, 0)

    if params.strategy_family == "v2_full":
        buy += np.where(cnn <= params.cnn_fear_threshold, 15, 0)
        buy += np.where(cnn_ma5 > cnn_ma5_prev, 15, 0)
        sell += np.where(cnn >= params.cnn_greed_threshold, 20, 0)
        sell += np.where(cnn_ma5 < cnn_ma5_prev, 10, 0)

    buy += np.where(ndxe_ndx > ndxe_ma, 15, 0)
    buy += np.where(sox_ndx > sox_ma, 15, 0)
    buy += np.where(ndx > (1 - params.sma_buffer_pct) * sma, 10, 0)

    sell += np.where(ndx > params.overheat_ratio * sma, 25, 0)
    sell += np.where((vxn_pctile <= 0.2) | (vix_pctile <= 0.2), 15, 0)
    ndx_high = ndx >= high
    sell += np.where(ndx_high & (ndxe_ndx < ndxe_prev), 15, 0)
    sell += np.where(ndx_high & (sox_ndx < sox_prev), 15, 0)

    return np.minimum(buy, 100), np.minimum(sell, 100)


def _desired_state(buy_score: int, sell_score: int, params: BacktestParams) -> tuple[int, int]:
    if sell_score > 60:
        return STATE_PAUSE, params.pause_window_days
    if sell_score >= 40:
        return STATE_SLOWDOWN, params.pause_window_days
    if buy_score > 75:
        return STATE_DEEP_BUY, params.deep_buy_window_days
    if buy_score >= 60:
        return STATE_STANDARD_BUY, params.standard_buy_window_days
    if buy_score >= 40:
        return STATE_LIGHT_BUY, 5
    return STATE_NORMAL, 1


def run_backtest(
    df: pd.DataFrame,
    params: BacktestParams,
    *,
    run_id: str,
    price_column: str = "ndx",
) -> BacktestResult:
    if df.empty:
        raise ValueError("cannot backtest an empty frame")

    work = df.dropna(subset=[price_column, "ndx"]).copy()
    dates = list(work.index)
    prices = _safe_array(work, price_column)
    buy_scores, sell_scores = _score_arrays(work, params)

    scheduled_state = np.full(len(work), -1, dtype=np.int16)
    scheduled_days = np.zeros(len(work), dtype=np.int16)
    scheduled_buy = np.zeros(len(work), dtype=np.int16)
    scheduled_sell = np.zeros(len(work), dtype=np.int16)

    for idx in range(len(work)):
        state, days = _desired_state(int(buy_scores[idx]), int(sell_scores[idx]), params)
        execution_idx = idx + params.lag_days
        if execution_idx < len(work):
            scheduled_state[execution_idx] = state
            scheduled_days[execution_idx] = days
            scheduled_buy[execution_idx] = buy_scores[idx]
            scheduled_sell[execution_idx] = sell_scores[idx]

    state = STATE_NORMAL
    state_days_left = 0
    cash = 0.0
    shares = 0.0
    invested = np.zeros(len(work), dtype=float)
    cash_series = np.zeros(len(work), dtype=float)
    shares_series = np.zeros(len(work), dtype=float)
    value_series = np.zeros(len(work), dtype=float)
    state_series: list[str] = []
    trigger_records = []

    for idx, price in enumerate(prices):
        if state_days_left <= 0 and scheduled_state[idx] >= 0:
            state = int(scheduled_state[idx])
            state_days_left = int(scheduled_days[idx])
            trigger_records.append(
                {
                    "date": dates[idx],
                    "state": STATE_NAMES[state],
                    "buy_score": int(scheduled_buy[idx]),
                    "sell_score": int(scheduled_sell[idx]),
                }
            )

        cash += BASE_DAILY_BUDGET
        if state == STATE_PAUSE:
            invest = 0.0
        elif state == STATE_SLOWDOWN:
            invest = min(cash, BASE_DAILY_BUDGET / 2)
        elif state in {STATE_LIGHT_BUY, STATE_STANDARD_BUY, STATE_DEEP_BUY}:
            invest = min(cash, MAX_BUY_DAILY_BUDGET)
        else:
            invest = min(cash, BASE_DAILY_BUDGET)

        shares += invest / price if price > 0 else 0.0
        cash -= invest
        invested[idx] = invest
        cash_series[idx] = cash
        shares_series[idx] = shares
        value_series[idx] = shares * price + cash
        state_series.append(STATE_NAMES[state])
        state_days_left -= 1

    daily = pd.DataFrame(
        {
            "price": prices,
            "state": state_series,
            "buy_score": buy_scores,
            "sell_score": sell_scores,
            "invested": invested,
            "cash": cash_series,
            "shares": shares_series,
            "portfolio_value": value_series,
        },
        index=pd.Index(dates, name="date"),
    )
    triggers = pd.DataFrame(trigger_records)
    return BacktestResult(run_id=run_id, params=params, daily=daily, triggers=triggers)


def run_mechanical_baseline(df: pd.DataFrame, *, run_id: str, price_column: str = "ndx") -> BacktestResult:
    params = BacktestParams(200, 0.05, 1.2, 0.8, 25, 75, 756, 20, 2, 0, 10, 20, 15, "baseline", "baseline")
    work = df.dropna(subset=[price_column]).copy()
    prices = _safe_array(work, price_column)
    shares = np.cumsum(np.where(prices > 0, BASE_DAILY_BUDGET / prices, 0.0))
    invested = np.full(len(work), BASE_DAILY_BUDGET, dtype=float)
    daily = pd.DataFrame(
        {
            "price": prices,
            "state": ["baseline"] * len(work),
            "buy_score": np.zeros(len(work), dtype=int),
            "sell_score": np.zeros(len(work), dtype=int),
            "invested": invested,
            "cash": np.zeros(len(work), dtype=float),
            "shares": shares,
            "portfolio_value": shares * prices,
        },
        index=pd.Index(work.index, name="date"),
    )
    return BacktestResult(run_id=run_id, params=params, daily=daily, triggers=pd.DataFrame())
