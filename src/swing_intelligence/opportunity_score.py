from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .autonomous_lab import _forward_path_table
from .walk_forward import _event_positions, _folds, _matched_random_percentile


@dataclass(frozen=True)
class OpportunityScoreConfig:
    first_test_year: int = 2010
    fold_years: int = 2
    horizon: int = 30
    min_gap: int = 30
    transaction_cost_bps_round_trip: float = 5.0
    trigger_levels: tuple[int, ...] = (65, 70, 75, 80, 85, 90)
    min_trades_total: int = 25
    min_folds_with_trades: int = 4
    min_positive_edge_fold_fraction: float = 0.60
    matched_random_iterations: int = 200
    min_matched_random_percentile: float = 0.80
    min_random_superiority_fold_fraction: float = 0.60


# Sign is +1 when high values are favorable for that component and -1 when low values are favorable.
# The structure is fixed a priori. Only percentile calibration is learned from the training fold.
COMMON_DAMAGE = (
    ("drawdown_252d", -1),
    ("drawdown_60d", -1),
    ("vix_percentile_252", +1),
    ("rsp_spy_ret_20d", -1),
    ("iwm_spy_ret_20d", -1),
    ("hy_spread_percentile_252", +1),
)
COMMON_REPAIR = (
    ("rebound_3d", +1),
    ("momentum_accel_5v20", +1),
    ("trend_repair_5d", +1),
    ("vix_cooling_5d", +1),
    ("rsp_spy_ret_5d", +1),
    ("iwm_spy_ret_5d", +1),
    ("hy_spread_cooling_5d", +1),
    ("yield_2y_change_5d", -1),
)
QQQ_DAMAGE = (("smh_qqq_ret_20d", -1),)
QQQ_REPAIR = (("smh_qqq_ret_5d", +1),)


def _empirical_percentile(train: pd.Series, values: pd.Series, favorable_sign: int) -> pd.Series:
    """Map values to [0,1] percentiles using training observations only."""
    ref = pd.to_numeric(train, errors="coerce").dropna().to_numpy(dtype=float)
    vals = pd.to_numeric(values, errors="coerce")
    if len(ref) < 100 or np.unique(ref).size < 20:
        return pd.Series(np.nan, index=values.index, dtype=float)
    ref = np.sort(ref)
    raw = pd.Series(np.searchsorted(ref, vals.to_numpy(dtype=float), side="right") / len(ref), index=values.index, dtype=float)
    raw[vals.isna()] = np.nan
    return raw if favorable_sign > 0 else 1.0 - raw


def _component_score(train: pd.DataFrame, frame: pd.DataFrame, specs: tuple[tuple[str, int], ...]) -> pd.DataFrame:
    cols = {}
    for feature, sign in specs:
        if feature in train.columns and feature in frame.columns:
            cols[feature] = _empirical_percentile(train[feature], frame[feature], sign)
    return pd.DataFrame(cols, index=frame.index)


def calibrated_opportunity_score(train: pd.DataFrame, frame: pd.DataFrame, target: str) -> pd.DataFrame:
    """Compute fixed-structure rolling/internal-correction opportunity score.

    Damage captures headline and under-the-surface reset. Repair captures evidence
    that the reset is ending. Percentiles are calibrated strictly on prior training
    data. The final score is the geometric mean, so large damage without repair (or
    repair without a meaningful reset) cannot create a high opportunity score.
    """
    target = target.upper()
    damage_specs = COMMON_DAMAGE + (QQQ_DAMAGE if target == "QQQ" else ())
    repair_specs = COMMON_REPAIR + (QQQ_REPAIR if target == "QQQ" else ())
    damage_components = _component_score(train, frame, damage_specs)
    repair_components = _component_score(train, frame, repair_specs)

    min_damage = max(2, min(4, damage_components.shape[1]))
    min_repair = max(2, min(4, repair_components.shape[1]))
    damage = damage_components.mean(axis=1, skipna=True).where(damage_components.notna().sum(axis=1) >= min_damage)
    repair = repair_components.mean(axis=1, skipna=True).where(repair_components.notna().sum(axis=1) >= min_repair)
    score = 100.0 * np.sqrt(damage.clip(0, 1) * repair.clip(0, 1))
    return pd.DataFrame({
        "damage_score": damage * 100.0,
        "repair_score": repair * 100.0,
        "opportunity_score": score,
    }, index=frame.index)


def _trade_table(test: pd.DataFrame, score: pd.Series, threshold: float, config: OpportunityScoreConfig) -> pd.DataFrame:
    paths = _forward_path_table(test, config.horizon)
    if paths.empty:
        return pd.DataFrame(columns=["return", "excess"])
    mask = (score >= threshold).reindex(paths.index).fillna(False)
    pos = _event_positions(mask, config.min_gap)
    if not pos:
        return pd.DataFrame(columns=["return", "excess"])
    baseline = paths["forward_return"].astype(float) - config.transaction_cost_bps_round_trip / 10000.0
    baseline_median = float(baseline.median())
    dates = paths.index[pos]
    ret = baseline.loc[dates]
    return pd.DataFrame({"return": ret, "excess": ret - baseline_median}, index=dates)


