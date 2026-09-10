from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from reentry_unified_snapshot_finalize import build_quality


def complete_payload():
    return {
        "values": {
            "SPXA20R": 20.0,
            "NYMO": -30.0,
            "NAMO": -25.0,
            "NYUD": -100.0,
            "NAUD": -200.0,
            "nyse_down_up_ratio": 1.5,
            "nasdaq_down_up_ratio": 1.7,
            "MMFD": 25.0,
            "NASI_RSI": 28.0,
            "VVIX": 100.0,
            "SKEW_LIVE_PROXY": 3.0,
        },
        "mmfd_live": {"coverage_pct": 95.0},
        "vvix_live": {},
        "skew_live": {},
        "errors": {},
        "unified_engine": {"engine_version": "REENTRY_UNIFIED_v1"},
    }


def test_complete_payload_is_ok():
    result = build_quality(complete_payload())
    assert result["status"] == "OK"
    assert result["actionable"] is True
    assert result["issues"] == []


def test_missing_required_context_marks_degraded():
    payload = complete_payload()
    payload["values"]["SKEW_LIVE_PROXY"] = None
    result = build_quality(payload)
    assert result["status"] == "DEGRADED"
    assert result["actionable"] is False
    assert any("SKEW_PROXY" in issue for issue in result["issues"])


def test_mmfd_below_hard_floor_marks_degraded():
    payload = complete_payload()
    payload["mmfd_live"]["coverage_pct"] = 54.9
    result = build_quality(payload)
    assert result["status"] == "DEGRADED"
    assert result["actionable"] is False


def test_mmfd_usable_but_below_80_marks_partial():
    payload = complete_payload()
    payload["mmfd_live"]["coverage_pct"] = 70.0
    result = build_quality(payload)
    assert result["status"] == "PARTIAL"
    assert result["actionable"] is True
    assert result["warnings"]
