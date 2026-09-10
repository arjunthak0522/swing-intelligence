from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .opportunity_score import calibrated_opportunity_score
from .walk_forward import _folds


@dataclass(frozen=True)
class CashDeploymentConfig:
    first_test_year: int = 2010
    fold_years: int = 2
    cash_sleeve_fraction: float = 0.10
    trigger: float = 70.0
    dca_days: int = 30
    random_iterations: int = 200
    transaction_cost_bps: float = 10.0
    starting_capital: float = 100000.0


def _daily_cash_return(yield_pct: pd.Series) -> pd.Series:
    y = pd.to_numeric(yield_pct, errors="coerce").ffill().fillna(0.0)
    return (1.0 + y / 100.0) ** (1.0 / 252.0) - 1.0


def _deployment_date_score(features: pd.DataFrame, config: CashDeploymentConfig) -> pd.Series:
    marks = pd.Series(False, index=features.index, dtype=bool)
    for _, _, test_start, test_end in _folds(pd.DatetimeIndex(features.index), config):
        train = features.loc[features.index < test_start]
        test = features.loc[(features.index >= test_start) & (features.index <= test_end)]
        if len(train) < 252 * 5 or len(test) < 2:
            continue
        score = calibrated_opportunity_score(train, test, "SPY")["opportunity_score"]
        hits = score >= config.trigger
        if hits.any():
            first_hit = hits[hits].index[0]
            pos = features.index.get_indexer([first_hit])[0]
            if pos + 1 < len(features.index):
                marks.iloc[pos + 1] = True
    return marks


def _simulate_policy(features: pd.DataFrame, cash_yield_pct: pd.Series, deploy_fraction_by_day: pd.Series, config: CashDeploymentConfig) -> dict:
    idx = features.index
    close = pd.to_numeric(features["close"], errors="coerce").ffill()
    open_px = pd.to_numeric(features.get("open", close), errors="coerce").fillna(close)
    px_ret = close.pct_change().fillna(0.0)
    intraday_ret = (close / open_px - 1.0).fillna(0.0)
    cash_ret = _daily_cash_return(cash_yield_pct.reindex(idx))

    core = config.starting_capital * (1.0 - config.cash_sleeve_fraction)
    sleeve_cash = config.starting_capital * config.cash_sleeve_fraction
    sleeve_equity = 0.0
    total_curve = []
    deployed = 0.0
    one_way_cost = config.transaction_cost_bps / 10000.0

    deploy = deploy_fraction_by_day.reindex(idx).fillna(0.0)
    for i, _ in enumerate(idx):
        if i > 0:
            core *= 1.0 + float(px_ret.iloc[i])
            sleeve_equity *= 1.0 + float(px_ret.iloc[i])
            sleeve_cash *= 1.0 + float(cash_ret.iloc[i])

        frac = float(deploy.iloc[i])
        if frac > 0 and sleeve_cash > 0:
            amount = min(sleeve_cash, config.starting_capital * config.cash_sleeve_fraction * frac)
            sleeve_cash -= amount
            sleeve_equity += amount * (1.0 - one_way_cost) * (1.0 + float(intraday_ret.iloc[i]))
            deployed += amount

        total_curve.append(core + sleeve_cash + sleeve_equity)

    total = pd.Series(total_curve, index=idx, dtype=float)
    peak = total.cummax()
    dd = total / peak - 1.0
    years = max((idx[-1] - idx[0]).days / 365.25, 1.0 / 365.25)
    end = float(total.iloc[-1])
    return {
        "ending_value": end,
        "total_return": float(end / config.starting_capital - 1.0),
        "cagr": float((end / config.starting_capital) ** (1.0 / years) - 1.0),
        "max_drawdown": float(dd.min()),
        "deployed_fraction_of_initial_sleeve": float(deployed / (config.starting_capital * config.cash_sleeve_fraction)),
    }


def run_cash_deployment_simulator(features: pd.DataFrame, cash_yield_pct: pd.Series, config: CashDeploymentConfig = CashDeploymentConfig()) -> dict:
    """Compare ways to deploy a pre-existing cash sleeve into SPY.

    The core remains invested in SPY. Only the initial cash sleeve deployment timing differs.
    Score calibration always uses the full history available before each walk-forward fold;
    performance measurement begins at `first_test_year`. Deployments occur at the session open.
    """
    full_features = features.sort_index().copy()
    if len(full_features) < 2:
        return {"config": asdict(config), "policies": {}}

    score_marks_full = _deployment_date_score(full_features, config)
    start = pd.Timestamp(f"{config.first_test_year}-01-01")
    features = full_features.loc[full_features.index >= start]
    idx = features.index
    if len(idx) < 2:
        return {"config": asdict(config), "policies": {}}
    cash_yield_pct = cash_yield_pct.reindex(idx).ffill().fillna(0.0)

    immediate = pd.Series(0.0, index=idx)
    immediate.iloc[0] = 1.0

    dca = pd.Series(0.0, index=idx)
    n_dca = min(config.dca_days, len(idx))
    if n_dca:
        dca.iloc[:n_dca] = 1.0 / n_dca

    score_marks = score_marks_full.reindex(idx).fillna(False)
    score_policy = pd.Series(0.0, index=idx)
    if score_marks.any():
        score_policy.loc[score_marks[score_marks].index[0]] = 1.0

    policies = {
        "immediate": _simulate_policy(features, cash_yield_pct, immediate, config),
        "dca": _simulate_policy(features, cash_yield_pct, dca, config),
        "score_triggered": _simulate_policy(features, cash_yield_pct, score_policy, config),
    }

    rng = np.random.default_rng(20260909)
    random_ends, random_cagrs, random_mdds = [], [], []
    for _ in range(config.random_iterations):
        p = pd.Series(0.0, index=idx)
        p.iloc[int(rng.integers(0, len(idx)))] = 1.0
        r = _simulate_policy(features, cash_yield_pct, p, config)
        random_ends.append(r["ending_value"])
        random_cagrs.append(r["cagr"])
        random_mdds.append(r["max_drawdown"])
    policies["random"] = {
        "iterations": config.random_iterations,
        "median_ending_value": float(np.median(random_ends)),
        "median_cagr": float(np.median(random_cagrs)),
        "median_max_drawdown": float(np.median(random_mdds)),
        "p10_ending_value": float(np.percentile(random_ends, 10)),
        "p90_ending_value": float(np.percentile(random_ends, 90)),
    }

    policies["score_triggered"]["deployment_date"] = str(score_marks[score_marks].index[0].date()) if score_marks.any() else None
    score_end = policies["score_triggered"]["ending_value"]
    policies["score_triggered"]["vs_immediate_ending_value"] = float(score_end - policies["immediate"]["ending_value"])
    policies["score_triggered"]["vs_dca_ending_value"] = float(score_end - policies["dca"]["ending_value"])
    policies["score_triggered"]["vs_random_median_ending_value"] = float(score_end - policies["random"]["median_ending_value"])

    return {"config": asdict(config), "policies": policies}
