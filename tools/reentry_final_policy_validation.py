from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from internal_correction_full_v2 import MATCH_FEATURES, bootstrap_median, build_full_v2_state
from internal_correction_v2 import build_cross_section, cooldown_dates, load_prices, PRIMARY_COOLDOWN
from reentry_confidence import analogs_for_date, feature_frame, summarize_analogs
from reentry_decision import decision_from_analogs
from reentry_early_entry_policy import early_entry_decision
from reentry_engine import _internal_reset, _selling_pressure, _unified_signal, weakness_context

HORIZONS = (5, 7, 10, 15, 30, 60)
ROUND_TRIP_COST = 0.001
DELAYS = (1, 2, 3, 5)


def outcome(series: pd.Series, date: pd.Timestamp, horizon: int, delay: int = 0):
    if date not in series.index:
        return None
    loc = series.index.get_loc(date)
    if not isinstance(loc, (int, np.integer)):
        return None
    entry_loc = loc + 1 + delay
    end_loc = entry_loc + horizon
    if end_loc >= len(series):
        return None
    entry = float(series.iloc[entry_loc])
    path = series.iloc[entry_loc:end_loc + 1].astype(float)
    if entry <= 0 or path.empty:
        return None
    path_ret = path / entry - 1.0
    ret = float(path_ret.iloc[-1] - ROUND_TRIP_COST)
    return ret, float(path_ret.min()), float(path_ret.max())


def stats_for_dates(series: pd.Series, dates: list[pd.Timestamp], horizon: int, delay: int = 0) -> dict:
    vals, maes, mfes = [], [], []
    for d in dates:
        x = outcome(series, d, horizon, delay=delay)
        if x is None:
            continue
        vals.append(x[0]); maes.append(x[1]); mfes.append(x[2])
    arr = np.asarray(vals, dtype=float)
    mae = np.asarray(maes, dtype=float)
    mfe = np.asarray(mfes, dtype=float)
    return {
        "n": int(len(arr)),
        "median_return": float(np.median(arr)) if len(arr) else None,
        "mean_return": float(np.mean(arr)) if len(arr) else None,
        "positive_rate": float(np.mean(arr > 0)) if len(arr) else None,
        "p25_return": float(np.quantile(arr, 0.25)) if len(arr) else None,
        "p75_return": float(np.quantile(arr, 0.75)) if len(arr) else None,
        "median_mae": float(np.median(mae)) if len(mae) else None,
        "p10_mae": float(np.quantile(mae, 0.10)) if len(mae) else None,
        "median_mfe": float(np.median(mfe)) if len(mfe) else None,
        "false_start_rate_return_lt_minus_2pct": float(np.mean(arr < -0.02)) if len(arr) else None,
    }


def nearest_prior_control(df: pd.DataFrame, date: pd.Timestamp, state_col: str) -> pd.Timestamp | None:
    loc = df.index.get_loc(date)
    if not isinstance(loc, (int, np.integer)) or loc < 252:
        return None
    hist = df.iloc[: max(0, loc - 20)].copy()
    shallow_now = bool(df.loc[date, "spy_dd20"] > -0.03)
    hist = hist[hist["broad_weakness"] == bool(df.loc[date, "broad_weakness"])]
    hist = hist[hist["spy_dd20"] > -0.03] if shallow_now else hist[hist["spy_dd20"] <= -0.03]
    hist = hist[~hist[state_col].fillna(False)]
    x = hist[MATCH_FEATURES].replace([np.inf, -np.inf], np.nan).dropna()
    if x.empty:
        return None
    target = df.loc[date, MATCH_FEATURES].astype(float)
    mu, sd = x.mean(), x.std().replace(0, np.nan)
    dist = ((((x - mu) / sd) - ((target - mu) / sd)) ** 2).mean(axis=1) ** 0.5
    dist = dist.replace([np.inf, -np.inf], np.nan).dropna()
    return None if dist.empty else pd.Timestamp(dist.idxmin())


