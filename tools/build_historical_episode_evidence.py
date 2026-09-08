from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CANONICAL_ENGINE_COMMIT = "47f38bf3362a97bcf9c9dd2d6545c4fae212e046"
CANONICAL_SAMPLE_END = pd.Timestamp("2026-09-04")
ARCHIVED_VALIDATION_EVENT_COUNT = 193
ARCHIVED_FIXED_HORIZON = {
    "SPY": {
        "5D": {"median": 0.0033556370510425823, "n": 192},
        "10D": {"median": 0.009152932300412253, "n": 192},
        "30D": {"median": 0.02466637540251826, "n": 190},
        "60D": {"median": 0.04115004106864273, "n": 188},
    },
    "QQQ": {
        "5D": {"median": 0.003169911810773974, "n": 192},
        "10D": {"median": 0.011375142671303129, "n": 192},
        "30D": {"median": 0.02742219834317583, "n": 190},
        "60D": {"median": 0.04901809774131394, "n": 188},
    },
}


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


def build_exact_policy(canonical_tools: Path):
    sys.path.insert(0, str(canonical_tools))
    from internal_correction_full_v2 import build_full_v2_state  # type: ignore
    from internal_correction_v2 import build_cross_section, cooldown_dates, load_prices, PRIMARY_COOLDOWN  # type: ignore
    from reentry_confidence import analogs_for_date, feature_frame, summarize_analogs  # type: ignore
    from reentry_decision import decision_from_analogs  # type: ignore
    from reentry_early_entry_policy import early_entry_decision  # type: ignore
    from reentry_engine import _internal_reset, _selling_pressure, _unified_signal, weakness_context  # type: ignore

    base = feature_frame(require_same_day=False)
    prices = load_prices()
    xs = build_cross_section(prices)
    df = base.join(xs, how="inner").dropna(subset=["spy_dd20", "sector_dispersion_pct"]).copy()
    df = build_full_v2_state(df)
    df = df.loc[:CANONICAL_SAMPLE_END].copy()

    final_signal: list[str] = []
    sources: list[str] = []
    analog_labels: list[str] = []
    for target in df.index:
        try:
            analogs = analogs_for_date(base, target)
            analog_summary = summarize_analogs(base, analogs)
            analog_decision, _, _ = decision_from_analogs(analog_summary, base.loc[target])
        except Exception:
            final_signal.append("NO RE-ENTRY SETUP")
            sources.append("UNAVAILABLE")
            analog_labels.append("NO")
            continue
        row = df.loc[target]
        weak, _ = weakness_context(row)
        base_signal, _, _ = _unified_signal(analog_decision, weak, row)
        signal, _, source = early_entry_decision(
            analog_decision=analog_decision,
            weakness_present=weak,
            internal_reset=_internal_reset(row),
            selling_pressure=_selling_pressure(row),
            existing_signal=base_signal,
        )
        final_signal.append(signal)
        sources.append(source)
        analog_labels.append(analog_decision)

    df["final_signal"] = final_signal
    df["signal_source"] = sources
    df["analog_decision"] = analog_labels
    df["final_reenter"] = df["final_signal"].eq("RE-ENTER")
    cooldown_events = cooldown_dates(df["final_reenter"], PRIMARY_COOLDOWN)
    return prices, df, cooldown_events, PRIMARY_COOLDOWN


