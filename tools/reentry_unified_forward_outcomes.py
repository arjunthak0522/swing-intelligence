#!/usr/bin/env python3
"""Prospective forward-outcome tracker for the unified RE-ENTRY engine.

Uses only actually captured snapshot-ledger events. No historical GO EARLY events are
invented. Baseline and simple confirmation shadows are evaluated side-by-side so future
research can quantify false starts versus missed rebound upside.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data/reentry/unified_snapshot_ledger.csv"
OUT_JSON = ROOT / "research/reentry_unified_forward_outcomes.json"
OUT_MD = ROOT / "research/reentry_unified_forward_outcomes.md"
HORIZONS = (1, 3, 5, 10, 15, 30, 60)


def finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except Exception:
        return False


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def truth(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def raw_state(row: dict) -> str:
    value = str(row.get("decision") or row.get("state") or "WAIT").upper()
    return value if value in {"WAIT", "WATCH", "GO_EARLY"} else "WAIT"


def assign_episode_ids(rows: list[dict]) -> list[dict]:
    out = []
    episode = 0
    prior_oversold = False
    for row in rows:
        oversold = truth(row.get("oversold_gate"))
        if oversold and not prior_oversold:
            episode += 1
        out.append({**row, "oversold_episode_id": episode if oversold else 0})
        prior_oversold = oversold
    return out


def apply_variant(rows: list[dict], required_go_snapshots: int) -> list[dict]:
    out = []
    streak = 0
    active_episode = 0
    for row in rows:
        episode = int(row.get("oversold_episode_id") or 0)
        state = raw_state(row)
        if episode == 0:
            streak = 0
            active_episode = 0
            shadow = "WAIT"
        else:
            if episode != active_episode:
                streak = 0
                active_episode = episode
            if state == "GO_EARLY":
                streak += 1
                shadow = "GO_EARLY" if streak >= required_go_snapshots else "WATCH"
            else:
                streak = 0
                shadow = state
        out.append({**row, "variant_state": shadow, "go_confirmation_streak": streak})
    return out


def event_rows(rows: list[dict], variant_name: str) -> list[dict]:
    first_by_episode = {}
    for row in rows:
        episode = int(row.get("oversold_episode_id") or 0)
        if episode <= 0 or row.get("variant_state") != "GO_EARLY" or episode in first_by_episode:
            continue
        if not finite(row.get("SPY_price")) or not finite(row.get("QQQ_price")):
            continue
        first_by_episode[episode] = {
            "variant": variant_name,
            "oversold_episode_id": episode,
            "market_date": row.get("market_date"),
            "timestamp_et": row.get("timestamp_et"),
            "market_phase": row.get("market_phase"),
            "SPY_entry_price": float(row["SPY_price"]),
            "QQQ_entry_price": float(row["QQQ_price"]),
            "fast_family_count": int(float(row.get("fast_family_count") or 0)),
            "context_support_count": int(float(row.get("context_support_count") or 0)),
            "data_quality_status": row.get("data_quality_status"),
            "actionable": truth(row.get("actionable")),
        }
    return list(first_by_episode.values())


def daily_close_series(symbol: str) -> pd.Series:
    frame = yf.download(symbol, period="5y", interval="1d", auto_adjust=False, progress=False, threads=False, timeout=30)
    if frame.empty:
        return pd.Series(dtype=float)
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = pd.to_numeric(close, errors="coerce").dropna()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close


def add_outcomes(event: dict, symbol: str, closes: pd.Series) -> None:
    date = pd.Timestamp(str(event["market_date"])).tz_localize(None)
    dates = list(closes.index)
    if date not in closes.index:
        event[f"{symbol}_same_day_close_return"] = None
        for h in HORIZONS:
            event[f"{symbol}_{h}D_return"] = None
            event[f"{symbol}_{h}D_MAE"] = None
            event[f"{symbol}_{h}D_MFE"] = None
        return

    entry = float(event[f"{symbol}_entry_price"])
    i = dates.index(date)
    event[f"{symbol}_same_day_close_return"] = float(closes.loc[date] / entry - 1.0)
    for h in HORIZONS:
        end = i + h
        if end >= len(dates):
            event[f"{symbol}_{h}D_return"] = None
            event[f"{symbol}_{h}D_MAE"] = None
            event[f"{symbol}_{h}D_MFE"] = None
            continue
        window = closes.iloc[i + 1 : end + 1]
        event[f"{symbol}_{h}D_return"] = float(closes.iloc[end] / entry - 1.0)
        event[f"{symbol}_{h}D_MAE"] = float((window / entry - 1.0).min()) if len(window) else None
        event[f"{symbol}_{h}D_MFE"] = float((window / entry - 1.0).max()) if len(window) else None


def stats(values: list[float]) -> dict:
    vals = [float(v) for v in values if finite(v)]
    if not vals:
        return {"n": 0, "mean": None, "median": None, "positive_rate": None}
    return {
        "n": len(vals),
        "mean": sum(vals) / len(vals),
        "median": statistics.median(vals),
        "positive_rate": sum(v > 0 for v in vals) / len(vals),
    }


def summarize(events: list[dict]) -> dict:
    out = {"event_count": len(events), "SPY": {}, "QQQ": {}}
    for symbol in ("SPY", "QQQ"):
        for h in HORIZONS:
            returns = [e.get(f"{symbol}_{h}D_return") for e in events]
            maes = [e.get(f"{symbol}_{h}D_MAE") for e in events]
            mfes = [e.get(f"{symbol}_{h}D_MFE") for e in events]
            out[symbol][f"{h}D"] = {
                "returns": stats(returns),
                "MAE": stats(maes),
                "MFE": stats(mfes),
            }
    return out


def main() -> None:
    rows = read_csv(LEDGER)
    rows = [r for r in rows if r.get("timestamp_et") and r.get("market_date")]
    rows.sort(key=lambda r: str(r["timestamp_et"]))
    rows = assign_episode_ids(rows)

    variants = {
        "baseline": 1,
        "confirm_2_snapshots": 2,
        "confirm_3_snapshots": 3,
    }
    spy = daily_close_series("SPY") if rows else pd.Series(dtype=float)
    qqq = daily_close_series("QQQ") if rows else pd.Series(dtype=float)

    event_sets = {}
    summaries = {}
    for name, required in variants.items():
        replay = apply_variant(rows, required)
        events = event_rows(replay, name)
        for event in events:
            add_outcomes(event, "SPY", spy)
            add_outcomes(event, "QQQ", qqq)
        event_sets[name] = events
        summaries[name] = summarize(events)

    payload = {
        "classification": "RESEARCH_ONLY_PROSPECTIVE",
        "engine_impact": "NONE",
        "generated_at": datetime.now().astimezone().isoformat(),
        "source": "data/reentry/unified_snapshot_ledger.csv",
        "captured_snapshots": len(rows),
        "horizons_sessions": list(HORIZONS),
        "event_definition": "First GO EARLY observation inside each prospectively captured continuous oversold-gate episode.",
        "variants": variants,
        "summaries": summaries,
        "events": event_sets,
        "promotion_status": "INSUFFICIENT_UNTIL_OUTCOMES_MATURE",
        "limitations": [
            "Only prospective point-in-time events are included.",
            "Forward outcomes use subsequent unadjusted daily closes relative to the captured intraday entry price.",
            "MAE and MFE are based on daily closes, not intraday highs and lows.",
            "No variant is promoted based on transition reduction alone.",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# RE-ENTRY prospective forward outcomes",
        "",
        "**Research only - no production signal change.**",
        "",
        f"Captured unified snapshots: **{len(rows)}**",
        "",
    ]
    for name in variants:
        lines.append(f"## {name}")
        lines.append(f"- candidate events: **{summaries[name]['event_count']}**")
        for symbol in ("SPY", "QQQ"):
            h5 = summaries[name][symbol]["5D"]["returns"]
            h10 = summaries[name][symbol]["10D"]["returns"]
            lines.append(f"- {symbol}: matured 5D n={h5['n']}; matured 10D n={h10['n']}")
        lines.append("")
    lines += [
        "## Promotion boundary",
        "",
        "Do not select a confirmation variant until enough events have matured to compare return, positive rate, adverse excursion, favorable excursion, and entry delay against the baseline.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
