from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from reentry_confidence import feature_frame, _normalize_daily_index
from reentry_engine import _build_unified_frame, _internal_reset, _selling_pressure, FAVORABLE_ANALOGS
from reentry_episode_exit_backtest import build_canonical_signal_history

HORIZONS = (5, 7, 10, 15, 30, 60)
ROUND_TRIP_COST = 0.001
COOLDOWN = 10
CONFIRM_WINDOW = 5
RNG = np.random.default_rng(20260905)


def fetch_rsp(start: str = "2016-09-01") -> pd.Series:
    raw = yf.download(
        "RSP",
        start=start,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
        group_by="column",
    )
    if raw.empty:
        raise RuntimeError("RSP history unavailable")
    raw = _normalize_daily_index(raw)
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = pd.to_numeric(close, errors="coerce").dropna().astype(float)
    close.name = "RSP"
    return close


def independent_starts(signal: pd.Series, cooldown: int = COOLDOWN) -> list[pd.Timestamp]:
    starts = signal.eq("RE-ENTER") & ~signal.shift(1, fill_value="").eq("RE-ENTER")
    candidates = list(signal.index[starts])
    kept: list[pd.Timestamp] = []
    last_pos = -10_000
    for d in candidates:
        pos = signal.index.get_loc(d)
        if isinstance(pos, (int, np.integer)) and pos - last_pos > cooldown:
            kept.append(pd.Timestamp(d))
            last_pos = int(pos)
    return kept


def cooldown_dates(mask: pd.Series, cooldown: int = COOLDOWN) -> list[pd.Timestamp]:
    out: list[pd.Timestamp] = []
    last = -10_000
    for i, flag in enumerate(mask.fillna(False).to_numpy(bool)):
        if flag and i - last > cooldown:
            out.append(pd.Timestamp(mask.index[i]))
            last = i
    return out


def outcome(frame: pd.DataFrame, date: pd.Timestamp, symbol: str, horizon: int) -> tuple[float, float] | None:
    if date not in frame.index:
        return None
    pos = frame.index.get_loc(date)
    if not isinstance(pos, (int, np.integer)) or pos + 1 + horizon >= len(frame):
        return None
    entry_i = int(pos) + 1
    path = frame[symbol].iloc[entry_i: entry_i + horizon + 1].astype(float)
    if len(path) < horizon + 1:
        return None
    entry = float(path.iloc[0])
    ret = float(path.iloc[-1] / entry - 1.0 - ROUND_TRIP_COST)
    mae = float((path / entry - 1.0).min())
    return ret, mae


def summarize(values: list[float]) -> dict:
    a = np.asarray(values, dtype=float)
    if len(a) == 0:
        return {"n": 0, "median": None, "mean": None, "positive_rate": None, "p25": None}
    return {
        "n": int(len(a)),
        "median": float(np.median(a)),
        "mean": float(np.mean(a)),
        "positive_rate": float(np.mean(a > 0)),
        "p25": float(np.quantile(a, 0.25)),
    }


def summarize_dates(frame: pd.DataFrame, dates: list[pd.Timestamp]) -> dict:
    result: dict = {"n_dates": len(dates), "SPY": {}, "QQQ": {}}
    for symbol in ("SPY", "QQQ"):
        for h in HORIZONS:
            rets, maes = [], []
            for d in dates:
                x = outcome(frame, d, symbol, h)
                if x is not None:
                    rets.append(x[0])
                    maes.append(x[1])
            result[symbol][str(h)] = {
                "return": summarize(rets),
                "mae": summarize(maes),
            }
    return result


def bootstrap_median_diff(a: list[float], b: list[float], reps: int = 5000) -> dict:
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    if len(aa) < 10 or len(bb) < 10:
        return {"median_diff": None, "ci_low": None, "ci_high": None}
    diffs = np.empty(reps)
    for i in range(reps):
        sa = RNG.choice(aa, len(aa), replace=True)
        sb = RNG.choice(bb, len(bb), replace=True)
        diffs[i] = np.median(sa) - np.median(sb)
    return {
        "median_diff": float(np.median(aa) - np.median(bb)),
        "ci_low": float(np.quantile(diffs, 0.025)),
        "ci_high": float(np.quantile(diffs, 0.975)),
    }


