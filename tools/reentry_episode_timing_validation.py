from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_confidence import feature_frame, forward_return
from reentry_walkforward_validation import generate_decisions

ROUND_TRIP_COST = 0.001
HORIZONS = (7, 10)
WAIT_DAYS = (1, 3, 5)


def weakness_mask(df: pd.DataFrame) -> pd.Series:
    # Broad, pre-declared weakness context. Correction depth is not a gate by itself.
    return (
        (df["spy_dd20"] <= -0.01)
        | (df["B50"] <= 0.50)
        | (df["vix_change5"] >= 0.10)
        | (df["curve_ratio"] >= 1.0)
    )


def episode_ids(mask: pd.Series) -> pd.Series:
    starts = mask & ~mask.shift(1, fill_value=False)
    ids = starts.cumsum()
    return ids.where(mask, 0)


def get_forward(frame: pd.DataFrame, symbol: str, signal_date: pd.Timestamp, wait: int, horizon: int) -> float | None:
    if signal_date not in frame.index:
        return None
    pos = frame.index.get_loc(signal_date)
    if not isinstance(pos, (int, np.integer)):
        return None
    entry_i = pos + 1 + wait
    exit_i = entry_i + horizon
    if exit_i >= len(frame):
        return None
    return float(frame[symbol].iloc[exit_i] / frame[symbol].iloc[entry_i] - 1.0 - ROUND_TRIP_COST)


def summarize(x: list[float]) -> dict:
    a = np.asarray(x, dtype=float)
    if len(a) == 0:
        return {"n": 0, "median_return": None, "mean_return": None, "positive_rate": None, "p25": None}
    return {
        "n": int(len(a)),
        "median_return": float(np.median(a)),
        "mean_return": float(np.mean(a)),
        "positive_rate": float(np.mean(a > 0)),
        "p25": float(np.quantile(a, 0.25)),
    }


def bootstrap_diff(a: list[float], b: list[float], seed: int, reps: int = 10000) -> dict:
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    n = min(len(aa), len(bb))
    if n < 10:
        return {"paired_n": n, "median_diff": None, "ci_low": None, "ci_high": None, "p_one_sided": None}
    aa = aa[:n]
    bb = bb[:n]
    d = aa - bb
    rng = np.random.default_rng(seed)
    draws = rng.choice(d, size=(reps, n), replace=True)
    meds = np.median(draws, axis=1)
    return {
        "paired_n": int(n),
        "median_diff": float(np.median(d)),
        "ci_low": float(np.quantile(meds, 0.025)),
        "ci_high": float(np.quantile(meds, 0.975)),
        "p_one_sided": float((np.count_nonzero(meds <= 0) + 1) / (reps + 1)),
    }


