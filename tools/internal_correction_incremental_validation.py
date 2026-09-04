from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from internal_correction_v2 import (
    HORIZONS,
    PRIMARY_COOLDOWN,
    build_cross_section,
    cooldown_dates,
    load_prices,
    primary_internal_signal,
    v1_weakness,
)
from reentry_confidence import feature_frame

MATCH_FEATURES = ["spy_dd20", "B50", "B200", "b50_change3", "vix_change5", "curve_ratio"]
RNG = np.random.default_rng(20260904)


def outcome(prices: pd.DataFrame, date: pd.Timestamp, symbol: str, horizon: int) -> tuple[float, float] | None:
    s = prices[symbol].dropna()
    if date not in s.index:
        return None
    pos = s.index.get_loc(date)
    if not isinstance(pos, (int, np.integer)) or pos + 1 + horizon >= len(s):
        return None
    entry = float(s.iloc[pos + 1])
    path = s.iloc[pos + 1:pos + 1 + horizon + 1].astype(float)
    ret = float(path.iloc[-1] / entry - 1.0 - 0.001)
    mae = float((path / entry - 1.0).min())
    return ret, mae


def nearest_prior_control(df: pd.DataFrame, date: pd.Timestamp, require_v1_state: bool) -> pd.Timestamp | None:
    loc = df.index.get_loc(date)
    if not isinstance(loc, (int, np.integer)) or loc < 252:
        return None
    cutoff_loc = loc - 20
    hist = df.iloc[:cutoff_loc].copy()
    hist = hist[(hist["spy_dd20"] > -0.03) & (~hist["internal_primary"])]
    if require_v1_state:
        hist = hist[hist["v1_weakness"] == bool(df.loc[date, "v1_weakness"])]
    if hist.empty:
        return None
    x = hist[MATCH_FEATURES].replace([np.inf, -np.inf], np.nan).dropna()
    if x.empty:
        return None
    target = df.loc[date, MATCH_FEATURES].astype(float)
    mu = x.mean()
    sd = x.std().replace(0, np.nan)
    z = (x - mu) / sd
    zt = (target - mu) / sd
    dist = ((z - zt) ** 2).mean(axis=1) ** 0.5
    dist = dist.replace([np.inf, -np.inf], np.nan).dropna()
    return None if dist.empty else pd.Timestamp(dist.idxmin())


def bootstrap_median(values: np.ndarray, reps: int = 4000) -> tuple[float, float]:
    if len(values) < 5:
        return (np.nan, np.nan)
    idx = RNG.integers(0, len(values), size=(reps, len(values)))
    meds = np.median(values[idx], axis=1)
    return float(np.quantile(meds, 0.025)), float(np.quantile(meds, 0.975))


def validate_group(df: pd.DataFrame, prices: pd.DataFrame, dates: list[pd.Timestamp], require_v1_state: bool) -> dict:
    pairs: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for d in dates:
        c = nearest_prior_control(df, d, require_v1_state=require_v1_state)
        if c is not None:
            pairs.append((d, c))

    out: dict = {"pairs": len(pairs), "metrics": {}}
    for symbol in ["SPY", "QQQ"]:
        out["metrics"][symbol] = {}
        for h in HORIZONS:
            diffs_ret, diffs_mae, sig_rets, ctrl_rets = [], [], [], []
            for sig, ctrl in pairs:
                a = outcome(prices, sig, symbol, h)
                b = outcome(prices, ctrl, symbol, h)
                if a is None or b is None:
                    continue
                sig_ret, sig_mae = a
                ctrl_ret, ctrl_mae = b
                sig_rets.append(sig_ret)
                ctrl_rets.append(ctrl_ret)
                diffs_ret.append(sig_ret - ctrl_ret)
                # positive means signal has less adverse excursion than control
                diffs_mae.append(sig_mae - ctrl_mae)
            arr = np.asarray(diffs_ret, dtype=float)
            arr_mae = np.asarray(diffs_mae, dtype=float)
            ci = bootstrap_median(arr)
            ci_mae = bootstrap_median(arr_mae)
            out["metrics"][symbol][str(h)] = {
                "n": int(len(arr)),
                "signal_median_return": float(np.median(sig_rets)) if sig_rets else None,
                "control_median_return": float(np.median(ctrl_rets)) if ctrl_rets else None,
                "median_return_advantage": float(np.median(arr)) if len(arr) else None,
                "return_advantage_ci95": list(ci),
                "fraction_signal_better": float((arr > 0).mean()) if len(arr) else None,
                "median_mae_advantage": float(np.median(arr_mae)) if len(arr_mae) else None,
                "mae_advantage_ci95": list(ci_mae),
            }
    return out


def main() -> None:
    base = feature_frame(require_same_day=False)
    prices = load_prices()
    xs = build_cross_section(prices)
    df = base.join(xs, how="inner").dropna(subset=["spy_dd20", "sector_dispersion_pct"]).copy()
    df["v1_weakness"] = v1_weakness(df)
    df["internal_primary"] = primary_internal_signal(df)

    primary_dates = cooldown_dates(df["internal_primary"].fillna(False), PRIMARY_COOLDOWN)
    missed_dates = cooldown_dates((df["internal_primary"] & ~df["v1_weakness"]).fillna(False), PRIMARY_COOLDOWN)

    result = {
        "status": "INCREMENTAL_VALIDATION_RESEARCH_ONLY",
        "primary_vs_matched_shallow_same_v1_state": validate_group(df, prices, primary_dates, True),
        "v1_missed_internal_vs_matched_v1_missed_shallow": validate_group(df, prices, missed_dates, True),
        "interpretation_rule": "Promotion requires positive short-horizon return advantage with robust confidence intervals or clear tail-risk improvement; positive raw returns alone are insufficient.",
    }
    out = Path("artifacts/internal_correction_v2")
    out.mkdir(parents=True, exist_ok=True)
    (out / "incremental_validation.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
