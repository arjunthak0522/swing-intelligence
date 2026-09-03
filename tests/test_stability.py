import pandas as pd

from swing_intelligence.stability import StabilityGate, summarize_parameter_stability


def test_stability_requires_broad_positive_neighborhood():
    table = pd.DataFrame({
        "variant": ["a", "b", "c"],
        "n": [80, 75, 70],
        "edge": [.010, .012, .008],
        "win_edge": [.03, .04, .02],
        "sample_ok": [True, True, True],
    })
    s = summarize_parameter_stability(table, StabilityGate(min_positive_fraction=.67, max_edge_cv=1.5))
    assert s["stable"]
    assert s["positive_fraction"] == 1.0


def test_stability_rejects_single_lucky_threshold():
    table = pd.DataFrame({
        "variant": ["a", "b", "c"],
        "n": [80, 75, 70],
        "edge": [.03, -.01, -.02],
        "win_edge": [.05, -.01, -.02],
        "sample_ok": [True, True, True],
    })
    s = summarize_parameter_stability(table)
    assert not s["stable"]
