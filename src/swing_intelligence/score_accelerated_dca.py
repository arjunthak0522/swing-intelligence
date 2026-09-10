from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .cash_deployment_episodes import _score_series


@dataclass(frozen=True)
class AcceleratedDCAConfig:
    first_test_year: int = 2010
    fold_years: int = 2
    trigger: float = 70.0
    dca_days: int = 30
    outcome_days: int = 126
    episode_spacing_days: int = 21
    transaction_cost_bps: float = 10.0


def _lot_return(features: pd.DataFrame, entry_pos: int, end_pos: int, cost_bps: float) -> float:
    open_px = pd.to_numeric(features["open"], errors="coerce")
    close = pd.to_numeric(features["close"], errors="coerce")
    if entry_pos >= len(features) or end_pos >= len(features):
        return np.nan
    entry = float(open_px.iloc[entry_pos])
    end = float(close.iloc[end_pos])
    if not np.isfinite(entry) or not np.isfinite(end) or entry <= 0:
        return np.nan
    return float((end / entry) * (1.0 - cost_bps / 10000.0) - 1.0)


def _weighted_policy_return(features: pd.DataFrame, lots: list[tuple[int, float]], end_pos: int, cost_bps: float) -> float:
    vals = []
    weights = []
    for pos, weight in lots:
        r = _lot_return(features, pos, end_pos, cost_bps)
        if np.isfinite(r) and weight > 0:
            vals.append(r)
            weights.append(weight)
    if not vals:
        return np.nan
    w = np.asarray(weights, dtype=float)
    w = w / w.sum()
    return float(np.dot(np.asarray(vals, dtype=float), w))


def run_score_accelerated_dca(features: pd.DataFrame, config: AcceleratedDCAConfig = AcceleratedDCAConfig()) -> dict:
    """Repeated episode test of score-accelerated DCA.

    Every episode starts a normal equal-weight `dca_days` schedule immediately.
    If frozen SPY Opportunity Score v1.0 reaches `trigger` before that schedule ends,
    all still-uninvested installments are pulled forward to the next session open.
    The score can accelerate deployment but can never delay it.
    """
    features = features.sort_index().copy()
    score_cfg = type("ScoreCfg", (), {
        "first_test_year": config.first_test_year,
        "fold_years": config.fold_years,
        "trigger": config.trigger,
    })()
    score = _score_series(features, score_cfg)
    idx = pd.DatetimeIndex(features.index)
    eligible = np.where(idx >= pd.Timestamp(f"{config.first_test_year}-01-01"))[0]
    rows: list[dict] = []
    if not len(eligible):
        return {"config": asdict(config), "summary": {}, "rows": []}

    first = int(eligible[0])
    last_start = len(idx) - config.outcome_days - 2
    for start_pos in range(first, last_start + 1, config.episode_spacing_days):
        immediate_pos = start_pos + 1
        end_pos = immediate_pos + config.outcome_days
        if end_pos >= len(idx):
            break

        n = min(config.dca_days, end_pos - immediate_pos + 1)
        base_lots = [(immediate_pos + i, 1.0 / n) for i in range(n)]
        dca_ret = _weighted_policy_return(features, base_lots, end_pos, config.transaction_cost_bps)
        immediate_ret = _lot_return(features, immediate_pos, end_pos, config.transaction_cost_bps)

        search_end = min(immediate_pos + n - 2, end_pos - 1)
        window = score.iloc[start_pos : search_end + 1]
        hits = window[window >= config.trigger]
        accelerated_lots = []
        trigger_date = pd.NaT
        acceleration_pos = None
        if len(hits):
            trigger_date = hits.index[0]
            signal_pos = int(features.index.get_loc(trigger_date))
            acceleration_pos = signal_pos + 1

        used_weight = 0.0
        for i in range(n):
            lot_pos = immediate_pos + i
            weight = 1.0 / n
            if acceleration_pos is not None and lot_pos >= acceleration_pos:
                remaining = 1.0 - used_weight
                if remaining > 1e-12:
                    accelerated_lots.append((acceleration_pos, remaining))
                used_weight = 1.0
                break
            accelerated_lots.append((lot_pos, weight))
            used_weight += weight
        if used_weight < 1.0 - 1e-12:
            accelerated_lots.append((immediate_pos + n - 1, 1.0 - used_weight))

        accel_ret = _weighted_policy_return(features, accelerated_lots, end_pos, config.transaction_cost_bps)
        rows.append({
            "cash_date": str(idx[start_pos].date()),
            "end_date": str(idx[end_pos].date()),
            "accelerated": acceleration_pos is not None,
            "trigger_date": None if pd.isna(trigger_date) else str(pd.Timestamp(trigger_date).date()),
            "acceleration_date": None if acceleration_pos is None else str(idx[acceleration_pos].date()),
            "immediate_return": immediate_ret,
            "dca_return": dca_ret,
            "accelerated_return": accel_ret,
            "accelerated_minus_dca": float(accel_ret - dca_ret),
            "accelerated_minus_immediate": float(accel_ret - immediate_ret),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return {"config": asdict(config), "summary": {}, "rows": []}
    ad = df["accelerated_minus_dca"].astype(float)
    ai = df["accelerated_minus_immediate"].astype(float)
    summary = {
        "episodes": int(len(df)),
        "acceleration_fraction": float(df["accelerated"].mean()),
        "median_immediate_return": float(df["immediate_return"].median()),
        "median_dca_return": float(df["dca_return"].median()),
        "median_accelerated_return": float(df["accelerated_return"].median()),
        "mean_accelerated_minus_dca": float(ad.mean()),
        "median_accelerated_minus_dca": float(ad.median()),
        "win_rate_vs_dca": float((ad > 0).mean()),
        "mean_accelerated_minus_immediate": float(ai.mean()),
        "median_accelerated_minus_immediate": float(ai.median()),
        "win_rate_vs_immediate": float((ai > 0).mean()),
        "p10_accelerated_minus_dca": float(np.percentile(ad, 10)),
        "p90_accelerated_minus_dca": float(np.percentile(ad, 90)),
    }
    return {"config": asdict(config), "summary": summary, "rows": rows}
