from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from internal_correction_v2 import HORIZONS, PRIMARY_COOLDOWN, cooldown_dates, forward_stats
from reentry_subsector_intelligence import SUBSECTOR_GROUPS, build_subsector_frame, load_subsector_prices


def _parent_dd20(prices: pd.DataFrame, parent: str) -> pd.Series:
    return prices[parent] / prices[parent].rolling(20).max() - 1.0


def main() -> None:
    prices = load_subsector_prices()
    frame = build_subsector_frame(prices)

    hidden_parts = []
    repair_parts = []
    per_sector = {}

    for parent, groups in SUBSECTOR_GROUPS.items():
        if parent not in prices.columns or f"sub_{parent}_damage_share_3" not in frame.columns:
            continue
        parent_dd = _parent_dd20(prices, parent).reindex(frame.index)
        damage_share = frame[f"sub_{parent}_damage_share_3"]
        repair_share = frame[f"sub_{parent}_repair_share"]

        # Parent looks relatively mild while at least half of tracked groups are already in a 3% correction.
        hidden = (parent_dd > -0.03) & (damage_share >= 0.50)
        # A damaged internal group starts repairing. This is diagnostic research only.
        repairing = (damage_share >= 0.50) & (repair_share >= (1 / max(2, len(groups))))

        hidden_parts.append(hidden.rename(parent))
        repair_parts.append(repairing.rename(parent))
        per_sector[parent] = {
            "tracked_groups": [symbol for symbol, _ in groups],
            "hidden_damage_days": int(hidden.fillna(False).sum()),
            "repair_days": int(repairing.fillna(False).sum()),
        }

    hidden_matrix = pd.concat(hidden_parts, axis=1).fillna(False)
    repair_matrix = pd.concat(repair_parts, axis=1).fillna(False)
    hidden_count = hidden_matrix.astype(int).sum(axis=1)
    repair_count = repair_matrix.astype(int).sum(axis=1)

    states = {
        "hidden_subsector_damage": hidden_count >= 1,
        "broad_hidden_subsector_damage": hidden_count >= 2,
        "subsector_repair": repair_count >= 1,
        "broad_subsector_repair": repair_count >= 2,
        "hidden_damage_plus_repair": (hidden_count >= 1) & (repair_count >= 1),
    }

    results = {}
    for name, mask in states.items():
        dates = cooldown_dates(mask.fillna(False), PRIMARY_COOLDOWN)
        results[name] = {
            "events": len(dates),
            "SPY": {str(h): forward_stats(prices, dates, "SPY", h) for h in HORIZONS},
            "QQQ": {str(h): forward_stats(prices, dates, "QQQ", h) for h in HORIZONS},
            "era_counts": {
                "2016_2020": sum(d < pd.Timestamp("2021-01-01") for d in dates),
                "2021_present": sum(d >= pd.Timestamp("2021-01-01") for d in dates),
            },
        }

    latest = frame.iloc[-1]
    latest_by_sector = {}
    for parent in SUBSECTOR_GROUPS:
        key = f"sub_{parent}_damage_share_3"
        if key not in frame.columns:
            continue
        latest_by_sector[parent] = {
            "damage_share_3pct": float(latest[key]),
            "repair_share": float(latest[f"sub_{parent}_repair_share"]),
            "median_drawdown_20d": float(latest[f"sub_{parent}_median_dd20"]),
        }

    payload = {
        "status": "RESEARCH_ONLY_SUBSECTOR_DIAGNOSTIC",
        "sample_start": str(frame.index.min().date()),
        "sample_end": str(frame.index.max().date()),
        "design": (
            "Tests whether corrections hidden beneath relatively mild parent-sector ETFs, and subsequent subgroup repair, "
            "carry useful forward-market information. These states do not alter the RE-ENTRY decision rule."
        ),
        "states": results,
        "per_sector_counts": per_sector,
        "latest": {
            "date": str(frame.index[-1].date()),
            "aggregate_damage_share_2pct": float(latest.get("subsector_damage_share_2", float("nan"))),
            "aggregate_damage_share_3pct": float(latest.get("subsector_damage_share_3", float("nan"))),
            "aggregate_repair_share": float(latest.get("subsector_repair_share", float("nan"))),
            "by_sector": latest_by_sector,
        },
        "promotion_rule": (
            "Do not alter canonical RE-ENTRY thresholds unless subsector states show robust incremental value across eras and do not merely duplicate existing sector/factor information."
        ),
    }

    out = Path("artifacts/internal_correction_v2")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "subsector_validation.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
