from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from internal_correction_v2 import (
    FACTORS,
    HORIZONS,
    PRIMARY_COOLDOWN,
    SECTORS,
    build_cross_section,
    cooldown_dates,
    forward_stats,
    load_prices,
    v1_weakness,
)
from reentry_confidence import feature_frame

ROUND_TRIP_COST = 0.001
RNG = np.random.default_rng(20260904)
MATCH_FEATURES = [
    "spy_dd20", "B50", "B200", "b50_change3", "vix_change5", "curve_ratio",
]


def build_full_v2_state(df: pd.DataFrame) -> pd.DataFrame:
    """Explicit full V2 state. All sector/factor proxies contribute to aggregates.

    This is deliberately not a fitted score. It creates interpretable buckets for
    damage, stabilization, and leadership/rotation using the complete cross-section.
    """
    out = df.copy()

    # Cross-sectional sector damage across all 11 sectors.
    sector_dd_cols = [f"{s}_dd20" for s in SECTORS]
    factor_dd_cols = [f"{s}_dd20" for s in FACTORS]
    sector_rs_cols = [f"{s}_rs20" for s in SECTORS]
    factor_rs_cols = [f"{s}_rs20" for s in FACTORS]

    sector_dd = out[sector_dd_cols]
    factor_dd = out[factor_dd_cols]
    sector_rs = out[sector_rs_cols]
    factor_rs = out[factor_rs_cols]

    out["v2_sector_damage_share_2"] = (sector_dd <= -0.02).mean(axis=1)
    out["v2_sector_damage_share_3"] = (sector_dd <= -0.03).mean(axis=1)
    out["v2_factor_damage_share_2"] = (factor_dd <= -0.02).mean(axis=1)
    out["v2_factor_damage_share_3"] = (factor_dd <= -0.03).mean(axis=1)
    out["v2_sector_median_dd"] = sector_dd.median(axis=1)
    out["v2_factor_median_dd"] = factor_dd.median(axis=1)
    out["v2_sector_rs_dispersion"] = sector_rs.std(axis=1)
    out["v2_factor_rs_dispersion"] = factor_rs.std(axis=1)

    # Every proxy is represented in the repair breadth, not only selected leaders.
    sector_repairs = []
    factor_repairs = []
    for s in SECTORS:
        sector_repairs.append(((out[f"{s}_dd20"] <= -0.02) & (out[f"{s}_rs20"] > out[f"{s}_rs60"])).astype(int))
    for s in FACTORS:
        factor_repairs.append(((out[f"{s}_dd20"] <= -0.02) & (out[f"{s}_rs20"] > out[f"{s}_rs60"])).astype(int))
    out["v2_sector_repair_share"] = pd.concat(sector_repairs, axis=1).mean(axis=1)
    out["v2_factor_repair_share"] = pd.concat(factor_repairs, axis=1).mean(axis=1)

    # Explicit rotation/leadership descriptors. These do not individually trigger V2.
    out["v2_momentum_reset"] = out["momentum_relative_20"] <= -0.02
    out["v2_quality_over_momentum"] = out["quality_minus_momentum_20"] >= 0.015
    out["v2_growth_reset"] = out["growth_minus_value_20"] <= -0.015
    out["v2_small_vs_large_reset"] = out["IWM_rs20"] <= -0.02
    out["v2_rotation_count"] = (
        out[["v2_momentum_reset", "v2_quality_over_momentum", "v2_growth_reset", "v2_small_vs_large_reset"]]
        .astype(int).sum(axis=1)
    )

    # Damage buckets. A bucket is meaningful only when broad enough to represent
    # the whole cross-section rather than one isolated ETF.
    out["v2_sector_damage_bucket"] = (
        (out["v2_sector_damage_share_3"] >= 4 / len(SECTORS))
        | ((out["v2_sector_damage_share_2"] >= 6 / len(SECTORS)) & (out["sector_dispersion_pct"] >= 0.70))
    )
    out["v2_factor_damage_bucket"] = (
        (out["v2_factor_damage_share_3"] >= 3 / len(FACTORS))
        | ((out["v2_factor_damage_share_2"] >= 4 / len(FACTORS)) & (out["factor_dispersion20"] >= out["factor_dispersion20"].rolling(252, min_periods=60).quantile(0.70)))
    )
    out["v2_dispersion_bucket"] = (
        (out["sector_dispersion_pct"] >= 0.80)
        | (out["v2_sector_rs_dispersion"] >= out["v2_sector_rs_dispersion"].rolling(252, min_periods=60).quantile(0.80))
        | (out["v2_factor_rs_dispersion"] >= out["v2_factor_rs_dispersion"].rolling(252, min_periods=60).quantile(0.80))
    )
    out["v2_rotation_bucket"] = out["v2_rotation_count"] >= 2

    out["v2_damage_bucket_count"] = (
        out[["v2_sector_damage_bucket", "v2_factor_damage_bucket", "v2_dispersion_bucket", "v2_rotation_bucket"]]
        .astype(int).sum(axis=1)
    )

    # Stabilization also uses both the sector and factor cross-section.
    out["v2_stabilizing"] = (
        (out["sector_repair"] >= 2)
        | (out["factor_repair"] >= 2)
        | ((out["sector_median_ret1"] > 0) & (out["factor_median_ret1"] > 0))
        | ((out["v2_sector_repair_share"] >= 0.25) & (out["v2_factor_repair_share"] >= 0.25))
    )

    # Full V2 research states. No requirement for a large SPY correction.
    out["v2_developing"] = out["v2_damage_bucket_count"] >= 1
    out["v2_meaningful"] = (out["v2_damage_bucket_count"] >= 2) & out["v2_stabilizing"]
    out["v2_broad"] = (out["v2_damage_bucket_count"] >= 3) & out["v2_stabilizing"]
    out["v2_hidden_reset"] = (out["spy_dd20"] > -0.03) & out["v2_meaningful"]
    return out


