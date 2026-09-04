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
) -> tuple[str, str, str]:
    """Apply the unified engine's intentional early-entry bias.

    The policy does not require a perfect bottom. A developing internal reset is
    enough once repair/stabilization is visible and historical analog evidence is
    at least cautiously favorable. Subsector repair is now an explicit decision
    input: when the aggregate selling-pressure state is MIXED, meaningful repair
    beneath sectors can supply the missing confirmation for an early entry.

    Existing broad-market RE-ENTER signals are preserved unchanged. Subsector
    evidence cannot veto a validated broad-market RE-ENTER by itself.

    RE-ENTER is re-evaluated independently each completed session. Persistence was
    historically tested from 1-5 sessions and rejected because it materially
    expanded active signal days beyond what is needed once the early-repair gate
    itself is available.
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

    # New role for subsectors: resolve an otherwise ambiguous MIXED repair state.
    # This is deliberately narrower than allowing subsector evidence to become a
    # standalone trigger.
    if (
        internal_setup
        and selling_pressure == "MIXED"
        and analog_favorable
        and subsector_supports_early_entry
    ):
        return (
            "RE-ENTER",
            f"the broad repair picture is mixed, but subsector evidence ({subsector_state}) shows repair beneath damaged groups while historical analogs remain favorable",
            "EARLY_SUBSECTOR_REPAIR",
        )

    if internal_setup:
        return (
            "WAIT",
            "an internal reset is present, but repair or historical confirmation is not yet sufficient",
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
        "subsector_can_resolve_mixed_repair": True,
        "subsector_can_veto_validated_broad_reentry": False,
        "required_analog_decision": sorted(FAVORABLE_ANALOGS),
        "reentry_window_sessions": REENTRY_WINDOW_SESSIONS,
        "window_status": "NO PERSISTENCE - 1-5 session persistence was historically tested and rejected as unnecessarily broad; the engine re-evaluates the opportunity every completed session",
    }
    return out
