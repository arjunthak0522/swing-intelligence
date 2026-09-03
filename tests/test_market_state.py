import numpy as np
import pandas as pd
from swing_intelligence.market_state import compute_cross_asset_features


def frame(vals):
    idx = pd.date_range("2020-01-01", periods=len(vals), freq="B")
    c = pd.Series(vals, index=idx, dtype=float)
    return pd.DataFrame({"open":c,"high":c*1.01,"low":c*.99,"close":c,"volume":1_000_000}, index=idx)


def test_cross_asset_relative_strength_is_created():
    n=320
    frames={"SPY":frame(np.linspace(100,150,n)), "QQQ":frame(np.linspace(100,180,n)), "VIX":frame(np.linspace(20,18,n))}
    x=compute_cross_asset_features(frames)
    assert "qqq_spy_ret_20d" in x.columns
    assert "vix_percentile_252" in x.columns
    assert x["qqq_spy_ret_20d"].dropna().iloc[-1] > 0
