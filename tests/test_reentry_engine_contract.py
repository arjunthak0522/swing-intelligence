from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from reentry_engine import (  # noqa: E402
    ENGINE_VERSION,
    EVIDENCE_HORIZONS,
    PROXY_CAVEAT,
    SUBSECTOR_PROXY_CAVEAT,
    _unified_signal,
    early_entry_decision,
    strategy_signal,
    validate_snapshot,
    weakness_context,
)


def row(**overrides):
    base = {
        "spy_dd20": -0.005,
        "B50": 0.60,
        "B200": 0.75,
        "vix_change5": 0.00,
        "curve_ratio": 0.85,
        "v2_meaningful": False,
        "v2_developing": False,
        "v2_stabilizing": False,
    }
    base.update(overrides)
    return pd.Series(base)


def test_validated_broad_market_thresholds_are_unchanged():
    weak, reasons = weakness_context(row(spy_dd20=-0.01))
    assert weak and any("20-day high" in r for r in reasons)

    weak, reasons = weakness_context(row(B50=0.50))
    assert weak and any("50DMA" in r for r in reasons)

    weak, reasons = weakness_context(row(vix_change5=0.10))
    assert weak and any("VIX is up" in r for r in reasons)

    weak, reasons = weakness_context(row(curve_ratio=1.0))
    assert weak and any("VIX/VIX3M" in r for r in reasons)

    weak, reasons = weakness_context(row())
    assert not weak and reasons == []


def test_validated_broad_market_strategy_mapping_is_unchanged():
    assert strategy_signal("YES", True)[0] == "RE-ENTER"
    assert strategy_signal("CAUTIOUS YES", True)[0] == "RE-ENTER"
    assert strategy_signal("STRONG YES", True)[0] == "RE-ENTER"
    assert strategy_signal("NO", True)[0] == "WAIT"
    assert strategy_signal("YES", False)[0] == "NO RE-ENTRY SETUP"


def test_unified_internal_only_policy_is_conservative():
    meaningful = row(v2_meaningful=True, v2_developing=True, v2_stabilizing=True)
    assert _unified_signal("YES", False, meaningful)[0] == "RE-ENTER"
    assert _unified_signal("STRONG YES", False, meaningful)[0] == "RE-ENTER"
    assert _unified_signal("CAUTIOUS YES", False, meaningful)[0] == "WAIT"
    assert _unified_signal("NO", False, meaningful)[0] == "WAIT"

    developing = row(v2_developing=True, v2_stabilizing=True)
    assert _unified_signal("STRONG YES", False, developing)[0] == "WAIT"

    no_setup = row()
    assert _unified_signal("STRONG YES", False, no_setup)[0] == "NO RE-ENTRY SETUP"


def test_canonical_early_entry_policy_preserves_validated_bias():
    signal, _, source = early_entry_decision(
        analog_decision="YES",
        weakness_present=False,
        internal_reset="DEVELOPING",
        selling_pressure="REPAIRING",
        existing_signal="WAIT",
    )
    assert signal == "RE-ENTER"
    assert source == "EARLY_INTERNAL_REPAIR"


def test_rejected_subsector_candidate_is_off_by_default():
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


def valid_snapshot():
    cell = {
        "n": 40,
        "median_return": 0.01,
        "positive_rate": 0.65,
        "median_max_drawdown": -0.01,
        "p10_max_drawdown": -0.03,
        "worst_max_drawdown": -0.08,
    }
    evidence = {
        symbol: {str(h): dict(cell) for h in EVIDENCE_HORIZONS}
        for symbol in ("SPY", "QQQ")
    }
    return {
        "schema_version": "2.0",
        "engine_version": ENGINE_VERSION,
        "as_of": "2026-09-03",
        "signal": "NO RE-ENTRY SETUP",
        "analog_decision": "YES",
        "market_state": "no material correction / stabilizing",
        "current_inputs": {},
        "signal_snapshot": {},
        "internal_reset": "NONE",
        "selling_pressure": "MIXED",
        "proxy_caveat": PROXY_CAVEAT,
        "analogs": [{"rank": i + 1, "date": "2020-01-01", "distance": 0.1} for i in range(40)],
        "extended_forward_evidence": evidence,
        "evidence_horizons": list(EVIDENCE_HORIZONS),
        "data_freshness": {"same_day_complete": True},
        "subsector_intelligence": {"proxy_caveat": SUBSECTOR_PROXY_CAVEAT},
        "subsector_decision_evidence": {"state": "NEUTRAL", "supports_early_entry": False},
        "early_entry_policy": {"subsector_can_resolve_mixed_repair": False},
    }


def test_contract_accepts_complete_snapshot():
    validate_snapshot(valid_snapshot(), require_same_day=True)


def test_contract_fails_closed_on_stale_live_snapshot():
    snapshot = valid_snapshot()
    snapshot["data_freshness"]["same_day_complete"] = False
    with pytest.raises(ValueError, match="same-day"):
        validate_snapshot(snapshot, require_same_day=True)


def test_contract_rejects_horizon_drift():
    snapshot = valid_snapshot()
    snapshot["evidence_horizons"] = [5, 7, 10]
    with pytest.raises(ValueError, match="horizons"):
        validate_snapshot(snapshot, require_same_day=True)


def test_contract_requires_exact_proxy_caveat():
    snapshot = valid_snapshot()
    snapshot["proxy_caveat"] = "ETF proxies"
    with pytest.raises(ValueError, match="proxy caveat"):
        validate_snapshot(snapshot, require_same_day=True)


def test_contract_requires_subsector_proxy_caveat():
    snapshot = valid_snapshot()
    snapshot["subsector_intelligence"]["proxy_caveat"] = "ETF proxies"
    with pytest.raises(ValueError, match="subsector proxy caveat"):
        validate_snapshot(snapshot, require_same_day=True)


def test_contract_rejects_reenabling_rejected_subsector_promotion():
    snapshot = valid_snapshot()
    snapshot["early_entry_policy"]["subsector_can_resolve_mixed_repair"] = True
    with pytest.raises(ValueError, match="must remain disabled"):
        validate_snapshot(snapshot, require_same_day=True)
