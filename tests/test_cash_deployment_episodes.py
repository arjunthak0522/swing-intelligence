import numpy as np
import pandas as pd

import swing_intelligence.cash_deployment_episodes as ce


def _frame():
    idx = pd.bdate_range("2000-01-03", "2014-12-31")
    close = pd.Series(100.0 * np.cumprod(np.full(len(idx), 1.0002)), index=idx)
    return pd.DataFrame({"open": close * 0.999, "close": close}, index=idx)


def test_score_uses_only_pre_fold_history(monkeypatch):
    frame = _frame()
    calls = []

    def fake_score(train, test, target):
        calls.append((train.index.max(), test.index.min()))
        return pd.DataFrame({"damage_score": 50.0, "repair_score": 50.0, "opportunity_score": 0.0}, index=test.index)

    monkeypatch.setattr(ce, "calibrated_opportunity_score", fake_score)
    ce.run_cash_deployment_episodes(frame, ce.CashEpisodeConfig(first_test_year=2010, outcome_days=20, episode_spacing_days=40, max_wait_days=(10,)))
    assert calls
    assert all(train_max < test_min for train_max, test_min in calls)


def test_wait_policy_falls_back_after_max_wait(monkeypatch):
    frame = _frame()

    def no_signal(train, test, target):
        return pd.DataFrame({"damage_score": 0.0, "repair_score": 0.0, "opportunity_score": 0.0}, index=test.index)

    monkeypatch.setattr(ce, "calibrated_opportunity_score", no_signal)
    cfg = ce.CashEpisodeConfig(first_test_year=2010, outcome_days=20, episode_spacing_days=200, max_wait_days=(5,))
    result = ce.run_cash_deployment_episodes(frame, cfg)
    first = result["waits"]["5"]["rows"][0]
    start_pos = frame.index.get_loc(pd.Timestamp(first["cash_date"]))
    assert first["triggered"] is False
    assert first["deployment_date"] == str(frame.index[start_pos + 6].date())


def test_episode_result_is_deterministic(monkeypatch):
    frame = _frame()

    def flat_score(train, test, target):
        return pd.DataFrame({"damage_score": 50.0, "repair_score": 50.0, "opportunity_score": 75.0}, index=test.index)

    monkeypatch.setattr(ce, "calibrated_opportunity_score", flat_score)
    cfg = ce.CashEpisodeConfig(first_test_year=2010, outcome_days=20, episode_spacing_days=100, max_wait_days=(10,))
    a = ce.run_cash_deployment_episodes(frame, cfg)
    b = ce.run_cash_deployment_episodes(frame, cfg)
    assert a == b
