import pandas as pd
from swing_intelligence.phase2 import backtest_fixed_horizon_selector


def test_fixed_horizon_selector_cannot_capture_pre_entry_jump():
    idx = pd.date_range("2024-01-01", periods=8, freq="B")
    prices = pd.DataFrame({
        "SPY": [100, 100, 100, 100, 100, 100, 100, 100],
        "QQQ": [100, 110, 110, 121, 121, 121, 121, 121],
    }, index=idx, dtype=float)
    decisions = pd.DataFrame([{"date": idx[0], "asset": "QQQ"}])
    out = backtest_fixed_horizon_selector(prices, decisions, horizon=2, cost_per_turnover=0)
    # Decision at close day 0 enters at close day 1, so the day0-to-day1 +10% jump is impossible to earn.
    assert out["returns"].iloc[1] == 0
    # The position is held over day1-to-day2 and day2-to-day3 intervals; only the latter moves here.
    assert out["returns"].iloc[3] > 0
