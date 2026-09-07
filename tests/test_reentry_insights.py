from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from reentry_insights import build_market_insights  # noqa: E402


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
    assert insights["holding_back"] == [{
        "title": "Historical setups",
        "state": "NO",
        "detail": "Similar prior market conditions are not favorable enough yet to justify re-entry.",
    }]
    assert insights["key_groups"][0]["symbol"] == "SMH"
    assert insights["key_groups"][0]["state"] == "REPAIRING"
    assert insights["key_groups"][0]["stance"] == "SUPPORTIVE FOR RE-ENTRY"
    assert "repairing after a meaningful reset" in insights["key_groups"][0]["interpretation"]
    assert "-4.6%" in insights["key_groups"][0]["interpretation"]
    assert "-15.2%" in insights["key_groups"][0]["interpretation"]
    assert "context and confirmation" in insights["key_groups"][0]["why_it_matters"]

    repair_item = next(item for item in insights["supporting_reentry"] if item["title"] == "Repair under the surface")
    assert repair_item["state"] == "REPAIRING"
    assert "Semiconductors" in repair_item["detail"]
    assert "cannot independently trigger or veto" in repair_item["why_it_matters"]


def test_insights_are_explanatory_only_and_match_web_item_contract():
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
    assert insights["headline"].startswith("RE-ENTER")

    historical = next(item for item in insights["supporting_reentry"] if item["title"] == "Historical setups")
    assert historical["state"] == "YES"
    assert historical["detail"]

    for item in insights["supporting_reentry"] + insights["holding_back"]:
        assert isinstance(item, dict)
        assert isinstance(item.get("title"), str) and item["title"]
        assert isinstance(item.get("detail"), str) and item["detail"]


def test_no_reentry_setup_copy_is_neutral_not_bearish():
    snapshot = {
        "signal": "NO RE-ENTRY SETUP",
        "analog_decision": "NO",
        "internal_reset": "NONE",
        "selling_pressure": "MIXED",
        "subsector_intelligence": {"proxies": {}},
    }

    insights = build_market_insights(snapshot)

    assert insights["signal"] == "NO RE-ENTRY SETUP"
    assert "not been enough of a correction" in insights["headline"]
    assert "bear" not in insights["headline"].lower()
