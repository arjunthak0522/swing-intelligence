import pandas as pd

from swing_intelligence.autonomous_robustness import independent_event_dates, rule_from_result


def test_independent_event_dates_collapses_clusters():
    idx = pd.bdate_range("2024-01-02", periods=100)
    frame = pd.DataFrame({"close": range(100)}, index=idx)
    mask = pd.Series(False, index=idx)
    mask.iloc[[2, 3, 4, 20, 31, 32, 62, 95]] = True

    dates = independent_event_dates(frame, mask, min_gap=30)
    positions = [frame.index.get_loc(dt) for dt in dates]
    assert positions == [2, 32, 62, 95]


def test_rule_reconstructs_from_research_result():
    result = {
        "name": "test_rule",
        "rationale": "example",
        "terms": [
            {"feature": "return_5d", "op": "<=", "threshold": -0.02},
            {"feature": "vix_level", "op": ">=", "threshold": 30.0},
        ],
    }
    rule = rule_from_result(result)
    assert rule.name == "test_rule"
    assert len(rule.terms) == 2
    assert rule.terms[0].feature == "return_5d"
    assert rule.terms[1].threshold == 30.0
