import numpy as np
import pandas as pd

from swing_intelligence.autonomous_lab import (
    LabConfig,
    ResearchSplit,
    RuleTerm,
    HypothesisRule,
    _forward_path_table,
    learn_hypotheses,
    skeptic_verdict,
)
from swing_intelligence.outcomes import forward_path_stats


def test_rule_mask_applies_all_terms():
    idx = pd.date_range("2020-01-01", periods=4, freq="D")
    df = pd.DataFrame({"a": [1, 2, 3, 4], "b": [4, 3, 2, 1]}, index=idx)
    rule = HypothesisRule(
        name="pair",
        terms=(RuleTerm("a", ">=", 2), RuleTerm("b", "<=", 2)),
        rationale="test",
    )
    assert rule.mask(df).tolist() == [False, False, True, True]


def test_hypothesis_thresholds_are_train_only():
    idx = pd.bdate_range("2000-01-03", "2024-12-31")
    base = np.linspace(-0.10, 0.10, len(idx))
    df = pd.DataFrame({"return_5d": base}, index=idx)
    split = ResearchSplit(train_end="2016-12-31", validation_end="2021-12-31")
    cfg = LabConfig(quantiles=(0.20, 0.80), max_pair_rules=0)

    rules_before = learn_hypotheses(df, split=split, config=cfg)
    thresholds_before = [(r.name, r.terms[0].threshold) for r in rules_before]

    mutated = df.copy()
    mutated.loc[mutated.index > pd.Timestamp("2021-12-31"), "return_5d"] = 999.0
    rules_after = learn_hypotheses(mutated, split=split, config=cfg)
    thresholds_after = [(r.name, r.terms[0].threshold) for r in rules_after]

    assert thresholds_before == thresholds_after


def test_precomputed_forward_paths_match_reference_implementation():
    idx = pd.bdate_range("2024-01-02", periods=12)
    close = np.array([100, 102, 101, 104, 103, 105, 107, 106, 109, 108, 111, 112], dtype=float)
    df = pd.DataFrame({
        "open": close,
        "high": close + np.array([1.0, 2.0, 1.5, 1.0, 2.5, 1.5, 2.0, 1.0, 2.0, 1.5, 1.0, 2.0]),
        "low": close - np.array([1.0, 1.0, 2.0, 1.5, 1.0, 2.0, 1.0, 2.5, 1.0, 2.0, 1.5, 1.0]),
        "close": close,
        "volume": 1000,
    }, index=idx)

    for horizon in (1, 3, 5):
        reference = forward_path_stats(df, df.index, horizon)
        fast = _forward_path_table(df, horizon)
        pd.testing.assert_index_equal(fast.index, reference.index, check_freq=False)
        pd.testing.assert_frame_equal(
            fast,
            reference,
            check_freq=False,
            check_exact=False,
            rtol=1e-12,
            atol=1e-12,
        )


def test_skeptic_requires_validation_and_holdout_edges():
    cfg = LabConfig(primary_horizon=30, min_n=25)
    good = {
        "periods": {
            "validation": {"horizons": {30: {"n": 40, "median_excess_edge": 0.02, "win_probability_edge": 0.08}}},
            "holdout": {"horizons": {30: {"n": 35, "median_excess_edge": 0.01, "win_probability_edge": 0.04}}},
        }
    }
    assert skeptic_verdict(good, cfg)["passed"] is True

    bad = {
        "periods": {
            "validation": {"horizons": {30: {"n": 40, "median_excess_edge": 0.02, "win_probability_edge": 0.08}}},
            "holdout": {"horizons": {30: {"n": 35, "median_excess_edge": -0.01, "win_probability_edge": 0.04}}},
        }
    }
    verdict = skeptic_verdict(bad, cfg)
    assert verdict["passed"] is False
    assert any("holdout" in reason for reason in verdict["reasons"])
