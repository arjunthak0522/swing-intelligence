#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_cash_policy_validation import historical_proxy_states
from reentry_confidence import feature_frame
from reentry_walkforward_validation import generate_decisions

START_YEAR = 2017
END_YEAR = 2026
MAX_CONFIRM_WAIT = 20
HORIZONS = (5, 10, 15, 30, 60)
ROUND_TRIP_COST = 0.001
OUT = Path("artifacts/reentry_nasi_ema10_validation")


def normalize_header(value: str) -> str:
    return "".join(ch.lower() for ch in (value or "") if ch.isalnum())


def parse_date(value: str) -> str | None:
    value = (value or "").strip()
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return pd.Timestamp.strptime(value, fmt).date().isoformat()
        except Exception:
            pass
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date().isoformat()


def fetch_nasdaq_daily_breadth(year: int) -> list[dict]:
    url = f"https://www.nasdaqtrader.com/dynamic/dailyfiles/daily{year}.txt"
    result = subprocess.run(
        [
            "curl", "--location", "--compressed", "--silent", "--show-error", "--fail",
            "--max-time", "45", "--user-agent", "Mozilla/5.0 RE-ENTRY-nasi-validation/1.0", url,
        ],
        check=True, capture_output=True, text=True, timeout=50,
    )
    text = result.stdout.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    normalized = {name: normalize_header(name) for name in fields}

    def choose_date() -> str:
        for name, norm in normalized.items():
            if norm == "date" or norm.endswith("tradedate"):
                return name
        raise ValueError(f"No date column in {year}: {fields}")

    def choose(kind: str) -> str:
        # Prefer explicitly Nasdaq-labeled breadth columns if the file contains multiple exchanges.
        candidates = []
        for name, norm in normalized.items():
            if kind == "adv" and "advance" in norm and "decline" not in norm:
                candidates.append((name, norm))
            if kind == "dec" and "decline" in norm:
                candidates.append((name, norm))
        for name, norm in candidates:
            if "nasdaq" in norm:
                return name
        exact = "advances" if kind == "adv" else "declines"
        for name, norm in candidates:
            if norm == exact:
                return name
        if len(candidates) == 1:
            return candidates[0][0]
        raise ValueError(f"Ambiguous {kind} column in {year}: {fields}")

    date_field = choose_date()
    adv_field = choose("adv")
    dec_field = choose("dec")
    rows = []
    for row in reader:
        market_date = parse_date(row.get(date_field, ""))
        if not market_date:
            continue
        try:
            advances = float(str(row.get(adv_field, "")).replace(",", ""))
            declines = float(str(row.get(dec_field, "")).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if advances < 0 or declines < 0 or advances + declines <= 0:
            continue
        rows.append({"date": market_date, "advances": advances, "declines": declines})
    if not rows:
        raise ValueError(f"Parsed zero Nasdaq breadth rows for {year}")
    return rows


def ema(values: pd.Series, length: int) -> pd.Series:
    return values.ewm(span=length, adjust=False).mean()


def build_nasi() -> pd.DataFrame:
    rows: list[dict] = []
    for year in range(START_YEAR, END_YEAR + 1):
        rows.extend(fetch_nasdaq_daily_breadth(year))
    df = pd.DataFrame(rows).drop_duplicates("date", keep="last")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    total = df["advances"] + df["declines"]
    df["rana"] = 1000.0 * (df["advances"] - df["declines"]) / total
    df["ema19"] = ema(df["rana"], 19)
    df["ema39"] = ema(df["rana"], 39)
    df["namo"] = df["ema19"] - df["ema39"]
    df["nasi"] = df["namo"].cumsum()
    df["nasi_ema10"] = ema(df["nasi"], 10)
    df["above_ema10"] = df["nasi"] > df["nasi_ema10"]
    df["rising"] = df["nasi"].diff() > 0
    df["bull_cross"] = df["above_ema10"] & ~df["above_ema10"].shift(1).fillna(False)
    return df


def summarize(x: list[float] | pd.Series) -> dict:
    s = pd.Series(x, dtype=float).replace([np.inf, -np.inf], np.nan).dropna()
    if s.empty:
        return {"n": 0, "median": None, "mean": None, "positive_rate": None, "p25": None, "p75": None}
    return {
        "n": int(len(s)),
        "median": float(s.median()),
        "mean": float(s.mean()),
        "positive_rate": float((s > 0).mean()),
        "p25": float(s.quantile(0.25)),
        "p75": float(s.quantile(0.75)),
    }


def fwd_return(px: pd.Series, pos: int, horizon: int) -> float | None:
    entry = pos + 1
    exit_ = entry + horizon
    if entry >= len(px) or exit_ >= len(px):
        return None
    return float(px.iloc[exit_] / px.iloc[entry] - 1.0 - ROUND_TRIP_COST)


def episode_starts(states: pd.DataFrame) -> pd.DatetimeIndex:
    d = states["deployment_signal"].eq("DEPLOY")
    return states.index[d & ~d.shift(1, fill_value=False)]


def main() -> None:
    frame, metadata = feature_frame(return_metadata=True, require_same_day=False)
    decisions = generate_decisions(frame)
    states = historical_proxy_states(frame, decisions)
    nasi = build_nasi()

    common = states.index.intersection(nasi.index)
    states = states.loc[common].copy()
    nasi = nasi.loc[common].copy()
    frame = frame.reindex(common)
    starts = episode_starts(states)

    episode_rows = []
    for d in starts:
        loc = common.get_loc(d)
        row = {
            "date": d.date().isoformat(),
            "nasi": float(nasi.at[d, "nasi"]),
            "nasi_ema10": float(nasi.at[d, "nasi_ema10"]),
            "above_ema10": bool(nasi.at[d, "above_ema10"]),
            "rising": bool(nasi.at[d, "rising"]),
            "bull_cross": bool(nasi.at[d, "bull_cross"]),
        }
        for sym in ("SPY", "QQQ"):
            px = frame[sym]
            for h in HORIZONS:
                row[f"{sym}_{h}d"] = fwd_return(px, loc, h)
        episode_rows.append(row)
    episodes = pd.DataFrame(episode_rows)

    groups = {}
    masks = {
        "ALL_DEPLOY_EPISODES": pd.Series(True, index=episodes.index),
        "NASI_ABOVE_EMA10": episodes["above_ema10"],
        "NASI_BELOW_OR_EQUAL_EMA10": ~episodes["above_ema10"],
        "NASI_RISING": episodes["rising"],
        "NASI_NOT_RISING": ~episodes["rising"],
        "NASI_BULL_CROSS_TODAY": episodes["bull_cross"],
    }
    for name, mask in masks.items():
        block = {"n_episodes": int(mask.sum()), "SPY": {}, "QQQ": {}}
        for sym in ("SPY", "QQQ"):
            for h in HORIZONS:
                block[sym][str(h)] = summarize(episodes.loc[mask, f"{sym}_{h}d"])
        groups[name] = block

    # Counterfactual: if NASI > 10EMA were required, how much later would entry occur?
    wait_rows = []
    positions = {d: i for i, d in enumerate(common)}
    for d in starts:
        i = positions[d]
        if bool(nasi.iloc[i]["above_ema10"]):
            j = i
        else:
            j = None
            for k in range(i + 1, min(i + 1 + MAX_CONFIRM_WAIT, len(common))):
                if bool(nasi.iloc[k]["above_ema10"]):
                    j = k
                    break
        if j is None:
            continue
        rec = {
            "deploy_date": d.date().isoformat(),
            "confirm_date": common[j].date().isoformat(),
            "wait_sessions": int(j - i),
        }
        for sym in ("SPY", "QQQ"):
            px = frame[sym]
            base_entry = i + 1
            delayed_entry = j + 1
            if delayed_entry < len(px):
                # Positive = waiting required paying a higher price.
                rec[f"{sym}_entry_price_cost"] = float(px.iloc[delayed_entry] / px.iloc[base_entry] - 1.0)
            for h in HORIZONS:
                base = fwd_return(px, i, h)
                delayed = fwd_return(px, j, h)
                rec[f"{sym}_{h}d_base_minus_delayed"] = None if base is None or delayed is None else float(base - delayed)
        wait_rows.append(rec)
    waits = pd.DataFrame(wait_rows)

    wait_summary = {
        "n_confirmed_within_window": int(len(waits)),
        "n_base_episodes": int(len(starts)),
        "n_not_confirmed_within_window": int(len(starts) - len(waits)),
        "median_wait_sessions": None if waits.empty else float(waits["wait_sessions"].median()),
        "pct_already_confirmed_at_deploy": None if episodes.empty else float(episodes["above_ema10"].mean()),
        "SPY_entry_price_cost": summarize(waits.get("SPY_entry_price_cost", pd.Series(dtype=float))),
        "QQQ_entry_price_cost": summarize(waits.get("QQQ_entry_price_cost", pd.Series(dtype=float))),
        "base_minus_delayed_forward_return": {"SPY": {}, "QQQ": {}},
        "interpretation": "Positive entry_price_cost means requiring NASI confirmation bought later at a higher price. Positive base_minus_delayed_forward_return means the existing DEPLOY timing outperformed the delayed NASI-confirmed timing over that forward horizon.",
    }
    for sym in ("SPY", "QQQ"):
        for h in HORIZONS:
            wait_summary["base_minus_delayed_forward_return"][sym][str(h)] = summarize(
                waits.get(f"{sym}_{h}d_base_minus_delayed", pd.Series(dtype=float))
            )

    # Simple research verdict. Never modifies signal logic.
    already = wait_summary["pct_already_confirmed_at_deploy"] or 0.0
    qqq_cost = (wait_summary["QQQ_entry_price_cost"].get("median") or 0.0)
    qqq_10 = wait_summary["base_minus_delayed_forward_return"]["QQQ"]["10"].get("median")
    qqq_30 = wait_summary["base_minus_delayed_forward_return"]["QQQ"]["30"].get("median")
    if already >= 0.75 and qqq_cost >= 0 and (qqq_10 is None or qqq_10 >= 0) and (qqq_30 is None or qqq_30 >= 0):
        verdict = "KEEP_CONTEXT_ONLY_NO_GATE"
    else:
        verdict = "RESEARCH_ONLY_REVIEW_INCREMENTAL_EDGE"

    payload = {
        "test_status": "COMPLETE",
        "research_only": True,
        "core_signal_logic_modified": False,
        "question": "Does Nasdaq McClellan Summation Index ($NASI) crossing/holding above its 10-day EMA add incremental value to RE-ENTRY, especially for QQQ, or mainly confirm after the existing DEPLOY signal?",
        "date_range": [str(common.min().date()), str(common.max().date())],
        "n_sessions": int(len(common)),
        "n_independent_deploy_episode_starts": int(len(starts)),
        "methodology": {
            "nasi_definition": "ratio-adjusted Nasdaq McClellan Summation Index reconstructed from Nasdaq Trader daily advances/declines; McClellan oscillator = EMA19(RANA)-EMA39(RANA); NASI = cumulative oscillator",
            "tested_signal": "NASI > 10-day EMA, plus same-day bullish cross and rising-state slices",
            "why_10_day_ema": "This matches the moving-average confirmation convention in the chart under review and StockCharts' documented use of a 10-day moving average to identify Summation Index turns.",
            "deploy_baseline": "independent DEPLOY episode starts from the already-validated historical proxy policy; exact live intraday engine is not backfilled where unavailable",
            "entry_assumption": "signal at close t, entry close t+1, 10 bps round-trip cost for forward-return comparisons",
            "confirmation_wait_cap_sessions": MAX_CONFIRM_WAIT,
            "no_lookahead": True,
        },
        "data_metadata": metadata,
        "group_forward_results": groups,
        "confirmation_delay_test": wait_summary,
        "verdict": verdict,
        "decision_rule": "Do not promote NASI/EMA10 into the core DEPLOY gate unless it improves outcomes without materially delaying entry. Context-only is preferred when it mainly arrives after or alongside the existing signal.",
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "reentry_nasi_ema10_validation.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    episodes.to_csv(OUT / "reentry_nasi_ema10_episodes.csv", index=False)
    waits.to_csv(OUT / "reentry_nasi_ema10_confirmation_waits.csv", index=False)

    compact = {
        "test_status": payload["test_status"],
        "date_range": payload["date_range"],
        "n_sessions": payload["n_sessions"],
        "n_independent_deploy_episode_starts": payload["n_independent_deploy_episode_starts"],
        "pct_already_confirmed_at_deploy": wait_summary["pct_already_confirmed_at_deploy"],
        "median_wait_sessions": wait_summary["median_wait_sessions"],
        "SPY_entry_price_cost_median": wait_summary["SPY_entry_price_cost"].get("median"),
        "QQQ_entry_price_cost_median": wait_summary["QQQ_entry_price_cost"].get("median"),
        "QQQ_10d_base_minus_delayed_median": wait_summary["base_minus_delayed_forward_return"]["QQQ"]["10"].get("median"),
        "QQQ_30d_base_minus_delayed_median": wait_summary["base_minus_delayed_forward_return"]["QQQ"]["30"].get("median"),
        "verdict": verdict,
    }
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
