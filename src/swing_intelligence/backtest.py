import numpy as np
import pandas as pd


def _metrics(returns: pd.Series, trades: pd.Series | None = None) -> dict:
    returns = returns.fillna(0.0)
    equity = (1 + returns).cumprod()
    years = max(len(returns) / 252, 1/252)
    cagr = equity.iloc[-1] ** (1 / years) - 1
    vol = returns.std(ddof=0) * np.sqrt(252)
    sharpe = (returns.mean() / returns.std(ddof=0) * np.sqrt(252)) if returns.std(ddof=0) else np.nan
    dd = equity / equity.cummax() - 1
    out = {
        "total_return": float(equity.iloc[-1] - 1),
        "cagr": float(cagr),
        "volatility": float(vol),
        "sharpe": float(sharpe) if np.isfinite(sharpe) else None,
        "max_drawdown": float(dd.min()),
    }
    if trades is not None:
        out["time_in_market"] = float((trades > 0).mean())
    return out


def backtest_long_only(close: pd.Series, signal: pd.Series,
                       cost_per_turnover: float = 0.0005,
                       signal_delay: int = 1) -> dict:
    """Simple auditable daily long/cash backtest with delayed execution."""
    signal = signal.reindex(close.index).fillna(0).clip(0, 1)
    position = signal.shift(signal_delay).fillna(0)
    ret = close.pct_change().fillna(0)
    turnover = position.diff().abs().fillna(position.abs())
    strategy_ret = position.shift(1).fillna(0) * ret - turnover * cost_per_turnover
    return {
        "returns": strategy_ret,
        "position": position,
        "metrics": _metrics(strategy_ret, position),
    }


def benchmark_buy_hold(close: pd.Series) -> dict:
    ret = close.pct_change().fillna(0)
    return {"returns": ret, "metrics": _metrics(ret)}
