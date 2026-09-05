from __future__ import annotations

from typing import Any


def _pct(value: float) -> str:
    return f"{float(value) * 100:+.1f}%"


def _subsector_state(item: dict[str, Any]) -> str:
    dd20 = float(item.get("drawdown_20d", 0.0))
    repairing = bool(item.get("repairing", False))
    if repairing:
        return "REPAIRING"
    if dd20 <= -0.05:
        return "DEEP CORRECTION"
    if dd20 <= -0.03:
        return "MEANINGFUL CORRECTION"
    return "LAGGING"


def _subsector_stance(item: dict[str, Any]) -> str:
    if bool(item.get("repairing", False)):
        return "SUPPORTIVE FOR RE-ENTRY"
    if float(item.get("drawdown_20d", 0.0)) <= -0.03:
        return "RESET PRESENT"
    return "NEUTRAL"


def _subsector_insight(symbol: str, item: dict[str, Any]) -> dict[str, Any]:
    label = str(item.get("label", symbol))
    parent = str(item.get("parent_sector", ""))
    dd20 = float(item.get("drawdown_20d", 0.0))
    dd60 = float(item.get("drawdown_60d", 0.0))
    ret1 = float(item.get("return_1d", 0.0))
    ret5 = float(item.get("return_5d", 0.0))
    rs20_parent = float(item.get("relative_strength_20d_vs_parent", 0.0))
    rs60_parent = float(item.get("relative_strength_60d_vs_parent", 0.0))
    repairing = bool(item.get("repairing", False))

    state = _subsector_state(item)
    if repairing:
        interpretation = (
            f"{symbol} ({label}) is repairing after a meaningful reset: {_pct(dd20)} from its 20-day high, "
            f"{_pct(dd60)} from its 60-day high, {_pct(ret1)} today and {_pct(ret5)} over 5 days. "
            f"It is still {_pct(rs20_parent)} versus {parent} over 20 days."
        )
        why = (
            "A damaged group beginning to recover is constructive early re-entry evidence, but lingering relative weakness means "
            "the repair is context and confirmation rather than an independent market trigger."
        )
    elif dd20 <= -0.05:
        interpretation = (
            f"{symbol} ({label}) remains in a deep internal correction at {_pct(dd20)} from its 20-day high and "
            f"{_pct(dd60)} from its 60-day high."
        )
        why = "Deep internal damage creates potential reset fuel, but the group has not yet met the engine's repair condition."
    else:
        interpretation = (
            f"{symbol} ({label}) is {_pct(dd20)} from its 20-day high and {_pct(rs20_parent)} versus {parent} over 20 days."
        )
        why = "This is material internal weakness that helps explain conditions hidden by the headline indexes."

    return {
        "symbol": symbol,
        "label": label,
        "parent_sector": parent,
        "state": state,
        "stance": _subsector_stance(item),
        "interpretation": interpretation,
        "why_it_matters": why,
        "metrics": {
            "drawdown_20d": dd20,
            "drawdown_60d": dd60,
            "return_1d": ret1,
            "return_5d": ret5,
            "relative_strength_20d_vs_spy": float(item.get("relative_strength_20d_vs_spy", 0.0)),
            "relative_strength_20d_vs_parent": rs20_parent,
            "relative_strength_60d_vs_parent": rs60_parent,
            "repairing": repairing,
        },
    }


def build_market_insights(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Create retail-readable insights from canonical engine evidence without changing the signal."""
    signal = str(snapshot.get("signal", "UNKNOWN"))
    analog = str(snapshot.get("analog_decision", "UNKNOWN"))
    reset = str(snapshot.get("internal_reset", "NONE"))
    pressure = str(snapshot.get("selling_pressure", "MIXED"))

    if signal == "RE-ENTER":
        headline = f"RE-ENTER - internal repair and historical evidence are sufficiently favorable."
    elif signal == "WAIT":
        headline = f"WAIT - a reset is developing, but the full historical evidence is not favorable enough yet."
    else:
        headline = "NO RE-ENTRY SETUP - current conditions do not show a meaningful enough reset."

    supporting: list[str] = []
    holding_back: list[str] = []
    if reset in {"DEVELOPING", "MEANINGFUL", "BROAD"}:
        supporting.append(f"Internal reset is {reset.lower()}.")
    if pressure in {"STABILIZING", "REPAIRING"}:
        supporting.append(f"Selling pressure is {pressure.lower()}.")
    if analog in {"CAUTIOUS YES", "YES", "STRONG YES"}:
        supporting.append(f"Historical analog decision is {analog}.")
    else:
        holding_back.append(f"Historical analog decision is {analog}.")

    proxies = snapshot.get("subsector_intelligence", {}).get("proxies", {})
    key_groups: list[dict[str, Any]] = []
    for symbol, item in proxies.items():
        dd20 = float(item.get("drawdown_20d", 0.0))
        rs_parent = float(item.get("relative_strength_20d_vs_parent", 0.0))
        repairing = bool(item.get("repairing", False))
        if repairing or dd20 <= -0.03 or rs_parent <= -0.025:
            key_groups.append(_subsector_insight(symbol, item))

    key_groups.sort(
        key=lambda x: (
            0 if x["metrics"]["repairing"] else 1,
            float(x["metrics"]["drawdown_20d"]),
        )
    )

    repairing_groups = [x for x in key_groups if x["metrics"]["repairing"]]
    if repairing_groups:
        names = ", ".join(x["label"] for x in repairing_groups[:5])
        supporting.append(f"Repair is visible beneath the indexes in {names}.")

    return {
        "headline": headline,
        "signal": signal,
        "internal_reset": reset,
        "selling_pressure": pressure,
        "analog_decision": analog,
        "supporting_reentry": supporting,
        "holding_back": holding_back,
        "key_groups": key_groups[:12],
        "insight_policy": (
            "Insights are deterministic explanations of existing engine evidence. They do not add signals, alter thresholds, "
            "override historical analogs, or change the canonical WAIT/RE-ENTER decision."
        ),
    }


def add_market_insights(snapshot: dict[str, Any]) -> dict[str, Any]:
    snapshot["market_insights"] = build_market_insights(snapshot)
    return snapshot
