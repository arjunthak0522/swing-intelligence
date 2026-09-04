from __future__ import annotations

from tools.reentry_subsector_intelligence import SUBSECTOR_GROUPS, build_market_commentary


def test_all_11_parent_sectors_have_deeper_coverage():
    expected = {"XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLB", "XLRE", "XLK", "XLU"}
    assert set(SUBSECTOR_GROUPS) == expected
    assert all(len(groups) >= 2 for groups in SUBSECTOR_GROUPS.values())


def test_technology_explicitly_contains_semis_and_software():
    symbols = {symbol for symbol, _ in SUBSECTOR_GROUPS["XLK"]}
    assert "SMH" in symbols
    assert "IGV" in symbols


def test_hidden_subsector_damage_is_surfaced_even_if_parent_is_mild():
    snapshot = {
        "signal_snapshot": {
            "sectors": {
                "XLK": {
                    "drawdown_20d": -0.015,
                    "relative_strength_20d_vs_spy": -0.002,
                }
            },
            "factors": {},
        },
        "factor_leadership_state": [],
    }
    subsectors = {
        "by_sector": {
            "XLK": {
                "damage_share_3pct": 2 / 3,
                "repair_share": 1 / 3,
            }
        },
        "proxies": {
            "SMH": {
                "label": "Semiconductors",
                "parent_sector": "XLK",
                "drawdown_20d": -0.055,
                "relative_strength_20d_vs_parent": -0.03,
                "repairing": True,
            },
            "IGV": {
                "label": "Software",
                "parent_sector": "XLK",
                "drawdown_20d": -0.04,
                "relative_strength_20d_vs_parent": -0.02,
                "repairing": False,
            },
        },
    }
    result = build_market_commentary(snapshot, subsectors)
    assert result["sectors"]
    assert "hidden internal damage" in result["sectors"][0]["commentary"]
    assert any(x["symbol"] == "SMH" for x in result["subsectors"])
    assert any(x["symbol"] == "IGV" for x in result["subsectors"])


def test_quiet_conditions_do_not_force_commentary():
    snapshot = {
        "signal_snapshot": {
            "sectors": {
                "XLK": {
                    "drawdown_20d": -0.005,
                    "relative_strength_20d_vs_spy": 0.003,
                }
            },
            "factors": {
                "QUAL": {
                    "drawdown_20d": -0.004,
                    "relative_strength_20d_vs_spy": 0.002,
                }
            },
        },
        "factor_leadership_state": ["NO MATERIAL FACTOR RESET"],
    }
    subsectors = {
        "by_sector": {"XLK": {"damage_share_3pct": 0.0, "repair_share": 0.0}},
        "proxies": {
            "SMH": {
                "label": "Semiconductors",
                "parent_sector": "XLK",
                "drawdown_20d": -0.01,
                "relative_strength_20d_vs_parent": 0.002,
                "repairing": False,
            }
        },
    }
    result = build_market_commentary(snapshot, subsectors)
    assert result["noteworthy_count"] == 0
    assert result["sectors"] == []
    assert result["subsectors"] == []
    assert result["factors"] == []
