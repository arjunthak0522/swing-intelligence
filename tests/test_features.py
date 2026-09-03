import numpy as np
import pandas as pd
from swing_intelligence.features import compute_features


def sample(n=320):
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    c = pd.Series(np.linspace(100, 150, n) + np.sin(np.arange(n)/8), index=idx)
    return pd.DataFrame({"open":c*.999,"high":c*1.01,"low":c*.99,"close":c,"volume":1_000_000}, index=idx)


def test_feature_columns_exist():
    f = compute_features(sample())
    for col in ["rsi_14","gap_sma_200","zscore_20","atr_pct_rank_252","donchian_breakout_up_20"]:
        assert col in f.columns


def test_no_future_dependency_for_past_rows():
    df = sample()
    a = compute_features(df.iloc[:300])
    b = compute_features(df)
    cols = ["return_20d","rsi_14","sma_200","zscore_20"]
    pd.testing.assert_frame_equal(a[cols], b.loc[a.index, cols])
