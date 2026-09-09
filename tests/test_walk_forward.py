import pandas as pd

from swing_intelligence.walk_forward import WalkForwardConfig, _event_positions, run_semantic_walk_forward


def test_event_positions_enforce_gap():
    s = pd.Series([True, True, False, True, False, False, True])
    assert _event_positions(s, 3) == [0, 3, 6]


def test_walk_forward_uses_only_prior_data_for_thresholds():
    idx = pd.bdate_range("2000-01-03", "2013-12-31")
    close = pd.Series(range(100, 100 + len(idx)), index=idx, dtype=float)
    df = pd.DataFrame({
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": 1000,
        "return_5d": close.pct_change(5),
        "return_20d": close.pct_change(20),
        "realized_vol_10": close.pct_change().rolling(10).std(),
        "realized_vol_20": close.pct_change().rolling(20).std(),
        "gap_sma_20": close / close.rolling(20).mean() - 1,
        "vix_percentile_252": 0.5,
        "vix_change_5d": 0.0,
    }, index=idx)
    cfg = WalkForwardConfig(first_test_year=2010, fold_years=2, horizon=30, min_gap=30)
    before = run_semantic_walk_forward(df, "SPY", cfg)
    mutated = df.copy()
    mutated.loc[mutated.index >= pd.Timestamp("2012-01-01"), "close"] *= 50
    after = run_semantic_walk_forward(mutated, "SPY", cfg)
    before_first = {r["name"]: r["folds"][0] for r in before["rows"] if r["folds"]}
    after_first = {r["name"]: r["folds"][0] for r in after["rows"] if r["folds"]}
    assert before_first == after_first
