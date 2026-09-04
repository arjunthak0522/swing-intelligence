from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from internal_correction_v2 import HORIZONS, PRIMARY_COOLDOWN, cooldown_dates, forward_stats, load_prices
from reentry_v2_engine import build_engine_frame

ROUND_TRIP_COST = 0.001
RNG = np.random.default_rng(20260904)


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
    return {
        "ret": float(path.iloc[-1] / entry - 1.0 - ROUND_TRIP_COST),
        "mae": float(path_ret.min()),
        "mfe": float(path_ret.max()),
    }


def summarize_dates(prices: pd.DataFrame, dates: list[pd.Timestamp]) -> dict:
    return {
        symbol: {str(h): forward_stats(prices, dates, symbol, h) for h in HORIZONS}
        for symbol in ["SPY", "QQQ"]
    }


def decision_dates(df: pd.DataFrame, decision: str, cooldown: int = PRIMARY_COOLDOWN) -> list[pd.Timestamp]:
    return cooldown_dates(df["decision"].eq(decision), cooldown)


def setup_dates(df: pd.DataFrame, setup_type: str, decision: str | None = None, cooldown: int = PRIMARY_COOLDOWN) -> list[pd.Timestamp]:
    mask = df["setup_type"].eq(setup_type)
    if decision is not None:
        mask &= df["decision"].eq(decision)
    return cooldown_dates(mask, cooldown)


def era_split(dates: list[pd.Timestamp]) -> dict[str, list[pd.Timestamp]]:
    return {
        "2016_2020": [d for d in dates if d < pd.Timestamp("2021-01-01")],
        "2021_present": [d for d in dates if d >= pd.Timestamp("2021-01-01")],
    }


def bootstrap_median_diff(a: np.ndarray, b: np.ndarray, reps: int = 4000) -> dict:
    if len(a) < 5 or len(b) < 5:
        return {"median_diff": None, "ci95": [None, None]}
    diffs = np.empty(reps)
    for i in range(reps):
        aa = a[RNG.integers(0, len(a), len(a))]
        bb = b[RNG.integers(0, len(b), len(b))]
        diffs[i] = np.median(aa) - np.median(bb)
    return {
        "median_diff": float(np.median(a) - np.median(b)),
        "ci95": [float(np.quantile(diffs, 0.025)), float(np.quantile(diffs, 0.975))],
    }


def compare_groups(prices: pd.DataFrame, a_dates: list[pd.Timestamp], b_dates: list[pd.Timestamp]) -> dict:
    out = {"SPY": {}, "QQQ": {}}
    for symbol in ["SPY", "QQQ"]:
        for h in HORIZONS:
            aa, bb, aa_mae, bb_mae = [], [], [], []
            for d in a_dates:
                o = outcome(prices, d, symbol, h)
                if o:
                    aa.append(o["ret"])
                    aa_mae.append(o["mae"])
            for d in b_dates:
                o = outcome(prices, d, symbol, h)
                if o:
                    bb.append(o["ret"])
                    bb_mae.append(o["mae"])
            a = np.asarray(aa, dtype=float)
            b = np.asarray(bb, dtype=float)
            amae = np.asarray(aa_mae, dtype=float)
            bmae = np.asarray(bb_mae, dtype=float)
            out[symbol][str(h)] = {
                "a_n": int(len(a)),
                "b_n": int(len(b)),
                "return": bootstrap_median_diff(a, b),
                "mae_median_diff": float(np.median(amae) - np.median(bmae)) if len(amae) and len(bmae) else None,
            }
    return out


def summarize_policy(df: pd.DataFrame, prices: pd.DataFrame) -> dict:
    reenter = decision_dates(df, "RE-ENTER")
    wait = decision_dates(df, "WAIT")
    no_setup = decision_dates(df, "NO RE-ENTRY SETUP")
    rolling = setup_dates(df, "ROLLING_INTERNAL_CORRECTION", "RE-ENTER")
    broad = setup_dates(df, "BROAD_CORRECTION", "RE-ENTER")
    broad_wait = setup_dates(df, "BROAD_CORRECTION", "WAIT")
    developing_wait = setup_dates(df, "DEVELOPING_INTERNAL_RESET", "WAIT")

    result = {
        "status": "REENTRY_V2_POLICY_VALIDATION_RESEARCH_ONLY",
        "sample_start": str(df.index.min().date()),
        "sample_end": str(df.index.max().date()),
        "cooldown_sessions": PRIMARY_COOLDOWN,
        "decision_counts": {
            "RE-ENTER": len(reenter),
            "WAIT": len(wait),
            "NO_RE_ENTRY_SETUP": len(no_setup),
        },
        "setup_counts": {
            "ROLLING_INTERNAL_CORRECTION_REENTER": len(rolling),
            "BROAD_CORRECTION_REENTER": len(broad),
            "BROAD_CORRECTION_WAIT": len(broad_wait),
            "DEVELOPING_INTERNAL_RESET_WAIT": len(developing_wait),
        },
        "decision_outcomes": {
            "RE-ENTER": summarize_dates(prices, reenter),
            "WAIT": summarize_dates(prices, wait),
            "NO_RE_ENTRY_SETUP": summarize_dates(prices, no_setup),
        },
        "setup_outcomes": {
            "ROLLING_INTERNAL_CORRECTION_REENTER": summarize_dates(prices, rolling),
            "BROAD_CORRECTION_REENTER": summarize_dates(prices, broad),
            "BROAD_CORRECTION_WAIT": summarize_dates(prices, broad_wait),
            "DEVELOPING_INTERNAL_RESET_WAIT": summarize_dates(prices, developing_wait),
        },
        "comparisons": {
            "REENTER_vs_WAIT": compare_groups(prices, reenter, wait),
            "REENTER_vs_NO_SETUP": compare_groups(prices, reenter, no_setup),
            "ROLLING_REENTER_vs_DEVELOPING_WAIT": compare_groups(prices, rolling, developing_wait),
            "BROAD_REENTER_vs_BROAD_WAIT": compare_groups(prices, broad, broad_wait),
        },
        "eras": {},
    }
    for label, dates in {"RE-ENTER": reenter, "WAIT": wait}.items():
        eras = era_split(dates)
        result["eras"][label] = {
            era: {"count": len(edates), "outcomes": summarize_dates(prices, edates)}
            for era, edates in eras.items()
        }
    return result


def main() -> None:
    df = build_engine_frame()
    prices = load_prices()
    result = summarize_policy(df, prices)
    out = Path("artifacts/internal_correction_v2")
    out.mkdir(parents=True, exist_ok=True)
    (out / "reentry_v2_policy_validation.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
