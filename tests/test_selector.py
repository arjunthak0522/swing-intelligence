import numpy as np
import pandas as pd

from swing_intelligence.selector import SelectionGate, choose_asset_by_evidence, backtest_asset_selector


def test_selector_chooses_best_supported_asset_and_cash():
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    ev = pd.DataFrame([
        [dates[0], "SPY", 50, .004, .03, True, True, -.02],
        [dates[0], "QQQ", 60, .009, .04, True, True, -.03],
        [dates[1], "SPY", 50, -.001, .02, True, True, -.01],
        [dates[1], "QQQ", 50, .006, .03, False, True, -.02],
    ], columns=["date", "asset", "n", "ci_low", "win_edge", "passes_fdr", "stable", "median_mae"])
    pick = choose_asset_by_evidence(ev)
    assert pick.loc[dates[0]] == "QQQ"
    assert pick.loc[dates[1]] == "CASH"


def test_selector_backtest_delays_decision():
    idx = pd.date_range("2024-01-01", periods=8, freq="B")
    spy = pd.Series([100, 101, 102, 103, 104, 105, 106, 107], index=idx)
    qqq = pd.Series([100, 100, 110, 110, 110, 110, 110, 110], index=idx)
    prices = pd.DataFrame({"SPY": spy, "QQQ": qqq})
    selected = pd.Series("CASH", index=idx)
    selected.iloc[1:] = "QQQ"
    out = backtest_asset_selector(prices, selected, cost_per_turnover=0, decision_delay=1)
    assert out["returns"].iloc[2] == 0
    assert set(out["implemented_asset"].unique()) <= {"CASH", "QQQ"}
