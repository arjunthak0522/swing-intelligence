from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_confidence import feature_frame
from reentry_engine import (
    _build_unified_frame,
    _selling_pressure,
    _internal_reset,
    _unified_signal,
    early_entry_decision,
    weakness_context,
)
from reentry_walkforward_validation import generate_decisions

POST_WAIT_HORIZONS = (5, 10, 20)


def summarize(values: list[float]) -> dict:
    a = np.asarray(values, dtype=float)
    if len(a) == 0:
        return {"n": 0, "median": None, "mean": None, "win_rate": None, "p25": None, "p75": None}
    return {
        "n": int(len(a)),
        "median": float(np.median(a)),
        "mean": float(np.mean(a)),
        "win_rate": float(np.mean(a > 0)),
        "p25": float(np.quantile(a, 0.25)),
        "p75": float(np.quantile(a, 0.75)),
    }


def build_canonical_signal_history(base: pd.DataFrame) -> pd.DataFrame:
    decisions = generate_decisions(base)
    unified = _build_unified_frame(base, require_same_day=False)
    common = decisions.index.intersection(unified.index)
    rows = []
    for date in common:
        row = unified.loc[date]
        analog = str(decisions.at[date, "decision"])
        weak, _ = weakness_context(row)
        base_signal, _, _ = _unified_signal(analog, weak, row)
        signal, _, source = early_entry_decision(
            analog_decision=analog,
            weakness_present=weak,
            internal_reset=_internal_reset(row),
            selling_pressure=_selling_pressure(row),
            existing_signal=base_signal,
            subsector_state="NEUTRAL",
            subsector_supports_early_entry=False,
            allow_subsector_candidate=False,
        )
        rows.append({"date": date, "signal": signal, "source": source, "analog": analog})
    return pd.DataFrame(rows).set_index("date")


def summarize_episode_set(episodes: list[dict]) -> dict:
    out: dict = {}
    for sym in ("SPY", "QQQ"):
        out[sym] = {
            "entry_to_exit": summarize([e[f"{sym}_return_to_exit"] for e in episodes]),
            "max_gain_during_episode": summarize([e[f"{sym}_max_gain_during_episode"] for e in episodes]),
            "max_adverse_during_episode": summarize([e[f"{sym}_max_adverse_during_episode"] for e in episodes]),
            **{f"post_exit_{h}d": summarize([e[f"{sym}_post_exit_{h}d"] for e in episodes if e[f"{sym}_post_exit_{h}d"] is not None]) for h in POST_WAIT_HORIZONS},
        }
    out["episode_length_sessions"] = summarize([float(e["reenter_sessions"]) for e in episodes])
    return out


def main() -> None:
    frame = feature_frame()
    signals = build_canonical_signal_history(frame)
    idx = signals.index
    price_pos = {d: i for i, d in enumerate(frame.index)}

    episodes = []
    i = 0
    while i < len(idx):
        if signals.iloc[i]["signal"] != "RE-ENTER":
            i += 1
            continue
        start_i = i
        while i + 1 < len(idx) and signals.iloc[i + 1]["signal"] == "RE-ENTER":
            i += 1
        last_reenter_i = i
        exit_i = i + 1 if i + 1 < len(idx) else None
        if exit_i is None:
            break

        start_date = idx[start_i]
        last_date = idx[last_reenter_i]
        exit_date = idx[exit_i]
        exit_signal = str(signals.iloc[exit_i]["signal"])
        start_pos = price_pos[start_date]
        exit_pos = price_pos[exit_date]
        rec = {
            "start": str(pd.Timestamp(start_date).date()),
            "last_reenter": str(pd.Timestamp(last_date).date()),
            "exit_date": str(pd.Timestamp(exit_date).date()),
            "exit_signal": exit_signal,
            "reenter_sessions": int(last_reenter_i - start_i + 1),
        }
        for sym in ("SPY", "QQQ"):
            entry = float(frame.at[start_date, sym])
            exit_px = float(frame.at[exit_date, sym])
            path = frame[sym].iloc[start_pos:exit_pos + 1].astype(float)
            rec[f"{sym}_entry_close"] = entry
            rec[f"{sym}_exit_close"] = exit_px
            rec[f"{sym}_return_to_exit"] = exit_px / entry - 1.0
            rec[f"{sym}_max_gain_during_episode"] = float(path.max() / entry - 1.0)
            rec[f"{sym}_max_adverse_during_episode"] = float(path.min() / entry - 1.0)
            for h in POST_WAIT_HORIZONS:
                j = exit_pos + h
                rec[f"{sym}_post_exit_{h}d"] = float(frame[sym].iloc[j] / exit_px - 1.0) if j < len(frame) else None
        episodes.append(rec)
        i += 1

    wait_episodes = [e for e in episodes if e["exit_signal"] == "WAIT"]
    no_setup_episodes = [e for e in episodes if e["exit_signal"] == "NO RE-ENTRY SETUP"]
    out = {
        "definition": "contiguous RE-ENTER episode measured from first RE-ENTER close to the next non-RE-ENTER close; explicit_wait_subset includes only episodes whose next state is WAIT",
        "episode_counts": {
            "all": len(episodes),
            "explicit_wait": len(wait_episodes),
            "no_setup": len(no_setup_episodes),
        },
        "summary_all_next_non_reenter": summarize_episode_set(episodes),
        "summary_explicit_wait": summarize_episode_set(wait_episodes),
        "episodes": episodes,
    }

    p = Path("artifacts/reentry_episode_exit")
    p.mkdir(parents=True, exist_ok=True)
    (p / "episode_exit_backtest.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    pd.DataFrame(episodes).to_csv(p / "episode_exit_backtest.csv", index=False)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
