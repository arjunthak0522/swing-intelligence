from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_cash_policy_validation import historical_proxy_states
from reentry_confidence import feature_frame
from reentry_walkforward_validation import generate_decisions

ROUND_TRIP_COST = 0.001
ENTRY_DELAYS = (0, 1, 2, 3, 5, 7, 10, 15, 20, 30)
HORIZONS = (1, 3, 5, 10, 15, 30, 60)
EPISODE_COOLDOWN = 10
MAX_WINDOW_SESSIONS = 30


def independent_deploy_dates(states: pd.DataFrame) -> list[pd.Timestamp]:
    deploy = states["deployment_signal"].eq("DEPLOY")
    starts = deploy & ~deploy.shift(1, fill_value=False)
    dates: list[pd.Timestamp] = []
    last_start_pos = -10_000
    for pos, (date, active) in enumerate(starts.items()):
        if active and pos - last_start_pos > EPISODE_COOLDOWN:
            dates.append(pd.Timestamp(date))
            last_start_pos = pos
    return dates


def forward_from_delay(frame: pd.DataFrame, symbol: str, signal_date: pd.Timestamp, delay: int, horizon: int) -> float | None:
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
        return {"n": 0, "median_return": None, "mean_return": None, "positive_rate": None, "p25": None, "p75": None}
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


def entry_price_cost(frame: pd.DataFrame, symbol: str, signal_date: pd.Timestamp, delay: int) -> float | None:
    pos = frame.index.get_loc(signal_date)
    if not isinstance(pos, (int, np.integer)):
        return None
    d0_i = pos + 1
    delayed_i = d0_i + delay
    if delayed_i >= len(frame):
        return None
    p0 = frame[symbol].iloc[d0_i]
    pdly = frame[symbol].iloc[delayed_i]
    if pd.isna(p0) or pd.isna(pdly):
        return None
    return float(pdly / p0 - 1.0)


def same_exit_capture(frame: pd.DataFrame, symbol: str, signal_date: pd.Timestamp, delay: int, terminal: int) -> float | None:
    pos = frame.index.get_loc(signal_date)
    if not isinstance(pos, (int, np.integer)):
        return None
    d0_i = pos + 1
    delayed_i = d0_i + delay
    exit_i = d0_i + terminal
    if delayed_i >= exit_i or exit_i >= len(frame):
        return None
    p0 = frame[symbol].iloc[d0_i]
    pdly = frame[symbol].iloc[delayed_i]
    pexit = frame[symbol].iloc[exit_i]
    if pd.isna(p0) or pd.isna(pdly) or pd.isna(pexit):
        return None
    d0_ret = float(pexit / p0 - 1.0 - ROUND_TRIP_COST)
    delayed_ret = float(pexit / pdly - 1.0 - ROUND_TRIP_COST)
    return d0_ret - delayed_ret


def candidate_flags(states: pd.DataFrame, frame: pd.DataFrame) -> dict[str, pd.Series]:
    idx = states.index
    spy = frame["SPY"].reindex(idx)
    low20 = spy.rolling(20, min_periods=5).min()
    recovery = spy / low20 - 1.0
    oversold_cleared = ~states["oversold_proxy"].astype(bool)
    b50 = pd.to_numeric(states["B50"], errors="coerce")
    vix_easing = pd.to_numeric(states["vix_change5"], errors="coerce") <= 0.0
    curve_calm = pd.to_numeric(states["curve_ratio"], errors="coerce") <= 0.95
    return {
        "oversold_cleared": oversold_cleared,
        "breadth_50pct": b50 >= 0.50,
        "breadth_60pct": b50 >= 0.60,
        "oversold_cleared_and_breadth_50pct": oversold_cleared & (b50 >= 0.50),
        "oversold_cleared_and_vix_easing": oversold_cleared & vix_easing,
        "recovered_2pct_from_20d_low": recovery >= 0.02,
        "recovered_4pct_from_20d_low": recovery >= 0.04,
        "recovered_4pct_and_breadth_50pct": (recovery >= 0.04) & (b50 >= 0.50),
        "breadth_50pct_and_vix_easing": (b50 >= 0.50) & vix_easing,
        "breadth_50pct_vix_easing_curve_calm": (b50 >= 0.50) & vix_easing & curve_calm,
    }


def first_hit_after_signal(series: pd.Series, signal_date: pd.Timestamp, max_sessions: int = MAX_WINDOW_SESSIONS) -> tuple[int, pd.Timestamp] | None:
    if signal_date not in series.index:
        return None
    pos = series.index.get_loc(signal_date)
    if not isinstance(pos, (int, np.integer)):
        return None
    for delay in range(1, max_sessions + 1):
        i = pos + delay
        if i >= len(series):
            break
        if bool(series.iloc[i]):
            return delay, pd.Timestamp(series.index[i])
    return None


