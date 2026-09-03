import pandas as pd
from swing_intelligence.backtest import backtest_long_only


def test_signal_delay_prevents_same_bar_execution():
    idx = pd.date_range("2024-01-01", periods=5, freq="B")
    close = pd.Series([100, 110, 110, 110, 110], index=idx, dtype=float)
    signal = pd.Series([1, 0, 0, 0, 0], index=idx, dtype=float)
    out = backtest_long_only(close, signal, cost_per_turnover=0, signal_delay=1)
    assert out["returns"].iloc[1] == 0
