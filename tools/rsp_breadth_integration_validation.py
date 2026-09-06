from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from reentry_confidence import feature_frame, forward_return, _normalize_daily_index
from reentry_decision import decision_from_analogs
from reentry_engine import _build_unified_frame, _internal_reset, _selling_pressure, _unified_signal, early_entry_decision, weakness_context

K = 40
EXCLUSION = 20
MIN_HISTORY = 252
ROUND_TRIP_COST = 0.001
HORIZONS = (5, 7, 10, 15, 30, 60)
BASE_FEATURES = ["spy_dd20", "spy_ret5", "B50", "B200", "b50_change1", "b50_change3", "vix_change5", "curve_ratio"]
RSP_FEATURES = ["rsp_spy_rs5", "rsp_spy_rs20"]


def fetch_rsp(start: str = "2016-09-01") -> pd.Series:
    raw = yf.download("RSP", start=start, interval="1d", auto_adjust=False, progress=False, threads=False)
    if raw.empty:
        raise RuntimeError("RSP history unavailable")
    raw = _normalize_daily_index(raw)
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return pd.to_numeric(close, errors="coerce").dropna().astype(float).rename("RSP")


def add_rsp(base: pd.DataFrame) -> pd.DataFrame:
    rsp = fetch_rsp().reindex(base.index)
    out = base.copy()
    out["RSP"] = rsp
    ratio = out["RSP"] / out["SPY"]
    out["rsp_spy_rs5"] = ratio.pct_change(5)
    out["rsp_spy_rs20"] = ratio.pct_change(20)
    return out.dropna(subset=RSP_FEATURES)


def historical_analogs(frame: pd.DataFrame, pos: int, features: list[str]) -> pd.DataFrame | None:
    cutoff = pos - EXCLUSION
    if cutoff < MIN_HISTORY:
        return None
    hist = frame.iloc[:cutoff]
    target = frame.iloc[pos]
    combo = pd.concat([hist[features], target[features].to_frame().T])
    scaled = pd.DataFrame(index=combo.index)
    for c in features:
        scaled[c] = combo[c].rank(method="average", pct=True)
    target_scaled = scaled.iloc[-1]
    hist_scaled = scaled.iloc[:-1]
    dist = ((hist_scaled - target_scaled) ** 2).mean(axis=1) ** 0.5
    nearest = dist.nsmallest(min(K, len(dist))).index
    result = hist.loc[nearest].copy()
    result["distance"] = dist.loc[nearest]
    return result.sort_values("distance")


def summarize_for_target(frame: pd.DataFrame, analogs: pd.DataFrame, current_pos: int) -> dict:
    output: dict[str, dict] = {}
    cutoff_date = frame.index[current_pos - EXCLUSION]
    for symbol in ("SPY", "QQQ"):
        output[symbol] = {}
        for h in (5, 7, 10):
            fwd = forward_return(frame[symbol], h).reindex(analogs.index).dropna()
            unconditional = forward_return(frame[symbol], h).loc[:cutoff_date].dropna()
            med = float(fwd.median())
            base = float(unconditional.median())
            output[symbol][str(h)] = {
                "n": int(len(fwd)), "median_return": med, "positive_rate": float((fwd > 0).mean()),
                "unconditional_median": base, "median_excess": med - base,
                "p25": float(fwd.quantile(0.25)), "p75": float(fwd.quantile(0.75)),
            }
    return output


