from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from internal_correction_v2 import HORIZONS, PRIMARY_COOLDOWN, cooldown_dates, forward_stats, load_prices
from reentry_v2_engine import build_engine_frame

ROUND_TRIP_COST = 0.001
RNG = np.random.default_rng(20260904)
MATCH_FEATURES = ["spy_dd20", "B50", "B200", "b50_change3", "vix_change5", "curve_ratio"]


def candidate_masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    shallow = ~df["broad_market_weakness"]
    meaningful = df["v2_meaningful"] & df["v2_stabilizing"]
    return {
        "CURRENT_HIDDEN_MEANINGFUL": shallow & meaningful,
        "HIDDEN_BROAD": shallow & df["v2_broad"] & df["v2_stabilizing"],
        "HIDDEN_MEANINGFUL_DISPERSION": shallow & meaningful & df["v2_dispersion_bucket"],
        "HIDDEN_MEANINGFUL_SECTOR": shallow & meaningful & df["v2_sector_damage_bucket"],
        "HIDDEN_MEANINGFUL_FACTOR": shallow & meaningful & df["v2_factor_damage_bucket"],
        "HIDDEN_SECTOR_FACTOR": shallow & meaningful & df["v2_sector_damage_bucket"] & df["v2_factor_damage_bucket"],
        "HIDDEN_SECTOR_DISPERSION": shallow & meaningful & df["v2_sector_damage_bucket"] & df["v2_dispersion_bucket"],
        "HIDDEN_FACTOR_DISPERSION": shallow & meaningful & df["v2_factor_damage_bucket"] & df["v2_dispersion_bucket"],
        "HIDDEN_ROTATION_DISPERSION": shallow & meaningful & df["v2_rotation_bucket"] & df["v2_dispersion_bucket"],
        "HIDDEN_SECTOR_ROTATION": shallow & meaningful & df["v2_sector_damage_bucket"] & df["v2_rotation_bucket"],
    }


def outcome(prices: pd.DataFrame, date: pd.Timestamp, symbol: str, horizon: int):
    s = prices[symbol].dropna()
    if date not in s.index:
        return None
    pos = s.index.get_loc(date)
    if not isinstance(pos, (int, np.integer)) or pos + 1 + horizon >= len(s):
        return None
    entry = float(s.iloc[pos + 1])
    path = s.iloc[pos + 1:pos + 1 + horizon + 1].astype(float)
    path_ret = path / entry - 1.0
    return float(path.iloc[-1] / entry - 1.0 - ROUND_TRIP_COST), float(path_ret.min())


def bootstrap_median(values: np.ndarray, reps: int = 4000):
    if len(values) < 5:
        return [None, None]
    ix = RNG.integers(0, len(values), size=(reps, len(values)))
    meds = np.median(values[ix], axis=1)
    return [float(np.quantile(meds, 0.025)), float(np.quantile(meds, 0.975))]


def nearest_prior_control(df: pd.DataFrame, date: pd.Timestamp, candidate: pd.Series) -> pd.Timestamp | None:
    loc = df.index.get_loc(date)
    if not isinstance(loc, (int, np.integer)) or loc < 252:
        return None
    hist = df.iloc[: max(0, loc - 20)].copy()
    hist_candidate = candidate.reindex(hist.index).fillna(False)
    hist = hist[(~hist["broad_market_weakness"]) & (hist["spy_dd20"] > -0.03) & (~hist_candidate)]
    x = hist[MATCH_FEATURES].replace([np.inf, -np.inf], np.nan).dropna()
    if x.empty:
        return None
    target = df.loc[date, MATCH_FEATURES].astype(float)
    mu, sd = x.mean(), x.std().replace(0, np.nan)
    dist = ((((x - mu) / sd) - ((target - mu) / sd)) ** 2).mean(axis=1) ** 0.5
    dist = dist.replace([np.inf, -np.inf], np.nan).dropna()
    return None if dist.empty else pd.Timestamp(dist.idxmin())


def matched(df: pd.DataFrame, prices: pd.DataFrame, dates: list[pd.Timestamp], candidate: pd.Series) -> dict:
    pairs = []
    for d in dates:
        c = nearest_prior_control(df, d, candidate)
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
                "ci95": bootstrap_median(arr),
                "fraction_better": float((arr > 0).mean()) if len(arr) else None,
                "median_mae_advantage": float(np.median(mae)) if len(mae) else None,
            }
    return out


def summarize(df: pd.DataFrame, prices: pd.DataFrame, mask: pd.Series) -> dict:
    dates = cooldown_dates(mask.fillna(False), PRIMARY_COOLDOWN)
    era1 = [d for d in dates if d < pd.Timestamp("2021-01-01")]
    era2 = [d for d in dates if d >= pd.Timestamp("2021-01-01")]
    return {
        "events": len(dates),
        "era_counts": {"2016_2020": len(era1), "2021_present": len(era2)},
        "raw": {
            symbol: {str(h): forward_stats(prices, dates, symbol, h) for h in HORIZONS}
            for symbol in ["SPY", "QQQ"]
        },
        "era_2016_2020": {
            symbol: {str(h): forward_stats(prices, era1, symbol, h) for h in HORIZONS}
            for symbol in ["SPY", "QQQ"]
        },
        "era_2021_present": {
            symbol: {str(h): forward_stats(prices, era2, symbol, h) for h in HORIZONS}
            for symbol in ["SPY", "QQQ"]
        },
        "matched": matched(df, prices, dates, mask),
    }


def main() -> None:
    df = build_engine_frame()
    prices = load_prices()
    masks = candidate_masks(df)
    result = {
        "status": "REENTRY_V2_HIDDEN_POLICY_REFINEMENT_RESEARCH_ONLY",
        "principle": "All candidates are refinements of the complete V2 sector-factor state. No candidate is a separate engine.",
        "candidates": {name: summarize(df, prices, mask) for name, mask in masks.items()},
    }
    out = Path("artifacts/internal_correction_v2")
    out.mkdir(parents=True, exist_ok=True)
    (out / "reentry_v2_hidden_policy_refinement.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
