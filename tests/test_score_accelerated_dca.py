import numpy as np
import pandas as pd

import swing_intelligence.score_accelerated_dca as sad


def _frame():
    idx = pd.bdate_range("2000-01-03", "2012-12-31")
    close = pd.Series(100.0 * np.cumprod(np.full(len(idx), 1.0002)), index=idx)
    return pd.DataFrame({"open": close * 0.999, "close": close}, index=idx)


def test_no_signal_equals_plain_dca(monkeypatch):
    frame = _frame()
    monkeypatch.setattr(sad, "_score_series", lambda features, cfg: pd.Series(0.0, index=features.index))
    result = sad.run_score_accelerated_dca(frame, sad.AcceleratedDCAConfig(first_test_year=2010))
    assert result["summary"]["acceleration_fraction"] == 0.0
    assert abs(result["summary"]["median_accelerated_minus_dca"]) < 1e-12


def test_signal_can_only_accelerate(monkeypatch):
    frame = _frame()
    score = pd.Series(0.0, index=frame.index)
    first_2010 = frame.loc[frame.index >= "2010-01-01"].index[0]
    score.loc[first_2010] = 80.0
    monkeypatch.setattr(sad, "_score_series", lambda features, cfg: score.reindex(features.index))
    result = sad.run_score_accelerated_dca(frame, sad.AcceleratedDCAConfig(first_test_year=2010))
    first = result["rows"][0]
    assert first["accelerated"] is True
    assert first["acceleration_date"] >= first["cash_date"]
