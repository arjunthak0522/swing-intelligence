#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_cash_policy_validation import historical_proxy_states
from reentry_confidence import feature_frame
from reentry_walkforward_validation import generate_decisions

START_YEAR = 2017
MAX_CONFIRM_WAIT = 20
HORIZONS = (5, 10, 15, 30, 60)
ROUND_TRIP_COST = 0.001
OUT = Path("artifacts/reentry_nasi_ema10_validation")
UNICORN_BASE = "https://unicorn.us.com/advdec"


def parse_date(value: str) -> pd.Timestamp | None:
    parsed = pd.to_datetime((value or "").strip(), errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).normalize()


def fetch_archived_series(filename: str) -> pd.Series:
    """Fetch Unicorn's archived breadth series.

    The archive's TLS certificate is expired, so curl uses --insecure only for this
    research-only historical download. The source stopped updating in February 2020.
    """
    url = f"{UNICORN_BASE}/{filename}"
    result = subprocess.run(
        [
            "curl", "--insecure", "--location", "--compressed", "--silent", "--show-error", "--fail",
            "--max-time", "45", "--user-agent", "Mozilla/5.0 RE-ENTRY-nasi-validation/1.0", url,
        ],
        check=True, capture_output=True, text=True, timeout=50,
    )
    rows: list[tuple[pd.Timestamp, float]] = []
    for row in csv.reader(io.StringIO(result.stdout.lstrip("\ufeff"))):
        if len(row) < 2:
            continue
        dt = parse_date(row[0])
        if dt is None:
            continue
        value = None
        for cell in reversed(row[1:]):
            try:
                value = float(str(cell).replace(",", "").strip())
                break
            except (TypeError, ValueError):
                continue
        if value is None or value < 0:
            continue
        rows.append((dt, value))
    if not rows:
        raise ValueError(f"Parsed zero rows from {url}")
    s = pd.Series({d: v for d, v in rows}, dtype=float).sort_index()
    s.index = pd.DatetimeIndex(s.index)
    return s


def ema(values: pd.Series, length: int) -> pd.Series:
    return values.ewm(span=length, adjust=False).mean()


def build_nasi() -> pd.DataFrame:
    advances = fetch_archived_series("NASDAQ_advn.csv")
    declines = fetch_archived_series("NASDAQ_decln.csv")
    common = advances.index.intersection(declines.index)
    df = pd.DataFrame({"advances": advances.reindex(common), "declines": declines.reindex(common)}).dropna()
    df = df[(df["advances"] + df["declines"]) > 0].copy()

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
    return df[df.index.year >= START_YEAR].copy()


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
    if common.empty:
        raise RuntimeError("No overlap between archived NASI breadth and historical RE-ENTRY states")
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
    if episodes.empty:
        raise RuntimeError("No independent DEPLOY episode starts in archived NASI overlap")

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
        "pct_already_confirmed_at_deploy": float(episodes["above_ema10"].mean()),
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

    n_episodes = int(len(starts))
    already = wait_summary["pct_already_confirmed_at_deploy"]
    qqq_cost = wait_summary["QQQ_entry_price_cost"].get("median")
    qqq_10 = wait_summary["base_minus_delayed_forward_return"]["QQQ"]["10"].get("median")
    qqq_30 = wait_summary["base_minus_delayed_forward_return"]["QQQ"]["30"].get("median")
    enough_sample = n_episodes >= 25
    if not enough_sample:
        verdict = "INSUFFICIENT_SAMPLE_KEEP_RESEARCH_ONLY"
    elif already >= 0.75 and (qqq_cost is None or qqq_cost >= 0) and (qqq_10 is None or qqq_10 >= 0) and (qqq_30 is None or qqq_30 >= 0):
        verdict = "KEEP_CONTEXT_ONLY_NO_GATE"
    else:
        verdict = "RESEARCH_ONLY_REVIEW_INCREMENTAL_EDGE"

    payload = {
        "test_status": "COMPLETE_LIMITED_HISTORY",
        "research_only": True,
        "core_signal_logic_modified": False,
        "question": "Does Nasdaq McClellan Summation Index ($NASI) crossing/holding above its 10-day EMA add incremental value to RE-ENTRY, especially for QQQ, or mainly confirm after the existing DEPLOY signal?",
        "date_range": [str(common.min().date()), str(common.max().date())],
        "n_sessions": int(len(common)),
        "n_independent_deploy_episode_starts": n_episodes,
        "sample_sufficient_for_primary_decision": enough_sample,
        "methodology": {
            "nasi_definition": "ratio-adjusted Nasdaq McClellan Summation Index reconstructed from archived Nasdaq advance/decline issues; McClellan oscillator = EMA19(RANA)-EMA39(RANA); NASI = cumulative oscillator",
            "breadth_source": "Unicorn Research archived NASDAQ_advn/NASDAQ_decln series, which aggregate historical public breadth sources and stop in February 2020",
            "source_limit": "This archive does not cover the full 2017-2026 RE-ENTRY validation window. Results are therefore a limited-history incremental test, not a full certification.",
            "tested_signal": "NASI > 10-day EMA, plus same-day bullish cross and rising-state slices",
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
        "sample_sufficient_for_primary_decision": enough_sample,
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
