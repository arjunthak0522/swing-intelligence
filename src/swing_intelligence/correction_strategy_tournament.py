from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .correction_reentry import CorrectionReentryConfig, _episode_onsets, _entry_return, _mae, _score_series, correction_state


@dataclass(frozen=True)
class CorrectionTournamentConfig:
    first_test_year: int = 2010
    fold_years: int = 2
    max_signal_wait_days: int = 20
    horizons: tuple[int, ...] = (10, 20, 30, 60)
    transaction_cost_bps: float = 10.0
    min_signals_total: int = 12
    min_folds_with_signals: int = 4
    min_positive_fold_fraction: float = 0.60
    min_win_rate: float = 0.60
    min_median_return_30d: float = 0.02
    min_median_edge_vs_onset_30d: float = 0.005


def _series(frame: pd.DataFrame, name: str) -> pd.Series:
    if name not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[name], errors="coerce")


def candidate_masks(features: pd.DataFrame, score: pd.Series) -> dict[str, pd.Series]:
    """Small predeclared family of causal re-entry hypotheses.

    These are intentionally simple and economically distinct. No threshold search is
    performed here; the tournament compares fixed rules inside already-detected
    correction episodes.
    """
    rebound3 = _series(features, "rebound_3d")
    accel = _series(features, "momentum_accel_5v20")
    trend = _series(features, "trend_repair_5d")
    vix_cool = _series(features, "vix_cooling_5d")
    rsp5 = _series(features, "rsp_spy_ret_5d")
    iwm5 = _series(features, "iwm_spy_ret_5d")
    qqq5 = _series(features, "qqq_spy_ret_5d")
    smh5 = _series(features, "smh_qqq_ret_5d")
    hycool = _series(features, "hy_spread_cooling_5d")
    y2 = _series(features, "yield_2y_change_5d")

    price_repair = (rebound3 > 0) & (accel > 0)
    trend_repair = (rebound3 > 0) & (trend > 0)
    vol_repair = (rebound3 > 0) & (vix_cool > 0)
    breadth_repair = (rebound3 > 0) & ((rsp5 > 0) | (iwm5 > 0))
    growth_repair = (rebound3 > 0) & ((qqq5 > 0) | (smh5 > 0))
    macro_repair = (rebound3 > 0) & ((hycool > 0) | (y2 < 0))
    broad_confirmed = price_repair & ((vix_cool > 0) | (rsp5 > 0) | (iwm5 > 0))
    growth_confirmed = price_repair & ((qqq5 > 0) | (smh5 > 0))

    return {
        "frozen_score_70": (score >= 70).fillna(False),
        "price_repair": price_repair.fillna(False),
        "trend_repair": trend_repair.fillna(False),
        "vol_repair": vol_repair.fillna(False),
        "breadth_repair": breadth_repair.fillna(False),
        "growth_repair": growth_repair.fillna(False),
        "macro_repair": macro_repair.fillna(False),
        "broad_confirmed_repair": broad_confirmed.fillna(False),
        "growth_confirmed_repair": growth_confirmed.fillna(False),
    }


