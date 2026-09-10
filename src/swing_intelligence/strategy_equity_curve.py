from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .opportunity_score import calibrated_opportunity_score
from .walk_forward import _folds


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
    return float((equity / peak - 1.0).min())


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
    """True walk-forward portfolio test for frozen SPY Opportunity Score >=70.

    A completed-close score can only be acted on afterward, so a signal observed at
    day t's close enters at day t+1's open. The position then remains invested for
    `horizon` trading sessions and exits at that session's close. Idle capital earns
    the contemporaneous 3-month Treasury yield. No overlapping positions are allowed.
    Score calibration in each test fold uses only data preceding that fold.
    """
    features = features.sort_index().copy()
    close = pd.to_numeric(features["close"], errors="coerce")
    open_px = pd.to_numeric(features["open"], errors="coerce")
    cash_yield = pd.to_numeric(cash_yield_percent, errors="coerce").reindex(features.index).ffill().fillna(0.0)
    index = pd.DatetimeIndex(features.index)

    raw_signals: list[tuple[pd.Timestamp, float]] = []
    for _, _, test_start, test_end in _folds(index, config):
        train = features.loc[features.index < test_start]
        test = features.loc[(features.index >= test_start) & (features.index <= test_end)]
        if len(train) < 252 * 5 or len(test) <= config.horizon + 1:
            continue
        scored = calibrated_opportunity_score(train, test, "SPY")["opportunity_score"]
        for dt, score in scored.items():
            if pd.notna(score) and float(score) >= config.trigger:
                raw_signals.append((pd.Timestamp(dt), float(score)))

    signals = sorted(raw_signals, key=lambda x: x[0])
    selected: list[tuple[pd.Timestamp, float, pd.Timestamp, pd.Timestamp]] = []
    last_signal_pos: int | None = None
    for signal_date, score in signals:
        try:
            signal_pos = int(index.get_loc(signal_date))
        except KeyError:
            continue
        if last_signal_pos is not None and signal_pos - last_signal_pos < config.min_gap:
            continue
        entry_pos = signal_pos + 1
        exit_pos = entry_pos + config.horizon - 1
        if exit_pos >= len(index):
            continue
        entry_date = index[entry_pos]
        exit_date = index[exit_pos]
        if selected and entry_date <= selected[-1][3]:
            continue
        selected.append((signal_date, score, entry_date, exit_date))
        last_signal_pos = signal_pos

    first_date = selected[0][2] if selected else pd.Timestamp(f"{config.first_test_year}-01-01")
    curve_idx = index[index >= first_date]
    if len(curve_idx) < 2:
        return {"config": asdict(config), "trades": [], "metrics": {}}

    cash_daily = (1.0 + cash_yield.reindex(curve_idx).fillna(0.0) / 100.0) ** (1.0 / 252.0) - 1.0
    strategy_daily = cash_daily.astype(float).copy()
    held = pd.Series(False, index=curve_idx, dtype=bool)
    trade_rows: list[dict] = []
    half_cost = config.transaction_cost_bps_round_trip / 20000.0

    for signal_date, score, entry_date, exit_date in selected:
        if entry_date not in strategy_daily.index or exit_date not in strategy_daily.index:
            continue
        entry_pos = int(index.get_loc(entry_date))
        exit_pos = int(index.get_loc(exit_date))
        trade_dates = index[entry_pos:exit_pos + 1]
        held.loc[trade_dates] = True

        first_day_ret = float(close.loc[entry_date] / open_px.loc[entry_date] - 1.0)
        strategy_daily.loc[entry_date] = (1.0 + first_day_ret) * (1.0 - half_cost) - 1.0
        if len(trade_dates) > 1:
            later = close.pct_change().reindex(trade_dates[1:]).astype(float)
            strategy_daily.loc[trade_dates[1:]] = later
        strategy_daily.loc[exit_date] = (1.0 + strategy_daily.loc[exit_date]) * (1.0 - half_cost) - 1.0

        gross = float(close.loc[exit_date] / open_px.loc[entry_date] - 1.0)
        net = float((1.0 - half_cost) * (1.0 + gross) * (1.0 - half_cost) - 1.0)
        trade_rows.append({
            "signal_date": str(signal_date.date()),
            "entry_date": str(entry_date.date()),
            "exit_date": str(exit_date.date()),
            "signal_score": score,
            "entry_open": float(open_px.loc[entry_date]),
            "exit_close": float(close.loc[exit_date]),
            "gross_return": gross,
            "net_return": net,
        })

    strategy_equity = config.starting_capital * (1.0 + strategy_daily).cumprod()
    bh_daily = close.pct_change().reindex(curve_idx).fillna(0.0).astype(float)
    bh_daily.iloc[0] = float(close.loc[curve_idx[0]] / open_px.loc[curve_idx[0]] - 1.0)
    bh_equity = config.starting_capital * (1.0 + bh_daily).cumprod()

    years = max((curve_idx[-1] - curve_idx[0]).days / 365.25, 1.0 / 365.25)
    strategy_end = float(strategy_equity.iloc[-1])
    bh_end = float(bh_equity.iloc[-1])
    metrics = {
        "start_date": str(pd.Timestamp(curve_idx[0]).date()),
        "end_date": str(pd.Timestamp(curve_idx[-1]).date()),
        "starting_capital": config.starting_capital,
        "strategy_ending_value": strategy_end,
        "buy_hold_ending_value": bh_end,
        "strategy_total_return": float(strategy_end / config.starting_capital - 1.0),
        "buy_hold_total_return": float(bh_end / config.starting_capital - 1.0),
        "strategy_cagr": _annualized_return(config.starting_capital, strategy_end, years),
        "buy_hold_cagr": _annualized_return(config.starting_capital, bh_end, years),
        "strategy_max_drawdown": _max_drawdown(strategy_equity),
        "buy_hold_max_drawdown": _max_drawdown(bh_equity),
        "strategy_sharpe": _sharpe(strategy_daily),
        "buy_hold_sharpe": _sharpe(bh_daily),
        "market_exposure_fraction": float(held.mean()),
        "cash_fraction": float((~held).mean()),
        "trade_count": len(trade_rows),
        "strategy_minus_buy_hold_ending_value": float(strategy_end - bh_end),
    }
    return {
        "config": asdict(config),
        "execution": "signal on completed close; enter next trading day open; exit after 30 trading sessions at close",
        "cash_proxy": "DGS3MO 3-month Treasury yield, daily-compounded approximation while idle",
        "trades": trade_rows,
        "metrics": metrics,
    }
