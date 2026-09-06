from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_confidence import feature_frame
from reentry_episode_exit_backtest import build_canonical_signal_history
from reentry_subsector_intelligence import (
    LABEL_BY_SYMBOL,
    PARENT_BY_SYMBOL,
    SUBSECTOR_SYMBOLS,
    load_subsector_prices,
)

HORIZONS = (5, 10, 15, 30, 60)
ROUND_TRIP_COST = 0.001
COOLDOWN = 10
SECTOR_LABELS = {
    "XLC": "Communication Services",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLV": "Health Care",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLK": "Technology",
    "XLU": "Utilities",
}
SECTORS = list(SECTOR_LABELS)


def episode_starts(signals: pd.Series) -> list[pd.Timestamp]:
    starts = signals.eq("RE-ENTER") & ~signals.shift(1, fill_value="").eq("RE-ENTER")
    return [pd.Timestamp(d) for d in signals.index[starts]]


def independent_starts(starts: list[pd.Timestamp], index: pd.Index, cooldown: int = COOLDOWN) -> list[pd.Timestamp]:
    out: list[pd.Timestamp] = []
    last_pos = -10000
    for d in starts:
        if d not in index:
            continue
        pos = index.get_loc(d)
        if isinstance(pos, (int, np.integer)) and int(pos) - last_pos > cooldown:
            out.append(d)
            last_pos = int(pos)
    return out


def outcome(prices: pd.DataFrame, signal_date: pd.Timestamp, symbol: str, horizon: int) -> float | None:
    if symbol not in prices.columns or signal_date not in prices.index:
        return None
    pos = prices.index.get_loc(signal_date)
    if not isinstance(pos, (int, np.integer)):
        return None
    entry_i = int(pos) + 1
    exit_i = entry_i + horizon
    if exit_i >= len(prices):
        return None
    entry = prices[symbol].iloc[entry_i]
    exit_px = prices[symbol].iloc[exit_i]
    if pd.isna(entry) or pd.isna(exit_px) or float(entry) <= 0:
        return None
    return float(exit_px / entry - 1.0 - ROUND_TRIP_COST)


def summarize(values: list[float]) -> dict:
    a = np.asarray(values, dtype=float)
    if len(a) == 0:
        return {"n": 0, "median": None, "mean": None, "positive_rate": None, "p25": None, "p75": None}
    return {
        "n": int(len(a)),
        "median": float(np.median(a)),
        "mean": float(np.mean(a)),
        "positive_rate": float(np.mean(a > 0)),
        "p25": float(np.quantile(a, 0.25)),
        "p75": float(np.quantile(a, 0.75)),
    }


def evaluate_universe(prices: pd.DataFrame, starts: list[pd.Timestamp], symbols: list[str], kind: str) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for sym in symbols:
        rec: dict = {
            "symbol": sym,
            "kind": kind,
            "label": SECTOR_LABELS.get(sym, LABEL_BY_SYMBOL.get(sym, sym)),
            "parent": PARENT_BY_SYMBOL.get(sym),
            "horizons": {},
        }
        score_parts = []
        for h in HORIZONS:
            vals = [x for d in starts if (x := outcome(prices, d, sym, h)) is not None]
            spy_vals = [x for d in starts if (x := outcome(prices, d, "SPY", h)) is not None]
            s = summarize(vals)
            spy = summarize(spy_vals)
            s["median_excess_vs_spy"] = None if s["median"] is None or spy["median"] is None else float(s["median"] - spy["median"])
            rec["horizons"][str(h)] = s
            if h in (10, 15, 30, 60) and s["median"] is not None and s["positive_rate"] is not None:
                score_parts.append((s["median"] * 100.0) + max(0.0, s["positive_rate"] - 0.5))
        rec["consistency_score"] = float(np.mean(score_parts)) if score_parts else None
        results[sym] = rec
    return results


