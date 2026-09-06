from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from reentry_subsector_intelligence import LABEL_BY_SYMBOL, PARENT_BY_SYMBOL, SUBSECTOR_SYMBOLS


def _zscore(values: pd.Series) -> pd.Series:
    vals = pd.to_numeric(values, errors="coerce")
    std = float(vals.std(ddof=0))
    if not np.isfinite(std) or std == 0:
        return pd.Series(0.0, index=vals.index)
    return (vals - float(vals.mean())) / std


def rank_subsector_outperformance(row: pd.Series, top_n: int = 5) -> list[dict[str, Any]]:
    """Rank audited subsector ETFs using only contemporaneous state.

    This is an advisory ranking layer, not a RE-ENTRY trigger. It favors:
    - improving relative strength versus the parent sector,
    - positive 5-day repair momentum,
    - meaningful-but-not-extreme reset depth,
    - explicit repair state.
    """
    rows: list[dict[str, Any]] = []
    for symbol in SUBSECTOR_SYMBOLS:
        required = [
            f"sub_{symbol}_ret5",
            f"sub_{symbol}_dd20",
            f"sub_{symbol}_rs20_parent",
            f"sub_{symbol}_rs60_parent",
        ]
        if any(k not in row.index or pd.isna(row[k]) for k in required):
            continue
        dd20 = float(row[f"sub_{symbol}_dd20"])
        ret5 = float(row[f"sub_{symbol}_ret5"])
        rs20_parent = float(row[f"sub_{symbol}_rs20_parent"])
        rs60_parent = float(row[f"sub_{symbol}_rs60_parent"])
        repairing = bool(row.get(f"sub_{symbol}_repair", False))
        rows.append({
            "symbol": symbol,
            "label": LABEL_BY_SYMBOL[symbol],
            "parent_sector": PARENT_BY_SYMBOL[symbol],
            "ret5": ret5,
            "dd20": dd20,
            "rs20_parent": rs20_parent,
            "rs_trend": rs20_parent - rs60_parent,
            "repairing": repairing,
        })
    if not rows:
        return []

    frame = pd.DataFrame(rows).set_index("symbol")
    # Reset opportunity peaks around a moderate correction; avoid rewarding the deepest damage blindly.
    reset_opportunity = -(frame["dd20"] + 0.04).abs()
    score = (
        0.35 * _zscore(frame["rs20_parent"])
        + 0.30 * _zscore(frame["rs_trend"])
        + 0.20 * _zscore(frame["ret5"])
        + 0.10 * _zscore(reset_opportunity)
        + 0.05 * frame["repairing"].astype(float)
    )
    frame["score"] = score
    frame = frame.sort_values(["score", "rs_trend", "ret5"], ascending=False)

    out: list[dict[str, Any]] = []
    for symbol, item in frame.head(top_n).iterrows():
        reasons: list[str] = []
        if item["rs_trend"] > 0:
            reasons.append("relative strength improving vs parent")
        if item["ret5"] > 0:
            reasons.append("positive 5-day repair momentum")
        if bool(item["repairing"]):
            reasons.append("repair signal active")
        if -0.08 <= item["dd20"] <= -0.02:
            reasons.append("meaningful reset without extreme damage")
        out.append({
            "rank": len(out) + 1,
            "symbol": symbol,
            "label": item["label"],
            "parent_sector": item["parent_sector"],
            "score": float(item["score"]),
            "reasons": reasons[:3],
            "metrics": {
                "return_5d": float(item["ret5"]),
                "drawdown_20d": float(item["dd20"]),
                "relative_strength_20d_vs_parent": float(item["rs20_parent"]),
                "relative_strength_trend": float(item["rs_trend"]),
            },
        })
    return out
