import numpy as np
import pandas as pd

from swing_intelligence.correction_strategy_tournament import (
    CorrectionTournamentConfig,
    candidate_masks,
    run_correction_strategy_tournament,
)


def _frame():
    idx = pd.bdate_range("2000-01-03", "2012-12-31")
    close = pd.Series(100.0, index=idx)
    close.loc["2010-03-01":"2010-03-31"] = np.linspace(100, 92, len(close.loc["2010-03-01":"2010-03-31"]))
    f = pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.001,
        "low": close * 0.998,
        "close": close,
        "rsp_spy_ret_20d": 0.0,
        "iwm_spy_ret_20d": 0.0,
        "qqq_spy_ret_20d": 0.0,
        "smh_qqq_ret_20d": 0.0,
        "vix_z_60": 0.0,
        "vix_change_5d": 0.0,
        "rebound_3d": 0.0,
        "momentum_accel_5v20": 0.0,
        "trend_repair_5d": 0.0,
        "vix_cooling_5d": 0.0,
        "rsp_spy_ret_5d": 0.0,
        "iwm_spy_ret_5d": 0.0,
        "qqq_spy_ret_5d": 0.0,
        "smh_qqq_ret_5d": 0.0,
        "hy_spread_cooling_5d": 0.0,
        "yield_2y_change_5d": 0.0,
    }, index=idx)
    return f


def test_candidate_family_contains_frozen_score_and_growth_repair():
    f = _frame()
    score = pd.Series(0.0, index=f.index)
    masks = candidate_masks(f, score)
    assert "frozen_score_70" in masks
    assert "growth_repair" in masks
    assert "broad_confirmed_repair" in masks


def test_growth_repair_fires_on_positive_rebound_and_growth_leadership():
    f = _frame()
    d = pd.Timestamp("2010-03-22")
    f.loc[d, "rebound_3d"] = 0.01
    f.loc[d, "qqq_spy_ret_5d"] = 0.01
    masks = candidate_masks(f, pd.Series(0.0, index=f.index))
    assert bool(masks["growth_repair"].loc[d])


def test_tournament_does_not_fabricate_signals(monkeypatch):
    import swing_intelligence.correction_strategy_tournament as cst
    f = _frame()
    monkeypatch.setattr(cst, "_score_series", lambda features, config: pd.Series(0.0, index=features.index))
    out = run_correction_strategy_tournament(f, CorrectionTournamentConfig(first_test_year=2010))
    assert out["episode_count"] >= 1
    frozen = next(x for x in out["results"] if x["name"] == "frozen_score_70")
    assert frozen["signals"] == 0
