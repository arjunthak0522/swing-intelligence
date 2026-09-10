import numpy as np
import pandas as pd

import swing_intelligence.cash_deployment as cd


def _frame():
    idx = pd.bdate_range("2000-01-03", "2012-12-31")
    close = pd.Series(100.0 * np.cumprod(np.full(len(idx), 1.0002)), index=idx)
    return pd.DataFrame({"open": close * 0.999, "close": close}, index=idx)


def test_score_policy_uses_pre_test_history_and_next_session(monkeypatch):
    frame = _frame()
    calls = []

    def fake_score(train, test, target):
        calls.append((train.index.min(), train.index.max(), test.index.min()))
        out = pd.DataFrame(index=test.index)
        out["damage_score"] = 50.0
        out["repair_score"] = 50.0
        out["opportunity_score"] = 0.0
        if test.index.min().year == 2010:
            out.iloc[0, out.columns.get_loc("opportunity_score")] = 80.0
        return out

    monkeypatch.setattr(cd, "calibrated_opportunity_score", fake_score)
    cfg = cd.CashDeploymentConfig(first_test_year=2010, random_iterations=5)
    cash = pd.Series(0.0, index=frame.index)
    result = cd.run_cash_deployment_simulator(frame, cash, cfg)

    assert calls
    assert calls[0][0].year == 2000
    assert calls[0][1].year == 2009
    first_2010 = frame.loc[frame.index >= "2010-01-01"].index[0]
    expected = frame.index[frame.index.get_loc(first_2010) + 1]
    assert result["policies"]["score_triggered"]["deployment_date"] == str(expected.date())


def test_random_policy_is_deterministic(monkeypatch):
    frame = _frame()

    def no_signal(train, test, target):
        return pd.DataFrame({"damage_score": 0.0, "repair_score": 0.0, "opportunity_score": 0.0}, index=test.index)

    monkeypatch.setattr(cd, "calibrated_opportunity_score", no_signal)
    cfg = cd.CashDeploymentConfig(first_test_year=2010, random_iterations=10)
    cash = pd.Series(2.0, index=frame.index)
    a = cd.run_cash_deployment_simulator(frame, cash, cfg)
    b = cd.run_cash_deployment_simulator(frame, cash, cfg)
    assert a["policies"]["random"] == b["policies"]["random"]


def test_immediate_deploys_full_sleeve(monkeypatch):
    frame = _frame()

    def no_signal(train, test, target):
        return pd.DataFrame({"damage_score": 0.0, "repair_score": 0.0, "opportunity_score": 0.0}, index=test.index)

    monkeypatch.setattr(cd, "calibrated_opportunity_score", no_signal)
    cfg = cd.CashDeploymentConfig(first_test_year=2010, random_iterations=2)
    cash = pd.Series(0.0, index=frame.index)
    result = cd.run_cash_deployment_simulator(frame, cash, cfg)
    assert result["policies"]["immediate"]["deployed_fraction_of_initial_sleeve"] == 1.0
