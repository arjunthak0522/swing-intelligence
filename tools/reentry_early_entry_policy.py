from __future__ import annotations

import os
from typing import Any

from reentry_engine import (
    FAVORABLE_ANALOGS,
    REENTRY_WINDOW_SESSIONS,
    _apply_canonical_early_entry,
    early_entry_decision as _engine_early_entry_decision,
)

RESEARCH_SUBSECTOR_ENV = "REENTRY_RESEARCH_SUBSECTOR_CANDIDATE"


def early_entry_decision(
    *,
    analog_decision: str,
    weakness_present: bool,
    internal_reset: str,
    selling_pressure: str,
    existing_signal: str,
    subsector_state: str = "NEUTRAL",
    subsector_supports_early_entry: bool = False,
    allow_subsector_candidate: bool | None = None,
) -> tuple[str, str, str]:
    """Deprecated compatibility adapter to the canonical engine decision.

    No live or snapshot path should import this module. It exists only so frozen
    historical validators can reproduce the rejected subsector candidate while
    migration finishes.
    """
    if allow_subsector_candidate is None:
        allow_subsector_candidate = os.getenv(RESEARCH_SUBSECTOR_ENV, "0") == "1"
    return _engine_early_entry_decision(
        analog_decision=analog_decision,
        weakness_present=weakness_present,
        internal_reset=internal_reset,
        selling_pressure=selling_pressure,
        existing_signal=existing_signal,
        subsector_state=subsector_state,
        subsector_supports_early_entry=subsector_supports_early_entry,
        allow_subsector_candidate=bool(allow_subsector_candidate),
    )


def apply_early_entry_bias(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Deprecated compatibility adapter. Canonical snapshots apply this internally."""
    return _apply_canonical_early_entry(snapshot)
