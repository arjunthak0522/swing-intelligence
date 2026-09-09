import pandas as pd

from swing_intelligence.conditional_search import (
    ConditionalSearchConfig,
    _max_consecutive_losses,
    _max_drawdown_from_trade_returns,
    run_conditional_walk_forward,
)
from swing_intelligence.walk_forward import WalkForwardConfig


def _frame():
    idx = pd.bdate_range("2000-01-03", "2016-12-30")
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
        "vix_percentile_252": pd.Series(0.5, index=idx),
        "vix_change_5d": pd.Series(0.0, index=idx),
        "rsp_spy_ret_5d": close.pct_change(5) * 0.1,
        "rsp_spy_ret_20d": close.pct_change(20) * 0.1,
        "iwm_spy_ret_5d": close.pct_change(5) * 0.2,
        "iwm_spy_ret_20d": close.pct_change(20) * 0.2,
        "smh_qqq_ret_5d": close.pct_change(5) * 0.3,
        "smh_qqq_ret_20d": close.pct_change(20) * 0.3,
    }, index=idx)
    # semantic derived features expected by the search
    df["drawdown_60d"] = close / close.rolling(60).max() - 1
    df["drawdown_252d"] = close / close.rolling(252).max() - 1
    df["return_3d"] = close.pct_change(3)
    df["rebound_3d"] = df["return_3d"]
    df["momentum_accel_5v20"] = df["return_5d"] - df["return_20d"] / 4
    df["vol_expansion_ratio"] = df["realized_vol_10"] / df["realized_vol_20"]
    df["trend_repair_5d"] = df["gap_sma_20"] - df["gap_sma_20"].shift(5)
    df["abs_gap_sma_20"] = df["gap_sma_20"].abs()
    df["vix_cooling_5d"] = -df["vix_change_5d"]
    return df


def test_strategy_risk_helpers():
    r = pd.Series([0.1, -0.1, -0.1, 0.05, -0.2]).to_numpy()
    assert _max_consecutive_losses(r) == 2
    assert _max_drawdown_from_trade_returns(r) < 0


def test_outer_future_mutation_does_not_change_earlier_fold_selection_or_results():
    df = _frame()
    cfg = ConditionalSearchConfig(
        walk_forward=WalkForwardConfig(first_test_year=2012, fold_years=2, horizon=30, min_gap=30),
        inner_validation_years=2,
        min_inner_trades=1,
        max_selected_per_fold=2,
        min_outer_trades_total=1,
        min_outer_folds=1,
        min_positive_edge_fold_fraction=0.0,
    )
    before = run_conditional_walk_forward(df, "SPY", cfg)
    mutated = df.copy()
    mutated.loc[mutated.index >= pd.Timestamp("2014-01-01"), "close"] *= 25
    after = run_conditional_walk_forward(mutated, "SPY", cfg)

    def first_fold_map(result):
        out = {}
        for row in result["rows"]:
            folds = [f for f in row["folds"] if f["start_year"] == 2012]
            if folds:
                out[row["name"]] = folds[0]
        return out

    assert first_fold_map(before) == first_fold_map(after)
