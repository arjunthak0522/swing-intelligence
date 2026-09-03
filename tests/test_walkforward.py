import pandas as pd
import numpy as np
from swing_intelligence.features import compute_features
from swing_intelligence.walkforward import expanding_windows, walk_forward_signal_table


def test_windows_do_not_overlap_train_and_test():
    idx=pd.bdate_range("2005-01-01","2025-12-31")
    for w in expanding_windows(idx, first_train_end="2012-12-31"):
        assert w.train_end < w.test_start


def test_walkforward_returns_table():
    idx=pd.bdate_range("2005-01-01","2025-12-31")
    rng=np.random.default_rng(2)
    c=100*np.exp(np.cumsum(rng.normal(.0002,.01,len(idx))))
    raw=pd.DataFrame({"open":c,"high":c*1.01,"low":c*.99,"close":c,"volume":1e6}, index=idx)
    f=compute_features(raw)
    t=walk_forward_signal_table(f,horizon=5,min_n=2,first_train_end="2012-12-31")
    assert set(["window","signal","median_excess_edge"]).issubset(t.columns)
