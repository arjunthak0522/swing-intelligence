import pandas as pd
from swing_intelligence.outcomes import forward_path_stats


def test_mae_mfe_path_math():
    idx=pd.date_range("2024-01-01", periods=5, freq="B")
    df=pd.DataFrame({
        "open":[100]*5,"close":[100,98,102,105,104],
        "high":[101,100,104,106,105],"low":[99,95,97,101,102],"volume":[1]*5
    }, index=idx)
    p=forward_path_stats(df,[idx[0]],3)
    assert round(p.iloc[0]["mae"],4)==-0.05
    assert round(p.iloc[0]["mfe"],4)==0.06
    assert round(p.iloc[0]["forward_return"],4)==0.05