def _fold_label(date: pd.Timestamp, first_year: int, fold_years: int) -> str:
    start = first_year + ((date.year - first_year) // fold_years) * fold_years
    return f"{start}-{start + fold_years - 1}"


def run_correction_strategy_tournament(
    features: pd.DataFrame,
    config: CorrectionTournamentConfig = CorrectionTournamentConfig(),
    correction_config: CorrectionReentryConfig | None = None,
) -> dict:
    features = features.sort_index().copy()
    if correction_config is None:
        correction_config = CorrectionReentryConfig(
            first_test_year=config.first_test_year,
            fold_years=config.fold_years,
            max_signal_wait_days=config.max_signal_wait_days,
            horizons=config.horizons,
            transaction_cost_bps=config.transaction_cost_bps,
        )
    state = correction_state(features, correction_config)
    score = _score_series(features, correction_config)
    masks = candidate_masks(features, score)
    idx = pd.DatetimeIndex(features.index)
    onsets = _episode_onsets(state, correction_config)

    results = []
    for name, mask in masks.items():
        rows = []
        for onset_pos in onsets:
            onset_date = idx[onset_pos]
            if onset_date.year < config.first_test_year:
                continue
            if onset_pos + max(config.horizons) + config.max_signal_wait_days + 2 >= len(features):
                continue
            search_end = min(onset_pos + config.max_signal_wait_days, len(features) - 2)
            hits = mask.iloc[onset_pos:search_end + 1]
            hit_positions = np.where(hits.to_numpy(dtype=bool))[0]
            if not len(hit_positions):
                continue
            signal_pos = onset_pos + int(hit_positions[0])
            entry_pos = signal_pos + 1
            onset_entry = onset_pos + 1
            row = {
                "onset_date": str(onset_date.date()),
                "signal_date": str(idx[signal_pos].date()),
                "entry_date": str(idx[entry_pos].date()),
                "correction_type": str(state["type"].iloc[onset_pos]),
                "delay_days": int(entry_pos - onset_pos),
                "fold": _fold_label(onset_date, config.first_test_year, config.fold_years),
            }
            for h in config.horizons:
                r = _entry_return(features, entry_pos, h, config.transaction_cost_bps)
                b = _entry_return(features, onset_entry, h, config.transaction_cost_bps)
                row[f"return_{h}d"] = r
                row[f"edge_vs_onset_{h}d"] = float(r - b) if np.isfinite(r) and np.isfinite(b) else np.nan
                row[f"mae_{h}d"] = _mae(features, entry_pos, h)
            rows.append(row)

        df = pd.DataFrame(rows)
        summary = {"name": name, "signals": int(len(df)), "qualifies": False, "rows": rows}
        if not df.empty:
            summary["median_delay_days"] = float(df["delay_days"].median())
            summary["type_counts"] = {str(k): int(v) for k, v in df["correction_type"].value_counts().to_dict().items()}
            folds = []
            for fold, g in df.groupby("fold"):
                med30 = float(g["return_30d"].median()) if "return_30d" in g else np.nan
                edge30 = float(g["edge_vs_onset_30d"].median()) if "edge_vs_onset_30d" in g else np.nan
                folds.append({"fold": str(fold), "n": int(len(g)), "median_return_30d": med30, "median_edge_vs_onset_30d": edge30})
            summary["folds"] = folds
            positive_folds = [f for f in folds if f["n"] > 0 and f["median_return_30d"] > 0 and f["median_edge_vs_onset_30d"] > 0]
            summary["positive_fold_fraction"] = float(len(positive_folds) / len(folds)) if folds else 0.0
            hs = {}
            for h in config.horizons:
                r = df[f"return_{h}d"].astype(float)
                e = df[f"edge_vs_onset_{h}d"].astype(float)
                hs[str(h)] = {
                    "median_return": float(r.median()),
                    "win_rate": float((r > 0).mean()),
                    "median_edge_vs_onset": float(e.median()),
                    "edge_win_rate": float((e > 0).mean()),
                    "median_mae": float(df[f"mae_{h}d"].median()),
                }
            summary["horizons"] = hs
            h30 = hs["30"]
            summary["qualifies"] = bool(
                len(df) >= config.min_signals_total
                and len(folds) >= config.min_folds_with_signals
                and summary["positive_fold_fraction"] >= config.min_positive_fold_fraction
                and h30["win_rate"] >= config.min_win_rate
                and h30["median_return"] >= config.min_median_return_30d
                and h30["median_edge_vs_onset"] >= config.min_median_edge_vs_onset_30d
            )
        results.append(summary)

    results.sort(
        key=lambda x: (
            bool(x.get("qualifies")),
            (x.get("horizons") or {}).get("30", {}).get("median_edge_vs_onset", -999),
            (x.get("horizons") or {}).get("30", {}).get("median_return", -999),
        ),
        reverse=True,
    )
    return {
        "config": asdict(config),
        "correction_config": asdict(correction_config),
        "episode_count": int(sum(1 for p in onsets if idx[p].year >= config.first_test_year)),
        "qualifying_strategy_count": int(sum(1 for x in results if x.get("qualifies"))),
        "results": results,
    }
