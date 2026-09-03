import numpy as np
import pandas as pd


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute transparent daily swing features from OHLCV.

    Expected columns: open, high, low, close, volume.
    No future data is used.
    """
    out = df.copy().sort_index()
    c = out["close"]
    r = c.pct_change()

    for n in (5, 10, 20):
        out[f"return_{n}d"] = c.pct_change(n)

    for n in (20, 50, 200):
        sma = c.rolling(n).mean()
        out[f"sma_{n}"] = sma
        out[f"gap_sma_{n}"] = c / sma - 1

    out["sma20_slope_5d"] = out["sma_20"].pct_change(5)
    out["rsi_5"] = _rsi(c, 5)
    out["rsi_14"] = _rsi(c, 14)

    mean20 = c.rolling(20).mean()
    std20 = c.rolling(20).std(ddof=0)
    out["zscore_20"] = (c - mean20) / std20.replace(0, np.nan)

    rolling_high_5 = c.rolling(5).max()
    out["drawdown_5d"] = c / rolling_high_5 - 1

    out["realized_vol_10"] = r.rolling(10).std(ddof=0) * np.sqrt(252)
    out["realized_vol_20"] = r.rolling(20).std(ddof=0) * np.sqrt(252)
    downside = r.where(r < 0)
    out["downside_vol_20"] = downside.rolling(20).std(ddof=0) * np.sqrt(252)

    out["atr_14"] = _atr(out, 14)
    out["atr_pct"] = out["atr_14"] / c
    out["atr_pct_rank_252"] = out["atr_pct"].rolling(252).rank(pct=True)

    v_mean = out["volume"].rolling(20).mean()
    v_std = out["volume"].rolling(20).std(ddof=0)
    out["volume_z_20"] = (out["volume"] - v_mean) / v_std.replace(0, np.nan)

    prev20_high = out["high"].rolling(20).max().shift(1)
    prev20_low = out["low"].rolling(20).min().shift(1)
    out["donchian_breakout_up_20"] = (out["close"] > prev20_high).astype(int)
    out["donchian_breakdown_20"] = (out["close"] < prev20_low).astype(int)
    return out