def build_signals(frame: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    unified = _build_unified_frame(frame, require_same_day=False)
    common = frame.index.intersection(unified.index)
    rows = []
    for date in common:
        pos = frame.index.get_loc(date)
        if not isinstance(pos, (int, np.integer)) or pos < MIN_HISTORY + EXCLUSION or pos >= len(frame) - 61:
            continue
        analogs = historical_analogs(frame, int(pos), features)
        if analogs is None or len(analogs) < K:
            continue
        stats = summarize_for_target(frame, analogs, int(pos))
        row = unified.loc[date]
        analog_decision, _, _ = decision_from_analogs(stats, row)
        weak, _ = weakness_context(row)
        base_signal, _, _ = _unified_signal(analog_decision, weak, row)
        final_signal, _, source = early_entry_decision(
            analog_decision=analog_decision,
            weakness_present=weak,
            internal_reset=_internal_reset(row),
            selling_pressure=_selling_pressure(row),
            existing_signal=base_signal,
            allow_subsector_candidate=False,
        )
        rows.append({"date": date, "signal": final_signal, "source": source, "analog": analog_decision})
    return pd.DataFrame(rows).set_index("date")


def independent_starts(signals: pd.Series, cooldown: int = 10) -> list[pd.Timestamp]:
    starts = signals.eq("RE-ENTER") & ~signals.shift(1, fill_value="").eq("RE-ENTER")
    out, last = [], -10000
    for i, flag in enumerate(starts.to_numpy(bool)):
        if flag and i - last > cooldown:
            out.append(pd.Timestamp(signals.index[i]))
            last = i
    return out


def outcome(frame: pd.DataFrame, d: pd.Timestamp, symbol: str, h: int) -> float | None:
    if d not in frame.index:
        return None
    pos = frame.index.get_loc(d)
    if not isinstance(pos, (int, np.integer)) or pos + 1 + h >= len(frame):
        return None
    return float(frame[symbol].iloc[pos + 1 + h] / frame[symbol].iloc[pos + 1] - 1.0 - ROUND_TRIP_COST)


def summarize_dates(frame: pd.DataFrame, dates: list[pd.Timestamp]) -> dict:
    out = {"n": len(dates), "SPY": {}, "QQQ": {}}
    for sym in ("SPY", "QQQ"):
        for h in HORIZONS:
            vals = [x for d in dates if (x := outcome(frame, d, sym, h)) is not None]
            a = np.asarray(vals, dtype=float)
            out[sym][str(h)] = {
                "n": len(vals),
                "median": float(np.median(a)) if len(a) else None,
                "mean": float(np.mean(a)) if len(a) else None,
                "positive_rate": float(np.mean(a > 0)) if len(a) else None,
                "p25": float(np.quantile(a, .25)) if len(a) else None,
            }
    return out


def main() -> None:
    base = add_rsp(feature_frame(require_same_day=False))
    baseline = build_signals(base, BASE_FEATURES)
    augmented = build_signals(base, BASE_FEATURES + RSP_FEATURES)
    common = baseline.index.intersection(augmented.index)
    baseline, augmented = baseline.loc[common], augmented.loc[common]

    base_starts = independent_starts(baseline["signal"])
    aug_starts = independent_starts(augmented["signal"])
    base_stats = summarize_dates(base, base_starts)
    aug_stats = summarize_dates(base, aug_starts)

    matched = []
    for d in base_starts:
        if d not in augmented.index:
            continue
        p = augmented.index.get_loc(d)
        if not isinstance(p, (int, np.integer)):
            continue
        nearest = None
        for k in range(-5, 6):
            j = int(p) + k
            if 0 <= j < len(augmented) and augmented.iloc[j]["signal"] == "RE-ENTER":
                nearest = pd.Timestamp(augmented.index[j]); break
        if nearest is not None:
            matched.append((d, nearest, int(augmented.index.get_loc(nearest) - p)))

    payload = {
        "status": "RSP_BREADTH_INPUT_INTEGRATION_VALIDATION",
        "methodology": {
            "baseline_features": BASE_FEATURES,
            "augmented_features": BASE_FEATURES + RSP_FEATURES,
            "rsp_features": {
                "rsp_spy_rs5": "5-session return of RSP/SPY ratio",
                "rsp_spy_rs20": "20-session return of RSP/SPY ratio",
            },
            "role": "breadth/participation dimensions in historical analog distance only; no gate, veto, or standalone trigger",
            "walk_forward": True,
            "execution": "signal close t; hypothetical entry close t+1; 10 bps round-trip friction",
        },
        "baseline": base_stats,
        "augmented_rsp_breadth": aug_stats,
        "signal_counts": {
            "baseline_reentry_days": int((baseline["signal"] == "RE-ENTER").sum()),
            "augmented_reentry_days": int((augmented["signal"] == "RE-ENTER").sum()),
            "baseline_independent_starts": len(base_starts),
            "augmented_independent_starts": len(aug_starts),
        },
        "matched_baseline_episodes": {
            "n": len(matched),
            "median_shift_sessions": float(np.median([x[2] for x in matched])) if matched else None,
            "mean_shift_sessions": float(np.mean([x[2] for x in matched])) if matched else None,
            "fraction_same_day": float(np.mean([x[2] == 0 for x in matched])) if matched else None,
            "fraction_later": float(np.mean([x[2] > 0 for x in matched])) if matched else None,
            "fraction_earlier": float(np.mean([x[2] < 0 for x in matched])) if matched else None,
        },
    }
    out = Path("artifacts/rsp_breadth_integration")
    out.mkdir(parents=True, exist_ok=True)
    (out / "rsp_breadth_integration_validation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
