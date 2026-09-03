import numpy as np
import pandas as pd
from swing_intelligence.features import compute_features
from swing_intelligence.regimes import classify_regime, REGIMES


def test_regime_labels_are_known():
    idx=pd.date_range("2018-01-01",periods=500,freq="B")
    c=pd.Series(np.linspace(100,200,500)+np.sin(np.arange(500)/10),index=idx)
    df=pd.DataFrame({"open":c,"high":c*1.01,"low":c*.99,"close":c,"volume":1_000_000},index=idx)
    labels=classify_regime(compute_features(df)).dropna()
    assert set(labels.unique()).issubset(set(REGIMES))