def paired_delay_test(frame: pd.DataFrame, signals: pd.DataFrame, starts: list[pd.Timestamp], rsp: pd.DataFrame) -> dict:
    pairs: list[tuple[pd.Timestamp, pd.Timestamp, int]] = []
    missed = 0
    for start in starts:
        loc = signals.index.get_loc(start)
        if not isinstance(loc, (int, np.integer)):
            continue
        confirmed = None
        for k in range(0, CONFIRM_WINDOW + 1):
            j = int(loc) + k
            if j >= len(signals):
                break
            d = pd.Timestamp(signals.index[j])
            if k > 0 and str(signals.iloc[j]["signal"]) != "RE-ENTER":
                break
            if d in rsp.index and float(rsp.at[d, "rsp_spy_rs5"]) > 0:
                confirmed = (d, k)
                break
        if confirmed is None:
            missed += 1
        else:
            pairs.append((start, confirmed[0], confirmed[1]))

    result: dict = {
        "baseline_episodes": len(starts),
        "confirmed_episodes": len(pairs),
        "coverage": float(len(pairs) / len(starts)) if starts else None,
        "missed_episodes": missed,
        "median_delay_sessions": float(np.median([p[2] for p in pairs])) if pairs else None,
        "mean_delay_sessions": float(np.mean([p[2] for p in pairs])) if pairs else None,
        "SPY": {},
        "QQQ": {},
    }
    for symbol in ("SPY", "QQQ"):
        for h in HORIZONS:
            base_rets, delayed_rets, diffs = [], [], []
            for base_d, confirm_d, _ in pairs:
                a = outcome(frame, base_d, symbol, h)
                b = outcome(frame, confirm_d, symbol, h)
                if a is None or b is None:
                    continue
                base_rets.append(a[0])
                delayed_rets.append(b[0])
                diffs.append(b[0] - a[0])
            result[symbol][str(h)] = {
                "n": len(diffs),
                "baseline_median": float(np.median(base_rets)) if base_rets else None,
                "delayed_median": float(np.median(delayed_rets)) if delayed_rets else None,
                "paired_median_advantage_of_waiting_for_rsp": float(np.median(diffs)) if diffs else None,
                "fraction_delayed_better": float(np.mean(np.asarray(diffs) > 0)) if diffs else None,
            }
    return result


