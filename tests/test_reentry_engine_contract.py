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
    }
    base.update(overrides)
    return pd.Series(base)


def test_frozen_weakness_thresholds():
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


def test_strategy_mapping_is_frozen():
    assert strategy_signal("YES", True)[0] == "RE-ENTER"
    assert strategy_signal("CAUTIOUS YES", True)[0] == "RE-ENTER"
    assert strategy_signal("STRONG YES", True)[0] == "RE-ENTER"
    assert strategy_signal("NO", True)[0] == "WAIT"
    assert strategy_signal("YES", False)[0] == "NO RE-ENTRY SETUP"


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
        "schema_version": "1.0",
        "engine_version": ENGINE_VERSION,
        "as_of": "2026-09-03",
        "signal": "NO RE-ENTRY SETUP",
        "analog_decision": "YES",
        "market_state": "no material correction / stabilizing",
        "current_inputs": {},
        "analogs": [{"rank": i + 1, "date": "2020-01-01", "distance": 0.1} for i in range(40)],
        "extended_forward_evidence": evidence,
        "evidence_horizons": list(EVIDENCE_HORIZONS),
        "data_freshness": {"same_day_complete": True},
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
