from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from reentry_early_entry_policy import early_entry_decision  # noqa: E402


def test_developing_repair_with_favorable_analogs_reenters():
    signal, _, source = early_entry_decision(
        analog_decision="YES",
        weakness_present=False,
        internal_reset="DEVELOPING",
        selling_pressure="REPAIRING",
        existing_signal="WAIT",
    )
    assert signal == "RE-ENTER"
    assert source == "EARLY_INTERNAL_REPAIR"


def test_developing_without_repair_waits():
    signal, _, _ = early_entry_decision(
        analog_decision="YES",
        weakness_present=False,
        internal_reset="DEVELOPING",
        selling_pressure="WORSENING",
        existing_signal="WAIT",
    )
    assert signal == "WAIT"


def test_unfavorable_analogs_do_not_force_early_entry():
    signal, _, _ = early_entry_decision(
        analog_decision="NO",
        weakness_present=False,
        internal_reset="DEVELOPING",
        selling_pressure="REPAIRING",
        existing_signal="WAIT",
    )
    assert signal == "WAIT"


def test_existing_reentry_is_never_downgraded():
    signal, _, source = early_entry_decision(
        analog_decision="CAUTIOUS YES",
        weakness_present=True,
        internal_reset="NONE",
        selling_pressure="WORSENING",
        existing_signal="RE-ENTER",
    )
    assert signal == "RE-ENTER"
    assert source == "BASE_REENTRY"
