from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CANONICAL_ENGINE_COMMIT = "47f38bf3362a97bcf9c9dd2d6545c4fae212e046"


def summarize(values: list[float]) -> dict[str, Any]:
    a = np.asarray(values, dtype=float)
    if len(a) == 0:
        return {
            "n": 0,
            "median": None,
            "mean": None,
            "positive_rate": None,
            "p25": None,
            "p75": None,
            "min": None,
            "max": None,
        }
    return {
        "n": int(len(a)),
        "median": float(np.median(a)),
        "mean": float(np.mean(a)),
        "positive_rate": float(np.mean(a > 0)),
        "p25": float(np.quantile(a, 0.25)),
        "p75": float(np.quantile(a, 0.75)),
        "min": float(np.min(a)),
        "max": float(np.max(a)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-root", default="canonical")
    parser.add_argument("--output", default="web/public/reentry/historical_episodes.json")
    args = parser.parse_args()

    canonical_tools = Path(args.canonical_root).resolve() / "tools"
    if not canonical_tools.exists():
        raise SystemExit(f"Canonical tools path not found: {canonical_tools}")
    sys.path.insert(0, str(canonical_tools))

    from reentry_confidence import feature_frame  # type: ignore
    from reentry_engine import historical_validation_block  # type: ignore
    from reentry_episode_exit_backtest import build_canonical_signal_history  # type: ignore
    from internal_correction_v2 import PRIMARY_COOLDOWN, cooldown_dates  # type: ignore

    frame = feature_frame()
    signals = build_canonical_signal_history(frame)
    idx = list(signals.index)
    pos = {d: i for i, d in enumerate(idx)}
    price_pos = {d: i for i, d in enumerate(frame.index)}

    reenter_mask = signals["signal"].eq("RE-ENTER")
    validated_signal_dates = cooldown_dates(reenter_mask, PRIMARY_COOLDOWN)

    validated = historical_validation_block()
    expected = int(validated["final_independent_reentry_episodes"])
    if len(validated_signal_dates) != expected:
        raise RuntimeError(
            f"Validated signal-date mismatch: reconstructed={len(validated_signal_dates)} expected={expected}"
        )

    episodes: list[dict[str, Any]] = []
    for signal_date in validated_signal_dates:
        start_i = pos[signal_date]
        last_i = start_i
        while last_i + 1 < len(idx) and str(signals.iloc[last_i + 1]["signal"]) == "RE-ENTER":
            last_i += 1

        next_i = last_i + 1 if last_i + 1 < len(idx) else None
        last_date = idx[last_i]
        next_date = idx[next_i] if next_i is not None else None
        next_signal = str(signals.iloc[next_i]["signal"]) if next_i is not None else None
        start_pos = price_pos[signal_date]
        last_pos = price_pos[last_date]

        rec: dict[str, Any] = {
            "start": str(pd.Timestamp(signal_date).date()),
            "last_favorable": str(pd.Timestamp(last_date).date()),
            "next_state_date": str(pd.Timestamp(next_date).date()) if next_date is not None else None,
            "next_state": next_signal,
            "active_at_sample_end": next_i is None,
            "reenter_sessions": int(last_i - start_i + 1),
            "setup_source": str(signals.loc[signal_date, "source"]),
            "analog_at_start": str(signals.loc[signal_date, "analog"]),
        }

        for sym in ("SPY", "QQQ"):
            entry = float(frame.at[signal_date, sym])
            last = float(frame.at[last_date, sym])
            path = frame[sym].iloc[start_pos : last_pos + 1].astype(float)
            rec[f"{sym}_entry_close"] = entry
            rec[f"{sym}_last_favorable_close"] = last
            rec[f"{sym}_return_during_episode"] = last / entry - 1.0
            rec[f"{sym}_max_gain_during_episode"] = float(path.max() / entry - 1.0)
            rec[f"{sym}_max_adverse_during_episode"] = float(path.min() / entry - 1.0)

        episodes.append(rec)

    completed = [e for e in episodes if not e["active_at_sample_end"]]
    summary = {
        "completed_episode_count": len(completed),
        "active_at_sample_end_count": len(episodes) - len(completed),
        "episode_length_sessions": summarize([float(e["reenter_sessions"]) for e in completed]),
        "SPY": {
            "return_during_episode": summarize([float(e["SPY_return_during_episode"]) for e in completed]),
            "max_gain_during_episode": summarize([float(e["SPY_max_gain_during_episode"]) for e in completed]),
            "max_adverse_during_episode": summarize([float(e["SPY_max_adverse_during_episode"]) for e in completed]),
        },
        "QQQ": {
            "return_during_episode": summarize([float(e["QQQ_return_during_episode"]) for e in completed]),
            "max_gain_during_episode": summarize([float(e["QQQ_max_gain_during_episode"]) for e in completed]),
            "max_adverse_during_episode": summarize([float(e["QQQ_max_adverse_during_episode"]) for e in completed]),
        },
    }

    payload = {
        "schema_version": "1.1",
        "canonical_engine_commit": CANONICAL_ENGINE_COMMIT,
        "validated_independent_reentry_signals": expected,
        "reconstructed_signal_rows": len(episodes),
        "signal_selection_definition": (
            f"Canonical RE-ENTER dates selected with the validated {PRIMARY_COOLDOWN}-session cooldown; this reproduces the {expected} independent signal dates used by the canonical validation."
        ),
        "definition": (
            "For each validated RE-ENTRY signal date, performance is measured from that completed signal close through the last consecutive completed close that still says RE-ENTER. "
            "The following WAIT or NO RE-ENTRY SETUP close is reported separately and is not included in the episode return."
        ),
        "return_definition": "close at last favorable RE-ENTER session divided by close at validated RE-ENTRY signal session minus one; this is historical evidence, not an exit or sell rule",
        "summary_completed_episodes": summary,
        "fixed_horizon_validation": {
            "SPY": {
                "5D_median": validated["SPY_5D_median_after_signal"],
                "10D_median": validated["SPY_10D_median_after_signal"],
                "30D_median": validated["SPY_30D_median_after_signal"],
                "60D_median": validated["SPY_60D_median_after_signal"],
            },
            "QQQ": {
                "5D_median": validated["QQQ_5D_median_after_signal"],
                "10D_median": validated["QQQ_10D_median_after_signal"],
                "30D_median": validated["QQQ_30D_median_after_signal"],
                "60D_median": validated["QQQ_60D_median_after_signal"],
            },
        },
        "episodes": list(reversed(episodes)),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps({
        "validated_independent_reentry_signals": expected,
        "reconstructed_signal_rows": len(episodes),
        "completed_episode_count": len(completed),
        "active_at_sample_end_count": len(episodes) - len(completed),
        "output": str(out),
    }, indent=2))


if __name__ == "__main__":
    main()
