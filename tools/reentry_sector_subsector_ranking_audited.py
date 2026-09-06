from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from reentry_confidence import feature_frame
from reentry_episode_exit_backtest import build_canonical_signal_history
from reentry_subsector_proxy_universe import (
    AUDIT_NOTES,
    LABEL_BY_SYMBOL,
    PARENT_BY_SYMBOL,
    SUBSECTOR_SYMBOLS,
    SUPPORTING_PROXIES,
)

HORIZONS = (5, 10, 15, 30, 60)
ROUND_TRIP_COST = 0.001
COOLDOWN = 10
SECTOR_LABELS = {
    "XLC": "Communication Services", "XLY": "Consumer Discretionary", "XLP": "Consumer Staples",
    "XLE": "Energy", "XLF": "Financials", "XLV": "Health Care", "XLI": "Industrials",
    "XLB": "Materials", "XLRE": "Real Estate", "XLK": "Technology", "XLU": "Utilities",
}
SECTORS = list(SECTOR_LABELS)


def load_prices(start: str = "2016-09-01") -> pd.DataFrame:
    symbols = sorted(set(["SPY", "QQQ"] + SECTORS + SUBSECTOR_SYMBOLS + list(SUPPORTING_PROXIES)))
    raw = yf.download(symbols, start=start, interval="1d", auto_adjust=True, progress=False, threads=True, group_by="column")
    if raw.empty:
        raise RuntimeError("ETF price download returned no data")
    if not isinstance(raw.columns, pd.MultiIndex) or "Close" not in raw.columns.get_level_values(0):
        raise RuntimeError("Unexpected Yahoo ETF schema")
    px = raw["Close"].copy().apply(pd.to_numeric, errors="coerce")
    px.index = pd.to_datetime(px.index).tz_localize(None).normalize()
    return px.sort_index()


def episode_starts(signals: pd.Series) -> list[pd.Timestamp]:
    starts = signals.eq("RE-ENTER") & ~signals.shift(1, fill_value="").eq("RE-ENTER")
    return [pd.Timestamp(d) for d in signals.index[starts]]


def independent_starts(starts: list[pd.Timestamp], index: pd.Index, cooldown: int = COOLDOWN) -> list[pd.Timestamp]:
    out, last_pos = [], -10000
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
    entry_i, exit_i = int(pos) + 1, int(pos) + 1 + horizon
    if exit_i >= len(prices):
        return None
    entry, exit_px = prices[symbol].iloc[entry_i], prices[symbol].iloc[exit_i]
    if pd.isna(entry) or pd.isna(exit_px) or float(entry) <= 0:
        return None
    return float(exit_px / entry - 1.0 - ROUND_TRIP_COST)


def summarize(values: list[float]) -> dict:
    a = np.asarray(values, dtype=float)
    if len(a) == 0:
        return {"n": 0, "median": None, "mean": None, "positive_rate": None, "p25": None, "p75": None}
    return {
        "n": int(len(a)), "median": float(np.median(a)), "mean": float(np.mean(a)),
        "positive_rate": float(np.mean(a > 0)), "p25": float(np.quantile(a, 0.25)),
        "p75": float(np.quantile(a, 0.75)),
    }


def evaluate(prices: pd.DataFrame, starts: list[pd.Timestamp], symbols: list[str], kind: str) -> dict[str, dict]:
    results = {}
    for sym in symbols:
        label = SECTOR_LABELS.get(sym, LABEL_BY_SYMBOL.get(sym, SUPPORTING_PROXIES.get(sym, {}).get("label", sym)))
        parent = PARENT_BY_SYMBOL.get(sym, SUPPORTING_PROXIES.get(sym, {}).get("parent"))
        rec = {"symbol": sym, "kind": kind, "label": label, "parent": parent, "horizons": {}}
        score_parts = []
        for h in HORIZONS:
            vals = [x for d in starts if (x := outcome(prices, d, sym, h)) is not None]
            spy_vals = [x for d in starts if (x := outcome(prices, d, "SPY", h)) is not None]
            s, spy = summarize(vals), summarize(spy_vals)
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
        rows.append({"symbol": rec["symbol"], "label": rec["label"], "parent": rec["parent"], **h})
    return sorted(rows, key=lambda x: (x["median"], x["positive_rate"]), reverse=True)


def consistent_rank(results: dict[str, dict], min_n: int = 40) -> list[dict]:
    rows = []
    for rec in results.values():
        if rec["consistency_score"] is None or not all(rec["horizons"][str(h)]["n"] >= min_n for h in (10, 15, 30, 60)):
            continue
        rows.append({
            "symbol": rec["symbol"], "label": rec["label"], "parent": rec["parent"],
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
    prices = load_prices().sort_index()
    common = signals.index.intersection(prices.index)
    starts_all = [d for d in episode_starts(signals["signal"]) if d in common]
    starts = independent_starts(starts_all, prices.index)

    sectors = [s for s in SECTORS if s in prices.columns]
    primary = [s for s in SUBSECTOR_SYMBOLS if s in prices.columns]
    supporting = [s for s in SUPPORTING_PROXIES if s in prices.columns]

    sector_results = evaluate(prices, starts, sectors, "sector")
    primary_results = evaluate(prices, starts, primary, "primary_subsector")
    supporting_results = evaluate(prices, starts, supporting, "supporting_diagnostic")

    payload = {
        "status": "AUDITED_REENTRY_SECTOR_SUBSECTOR_RANKING",
        "methodology": {
            "signal": "first completed-close RE-ENTER day of each contiguous canonical episode",
            "execution": "next-session close", "round_trip_cost": ROUND_TRIP_COST,
            "independent_episode_cooldown_sessions": COOLDOWN, "horizons": list(HORIZONS),
            "primary_proxy_rule": "industry/subindustry purity + usable history + liquidity; weighting-method ETFs excluded from subsector breadth",
        },
        "episode_counts": {"all_contiguous_starts": len(starts_all), "independent_subset": len(starts)},
        "coverage": {"sectors": sectors, "primary_subsectors": primary, "supporting_diagnostics": supporting},
        "audit_notes": AUDIT_NOTES,
        "sector_results": sector_results,
        "primary_subsector_results": primary_results,
        "supporting_diagnostic_results": supporting_results,
        "rankings": {
            "sectors": {str(h): ranked(sector_results, h) for h in HORIZONS},
            "primary_subsectors": {str(h): ranked(primary_results, h) for h in HORIZONS},
            "supporting_diagnostics": {str(h): ranked(supporting_results, h) for h in HORIZONS},
            "sectors_consistent": consistent_rank(sector_results),
            "primary_subsectors_consistent": consistent_rank(primary_results),
        },
    }
    out = Path("artifacts/reentry_sector_subsector_ranking_audited")
    out.mkdir(parents=True, exist_ok=True)
    (out / "ranking.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
