from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from reentry_engine import fetch_completed_twelve_close


def rsp_breadth_state(rs5: float, rs20: float) -> str:
    if rs5 > 0 and rs20 > 0:
        return "BROADENING"
    if rs5 > 0 and rs20 <= 0:
        return "REPAIRING"
    if rs5 <= 0 and rs20 > 0:
        return "COOLING"
    return "NARROWING"


def add_rsp_breadth(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Attach equal-weight participation to the canonical breadth diagnostics.

    RSP/SPY is intentionally *not* a hard gate, veto, or standalone RE-ENTER trigger.
    Incremental walk-forward testing found that adding RSP/SPY directly to analog
    distance weakened forward results and materially shifted many signals earlier.
    The engine therefore monitors RSP/SPY as a canonical breadth/participation input
    while preserving the validated decision math.
    """
    target = pd.Timestamp(snapshot["as_of"]).normalize()
    rsp = fetch_completed_twelve_close("RSP").sort_index()
    spy = fetch_completed_twelve_close("SPY").sort_index()
    ratio = (rsp / spy).dropna().loc[:target]
    if target not in ratio.index or len(ratio) < 21:
        raise RuntimeError(f"RSP/SPY breadth unavailable for completed session {target.date()}")

    rs5 = float(ratio.loc[target] / ratio.iloc[-6] - 1.0)
    rs20 = float(ratio.loc[target] / ratio.iloc[-21] - 1.0)
    rsp_close = float(rsp.loc[target])
    spy_close = float(spy.loc[target])
    if not all(np.isfinite(x) for x in (rs5, rs20, rsp_close, spy_close)):
        raise RuntimeError("Invalid RSP/SPY breadth values")

    state = rsp_breadth_state(rs5, rs20)
    block = {
        "as_of": str(target.date()),
        "rsp_close": rsp_close,
        "spy_close": spy_close,
        "rsp_spy_relative_5d": rs5,
        "rsp_spy_relative_20d": rs20,
        "state": state,
        "interpretation": {
            "BROADENING": "equal-weight S&P 500 participation is outperforming cap-weighted SPY over both 5D and 20D",
            "REPAIRING": "equal-weight participation is improving short term but remains behind over 20D",
            "COOLING": "equal-weight participation remains ahead over 20D but has softened over the last 5D",
            "NARROWING": "equal-weight participation is lagging cap-weighted SPY over both 5D and 20D",
        }[state],
        "decision_role": "canonical breadth/participation input; diagnostic/context only, not an independent gate, veto, or trigger",
        "validation_note": "direct inclusion in analog-distance decision math was rejected because incremental walk-forward results weakened and many signals shifted materially earlier",
    }

    snapshot["rsp_breadth"] = block
    snapshot.setdefault("current_inputs", {})["rsp_spy_relative_5d"] = rs5
    snapshot["current_inputs"]["rsp_spy_relative_20d"] = rs20
    snapshot["current_inputs"]["rsp_breadth_state"] = state
    signal_snapshot = snapshot.setdefault("signal_snapshot", {})
    breadth = signal_snapshot.setdefault("breadth", {})
    breadth["rsp_spy_relative_5d"] = rs5
    breadth["rsp_spy_relative_20d"] = rs20
    breadth["equal_weight_participation_state"] = state
    snapshot.setdefault("implementation", {}).setdefault("headline_market_inputs", []).append("RSP/SPY 5D and 20D relative strength (breadth context; non-gating)")
    return snapshot