def main() -> None:
    frame = feature_frame()
    decisions = generate_decisions(frame)
    data = decisions.join(frame[["SPY", "QQQ"]], how="left")
    weak = weakness_mask(decisions)
    ids = episode_ids(weak)

    episode_rows = []
    for eid in sorted(int(x) for x in ids.unique() if x > 0):
        dates = ids.index[ids == eid]
        if len(dates) == 0:
            continue
        start = dates[0]
        sub = decisions.loc[dates]
        eligible = sub[sub["decision"].isin(["CAUTIOUS YES", "YES", "STRONG YES"])]
        if eligible.empty:
            continue
        signal = eligible.index[0]
        episode_rows.append({
            "episode": eid,
            "start": start,
            "signal": signal,
            "signal_label": str(decisions.at[signal, "decision"]),
            "sessions_to_signal": int(decisions.index.get_loc(signal) - decisions.index.get_loc(start)),
            "spy_dd20_signal": float(decisions.at[signal, "spy_dd20"]),
            "B50_signal": float(decisions.at[signal, "B50"]),
        })

    episodes = pd.DataFrame(episode_rows)
    outcome_store: dict[str, dict[str, list[float]]] = {}
    for symbol in ("SPY", "QQQ"):
        outcome_store[symbol] = {}
        for h in HORIZONS:
            key = f"{h}D"
            outcome_store[symbol][key] = {"model": [], "wait1": [], "wait3": [], "wait5": [], "episode_start": []}

    usable = []
    for _, row in episodes.iterrows():
        record = row.to_dict()
        complete = True
        for symbol in ("SPY", "QQQ"):
            for h in HORIZONS:
                model = get_forward(frame, symbol, pd.Timestamp(row["signal"]), 0, h)
                start_ret = get_forward(frame, symbol, pd.Timestamp(row["start"]), 0, h)
                waits = {w: get_forward(frame, symbol, pd.Timestamp(row["signal"]), w, h) for w in WAIT_DAYS}
                if model is None or start_ret is None or any(v is None for v in waits.values()):
                    complete = False
                    break
                bucket = outcome_store[symbol][f"{h}D"]
                bucket["model"].append(model)
                bucket["episode_start"].append(start_ret)
                for w, val in waits.items():
                    bucket[f"wait{w}"].append(val)
            if not complete:
                break
        if complete:
            usable.append(record)

    results = {}
    comparisons = {}
    for symbol in ("SPY", "QQQ"):
        results[symbol] = {}
        comparisons[symbol] = {}
        for h in HORIZONS:
            bucket = outcome_store[symbol][f"{h}D"]
            results[symbol][f"{h}D"] = {k: summarize(v) for k, v in bucket.items()}
            comparisons[symbol][f"{h}D"] = {
                "vs_wait1": bootstrap_diff(bucket["model"], bucket["wait1"], 20260903 + h + 1),
                "vs_wait3": bootstrap_diff(bucket["model"], bucket["wait3"], 20260903 + h + 3),
                "vs_wait5": bootstrap_diff(bucket["model"], bucket["wait5"], 20260903 + h + 5),
                "vs_episode_start": bootstrap_diff(bucket["model"], bucket["episode_start"], 20260903 + h + 9),
            }

    # Era split on independent episode signals.
    usable_df = pd.DataFrame(usable)
    era_results = {}
    if not usable_df.empty:
        usable_df["signal"] = pd.to_datetime(usable_df["signal"])
        for era, start, end in [("2017-2020", "2017-01-01", "2020-12-31"), ("2021-2026", "2021-01-01", "2026-12-31")]:
            era_rows = usable_df[(usable_df["signal"] >= start) & (usable_df["signal"] <= end)]
            era_results[era] = {"n_episodes": int(len(era_rows)), "median_sessions_to_signal": float(era_rows["sessions_to_signal"].median()) if len(era_rows) else None}

    # Frozen useful-timing gate. We do not require superiority to buying at episode start,
    # because the purpose is deciding when cash already held should be redeployed. We do
    # require model entry to beat waiting 3 and 5 more sessions on at least 3 of 4
    # SPY/QQQ x 7/10D cells, while staying positive and reasonably consistent.
    cells_good = []
    timing_wins = 0
    for symbol in ("SPY", "QQQ"):
        for h in HORIZONS:
            r = results[symbol][f"{h}D"]["model"]
            c3 = comparisons[symbol][f"{h}D"]["vs_wait3"]
            c5 = comparisons[symbol][f"{h}D"]["vs_wait5"]
            good = bool(r["n"] >= 25 and r["median_return"] > 0 and r["positive_rate"] >= 0.55)
            cells_good.append(good)
            if c3["median_diff"] is not None and c5["median_diff"] is not None and c3["median_diff"] > 0 and c5["median_diff"] > 0:
                timing_wins += 1

    verdict = "GO_TO_IMPLEMENTABLE_STRATEGY" if all(cells_good) and timing_wins >= 3 else "DO_NOT_PROMOTE"

    payload = {
        "verdict": verdict,
        "question": "Once meaningful weakness exists, does the first model re-entry signal beat continuing to wait?",
        "methodology": {
            "weakness_context": "SPY >=1% below 20d high OR <=50% S&P above 50DMA OR VIX +>=10% over 5d OR VIX/VIX3M >=1.0",
            "reentry_signal": "first CAUTIOUS YES / YES / STRONG YES during each independent weakness episode",
            "execution": "signal close t, enter close t+1, 10 bps round-trip cost",
            "wait_comparators": [1, 3, 5],
            "horizons": list(HORIZONS),
            "no_large_dip_exclusion": True,
            "no_minimum_price_drawdown_gate": True,
        },
        "episode_count": int(len(usable)),
        "episode_signals": [
            {**r, "start": str(pd.Timestamp(r["start"]).date()), "signal": str(pd.Timestamp(r["signal"]).date())}
            for r in usable
        ],
        "results": results,
        "paired_bootstrap_comparisons": comparisons,
        "eras": era_results,
        "gate": {"all_cells_positive": bool(all(cells_good)), "timing_wins_vs_wait3_and_wait5": int(timing_wins)},
    }

    out = Path("artifacts/reentry_episode_timing")
    out.mkdir(parents=True, exist_ok=True)
    (out / "reentry_episode_timing_validation.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    if usable:
        pd.DataFrame(usable).to_csv(out / "reentry_episode_signals.csv", index=False)
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
