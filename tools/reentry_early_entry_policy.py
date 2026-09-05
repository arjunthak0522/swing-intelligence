from __future__ import annotations

from typing import Any

FAVORABLE_ANALOGS = {"CAUTIOUS YES", "YES", "STRONG YES"}
REENTRY_WINDOW_SESSIONS = 0


def early_entry_decision(
    *,
    analog_decision: str,
    weakness_present: bool,
    internal_reset: str,
    selling_pressure: str,
    existing_signal: str,
    subsector_state: str = "NEUTRAL",
    subsector_supports_early_entry: bool = False,
    allow_subsector_candidate: bool = False,
) -> tuple[str, str, str]:
    """Apply RE-ENTRY's intentional early-entry bias.

    The validated early-entry extension uses aggregate internal repair/stabilization
    plus favorable historical analogs. Subsector intelligence remains formal
    decision evidence, but the tested MIXED-state WAIT -> RE-ENTER override is
    disabled in operational use because exact incremental validation did not show
    sufficient short-horizon or matched-control support.

    `allow_subsector_candidate=True` exists only so the rejected candidate rule can
    be reproduced by historical research. Daily/live callers must leave it False.

    Existing broad-market RE-ENTER signals are preserved unchanged. RE-ENTER is
    re-evaluated independently each completed session; persistence remains zero.
    """
    if existing_signal == "RE-ENTER":
        return existing_signal, "existing validated re-entry condition remains active", "BASE_REENTRY"

    early_repair = selling_pressure in {"STABILIZING", "REPAIRING"}
    internal_setup = internal_reset in {"DEVELOPING", "MEANINGFUL", "BROAD"}
    analog_favorable = analog_decision in FAVORABLE_ANALOGS

    if internal_setup and early_repair and analog_favorable:
        return (
            "RE-ENTER",
            "internal damage is already repairing and historical analogs are favorable; RE-ENTRY intentionally prefers being slightly early rather than waiting for full confirmation",
            "EARLY_INTERNAL_REPAIR",
        )

    # Research-only reproduction of the rejected subsector promotion candidate.
    if (
        allow_subsector_candidate
        and internal_setup
        and selling_pressure == "MIXED"
        and analog_favorable
        and subsector_supports_early_entry
    ):
        return (
            "RE-ENTER",
            f"research-only candidate: the broad repair picture is mixed, but subsector evidence ({subsector_state}) shows repair beneath damaged groups while historical analogs remain favorable",
            "EARLY_SUBSECTOR_REPAIR_CANDIDATE",
        )

    if internal_setup:
        return (
            "WAIT",
            "an internal reset is present, but aggregate repair or historical confirmation is not yet sufficient; subsector evidence remains supporting context",
            "INTERNAL_SETUP_NOT_REPAIRED",
        )

    return existing_signal, "no early-entry override is active", "NO_EARLY_OVERRIDE"


def apply_early_entry_bias(snapshot: dict[str, Any]) -> dict[str, Any]:
    out = dict(snapshot)
    subsector = snapshot.get("subsector_decision_evidence", {})
    signal, interpretation, source = early_entry_decision(
        analog_decision=str(snapshot["analog_decision"]),
        weakness_present=bool(snapshot.get("weakness_present", False)),
        internal_reset=str(snapshot["internal_reset"]),
        selling_pressure=str(snapshot["selling_pressure"]),
        existing_signal=str(snapshot["signal"]),
        subsector_state=str(subsector.get("state", "NEUTRAL")),
        subsector_supports_early_entry=bool(subsector.get("supports_early_entry", False)),
        allow_subsector_candidate=False,
    )
    out["pre_early_bias_signal"] = snapshot["signal"]
    out["signal"] = signal
    if signal != snapshot["signal"]:
        out["signal_interpretation"] = interpretation
        out["setup_source"] = source
    out["early_entry_policy"] = {
        "preference": "slightly early rather than too late",
        "developing_reset_can_trigger": True,
        "required_repair_state": ["STABILIZING", "REPAIRING"],
        "subsector_is_decision_evidence": True,
        "subsector_can_resolve_mixed_repair": False,
        "subsector_promotion_status": "REJECTED BY EXACT INCREMENTAL HISTORICAL VALIDATION",
        "subsector_can_veto_validated_broad_reentry": False,
        "required_analog_decision": sorted(FAVORABLE_ANALOGS),
        "reentry_window_sessions": REENTRY_WINDOW_SESSIONS,
        "window_status": "NO PERSISTENCE - 1-5 session persistence was historically tested and rejected as unnecessarily broad; the engine re-evaluates the opportunity every completed session",
    }
    return out
