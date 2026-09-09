import numpy as np
import pandas as pd

from swing_intelligence.market_state_hypotheses import (
    add_market_state_features,
    learn_market_state_hypotheses,
)


def _feature_frame():
    idx = pd.bdate_range("2000-01-03", "2024-12-31")
    n = len(idx)
    close = 100 * np.exp(np.linspace(0, 1.1, n) + 0.03 * np.sin(np.linspace(0, 80, n)))
    df = pd.DataFrame(index=idx)
    df["close"] = close
    df["return_5d"] = pd.Series(close, index=idx).pct_change(5)
    df["return_20d"] = pd.Series(close, index=idx).pct_change(20)
    df["gap_sma_20"] = pd.Series(close, index=idx) / pd.Series(close, index=idx).rolling(20).mean() - 1
    df["realized_vol_10"] = df["return_5d"].rolling(10).std()
    df["realized_vol_20"] = df["return_5d"].rolling(20).std()
    df["vix_percentile_252"] = (np.sin(np.linspace(0, 50, n)) + 1) / 2
    df["vix_change_5d"] = 0.1 * np.sin(np.linspace(0, 70, n))
    df["rsp_spy_ret_20d"] = 0.02 * np.sin(np.linspace(0, 40, n))
    df["rsp_spy_ret_5d"] = 0.01 * np.cos(np.linspace(0, 45, n))
    df["smh_qqq_ret_20d"] = 0.03 * np.cos(np.linspace(0, 35, n))
    df["smh_qqq_ret_5d"] = 0.015 * np.sin(np.linspace(0, 55, n))
    return add_market_state_features(df)


def test_market_state_features_are_backward_looking():
    df = _feature_frame()
    cutoff = pd.Timestamp("2018-12-31")
    before = df.loc[:cutoff, ["drawdown_252d", "momentum_accel_5v20", "trend_repair_5d"]].copy()

    mutated = _feature_frame()
    mutated.loc[mutated.index > cutoff, "close"] *= 10
    mutated = add_market_state_features(mutated.drop(columns=[
        "return_3d", "drawdown_20d", "drawdown_60d", "drawdown_252d", "rebound_3d",
        "momentum_accel_5v20", "vol_expansion_ratio", "trend_repair_5d", "abs_gap_sma_20", "vix_cooling_5d"
    ], errors="ignore"))

    pd.testing.assert_frame_equal(
        before,
        mutated.loc[:cutoff, before.columns],
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )


def test_semantic_thresholds_use_train_data_only():
    df = _feature_frame()
    train = df.loc[:"2016-12-31"].copy()
    rules_before = learn_market_state_hypotheses(train, "SPY")
    sig_before = [(r.name, [(t.feature, t.op, t.threshold) for t in r.terms]) for r in rules_before]

    full = df.copy()
    full.loc[full.index > pd.Timestamp("2016-12-31"), "vix_percentile_252"] = 999
    rules_after = learn_market_state_hypotheses(full.loc[:"2016-12-31"], "SPY")
    sig_after = [(r.name, [(t.feature, t.op, t.threshold) for t in r.terms]) for r in rules_after]

    assert sig_before == sig_after


def test_target_specific_market_state_hypotheses():
    train = _feature_frame().loc[:"2016-12-31"]
    spy_names = {r.name for r in learn_market_state_hypotheses(train, "SPY")}
    qqq_names = {r.name for r in learn_market_state_hypotheses(train, "QQQ")}

    assert "spy_pullback_breadth_resilience" in spy_names
    assert "spy_rebound_with_breadth_confirmation" in spy_names
    assert "qqq_pullback_semiconductor_resilience" in qqq_names
    assert "qqq_rebound_with_semiconductor_confirmation" in qqq_names
    assert not any(name.startswith("qqq_") for name in spy_names)
    assert not any(name.startswith("spy_") for name in qqq_names)
