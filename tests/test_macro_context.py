import numpy as np
import pandas as pd

from swing_intelligence.market_state import compute_cross_asset_features
from swing_intelligence.walk_forward import _matched_random_percentile


def _frame(values, index):
    s = pd.Series(values, index=index, dtype=float)
    return pd.DataFrame({"open": s, "high": s, "low": s, "close": s, "volume": 0.0}, index=index)


def test_macro_features_are_backward_looking_only():
    idx = pd.bdate_range("2020-01-01", periods=320)
    frames = {
        "DGS2": _frame(np.linspace(1.0, 3.0, len(idx)), idx),
        "DGS10": _frame(np.linspace(2.0, 4.0, len(idx)), idx),
        "HY_SPREAD": _frame(np.linspace(5.0, 3.0, len(idx)), idx),
    }
    before = compute_cross_asset_features(frames)
    mutated = {k: v.copy() for k, v in frames.items()}
    cutoff = idx[250]
    for frame in mutated.values():
        frame.loc[frame.index > cutoff, "close"] *= 10
    after = compute_cross_asset_features(mutated)
    cols = [
        "yield_2y_change_20d", "yield_10y_change_20d", "yield_curve_change_20d",
        "hy_spread_change_20d", "hy_spread_cooling_5d",
    ]
    pd.testing.assert_frame_equal(before.loc[:cutoff, cols], after.loc[:cutoff, cols])


def test_matched_random_percentile_is_deterministic_and_rewards_strong_entries():
    idx = pd.bdate_range("2020-01-01", periods=300)
    baseline = pd.Series(np.linspace(-0.04, 0.08, len(idx)), index=idx)
    strong = _matched_random_percentile(baseline, n=5, observed_median=0.075, gap=30, iterations=300, seed=42)
    repeat = _matched_random_percentile(baseline, n=5, observed_median=0.075, gap=30, iterations=300, seed=42)
    ordinary = _matched_random_percentile(baseline, n=5, observed_median=0.01, gap=30, iterations=300, seed=42)
    assert strong == repeat
    assert strong is not None and strong > 0.90
    assert ordinary is not None and ordinary < strong