def matched_validation(df: pd.DataFrame, prices: pd.DataFrame, dates: list[pd.Timestamp], state_col: str) -> dict:
    pairs = []
    for d in dates:
        c = nearest_prior_control(df, d, state_col)
        if c is not None:
            pairs.append((d, c))
    out = {"pairs": len(pairs), "SPY": {}, "QQQ": {}}
    for symbol in ("SPY", "QQQ"):
        series = prices[symbol].dropna()
        for h in HORIZONS:
            diffs, mae_diffs = [], []
            for sig, ctrl in pairs:
                a, b = outcome(series, sig, h), outcome(series, ctrl, h)
                if a is None or b is None:
                    continue
                diffs.append(a[0] - b[0]); mae_diffs.append(a[1] - b[1])
            arr = np.asarray(diffs, dtype=float)
            mae = np.asarray(mae_diffs, dtype=float)
            out[symbol][str(h)] = {
                "n": int(len(arr)),
                "median_return_advantage": float(np.median(arr)) if len(arr) else None,
                "return_advantage_ci95": bootstrap_median(arr),
                "fraction_signal_better": float(np.mean(arr > 0)) if len(arr) else None,
                "median_mae_advantage": float(np.median(mae)) if len(mae) else None,
            }
    return out


def summarize_group(prices: pd.DataFrame, dates: list[pd.Timestamp]) -> dict:
    out = {"count": len(dates), "SPY": {}, "QQQ": {}}
    for symbol in ("SPY", "QQQ"):
        s = prices[symbol].dropna()
        for h in HORIZONS:
            out[symbol][str(h)] = stats_for_dates(s, dates, h)
    return out


