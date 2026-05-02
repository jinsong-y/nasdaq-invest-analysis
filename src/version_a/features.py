from __future__ import annotations

import pandas as pd


def rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    min_periods = max(3, min(window, 60))

    def pctile(values):
        current = values[-1]
        if pd.isna(current):
            return float("nan")
        valid = pd.Series(values).dropna()
        if valid.empty:
            return float("nan")
        return float((valid <= current).mean())

    return series.rolling(window=window, min_periods=min_periods).apply(pctile, raw=True)


def add_features(
    df: pd.DataFrame,
    *,
    sma_period: int,
    sentiment_lookback_days: int,
    repair_ma_days: int,
) -> pd.DataFrame:
    out = df.copy()
    out["sma"] = out["ndx"].rolling(sma_period, min_periods=min(sma_period, max(3, min(sma_period, 60)))).mean()
    out["dist_sma"] = out["ndx"] / out["sma"] - 1.0
    out["vxn_pctile"] = rolling_percentile(out["vxn"], sentiment_lookback_days)
    out["vix_pctile"] = rolling_percentile(out["vix"], sentiment_lookback_days)
    out["cnn_ma5"] = out["cnn_fear_greed"].rolling(5, min_periods=1).mean()
    out["ndxe_ma"] = out["ndxe_ndx"].rolling(repair_ma_days, min_periods=1).mean()
    out["sox_ma"] = out["sox_ndx"].rolling(repair_ma_days, min_periods=1).mean()
    return out