def build_continuous_episodes(prices: pd.DataFrame, df: pd.DataFrame) -> list[dict[str, Any]]:
    idx = list(df.index)
    episodes: list[dict[str, Any]] = []
    i = 0
    while i < len(idx):
        if str(df.iloc[i]["final_signal"]) != "RE-ENTER":
            i += 1
            continue
        if i > 0 and str(df.iloc[i - 1]["final_signal"]) == "RE-ENTER":
            i += 1
            continue

        start_i = i
        last_i = i
        while last_i + 1 < len(idx) and str(df.iloc[last_i + 1]["final_signal"]) == "RE-ENTER":
            last_i += 1

        start_date = idx[start_i]
        last_date = idx[last_i]
        next_i = last_i + 1 if last_i + 1 < len(idx) else None
        next_date = idx[next_i] if next_i is not None else None
        next_signal = str(df.iloc[next_i]["final_signal"]) if next_i is not None else None

        rec: dict[str, Any] = {
            "start": str(pd.Timestamp(start_date).date()),
            "last_favorable": str(pd.Timestamp(last_date).date()),
            "next_state_date": str(pd.Timestamp(next_date).date()) if next_date is not None else None,
            "next_state": next_signal,
            "active_at_sample_end": next_i is None,
            "reenter_sessions": int(last_i - start_i + 1),
            "setup_source": str(df.iloc[start_i]["signal_source"]),
            "analog_at_start": str(df.iloc[start_i]["analog_decision"]),
        }

        for sym in ("SPY", "QQQ"):
            series = prices[sym].dropna()
            if start_date not in series.index or last_date not in series.index:
                raise RuntimeError(f"Missing {sym} close for continuous episode {start_date} to {last_date}")
            entry = float(series.loc[start_date])
            last = float(series.loc[last_date])
            p0 = series.index.get_loc(start_date)
            p1 = series.index.get_loc(last_date)
            if not isinstance(p0, (int, np.integer)) or not isinstance(p1, (int, np.integer)):
                raise RuntimeError("Unexpected duplicate price index")
            path = series.iloc[p0:p1 + 1].astype(float)
            rec[f"{sym}_entry_close"] = entry
            rec[f"{sym}_last_favorable_close"] = last
            rec[f"{sym}_return_during_episode"] = last / entry - 1.0
            rec[f"{sym}_max_gain_during_episode"] = float(path.max() / entry - 1.0)
            rec[f"{sym}_max_adverse_during_episode"] = float(path.min() / entry - 1.0)

        episodes.append(rec)
        i = last_i + 1

    return episodes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-root", default="canonical")
    parser.add_argument("--output", default="web/public/reentry/historical_episodes.json")
    args = parser.parse_args()

    canonical_tools = Path(args.canonical_root).resolve() / "tools"
    if not canonical_tools.exists():
        raise SystemExit(f"Canonical tools path not found: {canonical_tools}")

    prices, df, cooldown_events, cooldown = build_exact_policy(canonical_tools)
    episodes = build_continuous_episodes(prices, df)
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
        "schema_version": "3.0",
        "canonical_engine_commit": CANONICAL_ENGINE_COMMIT,
        "canonical_sample_end": str(CANONICAL_SAMPLE_END.date()),
        "frozen_reconstruction_generated_at": datetime.now(timezone.utc).isoformat(),
        "continuous_episode_count": len(episodes),
        "continuous_episode_definition": (
            "An episode begins on the first completed close where the exact canonical final policy changes into RE-ENTER and ends on the last consecutive completed close that still says RE-ENTER. "
            "The next WAIT or NO RE-ENTRY SETUP close is shown separately and is not included in the return."
        ),
        "return_definition": (
            "Episode return equals the last favorable RE-ENTER close divided by the first RE-ENTER close minus one. "
            "This is historical measurement only and does not create an exit or sell rule."
        ),
        "continuous_episode_summary": summary,
        "continuous_episodes": list(reversed(episodes)),
        "archived_entry_timing_validation": {
            "source": "canonical run 34156095215 / reentry/final_policy_validation.json",
            "validation_event_count": ARCHIVED_VALIDATION_EVENT_COUNT,
            "event_definition": f"Cooldown-selected canonical RE-ENTRY validation events using a {cooldown}-session cooldown; these are validation events, not continuous episodes.",
            "fixed_horizon": ARCHIVED_FIXED_HORIZON,
        },
        "reconstruction_diagnostic": {
            "current_cooldown_event_count": len(cooldown_events),
            "archived_cooldown_event_count": ARCHIVED_VALIDATION_EVENT_COUNT,
            "status": "HISTORICAL_INPUT_DRIFT" if len(cooldown_events) != ARCHIVED_VALIDATION_EVENT_COUNT else "MATCH",
            "note": (
                "The row-level continuous episode reconstruction is frozen in this artifact. The archived fixed-horizon statistics are preserved from the original validation artifact and are not recomputed from mutable historical inputs."
            ),
        },
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({
        "continuous_episode_count": len(episodes),
        "completed_episode_count": len(completed),
        "active_at_sample_end_count": len(episodes) - len(completed),
        "SPY_episode_median": summary["SPY"]["return_during_episode"]["median"],
        "SPY_episode_positive_rate": summary["SPY"]["return_during_episode"]["positive_rate"],
        "QQQ_episode_median": summary["QQQ"]["return_during_episode"]["median"],
        "QQQ_episode_positive_rate": summary["QQQ"]["return_during_episode"]["positive_rate"],
        "median_sessions": summary["episode_length_sessions"]["median"],
        "current_cooldown_event_count": len(cooldown_events),
        "archived_validation_event_count": ARCHIVED_VALIDATION_EVENT_COUNT,
        "output": str(out),
    }, indent=2))


if __name__ == "__main__":
    main()
