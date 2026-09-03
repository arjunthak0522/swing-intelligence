import pandas as pd
from swing_intelligence.tournament import default_candidate_signals


def test_conditioned_signals_are_added_when_cross_asset_features_exist():
    idx = pd.date_range("2024-01-01", periods=300, freq="B")
    f = pd.DataFrame(index=idx)
    f["gap_sma_200"] = 0.05
    f["sma_200"] = range(300)
    f["rsi_14"] = 40
    f["rsi_5"] = 30
    f["zscore_20"] = -0.5
    f["donchian_breakout_up_20"] = 0
    f["return_20d"] = 0.04
    f["return_5d"] = -0.01
    f["atr_pct_rank_252"] = 0.5
    f["vix_shock"] = 0
    f["rsp_spy_ret_20d"] = 0.01
    f["rsp_spy_ret_5d"] = 0.01
    f["qqq_spy_ret_20d"] = 0.03
    f["smh_qqq_ret_20d"] = 0.01
    names = {x.name for x in default_candidate_signals(f)}
    assert {"vix_shock_pullback", "breadth_confirmed_breakout", "breadth_stabilized_pullback", "qqq_leadership_momentum", "semis_leadership_pullback"} <= names
