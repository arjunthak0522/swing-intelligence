from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

import numpy as np
import pandas as pd

from .autonomous_lab import HypothesisRule, RuleTerm, _forward_path_table
from .outcomes import summarize_forward_paths


@dataclass(frozen=True)
class Phase2BConfig:
    horizons: tuple[int, ...] = (10, 20, 30, 60)
    primary_horizon: int = 30
    min_events_per_slice: int = 8
    min_positive_horizons: int = 3
    min_positive_eras: int = 2
    era_years: int = 2
    min_regime_events: int = 8
    transaction_cost_bps_round_trip: float = 2.0


def rule_from_result(result: dict) -> HypothesisRule:
    terms = tuple(
        RuleTerm(str(t["feature"]), str(t["op"]), float(t["threshold"]))
        for t in result.get("terms", [])
    )
    if not terms:
        raise ValueError("Result has no reconstructable rule terms")
    return HypothesisRule(str(result["name"]), terms, str(result.get("rationale", "")))


def _net_stats(paths: pd.DataFrame, cost_bps: float) -> dict:
    if paths.empty:
        return {"n": 0}
    adjusted = paths.copy()
    adjusted["forward_return"] = adjusted["forward_return"] - cost_bps / 10000.0
    return summarize_forward_paths(adjusted)


def _slice_result(conditional: pd.DataFrame, baseline: pd.DataFrame, cost_bps: float) -> dict:
    cond = _net_stats(conditional, cost_bps)
    base = _net_stats(baseline, cost_bps)
    if not cond.get("n") or not base.get("n"):
        return {"n": int(cond.get("n", 0))}
    return {
        "n": int(cond["n"]),
        "median_return_net": float(cond["median_return"]),
        "win_probability_net": float(cond["win_probability"]),
        "median_excess_edge_net": float(cond["median_return"] - base["median_return"]),
        "win_probability_edge_net": float(cond["win_probability"] - base["win_probability"]),
    }


