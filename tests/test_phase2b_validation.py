import pandas as pd

from swing_intelligence.phase2b_validation import (
    Phase2BConfig,
    evidence_grade,
    evaluate_phase2b,
)


def _frame():
    idx = pd.bdate_range("2022-01-03", periods=160)
    close = pd.Series(range(100, 260), index=idx, dtype=float)
    frame = pd.DataFrame({
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": 1000,
        "signal_feature": [1 if i % 20 == 0 else 0 for i in range(len(idx))],
        "regime": ["bull_trend" if i < 80 else "transition" for i in range(len(idx))],
    }, index=idx)
    return frame


def _result():
    return {
        "name": "test_rule",
        "rationale": "test",
        "terms": [{"feature": "signal_feature", "op": ">=", "threshold": 1.0}],
    }


def test_phase2b_is_diagnostic_and_returns_all_requested_horizons():
    report = evaluate_phase2b(
        _frame(),
        _result(),
        config=Phase2BConfig(horizons=(10, 20, 30, 60), min_events_per_slice=2, min_positive_eras=1),
    )
    assert set(report["horizons"]) == {10, 20, 30, 60}
    assert report["usable_horizons"] >= 1
    assert "eras" in report
    assert "regimes" in report


def test_high_confidence_requires_robustness_plus_stability():
    stable = {
        "multi_horizon_consistent": True,
        "era_consistent": True,
        "positive_regimes": 2,
    }
    assert evidence_grade(stable, {"robust": True})["grade"] == "HIGH CONFIDENCE"
    assert evidence_grade(stable, {"robust": False})["grade"] == "INTERESTING"


def test_weak_stability_is_rejected_even_if_first_pass_robust():
    weak = {
        "multi_horizon_consistent": False,
        "era_consistent": False,
        "positive_regimes": 0,
    }
    assert evidence_grade(weak, {"robust": True})["grade"] == "REJECTED"
