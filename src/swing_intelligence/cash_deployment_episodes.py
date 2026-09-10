from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .opportunity_score import calibrated_opportunity_score
from .walk_forward import _folds


@dataclass(frozen=True)
class CashEpisodeConfig:
    first_test_year: int = 2010
    fold_years: int = 2
    trigger: float = 70.0
    dca_days: int = 30
    max_wait_days: tuple[int, ...] = (63, 126)
    outcome_days: int = 126
    episode_spacing_days: int = 21
    transaction_cost_bps: float = 10.0


def _score_series(features: pd.DataFrame, config: CashEpisodeConfig) -> pd.Series:
    out = pd.Series(np.nan, index=features.index, dtype=float)
    for _, _, test_start, test_end in _folds(pd.DatetimeIndex(features.index), config):
        train = features.loc[features.index < test_start]
        test = features.loc[(features.index >= test_start) & (features.index <= test_end)]
        if len(train) < 252 * 5 or len(test) < 2:
            continue
        out.loc[test.index] = calibrated_opportunity_score(train, test, "SPY")["opportunity_score"]
    return out


def _buy_return(features: pd.DataFrame, entry_pos: int, end_pos: int, cost_bps: float) -> float:
    open_px = pd.to_numeric(features["open"], errors="coerce")
    close = pd.to_numeric(features["close"], errors="coerce")
    if entry_pos >= len(features) or end_pos >= len(features):
        return np.nan
    entry = float(open_px.iloc[entry_pos])
    end = float(close.iloc[end_pos])
    if not np.isfinite(entry) or not np.isfinite(end) or entry <= 0:
        return np.nan
    return float((end / entry) * (1.0 - cost_bps / 10000.0) - 1.0)


def _dca_return(features: pd.DataFrame, start_pos: int, end_pos: int, dca_days: int, cost_bps: float) -> float:
    n = min(dca_days, end_pos - start_pos + 1)
    if n <= 0:
        return np.nan
    returns = [_buy_return(features, start_pos + i, end_pos, cost_bps) for i in range(n)]
    arr = np.asarray([x for x in returns if np.isfinite(x)], dtype=float)
    return float(arr.mean()) if len(arr) else np.nan


def run_cash_deployment_episodes(features: pd.DataFrame, config: CashEpisodeConfig = CashEpisodeConfig()) -> dict:
    """Repeated historical cash-arrival test for frozen SPY Opportunity Score v1.0.

    At regularly spaced historical dates, a fresh cash tranche is assumed to arrive.
    Compare immediate next-open deployment, 30-session DCA, and waiting for the first
    score >= trigger subject to a hard maximum wait. All policies are evaluated at the
    same fixed episode end date. Score calibration uses only pre-fold history.
    """
    features = features.sort_index().copy()
    score = _score_series(features, config)
    idx = pd.DatetimeIndex(features.index)
    start = pd.Timestamp(f"{config.first_test_year}-01-01")
    eligible = np.where(idx >= start)[0]
    rows_by_wait: dict[int, list[dict]] = {w: [] for w in config.max_wait_days}
    if not len(eligible):
        return {"config": asdict(config), "waits": {}}

    first = int(eligible[0])
    last_start = len(idx) - config.outcome_days - 2
    for start_pos in range(first, last_start + 1, config.episode_spacing_days):
        cash_date = idx[start_pos]
        immediate_pos = start_pos + 1
        end_pos = immediate_pos + config.outcome_days
        if end_pos >= len(idx):
            break
        immediate = _buy_return(features, immediate_pos, end_pos, config.transaction_cost_bps)
        dca = _dca_return(features, immediate_pos, end_pos, config.dca_days, config.transaction_cost_bps)

        for wait in config.max_wait_days:
            search_end = min(start_pos + wait, end_pos - 1)
            window = score.iloc[start_pos : search_end + 1]
            hits = window[window >= config.trigger]
            if len(hits):
                signal_date = hits.index[0]
                signal_pos = int(features.index.get_loc(signal_date))
                deploy_pos = min(signal_pos + 1, end_pos)
                triggered = True
            else:
                deploy_pos = min(start_pos + wait + 1, end_pos)
                signal_date = pd.NaT
                triggered = False
            score_ret = _buy_return(features, deploy_pos, end_pos, config.transaction_cost_bps)
            rows_by_wait[wait].append({
                "cash_date": str(cash_date.date()),
                "end_date": str(idx[end_pos].date()),
                "triggered": triggered,
                "signal_date": None if pd.isna(signal_date) else str(pd.Timestamp(signal_date).date()),
                "deployment_date": str(idx[deploy_pos].date()),
                "immediate_return": immediate,
                "dca_return": dca,
                "score_return": score_ret,
                "score_minus_immediate": float(score_ret - immediate),
                "score_minus_dca": float(score_ret - dca),
            })

    waits = {}
    for wait, rows in rows_by_wait.items():
        df = pd.DataFrame(rows)
        if df.empty:
            waits[str(wait)] = {"episodes": 0, "rows": []}
            continue
        di = df["score_minus_immediate"].astype(float)
        dd = df["score_minus_dca"].astype(float)
        waits[str(wait)] = {
            "episodes": int(len(df)),
            "trigger_fraction": float(df["triggered"].mean()),
            "median_immediate_return": float(df["immediate_return"].median()),
            "median_dca_return": float(df["dca_return"].median()),
            "median_score_return": float(df["score_return"].median()),
            "mean_score_minus_immediate": float(di.mean()),
            "median_score_minus_immediate": float(di.median()),
            "win_rate_vs_immediate": float((di > 0).mean()),
            "mean_score_minus_dca": float(dd.mean()),
            "median_score_minus_dca": float(dd.median()),
            "win_rate_vs_dca": float((dd > 0).mean()),
            "p10_score_minus_immediate": float(np.percentile(di, 10)),
            "p90_score_minus_immediate": float(np.percentile(di, 90)),
            "rows": rows,
        }
    return {"config": asdict(config), "waits": waits}