def evaluate_end_conditions(states: pd.DataFrame, frame: pd.DataFrame, deploy_dates: list[pd.Timestamp]) -> dict:
    flags = candidate_flags(states, frame)
    out: dict[str, dict] = {}
    for name, flag in flags.items():
        hits: list[int] = []
        hit_returns: dict[str, dict[str, list[float]]] = {
            sym: {f"{h}D": [] for h in (5, 10, 15, 30, 60)} for sym in ("SPY", "QQQ")
        }
        for date in deploy_dates:
            hit = first_hit_after_signal(flag, date)
            if hit is None:
                continue
            delay, _ = hit
            hits.append(delay)
            for sym in ("SPY", "QQQ"):
                for h in (5, 10, 15, 30, 60):
                    value = forward_from_delay(frame, sym, date, delay, h)
                    if value is not None:
                        hit_returns[sym][f"{h}D"].append(value)
        hit_arr = np.asarray(hits, dtype=float)
        result = {
            "episodes_hit": int(len(hits)),
            "hit_rate": float(len(hits) / len(deploy_dates)) if deploy_dates else None,
            "median_sessions_to_hit": float(np.median(hit_arr)) if len(hit_arr) else None,
            "p25_sessions_to_hit": float(np.quantile(hit_arr, 0.25)) if len(hit_arr) else None,
            "p75_sessions_to_hit": float(np.quantile(hit_arr, 0.75)) if len(hit_arr) else None,
            "forward_returns_when_condition_first_hits": {
                sym: {h: summarize(vals) for h, vals in hs.items()} for sym, hs in hit_returns.items()
            },
        }
        # A candidate is only plausible as an END condition if the opportunity is no longer broadly favorable after it hits.
        cells = []
        for sym in ("SPY", "QQQ"):
            for h in (10, 15, 30, 60):
                s = result["forward_returns_when_condition_first_hits"][sym][f"{h}D"]
                if s["n"] >= 20 and s["median_return"] is not None:
                    cells.append(s["median_return"] > 0)
        result["positive_medium_long_cells"] = int(sum(cells))
        result["eligible_medium_long_cells"] = int(len(cells))
        result["premature_exit_flag"] = bool(cells and sum(cells) >= max(1, int(np.ceil(0.75 * len(cells)))))
        out[name] = result
    return out


def main() -> None:
    frame, metadata = feature_frame(return_metadata=True, require_same_day=False)
    decisions = generate_decisions(frame)
    states = historical_proxy_states(frame, decisions)
    deploy_dates = independent_deploy_dates(states)

    raw: dict[str, dict[int, dict[int, dict[str, float]]]] = {
        symbol: {delay: {h: {} for h in HORIZONS} for delay in ENTRY_DELAYS}
        for symbol in ("SPY", "QQQ")
    }
    usable_dates: list[str] = []
    price_cost: dict[str, dict[int, list[float]]] = {sym: {d: [] for d in ENTRY_DELAYS if d > 0} for sym in ("SPY", "QQQ")}
    capture: dict[str, dict[int, dict[int, list[float]]]] = {
        sym: {d: {terminal: [] for terminal in (10, 15, 30, 60)} for d in ENTRY_DELAYS if d > 0}
        for sym in ("SPY", "QQQ")
    }

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
                if delay > 0:
                    pc = entry_price_cost(frame, symbol, date, delay)
                    if pc is not None:
                        price_cost[symbol][delay].append(pc)
                    for terminal in (10, 15, 30, 60):
                        sc = same_exit_capture(frame, symbol, date, delay, terminal)
                        if sc is not None:
                            capture[symbol][delay][terminal].append(sc)
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
                    f"{h}D": paired_delay_cost(raw[symbol][0][h], raw[symbol][delay][h]) for h in HORIZONS
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

    end_conditions = evaluate_end_conditions(states, frame, deploy_dates)
    payload = {
        "research_only": True,
        "question": "After an independent DEPLOY event, how long does favorable re-entry expectancy persist and do objective market-normalization conditions identify when it ends?",
        "production_engine_changed": False,
        "historical_signal_basis": "reentry_cash_policy_validation historical proxy states; exact live intraday family history is unavailable",
        "exact_live_state_replication": False,
        "entry_execution": "signal close t; D+0 enters close t+1; later delays add trading sessions; 10 bps round-trip cost",
        "independent_episode_definition": "transition into historical-proxy DEPLOY with 10-session cooldown between episode starts",
        "entry_delays": list(ENTRY_DELAYS),
        "forward_horizons": list(HORIZONS),
        "episode_count": len(usable_dates),
        "episode_dates": usable_dates,
        "data_metadata": metadata,
        "results": results,
        "delay_cost_vs_D0": delay_cost,
        "entry_price_cost_vs_D0": {
            sym: {f"D+{d}": summarize(vals) for d, vals in by_d.items()} for sym, by_d in price_cost.items()
        },
        "same_exit_opportunity_capture_D0_minus_delayed": {
            sym: {f"D+{d}": {f"{t}D_terminal": summarize(vals) for t, vals in terms.items()} for d, terms in by_d.items()}
            for sym, by_d in capture.items()
        },
        "persistence_summary": persistence,
        "objective_end_condition_tests": end_conditions,
        "methodology_checks": {
            "lookahead_entry": False,
            "signal_date_used_for_entry": "close t+1",
            "delay_cost_pairing": "matched by episode date",
            "episode_overlap_control": "episode starts separated by >10 sessions",
            "end_conditions": "first observable hit after signal using contemporaneous historical proxy features only",
            "production_logic_modified": False,
        },
        "interpretation_rule": "Research only. Prefer keeping a re-entry window active unless an objective end condition demonstrably coincides with loss of favorable expectancy. Do not alter REENTRY_UNIFIED_v1 without review and approval.",
    }

    out = Path("artifacts/reentry_deploy_window_decay")
    out.mkdir(parents=True, exist_ok=True)
    (out / "reentry_deploy_window_decay.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