def main() -> None:
    base = feature_frame(require_same_day=False)
    signals = build_canonical_signal_history(base)
    unified = _build_unified_frame(base, require_same_day=False)

    rsp_close = fetch_rsp()
    rsp = pd.DataFrame(index=base.index)
    rsp["RSP"] = rsp_close.reindex(base.index)
    rsp["ratio"] = rsp["RSP"] / base["SPY"]
    rsp["rsp_spy_rs1"] = rsp["ratio"].pct_change(1)
    rsp["rsp_spy_rs5"] = rsp["ratio"].pct_change(5)
    rsp["rsp_spy_rs20"] = rsp["ratio"].pct_change(20)
    rsp["state"] = np.where(
        (rsp["rsp_spy_rs5"] > 0) & (rsp["rsp_spy_rs20"] > 0),
        "BROADENING",
        np.where(rsp["rsp_spy_rs5"] > 0, "REPAIRING", "LAGGING"),
    )

    starts = independent_starts(signals["signal"])
    starts = [d for d in starts if d in rsp.index and pd.notna(rsp.at[d, "rsp_spy_rs5"])]
    by_state = {}
    for state in ("BROADENING", "REPAIRING", "LAGGING"):
        ds = [d for d in starts if rsp.at[d, "state"] == state]
        by_state[state] = summarize_dates(base, ds)

    gate_dates = [d for d in starts if float(rsp.at[d, "rsp_spy_rs5"]) > 0]
    rejected_dates = [d for d in starts if float(rsp.at[d, "rsp_spy_rs5"]) <= 0]

    common = signals.index.intersection(unified.index).intersection(rsp.index)
    research = signals.loc[common].join(
        unified.apply(lambda r: pd.Series({
            "internal_reset": _internal_reset(r),
            "selling_pressure": _selling_pressure(r),
        }), axis=1),
        how="left",
    ).join(rsp[["rsp_spy_rs1", "rsp_spy_rs5", "rsp_spy_rs20", "state"]], how="left")

    internal_setup = research["internal_reset"].isin(["DEVELOPING", "MEANINGFUL", "BROAD"])
    favorable = research["analog"].isin(FAVORABLE_ANALOGS)
    not_reenter = ~research["signal"].eq("RE-ENTER")
    rsp_repair = (research["rsp_spy_rs5"] > 0) & (research["rsp_spy_rs1"] > 0)
    aggregate_not_repaired = ~research["selling_pressure"].isin(["STABILIZING", "REPAIRING"])
    candidate_mask = not_reenter & internal_setup & favorable & rsp_repair & aggregate_not_repaired
    control_mask = not_reenter & internal_setup & favorable & (~rsp_repair) & aggregate_not_repaired
    candidate_dates = cooldown_dates(candidate_mask)
    control_dates = cooldown_dates(control_mask)

    candidate_summary = summarize_dates(base, candidate_dates)
    control_summary = summarize_dates(base, control_dates)
    candidate_vs_control: dict = {"SPY": {}, "QQQ": {}}
    for symbol in ("SPY", "QQQ"):
        for h in HORIZONS:
            a, b = [], []
            for d in candidate_dates:
                x = outcome(base, d, symbol, h)
                if x is not None:
                    a.append(x[0])
            for d in control_dates:
                x = outcome(base, d, symbol, h)
                if x is not None:
                    b.append(x[0])
            candidate_vs_control[symbol][str(h)] = bootstrap_median_diff(a, b)

    era = {}
    for label, start, end in (("2017-2020", "2017-01-01", "2020-12-31"), ("2021-2026", "2021-01-01", "2026-12-31")):
        ds = [d for d in starts if pd.Timestamp(start) <= d <= pd.Timestamp(end)]
        era[label] = {
            "all": summarize_dates(base, ds),
            "rsp5_positive": summarize_dates(base, [d for d in ds if float(rsp.at[d, "rsp_spy_rs5"]) > 0]),
            "rsp5_nonpositive": summarize_dates(base, [d for d in ds if float(rsp.at[d, "rsp_spy_rs5"]) <= 0]),
        }

    # Conservative promotion rule: RSP earns a decision role only if it adds robust
    # short-horizon information without materially delaying canonical entries.
    info_cells = 0
    for symbol in ("SPY", "QQQ"):
        for h in (5, 10, 15):
            good = by_state["BROADENING"][symbol][str(h)]["return"]["median"]
            lag = by_state["LAGGING"][symbol][str(h)]["return"]["median"]
            if good is not None and lag is not None and good > lag:
                info_cells += 1
    delay = paired_delay_test(base, signals, starts, rsp)
    promotion_cells = 0
    for symbol in ("SPY", "QQQ"):
        for h in (5, 10, 15):
            comp = candidate_vs_control[symbol][str(h)]
            if comp["median_diff"] is not None and comp["median_diff"] > 0 and comp["ci_low"] is not None and comp["ci_low"] >= 0:
                promotion_cells += 1

    if promotion_cells >= 4:
        verdict = "CANDIDATE_FOR_DECISION_LOGIC"
    elif info_cells >= 4:
        verdict = "USE_AS_CONTEXT_NOT_GATE"
    else:
        verdict = "DO_NOT_ADD"

    payload = {
        "status": "RSP_VS_SPY_INCREMENTAL_VALIDATION_RESEARCH_ONLY",
        "verdict": verdict,
        "methodology": {
            "data": "RSP daily close vs canonical SPY daily close; point-in-time ratio only",
            "features": {
                "rsp_spy_rs1": "1-session return of RSP/SPY ratio",
                "rsp_spy_rs5": "5-session return of RSP/SPY ratio",
                "rsp_spy_rs20": "20-session return of RSP/SPY ratio",
            },
            "states": {
                "BROADENING": "5D and 20D RSP/SPY relative returns both positive",
                "REPAIRING": "5D positive while 20D non-positive",
                "LAGGING": "5D non-positive",
            },
            "execution": "signal close t; hypothetical entry close t+1; 10 bps round-trip friction",
            "horizons": list(HORIZONS),
            "independent_episode_cooldown": COOLDOWN,
            "confirmation_window_sessions": CONFIRM_WINDOW,
            "anti_lateness_rule": "RSP confirmation is rejected as a gate if it materially delays or misses canonical entries even when selected returns look better",
        },
        "baseline_independent_reentry_episodes": len(starts),
        "baseline": summarize_dates(base, starts),
        "diagnostic_by_rsp_state": by_state,
        "same_day_rsp5_positive_gate": {
            "coverage": float(len(gate_dates) / len(starts)) if starts else None,
            "accepted": summarize_dates(base, gate_dates),
            "rejected": summarize_dates(base, rejected_dates),
        },
        "wait_for_rsp5_confirmation": delay,
        "early_repair_candidate": {
            "definition": "canonical non-RE-ENTER + internal reset + favorable analog + aggregate repair not yet sufficient + RSP/SPY 1D and 5D positive",
            "candidate": candidate_summary,
            "control": control_summary,
            "candidate_vs_control_bootstrap": candidate_vs_control,
        },
        "era_stability": era,
        "gate": {
            "diagnostic_short_horizon_cells_where_broadening_beats_lagging": info_cells,
            "robust_promotion_cells": promotion_cells,
        },
    }

    out = Path("artifacts/rsp_relative_strength")
    out.mkdir(parents=True, exist_ok=True)
    (out / "rsp_relative_strength_validation.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
