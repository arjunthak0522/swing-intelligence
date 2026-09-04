from __future__ import annotations

from typing import Any

import pandas as pd


def _pct(value: float) -> str:
    return f"{value * 100:+.1f}%"


def _num(value: Any, default: float = 0.0) -> float:
    return default if value is None or pd.isna(value) else float(value)


def build_prioritized_market_commentary(snapshot: dict[str, Any]) -> dict[str, Any]:
    subsectors = snapshot.get("subsector_intelligence", {})
    sectors = snapshot.get("signal_snapshot", {}).get("sectors", {})
    factors = snapshot.get("signal_snapshot", {}).get("factors", {})
    leadership = set(snapshot.get("factor_leadership_state", []))

    sector_candidates: list[dict[str, Any]] = []
    for symbol, item in sectors.items():
        dd20 = _num(item.get("drawdown_20d"))
        rs20 = _num(item.get("relative_strength_20d_vs_spy"))
        group = subsectors.get("by_sector", {}).get(symbol, {})
        sub_damage = _num(group.get("damage_share_3pct"))
        sub_repair = _num(group.get("repair_share"))
        hidden = sub_damage >= 0.50 and dd20 > -0.03
        repairing = sub_repair >= 0.50 and (dd20 <= -0.02 or sub_damage >= 0.50)
        warranted = hidden or repairing or dd20 <= -0.03 or rs20 <= -0.02
        if not warranted:
            continue

        if hidden:
            text = (
                f"{symbol} looks relatively mild at the headline level ({_pct(dd20)} from its 20-day high), "
                f"but {sub_damage:.0%} of tracked groups are down at least 3% - hidden internal damage is materially worse than the sector ETF suggests."
            )
            score = 5.0 + sub_damage + abs(dd20)
        elif repairing:
            text = (
                f"{symbol} remains internally damaged, but {sub_repair:.0%} of tracked groups are repairing - "
                "a constructive early-recovery signal beneath the sector level."
            )
            score = 4.0 + sub_repair + abs(dd20)
        else:
            text = f"{symbol} is {_pct(dd20)} from its 20-day high with {_pct(rs20)} 20-day relative strength versus SPY."
            score = 2.0 + abs(min(dd20, 0.0)) + abs(min(rs20, 0.0))

        sector_candidates.append({
            "sector": symbol,
            "commentary": text,
            "hidden_subsector_damage": hidden,
            "subsector_repairing": repairing,
            "priority_score": score,
        })

    subsector_candidates: list[dict[str, Any]] = []
    for symbol, item in subsectors.get("proxies", {}).items():
        dd20 = _num(item.get("drawdown_20d"))
        rs_parent = _num(item.get("relative_strength_20d_vs_parent"))
        ret1 = _num(item.get("return_1d"))
        ret5 = _num(item.get("return_5d"))
        repairing = bool(item.get("repairing"))
        warranted = repairing or dd20 <= -0.03 or rs_parent <= -0.025
        if not warranted:
            continue

        if repairing:
            text = (
                f"{symbol} ({item['label']}) is repairing after a meaningful reset: {_pct(dd20)} from its 20-day high, "
                f"{_pct(ret1)} today and {_pct(ret5)} over 5 days."
            )
            score = 6.0 + abs(dd20)
        elif dd20 <= -0.05:
            text = (
                f"{symbol} ({item['label']}) is in a deep internal correction: {_pct(dd20)} from its 20-day high, "
                f"{_pct(rs_parent)} relative to {item['parent_sector']} over 20 days."
            )
            score = 5.0 + abs(dd20) + abs(min(rs_parent, 0.0))
        elif dd20 <= -0.03:
            text = (
                f"{symbol} ({item['label']}) is in a meaningful internal correction: {_pct(dd20)} from its 20-day high, "
                f"{_pct(rs_parent)} relative to {item['parent_sector']} over 20 days."
            )
            score = 4.0 + abs(dd20) + abs(min(rs_parent, 0.0))
        else:
            text = f"{symbol} ({item['label']}) is materially lagging {item['parent_sector']} by {_pct(rs_parent)} over 20 days."
            score = 3.0 + abs(rs_parent)

        subsector_candidates.append({
            "symbol": symbol,
            "label": item["label"],
            "parent_sector": item["parent_sector"],
            "repairing": repairing,
            "commentary": text,
            "priority_score": score,
        })

    factor_candidates: list[dict[str, Any]] = []
    for symbol, item in factors.items():
        dd20 = _num(item.get("drawdown_20d"))
        rs20 = _num(item.get("relative_strength_20d_vs_spy"))
        if dd20 > -0.03 and rs20 > -0.02:
            continue
        factor_candidates.append({
            "factor": symbol,
            "commentary": f"{symbol} is {_pct(dd20)} from its 20-day high and {_pct(rs20)} versus SPY over 20 days.",
            "priority_score": 3.0 + abs(min(dd20, 0.0)) + abs(min(rs20, 0.0)),
        })

    if "MOMENTUM RESET" in leadership:
        factor_candidates.append({
            "factor": "MTUM",
            "commentary": "Momentum leadership is in a material reset relative to the broad market.",
            "priority_score": 6.0,
        })
    if "GROWTH RESET" in leadership:
        factor_candidates.append({
            "factor": "IWF/IWD",
            "commentary": "Growth is resetting relative to value, consistent with internal leadership rotation.",
            "priority_score": 5.5,
        })

    # Deduplicate factors while preserving the highest-priority description.
    dedup_factors: dict[str, dict[str, Any]] = {}
    for item in factor_candidates:
        key = item["factor"]
        if key not in dedup_factors or item["priority_score"] > dedup_factors[key]["priority_score"]:
            dedup_factors[key] = item

    sector_candidates.sort(key=lambda x: x["priority_score"], reverse=True)
    subsector_candidates.sort(key=lambda x: x["priority_score"], reverse=True)
    factor_candidates = sorted(dedup_factors.values(), key=lambda x: x["priority_score"], reverse=True)

    surfaced_sectors = sector_candidates[:6]
    surfaced_subsectors = subsector_candidates[:10]
    surfaced_factors = factor_candidates[:6]

    if not sector_candidates and not subsector_candidates and not factor_candidates:
        summary = "No material sector, subsector, or factor dislocation warrants additional commentary today."
    else:
        repairing_names = [x["symbol"] for x in subsector_candidates if x["repairing"]][:3]
        hidden_names = [x["sector"] for x in sector_candidates if x["hidden_subsector_damage"]][:3]
        parts = []
        if hidden_names:
            parts.append(f"hidden damage is notable beneath {', '.join(hidden_names)}")
        if repairing_names:
            parts.append(f"repair is emerging in {', '.join(repairing_names)}")
        if not parts:
            parts.append("material internal damage or relative-strength divergence is present")
        summary = "Market internals warrant attention: " + "; ".join(parts) + "."

    for collection in (surfaced_sectors, surfaced_subsectors, surfaced_factors):
        for item in collection:
            item.pop("priority_score", None)

    return {
        "summary": summary,
        "sectors": surfaced_sectors,
        "subsectors": surfaced_subsectors,
        "factors": surfaced_factors,
        "counts": {
            "warranted_sectors": len(sector_candidates),
            "warranted_subsectors": len(subsector_candidates),
            "warranted_factors": len(factor_candidates),
        },
        "commentary_policy": (
            "Commentary is surfaced only for material damage, hidden parent/subsector divergence, relative-strength weakness, or genuine repair. "
            "Hidden damage and repair are prioritized ahead of simple raw drawdown magnitude."
        ),
    }
