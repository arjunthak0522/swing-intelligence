import pandas as pd

REGIMES = (
    "bull_trend", "bull_pullback", "range_chop", "volatility_shock",
    "bear_rally", "bear_trend", "transition"
)


def classify_regime(features: pd.DataFrame) -> pd.Series:
    """Transparent baseline regime classifier.

    This is deliberately simple and auditable. It is a baseline to beat, not an
    assertion that rule-based classification is optimal.
    """
    f = features
    regime = pd.Series("transition", index=f.index, dtype="object")

    above200 = f["gap_sma_200"] > 0
    above50 = f["gap_sma_50"] > 0
    slope_up = f["sma20_slope_5d"] > 0
    oversold = (f["rsi_14"] < 40) | (f["zscore_20"] < -1)
    overbought = (f["rsi_14"] > 60) | (f["zscore_20"] > 1)
    high_vol = f["atr_pct_rank_252"] >= 0.80
    low_mom = f["return_20d"] < 0
    strong_mom = f["return_20d"] > 0.03

    regime.loc[above200 & above50 & slope_up & strong_mom & ~oversold] = "bull_trend"
    regime.loc[above200 & oversold & ~high_vol] = "bull_pullback"
    regime.loc[~above200 & overbought & low_mom] = "bear_rally"
    regime.loc[~above200 & ~above50 & ~slope_up & low_mom] = "bear_trend"
    regime.loc[high_vol & ((f["return_5d"] < -0.03) | (f["downside_vol_20"] > f["realized_vol_20"]))] = "volatility_shock"

    chop = (
        (f["gap_sma_50"].abs() < 0.025)
        & (f["return_20d"].abs() < 0.04)
        & ~high_vol
    )
    regime.loc[chop] = "range_chop"
    return regime
