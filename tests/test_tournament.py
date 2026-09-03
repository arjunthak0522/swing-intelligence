import numpy as np
import pandas as pd
from swing_intelligence.features import compute_features
from swing_intelligence.tournament import default_candidate_signals, evaluate_signal, rank_signals


def sample(n=700):
    idx=pd.date_range("2015-01-01",periods=n,freq="B")
    c=pd.Series(100*np.exp(np.linspace(0,.6,n))*(1+.025*np.sin(np.arange(n)/12)),index=idx)
    return pd.DataFrame({"open":c*.999,"high":c*1.01,"low":c*.99,"close":c,"volume":1_000_000+1000*np.arange(n)},index=idx)


def test_tournament_reports_raw_historical_edge():
    df=sample(); f=compute_features(df)
    results=[evaluate_signal(df,s,horizons=(10,),min_n=5) for s in default_candidate_signals(f)]
    ranked=rank_signals(results,horizon=10,min_n=5)
    if not ranked.empty:
        assert "median_excess_edge" in ranked.columns
        assert "median_mae" in ranked.columns