def main() -> None:
    base = feature_frame(require_same_day=False)
    prices = load_prices()
    xs = build_cross_section(prices)
    df = base.join(xs, how="inner").dropna(subset=["spy_dd20", "sector_dispersion_pct"]).copy()
    df = build_full_v2_state(df)

    final_signal = []
    base_signal = []
    source = []
    analog_labels = []
    broad_weakness = []

    for target in df.index:
        try:
            analogs = analogs_for_date(base, target)
            summary = summarize_analogs(base, analogs)
            analog_decision, _, _ = decision_from_analogs(summary, base.loc[target])
        except Exception:
            final_signal.append("NO RE-ENTRY SETUP")
            base_signal.append("NO RE-ENTRY SETUP")
            source.append("UNAVAILABLE")
            analog_labels.append("NO")
            broad_weakness.append(False)
            continue

        row = df.loc[target]
        weak, _ = weakness_context(row)
        bsignal, _, _ = _unified_signal(analog_decision, weak, row)
        fsignal, _, fsource = early_entry_decision(
            analog_decision=analog_decision,
            weakness_present=weak,
            internal_reset=_internal_reset(row),
            selling_pressure=_selling_pressure(row),
            existing_signal=bsignal,
        )
        final_signal.append(fsignal); base_signal.append(bsignal); source.append(fsource)
        analog_labels.append(analog_decision); broad_weakness.append(weak)

    df["final_signal"] = final_signal
    df["base_signal"] = base_signal
    df["signal_source"] = source
    df["analog_decision"] = analog_labels
    df["broad_weakness"] = broad_weakness
    df["final_reenter"] = df["final_signal"].eq("RE-ENTER")
    df["base_reenter"] = df["base_signal"].eq("RE-ENTER")
    df["early_only_reenter"] = df["final_reenter"] & ~df["base_reenter"]
    df["broad_driven_reenter"] = df["final_reenter"] & df["broad_weakness"]
    df["internal_only_reenter"] = df["final_reenter"] & ~df["broad_weakness"]

    final_dates = cooldown_dates(df["final_reenter"], PRIMARY_COOLDOWN)
    base_dates = cooldown_dates(df["base_reenter"], PRIMARY_COOLDOWN)
    early_dates = cooldown_dates(df["early_only_reenter"], PRIMARY_COOLDOWN)
    broad_dates = cooldown_dates(df["broad_driven_reenter"], PRIMARY_COOLDOWN)
    internal_dates = cooldown_dates(df["internal_only_reenter"], PRIMARY_COOLDOWN)

    # How much earlier are incremental early entries than the next stricter/base entry?
    lead_sessions = []
    idx = list(df.index)
    pos = {d: i for i, d in enumerate(idx)}
    base_set = set(df.index[df["base_reenter"]])
    for d in early_dates:
        i = pos[d]
        next_hits = [j - i for j in range(i + 1, min(i + 11, len(idx))) if idx[j] in base_set]
        if next_hits:
            lead_sessions.append(min(next_hits))

    wait_compare = {"SPY": {}, "QQQ": {}}
    for symbol in ("SPY", "QQQ"):
        s = prices[symbol].dropna()
        for h in HORIZONS:
            immediate = stats_for_dates(s, early_dates, h, 0)
            wait_compare[symbol][str(h)] = {"immediate": immediate}
            for delay in DELAYS:
                delayed = stats_for_dates(s, early_dates, h, delay)
                wait_compare[symbol][str(h)][f"wait_{delay}d"] = delayed
                if immediate["median_return"] is not None and delayed["median_return"] is not None:
                    wait_compare[symbol][str(h)][f"median_advantage_vs_wait_{delay}d"] = immediate["median_return"] - delayed["median_return"]

    eras = {
        "2016_2020": [d for d in final_dates if d < pd.Timestamp("2021-01-01")],
        "2021_present": [d for d in final_dates if d >= pd.Timestamp("2021-01-01")],
    }

    result = {
        "status": "FINAL_UNIFIED_POLICY_RESEARCH_ONLY",
        "sample_start": str(df.index.min().date()),
        "sample_end": str(df.index.max().date()),
        "policy": {
            "persistence_sessions": 0,
            "early_bias": "developing/meaningful/broad internal reset may RE-ENTER once selling pressure is stabilizing or repairing and analog decision is at least CAUTIOUS YES",
            "broad_mapping": "validated broad-market weakness mapping preserved",
            "execution": "next trading-session close with 10 bps round-trip friction",
            "analogs": "prior-only nearest historical states; no future data used in the daily decision",
        },
        "groups": {
            "final_all_reenter": summarize_group(prices, final_dates),
            "base_stricter_reenter": summarize_group(prices, base_dates),
            "incremental_early_only": summarize_group(prices, early_dates),
            "broad_driven": summarize_group(prices, broad_dates),
            "internal_only": summarize_group(prices, internal_dates),
        },
        "incremental_early_timing": {
            "event_count": len(early_dates),
            "events_with_stricter_signal_within_10_sessions": len(lead_sessions),
            "median_sessions_earlier": float(np.median(lead_sessions)) if lead_sessions else None,
            "p25_sessions_earlier": float(np.quantile(lead_sessions, 0.25)) if lead_sessions else None,
            "p75_sessions_earlier": float(np.quantile(lead_sessions, 0.75)) if lead_sessions else None,
            "immediate_vs_wait": wait_compare,
        },
        "matched_controls_incremental_early": matched_validation(df, prices, early_dates, "early_only_reenter"),
        "era_split_final_policy": {name: summarize_group(prices, dates) for name, dates in eras.items()},
        "latest_policy_rows": [
            {
                "date": str(d.date()),
                "final_signal": str(df.loc[d, "final_signal"]),
                "base_signal": str(df.loc[d, "base_signal"]),
                "signal_source": str(df.loc[d, "signal_source"]),
                "analog_decision": str(df.loc[d, "analog_decision"]),
                "broad_weakness": bool(df.loc[d, "broad_weakness"]),
                "internal_reset": _internal_reset(df.loc[d]),
                "selling_pressure": _selling_pressure(df.loc[d]),
            }
            for d in df.index[-10:]
        ],
    }

    out = Path("artifacts/reentry/final_policy_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
