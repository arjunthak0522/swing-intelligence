from tools.reentry_insights import build_market_insights


def test_semiconductor_repair_is_explained_without_changing_signal():
    snapshot = {
        "signal": "WAIT",
        "analog_decision": "NO",
        "internal_reset": "DEVELOPING",
        "selling_pressure": "STABILIZING",
        "subsector_intelligence": {
            "proxies": {
                "SMH": {
                    "label": "Semiconductors",
                    "parent_sector": "XLK",
                    "drawdown_20d": -0.0456,
                    "drawdown_60d": -0.1523,
                    "return_1d": 0.0261,
                    "return_5d": 0.0251,
                    "relative_strength_20d_vs_spy": -0.0230,
                    "relative_strength_20d_vs_parent": -0.0233,
                    "relative_strength_60d_vs_parent": -0.0684,
                    "repairing": True,
                }
            }
        },
    }

    insights = build_market_insights(snapshot)

    assert insights["signal"] == "WAIT"
    assert insights["holding_back"] == ["Historical analog decision is NO."]
    assert insights["key_groups"][0]["symbol"] == "SMH"
    assert insights["key_groups"][0]["state"] == "REPAIRING"
    assert insights["key_groups"][0]["stance"] == "SUPPORTIVE FOR RE-ENTRY"
    assert "repairing after a meaningful reset" in insights["key_groups"][0]["interpretation"]
    assert "-4.6%" in insights["key_groups"][0]["interpretation"]
    assert "-15.2%" in insights["key_groups"][0]["interpretation"]
    assert "context and confirmation" in insights["key_groups"][0]["why_it_matters"]


def test_insights_are_explanatory_only():
    snapshot = {
        "signal": "RE-ENTER",
        "analog_decision": "YES",
        "internal_reset": "MEANINGFUL",
        "selling_pressure": "REPAIRING",
        "subsector_intelligence": {"proxies": {}},
    }

    insights = build_market_insights(snapshot)

    assert insights["signal"] == "RE-ENTER"
    assert "do not add signals" in insights["insight_policy"]
    assert "Historical analog decision is YES." in insights["supporting_reentry"]
