from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from .tournament import SignalSpec, evaluate_signal


@dataclass(frozen=True)
class StabilityGate:
    """Research gate for a neighborhood of nearby parameter choices.

    A candidate is considered stable only when its nearby variants preserve the
    direction of edge rather than relying on one lucky threshold.
    """
    horizon: int = 10
    min_n: int = 30
    min_positive_fraction: float = 0.67
    max_edge_cv: float = 1.5


def evaluate_parameter_neighborhood(
    df: pd.DataFrame,
    variants: Mapping[str, pd.Series],
    *,
    rationale: str = "",
    gate: StabilityGate = StabilityGate(),
) -> pd.DataFrame:
    """Evaluate nearby parameter variants against the same unconditional baseline."""
    rows: list[dict] = []
    for name, mask in variants.items():
        result = evaluate_signal(
            df,
            SignalSpec(name=name, mask=mask, rationale=rationale),
            horizons=(gate.horizon,),
            min_n=gate.min_n,
        )
        h = result.get("horizons", {}).get(gate.horizon)
        if not h:
            rows.append({"variant": name, "n": 0, "edge": np.nan, "win_edge": np.nan, "sample_ok": False})
            continue
        rows.append({
            "variant": name,
            "n": int(h["n"]),
            "edge": float(h["median_excess_edge"]),
            "win_edge": float(h["win_probability_edge"]),
            "median_mae": float(h["median_mae"]),
            "median_mfe": float(h["median_mfe"]),
            "sample_ok": bool(h["n"] >= gate.min_n),
        })
    return pd.DataFrame(rows)


def summarize_parameter_stability(table: pd.DataFrame, gate: StabilityGate = StabilityGate()) -> dict:
    """Summarize whether a parameter neighborhood is broad enough to trust.

    This is deliberately not a score. The output exposes the raw stability
    statistics and a boolean gate.
    """
    if table.empty:
        return {
            "variants": 0,
            "eligible_variants": 0,
            "positive_fraction": 0.0,
            "edge_median": np.nan,
            "edge_min": np.nan,
            "edge_max": np.nan,
            "edge_cv": np.nan,
            "stable": False,
        }
    eligible = table.loc[table["sample_ok"] & table["edge"].notna()].copy()
    if eligible.empty:
        return {
            "variants": int(len(table)),
            "eligible_variants": 0,
            "positive_fraction": 0.0,
            "edge_median": np.nan,
            "edge_min": np.nan,
            "edge_max": np.nan,
            "edge_cv": np.nan,
            "stable": False,
        }
    edges = eligible["edge"].astype(float)
    positive_fraction = float((edges > 0).mean())
    mean_abs = float(abs(edges.mean()))
    edge_cv = float(edges.std(ddof=0) / mean_abs) if mean_abs > 1e-12 else np.inf
    stable = (
        positive_fraction >= gate.min_positive_fraction
        and float(edges.median()) > 0
        and np.isfinite(edge_cv)
        and edge_cv <= gate.max_edge_cv
    )
    return {
        "variants": int(len(table)),
        "eligible_variants": int(len(eligible)),
        "positive_fraction": positive_fraction,
        "edge_median": float(edges.median()),
        "edge_min": float(edges.min()),
        "edge_max": float(edges.max()),
        "edge_cv": edge_cv,
        "stable": bool(stable),
    }


def standard_parameter_neighborhoods(features: pd.DataFrame) -> dict[str, dict[str, pd.Series]]:
    """Predeclared nearby-threshold families for robustness testing.

    Thresholds are intentionally specified before outcome inspection.
    """
    above_rising_200 = (features["gap_sma_200"] > 0) & (features["sma_200"].pct_change(20) > 0)
    return {
        "rsi14_oversold": {
            "rsi14_lt_30": features["rsi_14"] < 30,
            "rsi14_lt_35": features["rsi_14"] < 35,
            "rsi14_lt_40": features["rsi_14"] < 40,
        },
        "bull_pullback_rsi": {
            "bull_rsi_lt_35": above_rising_200 & (features["rsi_14"] < 35),
            "bull_rsi_lt_40": above_rising_200 & (features["rsi_14"] < 40),
            "bull_rsi_lt_45": above_rising_200 & (features["rsi_14"] < 45),
        },
        "bull_pullback_z": {
            "bull_z_lt_m075": above_rising_200 & (features["zscore_20"] < -0.75),
            "bull_z_lt_m100": above_rising_200 & (features["zscore_20"] < -1.00),
            "bull_z_lt_m125": above_rising_200 & (features["zscore_20"] < -1.25),
        },
        "momentum_20d": {
            "mom20_gt_3pct": (features["return_20d"] > 0.03) & (features["gap_sma_200"] > 0),
            "mom20_gt_5pct": (features["return_20d"] > 0.05) & (features["gap_sma_200"] > 0),
            "mom20_gt_7pct": (features["return_20d"] > 0.07) & (features["gap_sma_200"] > 0),
        },
    }
