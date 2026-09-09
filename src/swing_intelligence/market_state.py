import numpy as np
import pandas as pd


def _align_close(frames: dict[str, pd.DataFrame], symbol: str) -> pd.Series:
    if symbol not in frames:
        raise KeyError(f"Missing required symbol: {symbol}")
    return frames[symbol]["close"].sort_index().rename(symbol)


def compute_cross_asset_features(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compute causal cross-asset and macro confirmation features.

    Expected symbols when available: SPY, QQQ, RSP, IWM, SMH, VIX plus
    macro context DGS2, DGS10, and HY_SPREAD. Missing optional series are
    skipped rather than fabricated.
    """
    symbols = ("SPY", "QQQ", "RSP", "IWM", "SMH", "VIX", "DGS2", "DGS10", "HY_SPREAD")
    closes = [_align_close(frames, symbol) for symbol in symbols if symbol in frames]
    if not closes:
        return pd.DataFrame()
    px = pd.concat(closes, axis=1).sort_index().ffill()
    out = pd.DataFrame(index=px.index)

    pairs = [
        ("QQQ", "SPY", "qqq_spy"),
        ("RSP", "SPY", "rsp_spy"),
        ("IWM", "SPY", "iwm_spy"),
        ("SMH", "QQQ", "smh_qqq"),
    ]
    for num, den, name in pairs:
        if num in px.columns and den in px.columns:
            ratio = px[num] / px[den]
            out[f"{name}_ratio"] = ratio
            out[f"{name}_ret_5d"] = ratio.pct_change(5)
            out[f"{name}_ret_20d"] = ratio.pct_change(20)
            mean = ratio.rolling(60).mean()
            std = ratio.rolling(60).std(ddof=0)
            out[f"{name}_z_60"] = (ratio - mean) / std.replace(0, np.nan)

    if "VIX" in px.columns:
        vix = px["VIX"]
        out["vix_level"] = vix
        out["vix_change_1d"] = vix.pct_change()
        out["vix_change_5d"] = vix.pct_change(5)
        mean = vix.rolling(60).mean()
        std = vix.rolling(60).std(ddof=0)
        out["vix_z_60"] = (vix - mean) / std.replace(0, np.nan)
        out["vix_percentile_252"] = vix.rolling(252).rank(pct=True)
        out["vix_shock"] = ((out["vix_change_5d"] >= 0.25) | (out["vix_z_60"] >= 1.5)).astype(int)

    if "DGS2" in px.columns:
        y2 = px["DGS2"].astype(float)
        out["yield_2y"] = y2
        out["yield_2y_change_5d"] = y2.diff(5)
        out["yield_2y_change_20d"] = y2.diff(20)
        out["yield_2y_percentile_252"] = y2.rolling(252).rank(pct=True)

    if "DGS10" in px.columns:
        y10 = px["DGS10"].astype(float)
        out["yield_10y"] = y10
        out["yield_10y_change_5d"] = y10.diff(5)
        out["yield_10y_change_20d"] = y10.diff(20)
        out["yield_10y_percentile_252"] = y10.rolling(252).rank(pct=True)

    if "DGS2" in px.columns and "DGS10" in px.columns:
        curve = px["DGS10"].astype(float) - px["DGS2"].astype(float)
        out["yield_curve_10y2y"] = curve
        out["yield_curve_change_20d"] = curve.diff(20)
        out["yield_curve_percentile_252"] = curve.rolling(252).rank(pct=True)

    if "HY_SPREAD" in px.columns:
        spread = px["HY_SPREAD"].astype(float)
        out["hy_spread"] = spread
        out["hy_spread_change_5d"] = spread.diff(5)
        out["hy_spread_change_20d"] = spread.diff(20)
        out["hy_spread_percentile_252"] = spread.rolling(252).rank(pct=True)
        out["hy_spread_cooling_5d"] = -spread.diff(5)

    return out