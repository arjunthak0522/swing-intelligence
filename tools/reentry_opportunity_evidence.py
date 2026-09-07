from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RANKING_PATH = Path("artifacts/reentry_sector_subsector_ranking/ranking.json")
HORIZONS = (10, 30, 60)


def _history(rec: dict[str, Any] | None) -> dict[str, Any] | None:
    if not rec:
        return None
    horizons = rec.get("horizons", {})
    out: dict[str, Any] = {}
    for h in HORIZONS:
        row = horizons.get(str(h), {})
        if row.get("n", 0) <= 0:
            continue
        out[str(h)] = {
            "n": int(row.get("n", 0)),
            "median": row.get("median"),
            "positive_rate": row.get("positive_rate"),
            "median_excess_vs_spy": row.get("median_excess_vs_spy"),
        }
    return out or None


def attach_opportunity_evidence(snapshot: dict[str, Any], ranking_path: Path = RANKING_PATH) -> dict[str, Any]:
    """Attach current repair candidates plus historical post-RE-ENTRY evidence.

    This does not create a sector/subsector timing signal. Current repair state comes
    from the existing subsector intelligence layer; historical statistics come from
    canonical RE-ENTRY episode outcomes. The broad-market decision remains the timing
    decision.
    """
    out = dict(snapshot)
    if not ranking_path.exists():
        out["opportunity_evidence"] = {
            "status": "HISTORICAL_RANKING_UNAVAILABLE",
            "role": "context only; broad-market RE-ENTRY remains the timing decision",
            "sectors": [],
            "subsectors": [],
        }
        return out

    ranking = json.loads(ranking_path.read_text(encoding="utf-8"))
    sector_results = ranking.get("sector_results", {})
    subsector_results = ranking.get("subsector_results", {})

    by_sector = snapshot.get("subsector_intelligence", {}).get("by_sector", {})
    proxies = snapshot.get("subsector_intelligence", {}).get("proxies", {})

    sectors: list[dict[str, Any]] = []
    for symbol, group in by_sector.items():
        damage3 = float(group.get("damage_share_3pct", 0.0) or 0.0)
        repair = float(group.get("repair_share", 0.0) or 0.0)
        if damage3 < 0.50 or repair < 0.25:
            continue
        rec = sector_results.get(symbol)
        sectors.append({
            "symbol": symbol,
            "label": (rec or {}).get("label", symbol),
            "current_state": "REPAIRING",
            "damage_share_3pct": damage3,
            "repair_share": repair,
            "historical_after_reentry": _history(rec),
        })

    subsectors: list[dict[str, Any]] = []
    for symbol, item in proxies.items():
        if not bool(item.get("repairing", False)):
            continue
        rec = subsector_results.get(symbol)
        subsectors.append({
            "symbol": symbol,
            "label": str(item.get("label", (rec or {}).get("label", symbol))),
            "parent_sector": str(item.get("parent_sector", (rec or {}).get("parent") or "")),
            "current_state": "REPAIRING",
            "drawdown_20d": float(item.get("drawdown_20d", 0.0) or 0.0),
            "return_5d": float(item.get("return_5d", 0.0) or 0.0),
            "historical_after_reentry": _history(rec),
        })

    def _sort_key(row: dict[str, Any]) -> tuple[float, float]:
        hist = row.get("historical_after_reentry") or {}
        h30 = hist.get("30", {})
        return (float(h30.get("median") or -999.0), float(h30.get("positive_rate") or -999.0))

    sectors.sort(key=_sort_key, reverse=True)
    subsectors.sort(key=_sort_key, reverse=True)

    out["opportunity_evidence"] = {
        "status": "CURRENT_REPAIR_PLUS_CANONICAL_HISTORY",
        "role": (
            "Current repair candidates plus historical outcomes after canonical RE-ENTRY episodes. "
            "This is not a standalone sector/subsector timing signal; the broad-market RE-ENTRY decision remains controlling."
        ),
        "methodology": ranking.get("methodology", {}),
        "sectors": sectors,
        "subsectors": subsectors,
    }
    return out