def outcome(prices: pd.DataFrame, date: pd.Timestamp, symbol: str, horizon: int):
    s = prices[symbol].dropna()
    if date not in s.index:
        return None
    pos = s.index.get_loc(date)
    if not isinstance(pos, (int, np.integer)) or pos + 1 + horizon >= len(s):
        return None
    entry = float(s.iloc[pos + 1])
    path = s.iloc[pos + 1:pos + 1 + horizon + 1].astype(float)
    ret = float(path.iloc[-1] / entry - 1.0 - ROUND_TRIP_COST)
    path_ret = path / entry - 1.0
    return ret, float(path_ret.min()), float(path_ret.max())


def bootstrap_median(values: np.ndarray, reps: int = 4000):
    if len(values) < 5:
        return [None, None]
    ix = RNG.integers(0, len(values), size=(reps, len(values)))
    meds = np.median(values[ix], axis=1)
    return [float(np.quantile(meds, 0.025)), float(np.quantile(meds, 0.975))]


def nearest_prior_control(df: pd.DataFrame, date: pd.Timestamp, state_col: str) -> pd.Timestamp | None:
    loc = df.index.get_loc(date)
    if not isinstance(loc, (int, np.integer)) or loc < 252:
        return None
    hist = df.iloc[: max(0, loc - 20)].copy()
    # Same shallow/broad headline regime and same V1 weakness status, but no full V2 state.
    shallow_now = bool(df.loc[date, "spy_dd20"] > -0.03)
    hist = hist[(hist["v1_weakness"] == bool(df.loc[date, "v1_weakness"]))]
    if shallow_now:
        hist = hist[hist["spy_dd20"] > -0.03]
    else:
        hist = hist[hist["spy_dd20"] <= -0.03]
    hist = hist[~hist[state_col].fillna(False)]
    x = hist[MATCH_FEATURES].replace([np.inf, -np.inf], np.nan).dropna()
    if x.empty:
        return None
    target = df.loc[date, MATCH_FEATURES].astype(float)
    mu, sd = x.mean(), x.std().replace(0, np.nan)
    dist = ((((x - mu) / sd) - ((target - mu) / sd)) ** 2).mean(axis=1) ** 0.5
    dist = dist.replace([np.inf, -np.inf], np.nan).dropna()
    return None if dist.empty else pd.Timestamp(dist.idxmin())


def matched_stats(df: pd.DataFrame, prices: pd.DataFrame, dates: list[pd.Timestamp], state_col: str) -> dict:
    pairs = []
    for d in dates:
        c = nearest_prior_control(df, d, state_col)
        if c is not None:
            pairs.append((d, c))
    out = {"pairs": len(pairs), "SPY": {}, "QQQ": {}}
    for symbol in ["SPY", "QQQ"]:
        for h in HORIZONS:
            diffs, mae_diffs = [], []
            for sig, ctrl in pairs:
                a, b = outcome(prices, sig, symbol, h), outcome(prices, ctrl, symbol, h)
                if a is None or b is None:
                    continue
                diffs.append(a[0] - b[0])
                mae_diffs.append(a[1] - b[1])
            arr = np.asarray(diffs, dtype=float)
            mae = np.asarray(mae_diffs, dtype=float)
            out[symbol][str(h)] = {
                "n": int(len(arr)),
                "median_return_advantage": float(np.median(arr)) if len(arr) else None,
                "return_advantage_ci95": bootstrap_median(arr),
                "fraction_signal_better": float((arr > 0).mean()) if len(arr) else None,
                "median_mae_advantage": float(np.median(mae)) if len(mae) else None,
            }
    return out


