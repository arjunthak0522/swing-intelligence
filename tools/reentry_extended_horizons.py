from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_confidence import feature_frame
from reentry_walkforward_validation import generate_decisions
from reentry_episode_timing_validation import weakness_mask, episode_ids, bootstrap_diff

ROUND_TRIP_COST = 0.001
HORIZONS = (7, 10, 15, 30, 60)
WAIT_DAYS = (1, 3, 5)


def summarize(x: list[float]) -> dict:
    a = np.asarray(x, dtype=float)
    if len(a) == 0:
        return {"n": 0, "median_return": None, "mean_return": None, "positive_rate": None, "p25": None, "p75": None}
    return {
        "n": int(len(a)),
        "median_return": float(np.median(a)),
        "mean_return": float(np.mean(a)),
        "positive_rate": float(np.mean(a > 0)),
        "p25": float(np.quantile(a, 0.25)),
        "p75": float(np.quantile(a, 0.75)),
    }


def path_metrics(frame: pd.DataFrame, symbol: str, signal: pd.Timestamp, wait: int, horizon: int) -> dict | None:
    if signal not in frame.index:
        return None
    pos = frame.index.get_loc(signal)
    if not isinstance(pos, (int, np.integer)):
        return None
    entry_i = int(pos) + 1 + wait
    exit_i = entry_i + horizon
    if exit_i >= len(frame):
        return None
    entry = float(frame[symbol].iloc[entry_i])
    exit_px = float(frame[symbol].iloc[exit_i])
    path = frame[symbol].iloc[entry_i + 1:exit_i + 1].astype(float) / entry - 1.0
    return {
        "return": float(exit_px / entry - 1.0 - ROUND_TRIP_COST),
        "mae": float(path.min()) if len(path) else 0.0,
        "mfe": float(path.max()) if len(path) else 0.0,
    }


def better_price_metrics(frame: pd.DataFrame, symbol: str, signal: pd.Timestamp) -> dict | None:
    pos = frame.index.get_loc(signal)
    if not isinstance(pos, (int, np.integer)):
        return None
    entry_i = int(pos) + 1
    if entry_i + 5 >= len(frame):
        return None
    entry = float(frame[symbol].iloc[entry_i])
    out = {}
    for w in WAIT_DAYS:
        future = frame[symbol].iloc[entry_i + 1:entry_i + w + 1].astype(float)
        if len(future) < w:
            return None
        rel = future / entry - 1.0
        out[f"next_{w}d_min_close_vs_entry"] = float(rel.min())
        out[f"next_{w}d_end_close_vs_entry"] = float(rel.iloc[-1])
        out[f"better_close_within_{w}d"] = bool((rel < 0).any())
        out[f"at_least_1pct_better_within_{w}d"] = bool((rel <= -0.01).any())
        out[f"at_least_2pct_better_within_{w}d"] = bool((rel <= -0.02).any())
    return out


def main() -> None:
    frame = feature_frame()
    decisions = generate_decisions(frame)
    weak = weakness_mask(decisions)
    ids = episode_ids(weak)

    episodes = []
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
        episodes.append({
            "episode": eid,
            "start": start,
            "signal": signal,
            "signal_label": str(decisions.at[signal, "decision"]),
        })

    results = {s: {f"{h}D": {"model": [], **{f"wait{w}": [] for w in WAIT_DAYS}, "mae": [], "mfe": []} for h in HORIZONS} for s in ("SPY", "QQQ")}
    better = {s: [] for s in ("SPY", "QQQ")}
    usable_by_horizon = {h: 0 for h in HORIZONS}

    for ep in episodes:
        signal = pd.Timestamp(ep["signal"])
        for symbol in ("SPY", "QQQ"):
            bp = better_price_metrics(frame, symbol, signal)
            if bp is not None:
                better[symbol].append(bp)
        for h in HORIZONS:
            complete_h = True
            staged = {}
            for symbol in ("SPY", "QQQ"):
                model = path_metrics(frame, symbol, signal, 0, h)
                waits = {w: path_metrics(frame, symbol, signal, w, h) for w in WAIT_DAYS}
                if model is None or any(v is None for v in waits.values()):
                    complete_h = False
                    break
                staged[symbol] = (model, waits)
            if complete_h:
                usable_by_horizon[h] += 1
                for symbol, (model, waits) in staged.items():
                    b = results[symbol][f"{h}D"]
                    b["model"].append(model["return"])
                    b["mae"].append(model["mae"])
                    b["mfe"].append(model["mfe"])
                    for w, val in waits.items():
                        b[f"wait{w}"].append(val["return"])

    summary = {}
    comparisons = {}
    for symbol in ("SPY", "QQQ"):
        summary[symbol] = {}
        comparisons[symbol] = {}
        for h in HORIZONS:
            b = results[symbol][f"{h}D"]
            summary[symbol][f"{h}D"] = {
                "model": summarize(b["model"]),
                "wait1": summarize(b["wait1"]),
                "wait3": summarize(b["wait3"]),
                "wait5": summarize(b["wait5"]),
                "median_mae": float(np.median(b["mae"])) if b["mae"] else None,
                "median_mfe": float(np.median(b["mfe"])) if b["mfe"] else None,
            }
            comparisons[symbol][f"{h}D"] = {
                f"vs_wait{w}": bootstrap_diff(b["model"], b[f"wait{w}"], 20260903 + h * 10 + w)
                for w in WAIT_DAYS
            }

    better_summary = {}
    for symbol in ("SPY", "QQQ"):
        rows = better[symbol]
        better_summary[symbol] = {"n": len(rows)}
        for w in WAIT_DAYS:
            mins = np.asarray([r[f"next_{w}d_min_close_vs_entry"] for r in rows], dtype=float)
            ends = np.asarray([r[f"next_{w}d_end_close_vs_entry"] for r in rows], dtype=float)
            better_summary[symbol][f"within_{w}d"] = {
                "any_better_close_rate": float(np.mean([r[f"better_close_within_{w}d"] for r in rows])) if rows else None,
                "at_least_1pct_better_rate": float(np.mean([r[f"at_least_1pct_better_within_{w}d"] for r in rows])) if rows else None,
                "at_least_2pct_better_rate": float(np.mean([r[f"at_least_2pct_better_within_{w}d"] for r in rows])) if rows else None,
                "median_best_close_improvement": float(np.median(mins)) if len(mins) else None,
                "median_end_close_move": float(np.median(ends)) if len(ends) else None,
            }

    payload = {
        "question": "After the frozen correction re-entry signal, do favorable outcomes persist over 15/30/60 trading days and was waiting rewarded with a better close?",
        "signal_unchanged": True,
        "methodology": {
            "weakness_context": "unchanged from prior validation",
            "reentry_signal": "first CAUTIOUS YES / YES / STRONG YES during each independent weakness episode",
            "execution": "signal close t, enter close t+1, 10 bps round-trip cost",
            "horizons": list(HORIZONS),
            "wait_comparators": list(WAIT_DAYS),
            "mae_mfe": "close-to-close path after entry; no intraday high/low data used",
            "better_price_test": "whether a lower daily close than the model entry close occurred within the next 1/3/5 sessions",
        },
        "episode_count_raw": len(episodes),
        "usable_episode_count_by_horizon": {str(k): int(v) for k, v in usable_by_horizon.items()},
        "results": summary,
        "paired_bootstrap_comparisons": comparisons,
        "waiting_for_better_price": better_summary,
    }

    out = Path("artifacts/reentry_extended_horizons")
    out.mkdir(parents=True, exist_ok=True)
    (out / "reentry_extended_horizons.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
