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

HORIZONS = (5, 7, 10, 15, 30, 60)
ENGINE_COMMIT = "47f38bf3362a97bcf9c9dd2d6545c4fae212e046"


def build_signal_history(base: pd.DataFrame) -> pd.DataFrame:
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


def forward_from_start(frame: pd.DataFrame, symbol: str, start_pos: int, horizon: int) -> float | None:
    j = start_pos + horizon
    if j >= len(frame):
        return None
    start_px = float(frame[symbol].iloc[start_pos])
    end_px = float(frame[symbol].iloc[j])
    return end_px / start_px - 1.0


def summarize(values: list[float]) -> dict:
    a = np.asarray(values, dtype=float)
    if not len(a):
        return {"n": 0, "mean": None, "median": None, "positive_rate": None, "p25": None, "p75": None}
    return {
        "n": int(len(a)),
        "mean": float(np.mean(a)),
        "median": float(np.median(a)),
        "positive_rate": float(np.mean(a > 0)),
        "p25": float(np.quantile(a, 0.25)),
        "p75": float(np.quantile(a, 0.75)),
    }


def main() -> None:
    frame = feature_frame()
    signals = build_signal_history(frame)
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
        last_i = i
        next_i = i + 1 if i + 1 < len(idx) else None

        start_date = idx[start_i]
        last_date = idx[last_i]
        next_date = idx[next_i] if next_i is not None else None
        start_pos = price_pos[start_date]
        last_pos = price_pos[last_date]
        transition_pos = price_pos[next_date] if next_date is not None else last_pos

        rec = {
            "start": str(pd.Timestamp(start_date).date()),
            "favorable_through": str(pd.Timestamp(last_date).date()),
            "next_state_date": str(pd.Timestamp(next_date).date()) if next_date is not None else None,
            "next_state": str(signals.iloc[next_i]["signal"]) if next_i is not None else None,
            "reenter_sessions": int(last_i - start_i + 1),
            "signal_source": str(signals.iloc[start_i]["source"]),
            "analog_at_start": str(signals.iloc[start_i]["analog"]),
        }

        for sym in ("SPY", "QQQ"):
            start_px = float(frame.at[start_date, sym])
            last_px = float(frame.at[last_date, sym])
            transition_px = float(frame.at[next_date, sym]) if next_date is not None else last_px
            favorable_path = frame[sym].iloc[start_pos:last_pos + 1].astype(float)
            active_path = frame[sym].iloc[start_pos:transition_pos + 1].astype(float)

            rec[f"{sym}_start_close"] = start_px
            rec[f"{sym}_favorable_through_close"] = last_px
            rec[f"{sym}_transition_close"] = transition_px if next_date is not None else None
            rec[f"{sym}_strict_last_reenter_close_return"] = last_px / start_px - 1.0
            # Primary episode return: the RE-ENTER state set at the prior close remains
            # the active state through the next completed close, when any WAIT/NO-SETUP
            # transition first becomes knowable.
            rec[f"{sym}_episode_return"] = transition_px / start_px - 1.0
            rec[f"{sym}_return_until_state_change"] = rec[f"{sym}_episode_return"]
            rec[f"{sym}_max_gain_during_episode"] = float(active_path.max() / start_px - 1.0)
            rec[f"{sym}_max_adverse_during_episode"] = float(active_path.min() / start_px - 1.0)
            rec[f"{sym}_max_gain_before_transition_close"] = float(favorable_path.max() / start_px - 1.0)
            rec[f"{sym}_max_adverse_before_transition_close"] = float(favorable_path.min() / start_px - 1.0)
            for h in HORIZONS:
                rec[f"{sym}_{h}d_from_start"] = forward_from_start(frame, sym, start_pos, h)

        episodes.append(rec)
        i += 1

    completed = [e for e in episodes if e["next_state_date"] is not None]
    payload = {
        "provenance": {
            "classification": "RECONSTRUCTED",
            "engine_commit": ENGINE_COMMIT,
            "rebuild_date": "2026-09-09",
            "data_note": "Rebuilt with the frozen validated engine and currently returned historical vendor series. Historical vendor adjustments can revise some reconstructed boundaries or prices; archived aggregate canonical validation remains authoritative for validated performance statistics.",
        },
        "definition": "A continuous episode begins on the first RE-ENTER completed close. RE-ENTER remains the active state until a later completed close changes it to WAIT or NO RE-ENTRY SETUP, so primary episode return is measured from the first RE-ENTER close through that state-change close. The last consecutive RE-ENTER close is retained separately as favorable_through for signal-path inspection.",
        "forward_return_definition": "Reconstructed row-level fixed-horizon returns are close-to-close from the first RE-ENTER close. They are transparency diagnostics and are not substituted for the archived canonical aggregate validator.",
        "episode_count": len(episodes),
        "completed_episode_count": len(completed),
        "active_episode_count": len(episodes) - len(completed),
        "summary": {
            "SPY_episode_return": summarize([e["SPY_episode_return"] for e in completed]),
            "QQQ_episode_return": summarize([e["QQQ_episode_return"] for e in completed]),
            "duration_sessions": summarize([float(e["reenter_sessions"]) for e in completed]),
        },
        "episodes": episodes,
    }

    out = Path("artifacts/reentry_historical_ledger")
    out.mkdir(parents=True, exist_ok=True)
    (out / "historical_episode_ledger.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    pd.DataFrame(episodes).to_csv(out / "historical_episode_ledger.csv", index=False)
    print(json.dumps({"episode_count": len(episodes), "completed": len(completed), "last": episodes[-1] if episodes else None}, indent=2))


if __name__ == "__main__":
    main()
