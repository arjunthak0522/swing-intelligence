from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from reentry_early_entry_policy import early_entry_decision  # noqa: E402


def test_subsector_repair_is_supporting_evidence_not_live_override():
    signal, _, source = early_entry_decision(
        analog_decision="YES",
        weakness_present=False,
        internal_reset="DEVELOPING",
        selling_pressure="MIXED",
        existing_signal="WAIT",
        subsector_state="HIDDEN_DAMAGE_REPAIRING",
        subsector_supports_early_entry=True,
    )
    assert signal == "WAIT"
    assert source == "INTERNAL_SETUP_NOT_REPAIRED"


def test_rejected_candidate_remains_reproducible_for_research_only():
    signal, _, source = early_entry_decision(
        analog_decision="YES",
        weakness_present=False,
        internal_reset="DEVELOPING",
        selling_pressure="MIXED",
        existing_signal="WAIT",
        subsector_state="HIDDEN_DAMAGE_REPAIRING",
        subsector_supports_early_entry=True,
        allow_subsector_candidate=True,
    )
    assert signal == "RE-ENTER"
    assert source == "EARLY_SUBSECTOR_REPAIR_CANDIDATE"


def test_subsector_damage_without_repair_does_not_trigger():
    signal, _, source = early_entry_decision(
        analog_decision="YES",
        weakness_present=False,
        internal_reset="DEVELOPING",
        selling_pressure="MIXED",
        existing_signal="WAIT",
        subsector_state="HIDDEN_DAMAGE",
        subsector_supports_early_entry=False,
    )
    assert signal == "WAIT"
    assert source == "INTERNAL_SETUP_NOT_REPAIRED"


def test_subsector_repair_requires_favorable_analogs():
    signal, _, source = early_entry_decision(
        analog_decision="NO",
        weakness_present=False,
        internal_reset="MEANINGFUL",
        selling_pressure="MIXED",
        existing_signal="WAIT",
        subsector_state="REPAIRING",
        subsector_supports_early_entry=True,
    )
    assert signal == "WAIT"
    assert source == "INTERNAL_SETUP_NOT_REPAIRED"


def test_subsector_layer_never_vetoes_existing_reenter():
    signal, _, source = early_entry_decision(
        analog_decision="NO",
        weakness_present=True,
        internal_reset="NONE",
        selling_pressure="WORSENING",
        existing_signal="RE-ENTER",
        subsector_state="BROAD_SUBSECTOR_DAMAGE",
        subsector_supports_early_entry=False,
    )
    assert signal == "RE-ENTER"
    assert source == "BASE_REENTRY"
