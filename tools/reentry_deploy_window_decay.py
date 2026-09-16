from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_cash_policy_validation import historical_proxy_states
from reentry_confidence import feature_frame
from reentry_walkforward_validation import generate_decisions

ROUND_TRIP_COST = 0.001
ENTRY_DELAYS = (0, 1, 2, 3, 5, 7, 10)
HORIZONS = (1, 3, 5, 10, 15, 30, 60)
EPISODE_COOLDOWN = 10


def independent_deploy_dates(states: pd.DataFrame) -> list[pd.Timestamp]:
    """Return starts of independent historical proxy DEPLOY episodes.

    A DEPLOY episode begins on the transition into DEPLOY. The cooldown applies between
    episode starts, not between every active DEPLOY day. This mirrors the established
    independent-episode convention and prevents long DEPLOY stretches from suppressing
    every later historical episode.
    """
    deploy = states["deployment_signal"].eq("DEPLOY")
    starts = deploy & ~deploy.shift(1, fill_value=False)
    dates: list[pd.Timestamp] = []
    last_start_pos = -10_000
    for pos, (date, active) in enumerate(starts.items()):
        if active and pos - last_start_pos > EPISODE_COOLDOWN:
            dates.append(pd.Timestamp(date))
            last_start_pos = pos
    return dates


def forward_from_delay(
    frame: pd.DataFrame,
    symbol: str,
    signal_date: pd.Timestamp,
    delay: int,
    horizon: int,
) -> float | None:
    if signal_date not in frame.index:
        return None
    pos = frame.index.get_loc(signal_date)
    if not isinstance(pos, (int, np.integer)):
        return None
    entry_i = pos + 1 + delay
    exit_i = entry_i + horizon
    if exit_i >= len(frame):
        return None
    entry = frame[symbol].iloc[entry_i]
    exit_ = frame[symbol].iloc[exit_i]
    if pd.isna(entry) or pd.isna(exit_):
        return None
    return float(exit_ / entry - 1.0 - ROUND_TRIP_COST)


def summarize(values: list[float]) -> dict:
    a = np.asarray(values, dtype=float)
    if len(a) == 0:
        return {
            "n": 0,
            "median_return": None,
            "mean_return": None,
            "positive_rate": None,
            "p25": None,
            "p75": None,
        }
    return {
        "n": int(len(a)),
        "median_return": float(np.median(a)),
        "mean_return": float(np.mean(a)),
        "positive_rate": float(np.mean(a > 0)),
        "p25": float(np.quantile(a, 0.25)),
        "p75": float(np.quantile(a, 0.75)),
    }


def paired_delay_cost(d0_by_date: dict[str, float], delayed_by_date: dict[str, float]) -> dict:
    common = sorted(set(d0_by_date).intersection(delayed_by_date))
    if not common:
        return {"n": 0, "median_d0_minus_delayed": None, "mean_d0_minus_delayed": None}
    diff = np.asarray([d0_by_date[d] - delayed_by_date[d] for d in common], dtype=float)
    return {
        "n": int(len(diff)),
        "median_d0_minus_delayed": float(np.median(diff)),
        "mean_d0_minus_delayed": float(np.mean(diff)),
    }


def main() -> None:
    frame, metadata = feature_frame(return_metadata=True, require_same_day=False)
    decisions = generate_decisions(frame)
    states = historical_proxy_states(frame, decisions)
    deploy_dates = independent_deploy_dates(states)

    # Preserve episode identity so D0-vs-delayed comparisons are truly paired even when
    # late-sample horizons become unavailable near the end of the data set.
    raw: dict[str, dict[int, dict[int, dict[str, float]]]] = {
        symbol: {delay: {h: {} for h in HORIZONS} for delay in ENTRY_DELAYS}
        for symbol in ("SPY", "QQQ")
    }
    usable_dates: list[str] = []

    for date in deploy_dates:
        date_key = str(date.date())
        complete_any = False
        for symbol in ("SPY", "QQQ"):
            for delay in ENTRY_DELAYS:
                for horizon in HORIZONS:
                    value = forward_from_delay(frame, symbol, date, delay, horizon)
                    if value is not None:
                        raw[symbol][delay][horizon][date_key] = value
                        complete_any = True
        if complete_any:
            usable_dates.append(date_key)

    results: dict = {}
    delay_cost: dict = {}
    for symbol in ("SPY", "QQQ"):
        results[symbol] = {}
        delay_cost[symbol] = {}
        for delay in ENTRY_DELAYS:
            results[symbol][f"D+{delay}"] = {
                f"{h}D": summarize(list(raw[symbol][delay][h].values())) for h in HORIZONS
            }
            if delay > 0:
                delay_cost[symbol][f"D+{delay}"] = {
                    f"{h}D": paired_delay_cost(raw[symbol][0][h], raw[symbol][delay][h])
                    for h in HORIZONS
                }

    persistence = {}
    for delay in ENTRY_DELAYS:
        if delay == 0:
            continue
        cells = []
        for symbol in ("SPY", "QQQ"):
            for h in (5, 10, 15, 30, 60):
                r = results[symbol][f"D+{delay}"][f"{h}D"]
                if r["n"] >= 20 and r["median_return"] is not None:
                    cells.append(r["median_return"] > 0)
        persistence[f"D+{delay}"] = {
            "eligible_cells": len(cells),
            "positive_median_cells": int(sum(cells)),
            "positive_median_share": float(np.mean(cells)) if cells else None,
        }

    payload = {
        "research_only": True,
        "question": "After an independent DEPLOY event, how quickly does the historical re-entry advantage decay if spare cash is deployed on later sessions?",
        "production_engine_changed": False,
        "historical_signal_basis": "reentry_cash_policy_validation historical proxy states; exact live intraday family history is unavailable",
        "exact_live_state_replication": False,
        "entry_execution": "signal close t; D+0 enters close t+1; later delays add trading sessions; 10 bps round-trip cost",
        "independent_episode_definition": "transition into historical-proxy DEPLOY with 10-session cooldown between episode starts",
        "independent_episode_cooldown_sessions": EPISODE_COOLDOWN,
        "entry_delays": list(ENTRY_DELAYS),
        "forward_horizons": list(HORIZONS),
        "episode_count": len(usable_dates),
        "episode_dates": usable_dates,
        "data_metadata": metadata,
        "results": results,
        "delay_cost_vs_D0": delay_cost,
        "persistence_summary": persistence,
        "methodology_checks": {
            "lookahead_entry": False,
            "signal_date_used_for_entry": "close t+1",
            "delay_cost_pairing": "matched by episode date",
            "episode_overlap_control": "episode starts separated by >10 sessions",
            "production_logic_modified": False,
        },
        "interpretation_rule": "Descriptive evidence only. Do not alter REENTRY_UNIFIED_v1 or create an active-window rule without separate review and approval.",
    }

    out = Path("artifacts/reentry_deploy_window_decay")
    out.mkdir(parents=True, exist_ok=True)
    (out / "reentry_deploy_window_decay.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