def ranked(results: dict[str, dict], horizon: int, min_n: int = 40) -> list[dict]:
    rows = []
    for rec in results.values():
        h = rec["horizons"][str(horizon)]
        if h["n"] < min_n or h["median"] is None:
            continue
        rows.append({
            "symbol": rec["symbol"],
            "label": rec["label"],
            "parent": rec["parent"],
            "n": h["n"],
            "median": h["median"],
            "mean": h["mean"],
            "positive_rate": h["positive_rate"],
            "median_excess_vs_spy": h["median_excess_vs_spy"],
        })
    return sorted(rows, key=lambda x: (x["median"], x["positive_rate"]), reverse=True)


def consistent_rank(results: dict[str, dict], min_n: int = 40) -> list[dict]:
    rows = []
    for rec in results.values():
        eligible = all(rec["horizons"][str(h)]["n"] >= min_n for h in (10, 15, 30, 60))
        if not eligible or rec["consistency_score"] is None:
            continue
        rows.append({
            "symbol": rec["symbol"],
            "label": rec["label"],
            "parent": rec["parent"],
            "consistency_score": rec["consistency_score"],
            "median_10d": rec["horizons"]["10"]["median"],
            "median_15d": rec["horizons"]["15"]["median"],
            "median_30d": rec["horizons"]["30"]["median"],
            "median_60d": rec["horizons"]["60"]["median"],
            "positive_30d": rec["horizons"]["30"]["positive_rate"],
            "positive_60d": rec["horizons"]["60"]["positive_rate"],
        })
    return sorted(rows, key=lambda x: x["consistency_score"], reverse=True)


def main() -> None:
    base = feature_frame(require_same_day=False)
    signals = build_canonical_signal_history(base)
    prices = load_subsector_prices(start="2016-09-01").sort_index()
    common_idx = signals.index.intersection(prices.index)
    starts_all = [d for d in episode_starts(signals["signal"]) if d in common_idx]
    starts_independent = independent_starts(starts_all, prices.index)

    available_sectors = [s for s in SECTORS if s in prices.columns]
    available_subsectors = [s for s in SUBSECTOR_SYMBOLS if s in prices.columns]

    sector_results = evaluate_universe(prices, starts_independent, available_sectors, "sector")
    subsector_results = evaluate_universe(prices, starts_independent, available_subsectors, "subsector")

    payload = {
        "status": "CANONICAL_REENTRY_SECTOR_SUBSECTOR_RANKING",
        "methodology": {
            "signal": "first completed-close RE-ENTER day of each contiguous canonical episode",
            "execution": "next-session close",
            "round_trip_cost": ROUND_TRIP_COST,
            "independent_episode_cooldown_sessions": COOLDOWN,
            "horizons": list(HORIZONS),
            "ranking_sample": "10-session cooldown subset used to reduce double-counting of clustered signals",
            "proxy_caveat": "Sector/subsector results use liquid ETF proxies and their actual available histories; newer ETFs therefore have smaller samples.",
        },
        "episode_counts": {
            "all_contiguous_starts_with_price_data": len(starts_all),
            "independent_cooldown_subset": len(starts_independent),
        },
        "coverage": {
            "sectors": available_sectors,
            "subsectors": available_subsectors,
        },
        "sector_results": sector_results,
        "subsector_results": subsector_results,
        "rankings": {
            "sectors": {str(h): ranked(sector_results, h) for h in HORIZONS},
            "subsectors": {str(h): ranked(subsector_results, h) for h in HORIZONS},
            "sectors_consistent": consistent_rank(sector_results),
            "subsectors_consistent": consistent_rank(subsector_results),
        },
    }

    out = Path("artifacts/reentry_sector_subsector_ranking")
    out.mkdir(parents=True, exist_ok=True)
    (out / "ranking.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    rows = []
    for universe, results in (("sector", sector_results), ("subsector", subsector_results)):
        for rec in results.values():
            for h in HORIZONS:
                x = rec["horizons"][str(h)]
                rows.append({
                    "universe": universe,
                    "symbol": rec["symbol"],
                    "label": rec["label"],
                    "parent": rec["parent"],
                    "horizon": h,
                    **x,
                })
    pd.DataFrame(rows).to_csv(out / "ranking.csv", index=False)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
