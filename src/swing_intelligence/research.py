from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from .features import compute_features
from .market_state import compute_cross_asset_features
from .regimes import classify_regime
from .tournament import default_candidate_signals, evaluate_signal, rank_signals


@dataclass(frozen=True)
class ResearchSplit:
    train_end: str = "2016-12-31"
    validation_end: str = "2021-12-31"
    holdout_end: str | None = None


def add_research_features(frames: dict[str, pd.DataFrame], target: str) -> pd.DataFrame:
    target = target.upper()
    if target not in frames:
        raise KeyError(f"Missing target {target}")
    base = compute_features(frames[target])
    cross = compute_cross_asset_features(frames)
    out = base.join(cross, how="left")
    out["regime"] = classify_regime(out)
    return out


def split_periods(df: pd.DataFrame, split: ResearchSplit = ResearchSplit()) -> dict[str, pd.DataFrame]:
    idx = pd.DatetimeIndex(df.index)
    train_end = pd.Timestamp(split.train_end)
    val_end = pd.Timestamp(split.validation_end)
    end = pd.Timestamp(split.holdout_end) if split.holdout_end else idx.max()
    return {
        "train": df.loc[idx <= train_end],
        "validation": df.loc[(idx > train_end) & (idx <= val_end)],
        "holdout": df.loc[(idx > val_end) & (idx <= end)],
    }


def run_signal_tournament(df: pd.DataFrame, horizons=(3, 5, 10, 20), min_n=30) -> list[dict]:
    signals = default_candidate_signals(df)
    return [evaluate_signal(df, s, horizons=horizons, min_n=min_n) for s in signals]


def evaluate_frozen_signals(full_features: pd.DataFrame, split: ResearchSplit = ResearchSplit(), horizon=10, min_n=30) -> dict:
    """Evaluate the same predefined hypotheses separately in train/validation/holdout.

    This does not optimize thresholds. It is a guardrail-oriented first research pass.
    """
    periods = split_periods(full_features, split)
    out = {}
    for name, frame in periods.items():
        results = run_signal_tournament(frame, min_n=min_n)
        out[name] = {
            "results": results,
            "ranking": rank_signals(results, horizon=horizon, min_n=min_n),
        }
    return out


def survivor_table(evaluation: dict, horizon=10, min_n=30, min_edge=0.0, min_win_edge=0.0) -> pd.DataFrame:
    """Require positive validation AND holdout edge. Train results never qualify a survivor alone."""
    rows = []
    by_period = {}
    for period in ("train", "validation", "holdout"):
        period_results = evaluation[period]["results"]
        by_period[period] = {r["name"]: r for r in period_results}
    names = sorted(set(by_period["train"]) & set(by_period["validation"]) & set(by_period["holdout"]))
    for name in names:
        row = {"signal": name}
        qualifies = True
        for period in ("train", "validation", "holdout"):
            h = by_period[period][name].get("horizons", {}).get(horizon)
            if not h:
                qualifies = False
                continue
            row[f"{period}_n"] = h["n"]
            row[f"{period}_edge"] = h["median_excess_edge"]
            row[f"{period}_win_edge"] = h["win_probability_edge"]
            if period in ("validation", "holdout"):
                qualifies &= h["n"] >= min_n and h["median_excess_edge"] > min_edge and h["win_probability_edge"] > min_win_edge
        row["survives"] = bool(qualifies)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["survives", "holdout_edge"], ascending=[False, False]).reset_index(drop=True)
