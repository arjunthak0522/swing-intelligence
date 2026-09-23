from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from reentry_nyse_context import classic_nyse_zweig, high_low_state, tick_state  # noqa: E402


def test_classic_nyse_zweig_requires_history() -> None:
    rows = [
        {"market_date": f"2026-09-{day:02d}", "advance_share": value}
        for day, value in zip(range(1, 10), [0.30, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90])
    ]
    result = classic_nyse_zweig(rows)
    assert result["state"] == "BUILDING HISTORY"
    assert result["triggered"] is False
    assert result["decision_input"] is False


def test_classic_nyse_zweig_triggers_only_after_classic_condition() -> None:
    rows = [
        {"market_date": f"2026-09-{day:02d}", "advance_share": value}
        for day, value in zip(range(1, 11), [0.30, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90])
    ]
    result = classic_nyse_zweig(rows)
    assert result["session_count"] == 10
    assert result["recent_10_session_low_ema"] <= 0.40
    assert result["current_10d_ema"] >= 0.615
    assert result["triggered"] is True
    assert result["state"] == "THRUST TRIGGERED"
    assert result["decision_input"] is False
    assert result["changes_deploy_trigger"] is False
    assert result["changes_recovery_stage"] is False


def test_context_states_are_descriptive_only() -> None:
    assert tick_state(900) == "STRONG BUYING"
    assert tick_state(-900) == "STRONG SELLING"
    assert high_low_state(100, 25) == "MORE NEW HIGHS"
    assert high_low_state(25, 100) == "MORE NEW LOWS"