def run_opportunity_score_walk_forward(features: pd.DataFrame, target: str, config: OpportunityScoreConfig = OpportunityScoreConfig()) -> dict:
    features = features.sort_index()
    by_level: dict[int, dict] = {level: {"trigger": level, "folds": [], "returns": [], "excess": []} for level in config.trigger_levels}
    calibration_rows = []

    for start_year, end_year, test_start, test_end in _folds(pd.DatetimeIndex(features.index), config):
        train = features.loc[features.index < test_start]
        test = features.loc[(features.index >= test_start) & (features.index <= test_end)]
        if len(train) < 252 * 5 or len(test) <= config.horizon:
            continue
        scored = calibrated_opportunity_score(train, test, target)
        paths = _forward_path_table(test, config.horizon)
        if paths.empty:
            continue
        baseline = paths["forward_return"].astype(float) - config.transaction_cost_bps_round_trip / 10000.0
        baseline_median = float(baseline.median())

        # Calibration evidence: fixed score buckets should show improving forward returns.
        aligned_score = scored["opportunity_score"].reindex(paths.index)
        for lo, hi in ((0, 50), (50, 60), (60, 70), (70, 80), (80, 90), (90, 101)):
            mask = (aligned_score >= lo) & (aligned_score < hi)
            vals = baseline.loc[mask.fillna(False)]
            calibration_rows.append({
                "start_year": start_year, "end_year": end_year, "bucket_low": lo, "bucket_high": hi,
                "n": int(len(vals)), "median_return": float(vals.median()) if len(vals) else None,
                "median_excess": float(vals.median() - baseline_median) if len(vals) else None,
                "win_rate": float((vals > 0).mean()) if len(vals) else None,
            })

        for level in config.trigger_levels:
            trades = _trade_table(test, scored["opportunity_score"], level, config)
            median_return = float(trades["return"].median()) if len(trades) else None
            random_pct = _matched_random_percentile(
                baseline, len(trades), median_return, config.min_gap,
                config.matched_random_iterations, seed=start_year * 1613 + level * 37 + (1 if target.upper() == "QQQ" else 0),
            )
            fold = {
                "start_year": start_year, "end_year": end_year, "n": int(len(trades)),
                "median_return": median_return,
                "median_excess_edge": float(trades["excess"].median()) if len(trades) else None,
                "win_rate": float((trades["return"] > 0).mean()) if len(trades) else None,
                "excess_hit_rate": float((trades["excess"] > 0).mean()) if len(trades) else None,
                "matched_random_percentile": random_pct,
            }
            row = by_level[level]
            row["folds"].append(fold)
            row["returns"].extend(float(x) for x in trades["return"].to_numpy())
            row["excess"].extend(float(x) for x in trades["excess"].to_numpy())

    rows = []
    for level, row in by_level.items():
        returns = np.asarray(row.pop("returns"), dtype=float)
        excess = np.asarray(row.pop("excess"), dtype=float)
        trade_folds = [f for f in row["folds"] if f["n"] > 0]
        positive = [f for f in trade_folds if f["median_excess_edge"] is not None and f["median_excess_edge"] > 0]
        random_tested = [f for f in trade_folds if f["matched_random_percentile"] is not None]
        random_good = [f for f in random_tested if f["matched_random_percentile"] >= config.min_matched_random_percentile]
        fold_fraction = len(positive) / len(trade_folds) if trade_folds else 0.0
        random_fraction = len(random_good) / len(random_tested) if random_tested else 0.0
        median_random = float(np.median([f["matched_random_percentile"] for f in random_tested])) if random_tested else None
        n = len(returns)
        qualifies = bool(
            n >= config.min_trades_total
            and len(trade_folds) >= config.min_folds_with_trades
            and fold_fraction >= config.min_positive_edge_fold_fraction
            and len(random_tested) >= config.min_folds_with_trades
            and random_fraction >= config.min_random_superiority_fold_fraction
            and median_random is not None and median_random >= config.min_matched_random_percentile
            and len(excess) and float(np.median(excess)) > 0
            and float((excess > 0).mean()) > 0.50
            and float(np.median(returns)) > 0
            and float((returns > 0).mean()) > 0.50
        )
        row.update({
            "trades": int(n), "folds_with_trades": len(trade_folds),
            "positive_edge_fold_fraction": float(fold_fraction),
            "matched_random_superiority_fold_fraction": float(random_fraction),
            "median_matched_random_percentile": median_random,
            "mean_trade_return": float(np.mean(returns)) if n else None,
            "median_trade_return": float(np.median(returns)) if n else None,
            "win_rate": float((returns > 0).mean()) if n else None,
            "mean_excess_edge": float(np.mean(excess)) if len(excess) else None,
            "median_excess_edge": float(np.median(excess)) if len(excess) else None,
            "excess_hit_rate": float((excess > 0).mean()) if len(excess) else None,
            "qualifies": qualifies,
        })
        rows.append(row)

    rows.sort(key=lambda r: (r["qualifies"], r["matched_random_superiority_fold_fraction"], r["median_excess_edge"] or -999.0), reverse=True)

    # Latest score uses all history prior to the latest row for calibration, never the latest row itself.
    latest_train = features.iloc[:-1]
    latest_frame = features.iloc[[-1]]
    latest = calibrated_opportunity_score(latest_train, latest_frame, target).iloc[0].to_dict() if len(features) > 1 else {}
    latest["as_of"] = str(pd.Timestamp(features.index[-1]).date()) if len(features) else None

    return {
        "target": target.upper(),
        "config": asdict(config),
        "qualifying_trigger_count": sum(1 for r in rows if r["qualifies"]),
        "rows": rows,
        "calibration_buckets": calibration_rows,
        "latest": latest,
    }
