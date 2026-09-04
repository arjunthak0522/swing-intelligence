from __future__ import annotations

from typing import Any


def build_subsector_decision_evidence(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Translate enriched subsector data into compact decision evidence.

    This layer is deliberately confirmatory rather than a standalone market-timing
    engine. It looks for hidden damage beneath relatively mild parent sectors and
    for repair inside already-damaged groups. The resulting state can influence
    ambiguous early-entry decisions but does not veto validated broad RE-ENTER
    conditions by itself.
    """
    subsectors = snapshot.get("subsector_intelligence", {})
    by_sector = subsectors.get("by_sector", {})
    sectors = snapshot.get("signal_snapshot", {}).get("sectors", {})

    hidden_damage_sectors: list[str] = []
    repairing_sectors: list[str] = []
    deep_damage_sectors: list[str] = []

    for parent, group in by_sector.items():
        parent_row = sectors.get(parent, {})
        parent_dd20 = float(parent_row.get("drawdown_20d", 0.0) or 0.0)
        damage3 = float(group.get("damage_share_3pct", 0.0) or 0.0)
        repair = float(group.get("repair_share", 0.0) or 0.0)

        if parent_dd20 > -0.03 and damage3 >= 0.50:
            hidden_damage_sectors.append(parent)
        if damage3 >= 0.50:
            deep_damage_sectors.append(parent)
        if damage3 >= 0.50 and repair >= 0.25:
            repairing_sectors.append(parent)

    agg = subsectors.get("aggregate", {})
    aggregate_damage3 = float(agg.get("damage_share_3pct", 0.0) or 0.0)
    aggregate_repair = float(agg.get("repair_share", 0.0) or 0.0)

    hidden = len(hidden_damage_sectors) >= 1
    repair = len(repairing_sectors) >= 1
    broad_hidden = len(hidden_damage_sectors) >= 2
    broad_repair = len(repairing_sectors) >= 2

    if repair and hidden:
        state = "HIDDEN_DAMAGE_REPAIRING"
    elif broad_repair:
        state = "BROAD_REPAIR"
    elif repair:
        state = "REPAIRING"
    elif broad_hidden:
        state = "BROAD_HIDDEN_DAMAGE"
    elif hidden:
        state = "HIDDEN_DAMAGE"
    elif aggregate_damage3 >= 0.40:
        state = "BROAD_SUBSECTOR_DAMAGE"
    else:
        state = "NEUTRAL"

    supports_early_entry = state in {"HIDDEN_DAMAGE_REPAIRING", "BROAD_REPAIR", "REPAIRING"}
    supports_damage_case = state in {
        "HIDDEN_DAMAGE_REPAIRING",
        "BROAD_REPAIR",
        "REPAIRING",
        "BROAD_HIDDEN_DAMAGE",
        "HIDDEN_DAMAGE",
        "BROAD_SUBSECTOR_DAMAGE",
    }

    return {
        "state": state,
        "supports_early_entry": supports_early_entry,
        "supports_damage_case": supports_damage_case,
        "hidden_damage_sectors": hidden_damage_sectors,
        "repairing_sectors": repairing_sectors,
        "deep_damage_sectors": deep_damage_sectors,
        "aggregate_damage_share_3pct": aggregate_damage3,
        "aggregate_repair_share": aggregate_repair,
        "role": (
            "decision evidence: may confirm ambiguous internal-reset/repair setups; "
            "does not independently veto validated broad-market RE-ENTER conditions"
        ),
    }


def attach_subsector_decision_evidence(snapshot: dict[str, Any]) -> dict[str, Any]:
    out = dict(snapshot)
    out["subsector_decision_evidence"] = build_subsector_decision_evidence(snapshot)
    return out