def summarize_state(df: pd.DataFrame, prices: pd.DataFrame, state_col: str, cooldown: int = PRIMARY_COOLDOWN) -> dict:
    dates = cooldown_dates(df[state_col].fillna(False), cooldown)
    missed = cooldown_dates((df[state_col] & ~df["v1_weakness"]).fillna(False), cooldown)
    era1 = [d for d in dates if d < pd.Timestamp("2021-01-01")]
    era2 = [d for d in dates if d >= pd.Timestamp("2021-01-01")]
    return {
        "event_count": len(dates),
        "v1_missed_count": len(missed),
        "raw": {
            "SPY": {str(h): forward_stats(prices, dates, "SPY", h) for h in HORIZONS},
            "QQQ": {str(h): forward_stats(prices, dates, "QQQ", h) for h in HORIZONS},
        },
        "v1_missed": {
            "SPY": {str(h): forward_stats(prices, missed, "SPY", h) for h in HORIZONS},
            "QQQ": {str(h): forward_stats(prices, missed, "QQQ", h) for h in HORIZONS},
        },
        "era_counts": {"2016_2020": len(era1), "2021_present": len(era2)},
        "era_2016_2020": {
            "SPY": {str(h): forward_stats(prices, era1, "SPY", h) for h in HORIZONS},
            "QQQ": {str(h): forward_stats(prices, era1, "QQQ", h) for h in HORIZONS},
        },
        "era_2021_present": {
            "SPY": {str(h): forward_stats(prices, era2, "SPY", h) for h in HORIZONS},
            "QQQ": {str(h): forward_stats(prices, era2, "QQQ", h) for h in HORIZONS},
        },
        "matched": matched_stats(df, prices, dates, state_col),
    }


def main() -> None:
    base = feature_frame(require_same_day=False)
    prices = load_prices()
    xs = build_cross_section(prices)
    df = base.join(xs, how="inner").dropna(subset=["spy_dd20", "sector_dispersion_pct"]).copy()
    df["v1_weakness"] = v1_weakness(df)
    df = build_full_v2_state(df)

    result = {
        "status": "FULL_V2_RESEARCH_ONLY_DO_NOT_PROMOTE",
        "sample_start": str(df.index.min().date()),
        "sample_end": str(df.index.max().date()),
        "design": "Complete sector-factor state model. All 11 sector ETFs and all 8 factor proxies contribute to aggregate damage/dispersion/repair. Subtypes are diagnostics, not competing engines.",
        "states": {
            "developing": summarize_state(df, prices, "v2_developing"),
            "meaningful": summarize_state(df, prices, "v2_meaningful"),
            "broad": summarize_state(df, prices, "v2_broad"),
            "hidden_reset": summarize_state(df, prices, "v2_hidden_reset"),
        },
        "latest": {
            "date": str(df.index[-1].date()),
            "spy_dd20": float(df.iloc[-1]["spy_dd20"]),
            "v1_weakness": bool(df.iloc[-1]["v1_weakness"]),
            "damage_bucket_count": int(df.iloc[-1]["v2_damage_bucket_count"]),
            "sector_damage_bucket": bool(df.iloc[-1]["v2_sector_damage_bucket"]),
            "factor_damage_bucket": bool(df.iloc[-1]["v2_factor_damage_bucket"]),
            "dispersion_bucket": bool(df.iloc[-1]["v2_dispersion_bucket"]),
            "rotation_bucket": bool(df.iloc[-1]["v2_rotation_bucket"]),
            "stabilizing": bool(df.iloc[-1]["v2_stabilizing"]),
            "developing": bool(df.iloc[-1]["v2_developing"]),
            "meaningful": bool(df.iloc[-1]["v2_meaningful"]),
            "broad": bool(df.iloc[-1]["v2_broad"]),
            "hidden_reset": bool(df.iloc[-1]["v2_hidden_reset"]),
            "sector_damage_share_2": float(df.iloc[-1]["v2_sector_damage_share_2"]),
            "factor_damage_share_2": float(df.iloc[-1]["v2_factor_damage_share_2"]),
            "rotation_count": int(df.iloc[-1]["v2_rotation_count"]),
        },
        "proxy_caveat": "Sector and factor histories use liquid ETF proxies and are not proprietary point-in-time factor-index constituent histories.",
    }

    out = Path("artifacts/internal_correction_v2")
    out.mkdir(parents=True, exist_ok=True)
    (out / "full_v2_results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
