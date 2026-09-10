from __future__ import annotations

from typing import Any

RULE_VERSION = "UNIFIED_REENTRY_v1"


def evaluate_unified_reentry(
    *,
    oversold_gate: bool,
    fast_family_count: int,
    mmfd_improving: bool = False,
    nasi_turning_up: bool = False,
    vvix_easing: bool = False,
    skew_narrowing: bool = False,
    mode: str,
) -> dict[str, Any]:
    """One operational RE-ENTRY rule for intraday and completed-close data.

    The only permitted difference between modes is input finality. Intraday inputs may be
    provisional; CLOSE inputs must represent a completed session. Decision semantics are
    identical in both modes.
    """
    context = {
        "MMFD_IMPROVING": bool(mmfd_improving),
        "NASI_TURNING_UP": bool(nasi_turning_up),
        "VVIX_EASING": bool(vvix_easing),
        "SKEW_NARROWING": bool(skew_narrowing),
    }
    context_count = sum(context.values())
    fast_count = max(0, int(fast_family_count))

    if not oversold_gate:
        state, action = "INACTIVE", "WAIT"
    elif fast_count >= 2:
        state, action = "EARLY_GO", "GO_EARLY"
    elif fast_count >= 1 and context_count >= 1:
        state, action = "EARLY_GO", "GO_EARLY"
    elif fast_count >= 1 or context_count >= 2:
        state, action = "WATCH", "WATCH_EARLY_TURN"
    else:
        state, action = "WAIT", "WAIT_FOR_WASHOUT"

    return {
        "rule_version": RULE_VERSION,
        "mode": mode.upper(),
        "oversold_gate": bool(oversold_gate),
        "fast_family_count": fast_count,
        "context_support_count": context_count,
        "context_support": context,
        "state": state,
        "candidate_action": action,
        "logic": "GO when oversold and either 2+ fast families turn, or 1 fast family plus 1 independent context turn from MMFD/NASI/VVIX/SKEW.",
    }
