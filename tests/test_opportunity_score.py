import numpy as np
import pandas as pd

from swing_intelligence.opportunity_score import calibrated_opportunity_score


def _frame(n=320):
    idx = pd.bdate_range("2010-01-01", periods=n)
    x = np.linspace(-1.0, 1.0, n)
    return pd.DataFrame({
        "drawdown_252d": -0.15 + 0.10 * x,
        "drawdown_60d": -0.08 + 0.06 * x,
        "vix_percentile_252": np.linspace(0.05, 0.95, n),
        "rsp_spy_ret_20d": np.linspace(-0.08, 0.08, n),
        "iwm_spy_ret_20d": np.linspace(-0.10, 0.10, n),
        "hy_spread_percentile_252": np.linspace(0.02, 0.98, n),
        "rebound_3d": np.linspace(-0.06, 0.06, n),
        "momentum_accel_5v20": np.linspace(-0.05, 0.05, n),
        "trend_repair_5d": np.linspace(-0.04, 0.04, n),
        "vix_cooling_5d": np.linspace(-0.20, 0.20, n),
        "rsp_spy_ret_5d": np.linspace(-0.04, 0.04, n),
        "iwm_spy_ret_5d": np.linspace(-0.05, 0.05, n),
        "hy_spread_cooling_5d": np.linspace(-0.30, 0.30, n),
        "yield_2y_change_5d": np.linspace(0.30, -0.30, n),
        "smh_qqq_ret_20d": np.linspace(-0.12, 0.12, n),
        "smh_qqq_ret_5d": np.linspace(-0.06, 0.06, n),
    }, index=idx)


def test_score_calibration_uses_train_only():
    train = _frame(260)
    future = _frame(60).copy()
    future.index = pd.bdate_range("2020-01-01", periods=60)
    a = calibrated_opportunity_score(train, future, "QQQ")

    mutated_future = future.copy()
    mutated_future.iloc[-1, :] = 999.0
    b = calibrated_opportunity_score(train, mutated_future, "QQQ")

    pd.testing.assert_series_equal(a.iloc[:-1]["opportunity_score"], b.iloc[:-1]["opportunity_score"])


def test_opportunity_requires_damage_and_repair():
    train = _frame(300)
    probe = train.iloc[[-1]].copy()

    # High damage but deliberately terrible repair should not produce a high score.
    for col in ["drawdown_252d", "drawdown_60d", "rsp_spy_ret_20d", "iwm_spy_ret_20d", "smh_qqq_ret_20d"]:
        probe[col] = -10.0
    probe["vix_percentile_252"] = 1.0
    probe["hy_spread_percentile_252"] = 1.0
    for col in ["rebound_3d", "momentum_accel_5v20", "trend_repair_5d", "vix_cooling_5d", "rsp_spy_ret_5d", "iwm_spy_ret_5d", "hy_spread_cooling_5d", "smh_qqq_ret_5d"]:
        probe[col] = -10.0
    probe["yield_2y_change_5d"] = 10.0
    bad_repair = calibrated_opportunity_score(train, probe, "QQQ").iloc[0]

    good = probe.copy()
    for col in ["rebound_3d", "momentum_accel_5v20", "trend_repair_5d", "vix_cooling_5d", "rsp_spy_ret_5d", "iwm_spy_ret_5d", "hy_spread_cooling_5d", "smh_qqq_ret_5d"]:
        good[col] = 10.0
    good["yield_2y_change_5d"] = -10.0
    good_repair = calibrated_opportunity_score(train, good, "QQQ").iloc[0]

    assert bad_repair["damage_score"] > 80
    assert bad_repair["opportunity_score"] < 35
    assert good_repair["opportunity_score"] > 80
