from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_confidence import feature_frame
from reentry_engine import ENGINE_VERSION, strategy_signal, weakness_context
from reentry_episode_timing_validation import (
    HORIZONS,
    WAIT_DAYS,
    bootstrap_diff,
    episode_ids,
    get_forward,
    summarize,
    weakness_mask,
)
from reentry_walkforward_validation import generate_decisions

# Freeze the same information set used by the validated 145-episode study.
AUDIT_DATA_END = "2026-09-02"
REFERENCE_EPISODES = 145
REFERENCE = {
    "SPY_7D": {"median_return": 0.008585570190091318, "positive_rate": 0.6551724137931034},
    "SPY_10D": {"median_return": 0.010660180393483043, "positive_rate": 0.6689655172413793},
    "QQQ_7D": {"median_return": 0.010538951553654141, "positive_rate": 0.6137931034482759},
    "QQQ_10D": {"median_return": 0.014405462638181654, "positive_rate": 0.6344827586206897},
}
# Historical vendors can make tiny back-adjustment revisions. These tolerances are
# deliberately narrow enough to catch meaningful drift without treating rounding noise
# as a strategy change.
RETURN_TOL = 0.0005
RATE_TOL = 0.005


def production_weakness_mask(decisions: pd.DataFrame) -> pd.Series:
    values = []
    for _, row in decisions.iterrows():
        weak, _ = weakness_context(row)
        values.append(weak)
    return pd.Series(values, index=decisions.index, dtype=bool)


def production_signal_series(decisions: pd.DataFrame, weak: pd.Series) -> pd.Series:
    out = []
    for date, row in decisions.iterrows():
        signal, _ = strategy_signal(str(row["decision"]), bool(weak.loc[date]))
        out.append(signal)
    return pd.Series(out, index=decisions.index, dtype="object")


def extract_episode_rows(decisions: pd.DataFrame, weak: pd.Series, signals: pd.Series) -> list[dict]:
    ids = episode_ids(weak)
    rows: list[dict] = []
    for eid in sorted(int(x) for x in ids.unique() if x > 0):
        dates = ids.index[ids == eid]
        if len(dates) == 0:
            continue
        start = dates[0]
        eligible_dates = dates[signals.loc[dates].eq("RE-ENTER")]
        if len(eligible_dates) == 0:
            continue
        signal = eligible_dates[0]
        rows.append({
            "episode": eid,
            "start": start,
            "signal": signal,
            "signal_label": str(decisions.at[signal, "decision"]),
            "sessions_to_signal": int(decisions.index.get_loc(signal) - decisions.index.get_loc(start)),
        })
    return rows


def usable_outcomes(frame: pd.DataFrame, episodes: list[dict]) -> tuple[list[dict], dict]:
    store: dict[str, dict[str, dict[str, list[float]]]] = {}
    for symbol in ("SPY", "QQQ"):
        store[symbol] = {}
        for h in HORIZONS:
            store[symbol][f"{h}D"] = {"model": [], "wait1": [], "wait3": [], "wait5": [], "episode_start": []}

    usable = []
    for row in episodes:
        complete = True
        staged = []
        for symbol in ("SPY", "QQQ"):
            for h in HORIZONS:
                model = get_forward(frame, symbol, pd.Timestamp(row["signal"]), 0, h)
                start_ret = get_forward(frame, symbol, pd.Timestamp(row["start"]), 0, h)
                waits = {w: get_forward(frame, symbol, pd.Timestamp(row["signal"]), w, h) for w in WAIT_DAYS}
                if model is None or start_ret is None or any(v is None for v in waits.values()):
                    complete = False
                    break
                staged.append((symbol, h, model, start_ret, waits))
            if not complete:
                break
        if not complete:
            continue
        usable.append(row)
        for symbol, h, model, start_ret, waits in staged:
            bucket = store[symbol][f"{h}D"]
            bucket["model"].append(model)
            bucket["episode_start"].append(start_ret)
            for w, val in waits.items():
                bucket[f"wait{w}"].append(val)
    return usable, store


def summarize_store(store: dict) -> tuple[dict, dict]:
    results = {}
    comparisons = {}
    for symbol in ("SPY", "QQQ"):
        results[symbol] = {}
        comparisons[symbol] = {}
        for h in HORIZONS:
            bucket = store[symbol][f"{h}D"]
            results[symbol][f"{h}D"] = {k: summarize(v) for k, v in bucket.items()}
            comparisons[symbol][f"{h}D"] = {
                "vs_wait1": bootstrap_diff(bucket["model"], bucket["wait1"], 20260903 + h + 1),
                "vs_wait3": bootstrap_diff(bucket["model"], bucket["wait3"], 20260903 + h + 3),
                "vs_wait5": bootstrap_diff(bucket["model"], bucket["wait5"], 20260903 + h + 5),
                "vs_episode_start": bootstrap_diff(bucket["model"], bucket["episode_start"], 20260903 + h + 9),
            }
    return results, comparisons


