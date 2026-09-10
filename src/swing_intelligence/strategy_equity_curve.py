from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .opportunity_score import calibrated_opportunity_score
from .walk_forward import _event_positions, _folds


@dataclass(frozen=True)
class StrategyEquityCurveConfig:
    first_test_year: int = 2010
    fold_years: int = 2
    trigger: float = 70.0
    horizon: int = 30
    min_gap: int = 30
    transaction_cost_bps_round_trip: float = 10.0
    starting_capital: float = 100000.0


def _annualized_return(start: float, end: float, years: float) -> float | None:
    if start <= 0 or end <= 0 or years <= 0:
        return None
    return float((end / start) ** (1.0 / years) - 1.0)


def _max_drawdown(equity: pd.Series) -> float | None:
    if equity.empty:
        return None
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def _sharpe(daily_returns: pd.Series) -> float | None:
    r = pd.to_numeric(daily_returns, errors="coerce").dropna()
    if len(r) < 2 or float(r.std(ddof=1)) == 0.0:
        return None
    return float(np.sqrt(252.0) * r.mean() / r.std(ddof=1))


def run_frozen_strategy_equity_curve(
    features: pd.DataFrame,
    cash_yield_percent: pd.Series,
    config: StrategyEquityCurveConfig = StrategyEquityCurveConfig(),
) -> dict:
    """Walk-forward equity curve for the frozen SPY Opportunity Score >=70 strategy.

    The signal threshold/holding rule is fixed. Each test fold calibrates score percentiles
    only from data before that fold. Capital is fully invested in SPY for `horizon`
    trading days after an entry, otherwise it earns the contemporaneous 3-month Treasury
    yield. Trading costs are charged half on entry and half on exit.
    """
    features = features.sort_index().copy()
    close = pd.to_numeric(features["close"], errors="coerce")
    cash_yield = pd.to_numeric(cash_yield_percent, errors="coerce").reindex(features.index).ffill().fillna(0.0)

    strategy_daily = pd.Series(0.0, index=features.index, dtype=float)
    invested = pd.Series(False, index=features.index, dtype=bool)
    entry_dates: list[pd.Timestamp] = []
    trade_rows: list[dict] = []

    half_cost = config.transaction_cost_bps_round_trip / 20000.0

    for start_year, end_year, test_start, test_end in _folds(pd.DatetimeIndex(features.index), config):
        train = features.loc[features.index < test_start]
        test = features.loc[(features.index >= test_start) & (features.index <= test_end)]
        if len(train) < 252 * 5 or len(test) <= config.horizon:
            continue
        scored = calibrated_opportunity_score(train, test, "SPY")["opportunity_score"]
        possible = scored.iloc[:-config.horizon] >= config.trigger
        positions = _event_positions(possible, config.min_gap)
        test_idx = pd.DatetimeIndex(test.index)
        for pos in positions:
            entry = test_idx[pos]
            exit_pos = pos + config.horizon
            if exit_pos >= len(test_idx):
                continue
            exit_date = test_idx[exit_pos]
            entry_dates.append(entry)
            invested.loc[entry:exit_date] = True
            gross = float(close.loc[exit_date] / close.loc[entry] - 1.0)
            net = (1.0 - half_cost) * (1.0 + gross) * (1.0 - half_cost) - 1.0
            trade_rows.append({
                "entry_date": str(entry.date()),
                "exit_date": str(exit_date.date()),
                "entry_score": float(scored.loc[entry]),
                "gross_return": gross,
                "net_return": float(net),
            })

    first_date = min(entry_dates) if entry_dates else pd.Timestamp(f"{config.first_test_year}-01-01")
    curve_idx = features.index[features.index >= first_date]
    if len(curve_idx) < 2:
        return {"config": asdict(config), "trades": [], "metrics": {}}

    px_ret = close.pct_change().reindex(curve_idx).fillna(0.0)
    cash_daily = ((1.0 + cash_yield.reindex(curve_idx).fillna(0.0) / 100.0) ** (1.0 / 252.0) - 1.0)
    held = invested.reindex(curve_idx).fillna(False)
    strategy_daily = pd.Series(np.where(held, px_ret, cash_daily), index=curve_idx, dtype=float)

    for row in trade_rows:
        entry = pd.Timestamp(row["entry_date"])
        exit_date = pd.Timestamp(row["exit_date"])
        if entry in strategy_daily.index:
            strategy_daily.loc[entry] = (1.0 + strategy_daily.loc[entry]) * (1.0 - half_cost) - 1.0
        if exit_date in strategy_daily.index:
            strategy_daily.loc[exit_date] = (1.0 + strategy_daily.loc[exit_date]) * (1.0 - half_cost) - 1.0

    strategy_equity = config.starting_capital * (1.0 + strategy_daily).cumprod()
    bh_daily = px_ret.copy()
    bh_equity = config.starting_capital * (1.0 + bh_daily).cumprod()

    years = max((curve_idx[-1] - curve_idx[0]).days / 365.25, 1.0 / 365.25)
    exposure = float(held.mean())
    metrics = {
        "start_date": str(pd.Timestamp(curve_idx[0]).date()),
        "end_date": str(pd.Timestamp(curve_idx[-1]).date()),
        "starting_capital": config.starting_capital,
        "strategy_ending_value": float(strategy_equity.iloc[-1]),
        "buy_hold_ending_value": float(bh_equity.iloc[-1]),
        "strategy_total_return": float(strategy_equity.iloc[-1] / config.starting_capital - 1.0),
        "buy_hold_total_return": float(bh_equity.iloc[-1] / config.starting_capital - 1.0),
        "strategy_cagr": _annualized_return(config.starting_capital, float(strategy_equity.iloc[-1]), years),
        "buy_hold_cagr": _annualized_return(config.starting_capital, float(bh_equity.iloc[-1]), years),
        "strategy_max_drawdown": _max_drawdown(strategy_equity),
        "buy_hold_max_drawdown": _max_drawdown(bh_equity),
        "strategy_sharpe": _sharpe(strategy_daily),
        "buy_hold_sharpe": _sharpe(bh_daily),
        "market_exposure_fraction": exposure,
        "trade_count": len(trade_rows),
        "strategy_minus_buy_hold_ending_value": float(strategy_equity.iloc[-1] - bh_equity.iloc[-1]),
    }
    return {
        "config": asdict(config),
        "cash_proxy": "DGS3MO 3-month Treasury yield, daily-compounded approximation while idle",
        "trades": trade_rows,
        "metrics": metrics,
    }