def _era_label(ts: pd.Timestamp, years: int) -> str:
    start = (ts.year // years) * years
    return f"{start}-{start + years - 1}"


def evaluate_phase2b(
    frame: pd.DataFrame,
    result: dict,
    config: Phase2BConfig = Phase2BConfig(),
) -> dict:
    """Post-selection stability diagnostics for a frozen hypothesis.

    No thresholds are optimized here. All horizon, regime and era checks use the
    already-frozen rule and report returns net of a small fixed round-trip cost.
    """
    rule = rule_from_result(result)
    mask = rule.mask(frame).reindex(frame.index).fillna(False)
    dates = frame.index[mask]

    horizon_rows: dict[int, dict] = {}
    caches: dict[int, pd.DataFrame] = {}
    for horizon in config.horizons:
        paths = _forward_path_table(frame, horizon)
        caches[horizon] = paths
        conditional = paths.loc[paths.index.intersection(dates)]
        horizon_rows[horizon] = _slice_result(
            conditional, paths, config.transaction_cost_bps_round_trip
        )

    usable_horizons = [
        row for row in horizon_rows.values()
        if row.get("n", 0) >= config.min_events_per_slice
    ]
    positive_horizons = sum(
        1 for row in usable_horizons
        if row.get("median_excess_edge_net", -np.inf) > 0
        and row.get("win_probability_edge_net", -np.inf) >= 0
    )

    primary_paths = caches[config.primary_horizon]
    primary_dates = primary_paths.index.intersection(dates)

    regime_rows: dict[str, dict] = {}
    if "regime" in frame.columns:
        regime_series = frame["regime"].astype(str)
        for regime in sorted(regime_series.dropna().unique()):
            conditional_dates = frame.index[(regime_series == regime) & mask]
            baseline_dates = frame.index[regime_series == regime]
            conditional = primary_paths.loc[primary_paths.index.intersection(conditional_dates)]
            baseline = primary_paths.loc[primary_paths.index.intersection(baseline_dates)]
            row = _slice_result(conditional, baseline, config.transaction_cost_bps_round_trip)
            if row.get("n", 0):
                regime_rows[str(regime)] = row

    era_rows: dict[str, dict] = {}
    eras = pd.Series(
        [_era_label(pd.Timestamp(d), config.era_years) for d in primary_dates],
        index=primary_dates,
        dtype="object",
    )
    for era in sorted(eras.unique()):
        conditional_dates = eras.index[eras == era]
        baseline_dates = pd.DatetimeIndex([
            d for d in primary_paths.index
            if _era_label(pd.Timestamp(d), config.era_years) == era
        ])
        row = _slice_result(
            primary_paths.loc[primary_paths.index.intersection(conditional_dates)],
            primary_paths.loc[primary_paths.index.intersection(baseline_dates)],
            config.transaction_cost_bps_round_trip,
        )
        if row.get("n", 0):
            era_rows[str(era)] = row

    usable_eras = [r for r in era_rows.values() if r.get("n", 0) >= config.min_events_per_slice]
    positive_eras = sum(
        1 for r in usable_eras
        if r.get("median_excess_edge_net", -np.inf) > 0
        and r.get("win_probability_edge_net", -np.inf) >= 0
    )
    usable_regimes = [r for r in regime_rows.values() if r.get("n", 0) >= config.min_regime_events]
    positive_regimes = sum(
        1 for r in usable_regimes
        if r.get("median_excess_edge_net", -np.inf) > 0
        and r.get("win_probability_edge_net", -np.inf) >= 0
    )

    return {
        "name": rule.name,
        "horizons": horizon_rows,
        "positive_horizons": positive_horizons,
        "usable_horizons": len(usable_horizons),
        "regimes": regime_rows,
        "positive_regimes": positive_regimes,
        "usable_regimes": len(usable_regimes),
        "eras": era_rows,
        "positive_eras": positive_eras,
        "usable_eras": len(usable_eras),
        "multi_horizon_consistent": bool(positive_horizons >= config.min_positive_horizons),
        "era_consistent": bool(positive_eras >= config.min_positive_eras),
        "config": asdict(config),
    }


def evidence_grade(stability: dict, robustness_row: dict | None) -> dict:
    robust = bool((robustness_row or {}).get("robust", False))
    multi = bool(stability.get("multi_horizon_consistent", False))
    era = bool(stability.get("era_consistent", False))
    positive_regimes = int(stability.get("positive_regimes", 0))

    if robust and multi and era and positive_regimes >= 2:
        grade = "HIGH CONFIDENCE"
    elif robust and multi and era:
        grade = "STRONG"
    elif robust and (multi or era):
        grade = "PROMISING"
    elif multi and era:
        grade = "INTERESTING"
    else:
        grade = "REJECTED"

    return {
        "grade": grade,
        "robust": robust,
        "multi_horizon_consistent": multi,
        "era_consistent": era,
        "positive_regimes": positive_regimes,
    }


def phase2b_report(
    frame: pd.DataFrame,
    survivors: Iterable[dict],
    robustness_rows: Iterable[dict],
    config: Phase2BConfig = Phase2BConfig(),
) -> dict:
    robust_map = {str(r["name"]): r for r in robustness_rows}
    rows = []
    for result in survivors:
        row = evaluate_phase2b(frame, result, config=config)
        row["evidence"] = evidence_grade(row, robust_map.get(row["name"]))
        rows.append(row)

    order = {"HIGH CONFIDENCE": 4, "STRONG": 3, "PROMISING": 2, "INTERESTING": 1, "REJECTED": 0}
    rows.sort(key=lambda r: order[r["evidence"]["grade"]], reverse=True)
    return {
        "config": asdict(config),
        "tested": len(rows),
        "grade_counts": {grade: sum(r["evidence"]["grade"] == grade for r in rows) for grade in order},
        "rows": rows,
    }
