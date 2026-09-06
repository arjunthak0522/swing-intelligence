from __future__ import annotations

from typing import Any

import pandas as pd

from reentry_confidence import feature_frame
from reentry_episode_exit_backtest import build_canonical_signal_history
from reentry_conditional_outperform_backtest import episode_starts, independent, predict_for_symbol
from reentry_subsector_intelligence import build_subsector_frame, load_subsector_prices
from reentry_subsector_proxy_universe import LABEL_BY_SYMBOL, PARENT_BY_SYMBOL, SUBSECTOR_SYMBOLS

MIN_MEDIAN_EXCESS = 0.01
MIN_POSITIVE_EXCESS_RATE = 0.60
MAX_CANDIDATES = 3


def add_outperformance_highlights(snapshot: dict[str, Any]) -> dict[str, Any]:
    signal = snapshot.get("signal")
    result: dict[str, Any] = {
        "status": "INACTIVE" if signal != "RE-ENTER" else "NO_HIGH_CONFIDENCE_EDGE",
        "label": "OUTPERFORMANCE CANDIDATE",
        "as_of": snapshot.get("as_of"),
        "candidate_count": 0,
        "candidates": [],
        "gate": {
            "minimum_predicted_median_excess_vs_spy": MIN_MEDIAN_EXCESS,
            "minimum_neighbor_positive_excess_rate": MIN_POSITIVE_EXCESS_RATE,
        },
        "interpretation": (
            "Sector/subsector selection is inactive until the official RE-ENTRY signal is favorable."
            if signal != "RE-ENTER"
            else "No sector/subsector ETF currently clears the validated high-confidence outperformance gate."
        ),
        "methodology": "Prior-only nearest-neighbor comparison using historical RE-ENTRY episodes; advisory only and never changes the official RE-ENTRY decision.",
    }
    snapshot["outperformance_intelligence"] = result
    if signal != "RE-ENTER":
        return snapshot

    as_of = pd.Timestamp(str(snapshot.get("as_of"))).tz_localize(None).normalize()
    base = feature_frame(require_same_day=False)
    sig = build_canonical_signal_history(base)["signal"]
    px = load_subsector_prices(start="2016-09-01").sort_index()
    sf = build_subsector_frame(px)
    if as_of not in sf.index:
        return snapshot

    history_dates = independent(
        [d for d in episode_starts(sig) if d in sf.index and d < as_of],
        px.index,
    )
    dates = [*history_dates, as_of]
    current_i = len(dates) - 1
    ranked: list[tuple[str, dict[str, Any]]] = []
    for sym in SUBSECTOR_SYMBOLS:
        pred = predict_for_symbol(px, sf, dates, current_i, sym)
        if pred is None:
            continue
        if pred["score"] < MIN_MEDIAN_EXCESS or pred["positive_excess_rate"] < MIN_POSITIVE_EXCESS_RATE:
            continue
        ranked.append((sym, pred))

    ranked.sort(key=lambda x: (x[1]["score"], x[1]["positive_excess_rate"]), reverse=True)
    candidates = []
    for rank, (sym, pred) in enumerate(ranked[:MAX_CANDIDATES], start=1):
        candidates.append({
            "rank": rank,
            "symbol": sym,
            "label": LABEL_BY_SYMBOL.get(sym, sym),
            "parent_sector": PARENT_BY_SYMBOL.get(sym),
            "predicted_median_excess_vs_spy": float(pred["score"]),
            "neighbor_positive_excess_rate": float(pred["positive_excess_rate"]),
            "neighbors": int(pred["neighbors"]),
        })

    if candidates:
        result["status"] = "HIGH_CONFIDENCE_CANDIDATES"
        result["candidate_count"] = len(candidates)
        result["candidates"] = candidates
        result["interpretation"] = "These ETFs have the strongest historically supported relative setups among the tracked subsectors for this RE-ENTRY state."
    snapshot["outperformance_intelligence"] = result
    return snapshot
