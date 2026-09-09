import pandas as pd

from swing_intelligence.qqq_family_robustness import QQQFamilyConfig, run_qqq_family_robustness


def _frame():
    idx = pd.bdate_range("2000-01-03", "2015-12-31")
    close = pd.Series(range(100, 100 + len(idx)), index=idx, dtype=float)
    ret = close.pct_change()
    df = pd.DataFrame({
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": 1000,
        "return_5d": close.pct_change(5),
        "return_20d": close.pct_change(20),
        "realized_vol_10": ret.rolling(10).std(),
        "realized_vol_20": ret.rolling(20).std(),
        "gap_sma_20": close / close.rolling(20).mean() - 1,
        "gap_sma_50": close / close.rolling(50).mean() - 1,
        "gap_sma_200": close / close.rolling(200).mean() - 1,
        "sma20_slope_5d": close.rolling(20).mean().pct_change(5),
        "rsi_14": 55.0,
        "zscore_20": 0.0,
        "atr_pct_rank_252": 0.5,
        "downside_vol_20": ret.rolling(20).std(),
        "drawdown_60d": close / close.rolling(60).max() - 1,
        "drawdown_252d": close / close.rolling(252).max() - 1,
        "rebound_3d": close.pct_change(3),
        "momentum_accel_5v20": close.pct_change(5) - close.pct_change(20) / 4,
        "vol_expansion_ratio": ret.rolling(10).std() / ret.rolling(20).std(),
        "trend_repair_5d": (close / close.rolling(20).mean() - 1).diff(5),
        "abs_gap_sma_20": (close / close.rolling(20).mean() - 1).abs(),
        "vix_percentile_252": pd.Series(range(len(idx)), index=idx).rolling(252).rank(pct=True),
        "vix_change_5d": pd.Series(range(len(idx)), index=idx).pct_change(5),
        "vix_cooling_5d": -pd.Series(range(len(idx)), index=idx).pct_change(5),
        "smh_qqq_ret_5d": close.pct_change(5) * 0.5,
        "smh_qqq_ret_20d": close.pct_change(20) * 0.5,
        "rsp_spy_ret_5d": 0.0,
        "rsp_spy_ret_20d": 0.0,
    }, index=idx)
    return df


def test_phase3b_future_mutation_does_not_change_earlier_fold():
    df = _frame()
    cfg = QQQFamilyConfig(first_test_year=2010, fold_years=2, horizons=(20,), min_gaps=(20,), cost_bps=(2.0,), vix_cooling_quantiles=(0.5,))
    before = run_qqq_family_robustness(df, cfg)
    mutated = df.copy()
    mutated.loc[mutated.index >= pd.Timestamp("2014-01-01"), "close"] *= 100
    after = run_qqq_family_robustness(mutated, cfg)
    if before["rows"] and after["rows"]:
        assert before["rows"][0]["folds"][:2] == after["rows"][0]["folds"][:2]


def test_phase3b_reports_family_level_gate():
    result = run_qqq_family_robustness(_frame(), QQQFamilyConfig(first_test_year=2010, fold_years=2, horizons=(20,), min_gaps=(20,), cost_bps=(2.0,), vix_cooling_quantiles=(0.5,)))
    assert "family_robust" in result
    assert "passing_variant_fraction" in result
