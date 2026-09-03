import numpy as np
import pandas as pd
from .outcomes import forward_path_stats, summarize_forward_paths

DEFAULT_FEATURES = [
    "return_5d", "return_10d", "return_20d",
    "gap_sma_20", "gap_sma_50", "gap_sma_200",
    "sma20_slope_5d", "rsi_5", "rsi_14", "zscore_20",
    "drawdown_5d", "realized_vol_10", "realized_vol_20",
    "downside_vol_20", "atr_pct_rank_252", "volume_z_20",
]


def historical_analogs(features: pd.DataFrame, asof=None, k: int = 100,
                       horizons=(3, 5, 10, 20), feature_cols=None) -> dict:
    """Find nearest prior historical states using robust standardized distance.

    All analog candidates precede `asof`; only completed future paths are evaluated.
    """
    feature_cols = feature_cols or DEFAULT_FEATURES
    x = features.copy()
    if asof is None:
        asof = x.index[-1]
    x = x.loc[:asof]
    current = x.loc[asof, feature_cols]

    hist = x.loc[x.index < asof, feature_cols].copy()
    med = hist.median()
    mad = (hist - med).abs().median().replace(0, np.nan)
    z_hist = (hist - med) / (1.4826 * mad)
    z_cur = (current - med) / (1.4826 * mad)
    valid = z_hist.notna().all(axis=1) & z_cur.notna().all()
    z_hist = z_hist.loc[valid]
    dist = np.sqrt(((z_hist - z_cur) ** 2).mean(axis=1)).sort_values()
    chosen = dist.head(k).index

    stats = {}
    for h in horizons:
        vals = forward_path_stats(features, chosen, h)
        unconditional = forward_path_stats(features.loc[:asof], features.loc[:asof].index, h)
        cs = summarize_forward_paths(vals)
        bs = summarize_forward_paths(unconditional)
        if cs.get("n", 0) == 0:
            continue
        stats[h] = {
            **cs,
            "normal_median_return": bs["median_return"],
            "normal_win_probability": bs["win_probability"],
            "median_excess_edge": float(cs["median_return"] - bs["median_return"]),
            "win_probability_edge": float(cs["win_probability"] - bs["win_probability"]),
        }

    return {
        "asof": asof,
        "analog_count_requested": k,
        "analog_dates": list(chosen),
        "distances": dist.head(k),
        "horizons": stats,
    }
