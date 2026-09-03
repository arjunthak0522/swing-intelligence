import numpy as np
import pandas as pd


def _align_close(frames: dict[str, pd.DataFrame], symbol: str) -> pd.Series:
    if symbol not in frames:
        raise KeyError(f"Missing required symbol: {symbol}")
    return frames[symbol]["close"].sort_index().rename(symbol)


def compute_cross_asset_features(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compute cross-asset confirmation features without using future information.

    Expected symbols when available: SPY, QQQ, RSP, IWM, SMH, VIX.
    Missing optional symbols are skipped rather than fabricated.
    """
    closes = []
    for symbol in ("SPY", "QQQ", "RSP", "IWM", "SMH", "VIX"):
        if symbol in frames:
            closes.append(_align_close(frames, symbol))
    if not closes:
        return pd.DataFrame()
    px = pd.concat(closes, axis=1).sort_index()
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

    return out
