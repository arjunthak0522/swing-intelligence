import numpy as np
import pandas as pd

from swing_intelligence.correction_reentry import CorrectionReentryConfig, correction_state, run_correction_reentry_validation


def _frame():
    idx = pd.bdate_range("2000-01-03", "2012-12-31")
    close = pd.Series(100.0, index=idx)
    close.loc["2010-03-01":"2010-03-31"] = np.linspace(100, 92, len(close.loc["2010-03-01":"2010-03-31"]))
    frame = pd.DataFrame({
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
    }, index=idx)
    return frame


def test_headline_correction_detected():
    f = _frame()
    s = correction_state(f, CorrectionReentryConfig())
    assert s["headline"].any()


def test_rolling_correction_detected_without_headline():
    f = _frame()
    f["close"] = 100.0
    f.loc["2010-04-01":"2010-04-30", "rsp_spy_ret_20d"] = -0.02
    f.loc["2010-04-01":"2010-04-30", "iwm_spy_ret_20d"] = -0.03
    s = correction_state(f, CorrectionReentryConfig())
    assert s.loc["2010-04-01":"2010-04-30", "rolling_breadth_down"].any()


def test_growth_led_rolling_correction_detected_when_broad_market_outperforms():
    f = _frame()
    f["close"] = 100.0
    mask = (f.index >= "2010-05-03") & (f.index <= "2010-05-31")
    f.loc[mask, "rsp_spy_ret_20d"] = 0.012
    f.loc[mask, "iwm_spy_ret_20d"] = 0.015
    f.loc[mask, "qqq_spy_ret_20d"] = -0.02
    f.loc[mask, "smh_qqq_ret_20d"] = -0.025
    s = correction_state(f, CorrectionReentryConfig())
    assert s.loc[mask, "rolling_growth_down"].any()
    assert (s.loc[mask & s["rolling_growth_down"], "type"] == "rolling_growth_down").all()


def test_no_signal_does_not_fabricate_entry(monkeypatch):
    import swing_intelligence.correction_reentry as cr
    f = _frame()
    def fake_score(train, test, target):
        return pd.DataFrame({"opportunity_score": 0.0}, index=test.index)
    monkeypatch.setattr(cr, "calibrated_opportunity_score", fake_score)
    out = run_correction_reentry_validation(f, CorrectionReentryConfig(first_test_year=2010))
    assert out["summary"]["episode_count"] >= 1
    assert out["summary"].get("signal_episode_count", 0) == 0


def test_signal_uses_next_session(monkeypatch):
    import swing_intelligence.correction_reentry as cr
    f = _frame()
    def fake_score(train, test, target):
        out = pd.DataFrame({"opportunity_score": 0.0}, index=test.index)
        mask = test.index >= pd.Timestamp("2010-03-10")
        if mask.any():
            out.loc[mask, "opportunity_score"] = 80.0
        return out
    monkeypatch.setattr(cr, "calibrated_opportunity_score", fake_score)
    out = run_correction_reentry_validation(f, CorrectionReentryConfig(first_test_year=2010))
    signaled = [r for r in out["rows"] if r["signal_found"]]
    assert signaled
    assert signaled[0]["signal_date"] == "2010-03-10"
    assert signaled[0]["signal_delay_days"] >= 1
