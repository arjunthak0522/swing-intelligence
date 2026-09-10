import numpy as np
import pandas as pd

from swing_intelligence.strategy_equity_curve import (
    StrategyEquityCurveConfig,
    _max_drawdown,
    _sharpe,
)


def test_max_drawdown_and_sharpe_are_sane():
    equity = pd.Series([100.0, 110.0, 99.0, 120.0])
    assert np.isclose(_max_drawdown(equity), -0.10)
    r = pd.Series([0.01, -0.005, 0.007, 0.002])
    assert _sharpe(r) is not None


def test_frozen_config_is_exact_candidate():
    cfg = StrategyEquityCurveConfig()
    assert cfg.trigger == 70.0
    assert cfg.horizon == 30
    assert cfg.min_gap == 30
    assert cfg.transaction_cost_bps_round_trip == 10.0
    assert cfg.starting_capital == 100000.0
