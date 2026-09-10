from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from reentry_unified_engine import evaluate


def payload(*, sp20=20.0, mmfd=20.0, fast=0, daily="OVERSOLD", nasi_direction="FLAT", vvix_direction="FLAT", skew_direction="FLAT"):
    return {
        "turn_family_count": fast,
        "daily_context_state": daily,
        "values": {
            "SPXA20R": sp20,
            "MMFD": mmfd,
            "NASI_RSI": 25.0,
            "NASI_DIRECTION": nasi_direction,
            "VVIX": 100.0,
            "VVIX_DIRECTION": vvix_direction,
            "SKEW_LIVE_PROXY": 3.0,
            "SKEW_DIRECTION": skew_direction,
        },
    }


def test_no_oversold_gate_forces_wait_even_with_reversal_evidence():
    p = payload(sp20=60.0, mmfd=60.0, fast=4, daily="NORMAL", nasi_direction="RISING", vvix_direction="FALLING", skew_direction="NARROWING")
    result = evaluate(p, None)
    assert result["oversold_gate"] is False
    assert result["decision"] == "WAIT"


def test_two_fast_families_trigger_go_early_when_oversold():
    result = evaluate(payload(fast=2), None)
    assert result["oversold_gate"] is True
    assert result["decision"] == "GO_EARLY"


def test_one_fast_plus_one_context_triggers_go_early():
    result = evaluate(payload(fast=1, skew_direction="NARROWING"), None)
    assert result["context_support_count"] == 1
    assert result["decision"] == "GO_EARLY"


def test_one_fast_without_context_is_watch():
    result = evaluate(payload(fast=1), None)
    assert result["context_support_count"] == 0
    assert result["decision"] == "WATCH"


def test_two_context_families_without_fast_is_watch():
    result = evaluate(payload(fast=0, vvix_direction="FALLING", skew_direction="NARROWING"), None)
    assert result["context_support_count"] == 2
    assert result["decision"] == "WATCH"


def test_one_context_without_fast_is_wait():
    result = evaluate(payload(fast=0, skew_direction="NARROWING"), None)
    assert result["context_support_count"] == 1
    assert result["decision"] == "WAIT"


def test_prior_snapshot_can_supply_context_turns():
    p = payload(fast=1)
    p["values"]["MMFD"] = 22.0
    prior = {"MMFD": "21.0", "NASI_RSI": "25.0", "VVIX": "100.0", "SKEW_LIVE_PROXY": "3.0"}
    result = evaluate(p, prior)
    assert result["context_support"]["MMFD_IMPROVING"] is True
    assert result["decision"] == "GO_EARLY"


def test_exactly_30_does_not_open_numeric_oversold_gate_under_v1():
    p = payload(sp20=30.0, mmfd=30.0, fast=0, daily="NORMAL")
    result = evaluate(p, None)
    assert result["oversold_gate"] is False
    assert result["decision"] == "WAIT"


def test_daily_oversold_context_can_open_gate():
    p = payload(sp20=55.0, mmfd=55.0, fast=1, daily="OVERSOLD")
    result = evaluate(p, None)
    assert result["oversold_gate"] is True
    assert result["decision"] == "WATCH"
