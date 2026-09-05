from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_confidence import feature_frame
from reentry_engine import build_signal_frame

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


def main() -> None:
    frame = feature_frame()
    signals = build_signal_frame(frame)
    if "signal" not in signals.columns:
        raise SystemExit("build_signal_frame must return a signal column")

    idx = signals.index
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
        wait_i = i + 1 if i + 1 < len(idx) else None
        if wait_i is None:
            break

        start_date = idx[start_i]
        last_date = idx[last_reenter_i]
        wait_date = idx[wait_i]
        rec = {
            "start": str(pd.Timestamp(start_date).date()),
            "last_reenter": str(pd.Timestamp(last_date).date()),
            "first_wait": str(pd.Timestamp(wait_date).date()),
            "reenter_sessions": int(last_reenter_i - start_i + 1),
        }
        for sym in ("SPY", "QQQ"):
            entry = float(frame.at[start_date, sym])
            wait_px = float(frame.at[wait_date, sym])
            path = frame[sym].iloc[start_i:wait_i + 1].astype(float)
            rec[f"{sym}_entry_close"] = entry
            rec[f"{sym}_first_wait_close"] = wait_px
            rec[f"{sym}_return_to_first_wait"] = wait_px / entry - 1.0
            rec[f"{sym}_max_gain_during_episode"] = float(path.max() / entry - 1.0)
            rec[f"{sym}_max_adverse_during_episode"] = float(path.min() / entry - 1.0)
            for h in POST_WAIT_HORIZONS:
                j = wait_i + h
                rec[f"{sym}_post_wait_{h}d"] = float(frame[sym].iloc[j] / wait_px - 1.0) if j < len(frame) else None
        episodes.append(rec)
        i += 1

    out = {"episodes": episodes, "summary": {}}
    for sym in ("SPY", "QQQ"):
        out["summary"][sym] = {
            "entry_to_first_wait": summarize([e[f"{sym}_return_to_first_wait"] for e in episodes]),
            "max_gain_during_episode": summarize([e[f"{sym}_max_gain_during_episode"] for e in episodes]),
            "max_adverse_during_episode": summarize([e[f"{sym}_max_adverse_during_episode"] for e in episodes]),
            **{f"post_wait_{h}d": summarize([e[f"{sym}_post_wait_{h}d"] for e in episodes if e[f"{sym}_post_wait_{h}d"] is not None]) for h in POST_WAIT_HORIZONS},
        }
    out["summary"]["episode_length_sessions"] = summarize([float(e["reenter_sessions"]) for e in episodes])

    p = Path("artifacts/reentry_episode_exit")
    p.mkdir(parents=True, exist_ok=True)
    (p / "episode_exit_backtest.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    pd.DataFrame(episodes).to_csv(p / "episode_exit_backtest.csv", index=False)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
