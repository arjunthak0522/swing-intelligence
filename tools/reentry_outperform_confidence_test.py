from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_confidence import feature_frame
from reentry_episode_exit_backtest import build_canonical_signal_history
from reentry_conditional_outperform_backtest import (
    episode_starts, independent, predict_for_symbol, fret, summarize, EVAL_H,
)
from reentry_subsector_intelligence import SUBSECTOR_SYMBOLS, build_subsector_frame, load_subsector_prices

MIN_MEDIAN_EXCESS = 0.01
MIN_POSITIVE_EXCESS_RATE = 0.60


def main():
    base = feature_frame(require_same_day=False)
    sig = build_canonical_signal_history(base)["signal"]
    px = load_subsector_prices(start="2016-09-01").sort_index()
    sf = build_subsector_frame(px)
    dates = independent([d for d in episode_starts(sig) if d in sf.index], px.index)

    selections = []
    for i, d in enumerate(dates):
        ranked = []
        for sym in SUBSECTOR_SYMBOLS:
            pred = predict_for_symbol(px, sf, dates, i, sym)
            if pred is None:
                continue
            if pred["score"] >= MIN_MEDIAN_EXCESS and pred["positive_excess_rate"] >= MIN_POSITIVE_EXCESS_RATE:
                ranked.append((sym, pred))
        ranked.sort(key=lambda x: (x[1]["score"], x[1]["positive_excess_rate"]), reverse=True)
        if ranked:
            selections.append((d, ranked[:3]))

    result = {
        "eligible_episodes": len(selections),
        "gate": {
            "minimum_predicted_median_excess_vs_spy": MIN_MEDIAN_EXCESS,
            "minimum_neighbor_positive_excess_rate": MIN_POSITIVE_EXCESS_RATE,
            "label": "OUTPERFORMANCE CANDIDATE",
        },
        "horizons": {},
    }
    for h in EVAL_H:
        basket=[]; spy=[]; qqq=[]; smh=[]; bspy=[]; bqqq=[]; bsmh=[]
        for d, ranks in selections:
            vals=[fret(px,d,s,h) for s,_ in ranks]
            vals=[x for x in vals if x is not None]
            r=float(np.mean(vals)) if vals else None
            s=fret(px,d,"SPY",h); q=fret(px,d,"QQQ",h); m=fret(px,d,"SMH",h)
            basket.append(r); spy.append(s); qqq.append(q); smh.append(m)
            if r is not None and s is not None: bspy.append(r>s)
            if r is not None and q is not None: bqqq.append(r>q)
            if r is not None and m is not None: bsmh.append(r>m)
        result["horizons"][str(h)] = {
            "candidates": summarize(basket), "SPY": summarize(spy), "QQQ": summarize(qqq), "SMH_static": summarize(smh),
            "beat_SPY_rate": float(np.mean(bspy)) if bspy else None,
            "beat_QQQ_rate": float(np.mean(bqqq)) if bqqq else None,
            "beat_SMH_rate": float(np.mean(bsmh)) if bsmh else None,
        }

    out=Path("artifacts/reentry_outperform_confidence"); out.mkdir(parents=True,exist_ok=True)
    (out/"results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))

if __name__ == "__main__":
    main()