def main() -> None:
    frame = feature_frame().loc[:AUDIT_DATA_END].copy()
    decisions = generate_decisions(frame)

    # The legacy validation and production V1 must describe weakness identically.
    legacy_weak = weakness_mask(decisions)
    prod_weak = production_weakness_mask(decisions)
    weakness_mismatch_dates = [str(x.date()) for x in decisions.index[legacy_weak.ne(prod_weak)]]

    prod_signals = production_signal_series(decisions, prod_weak)
    prod_episode_rows = extract_episode_rows(decisions, prod_weak, prod_signals)

    # Independently reconstruct legacy eligible dates, then compare episode signals one-for-one.
    ids = episode_ids(legacy_weak)
    legacy_rows = []
    for eid in sorted(int(x) for x in ids.unique() if x > 0):
        dates = ids.index[ids == eid]
        if len(dates) == 0:
            continue
        sub = decisions.loc[dates]
        eligible = sub[sub["decision"].isin(["CAUTIOUS YES", "YES", "STRONG YES"])]
        if eligible.empty:
            continue
        legacy_rows.append({"episode": eid, "start": dates[0], "signal": eligible.index[0]})

    legacy_pairs = [(r["episode"], r["start"], r["signal"]) for r in legacy_rows]
    prod_pairs = [(r["episode"], r["start"], r["signal"]) for r in prod_episode_rows]
    episode_mapping_exact = legacy_pairs == prod_pairs

    usable, store = usable_outcomes(frame, prod_episode_rows)
    results, comparisons = summarize_store(store)

    metric_checks = {}
    frozen_ok = len(usable) == REFERENCE_EPISODES
    for symbol in ("SPY", "QQQ"):
        for h in HORIZONS:
            key = f"{symbol}_{h}D"
            actual = results[symbol][f"{h}D"]["model"]
            ref = REFERENCE[key]
            return_diff = abs(float(actual["median_return"]) - ref["median_return"])
            rate_diff = abs(float(actual["positive_rate"]) - ref["positive_rate"])
            ok = return_diff <= RETURN_TOL and rate_diff <= RATE_TOL
            frozen_ok = frozen_ok and ok
            metric_checks[key] = {
                "actual": actual,
                "reference": ref,
                "absolute_median_return_diff": return_diff,
                "absolute_positive_rate_diff": rate_diff,
                "within_tolerance": ok,
            }

    timing_wins = 0
    cells_positive = True
    for symbol in ("SPY", "QQQ"):
        for h in HORIZONS:
            r = results[symbol][f"{h}D"]["model"]
            c3 = comparisons[symbol][f"{h}D"]["vs_wait3"]
            c5 = comparisons[symbol][f"{h}D"]["vs_wait5"]
            cells_positive = cells_positive and bool(r["n"] >= 25 and r["median_return"] > 0 and r["positive_rate"] >= 0.55)
            if c3["median_diff"] is not None and c5["median_diff"] is not None and c3["median_diff"] > 0 and c5["median_diff"] > 0:
                timing_wins += 1

    code_equivalent = not weakness_mismatch_dates and episode_mapping_exact
    historical_gate_reproduced = bool(cells_positive and timing_wins >= 3)
    passed = bool(code_equivalent and frozen_ok and historical_gate_reproduced)

    payload = {
        "verdict": "PASS_PRODUCTION_EQUIVALENCE" if passed else "FAIL_PRODUCTION_EQUIVALENCE",
        "engine_version": ENGINE_VERSION,
        "audit_data_end": AUDIT_DATA_END,
        "purpose": "confirm final production V1 logic reproduces the frozen 145-episode re-entry timing validation without changing strategy rules",
        "checks": {
            "production_vs_legacy_weakness_exact": not weakness_mismatch_dates,
            "weakness_mismatch_dates": weakness_mismatch_dates,
            "production_vs_legacy_episode_mapping_exact": episode_mapping_exact,
            "legacy_candidate_episodes": len(legacy_rows),
            "production_candidate_episodes": len(prod_episode_rows),
            "usable_episode_count": len(usable),
            "reference_episode_count": REFERENCE_EPISODES,
            "frozen_reference_metrics_within_tolerance": frozen_ok,
            "historical_gate_reproduced": historical_gate_reproduced,
            "timing_wins_vs_wait3_and_wait5": timing_wins,
        },
        "metric_checks": metric_checks,
        "results": results,
        "paired_bootstrap_comparisons": comparisons,
        "production_episode_signals": [
            {**r, "start": str(pd.Timestamp(r["start"]).date()), "signal": str(pd.Timestamp(r["signal"]).date())}
            for r in usable
        ],
        "tolerances": {"median_return_absolute": RETURN_TOL, "positive_rate_absolute": RATE_TOL},
        "important_limit": "This is a regression/equivalence audit, not a new optimization or an additional claim of standalone alpha.",
    }

    out = Path("artifacts/reentry_production_equivalence")
    out.mkdir(parents=True, exist_ok=True)
    (out / "reentry_production_equivalence.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
