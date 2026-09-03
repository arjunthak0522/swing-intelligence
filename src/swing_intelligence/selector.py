from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .backtest import _metrics


@dataclass(frozen=True)
class SelectionGate:
    """Evidence requirements for promoting an asset from CASH into the strategy."""
    min_n: int = 30
    require_fdr: bool = True
    min_ci_low: float = 0.0
    min_win_edge: float = 0.0


def eligible_evidence(evidence: pd.DataFrame, gate: SelectionGate = SelectionGate()) -> pd.Series:
    required = {"n", "ci_low", "win_edge"}
    missing = required - set(evidence.columns)
    if missing:
        raise ValueError(f"Missing evidence fields: {sorted(missing)}")
    ok = (
        (evidence["n"] >= gate.min_n)
        & (evidence["ci_low"] > gate.min_ci_low)
        & (evidence["win_edge"] > gate.min_win_edge)
    )
    if gate.require_fdr:
        if "passes_fdr" not in evidence.columns:
            raise ValueError("passes_fdr required when require_fdr=True")
        ok &= evidence["passes_fdr"].astype(bool)
    if "stable" in evidence.columns:
        ok &= evidence["stable"].astype(bool)
    return ok.fillna(False)


def choose_asset_by_evidence(evidence: pd.DataFrame, gate: SelectionGate = SelectionGate()) -> pd.Series:
    """Choose SPY, QQQ or CASH from dated, walk-forward evidence.

    Expected input has a MultiIndex (date, asset), or columns date/asset.
    Selection is based on the lower confidence bound of historical excess edge,
    not on a proprietary weighted score. Ties favor lower adverse excursion when
    available, then deterministic alphabetical ordering.
    """
    if not isinstance(evidence.index, pd.MultiIndex):
        if not {"date", "asset"}.issubset(evidence.columns):
            raise ValueError("Evidence must have MultiIndex(date, asset) or date/asset columns")
        evidence = evidence.set_index(["date", "asset"])
    work = evidence.copy().reset_index()
    work["date"] = pd.to_datetime(work["date"])
    work["asset"] = work["asset"].astype(str).str.upper()
    work["eligible"] = eligible_evidence(work, gate)

    picks: list[tuple[pd.Timestamp, str]] = []
    for date, group in work.groupby("date", sort=True):
        g = group.loc[group["eligible"]].copy()
        if g.empty:
            picks.append((date, "CASH"))
            continue
        sort_cols = ["ci_low"]
        ascending = [False]
        if "median_mae" in g.columns:
            sort_cols.append("median_mae")
            ascending.append(False)
        sort_cols.append("asset")
        ascending.append(True)
        pick = g.sort_values(sort_cols, ascending=ascending).iloc[0]["asset"]
        picks.append((date, str(pick)))
    return pd.Series(dict(picks), name="selected_asset").sort_index()


def backtest_asset_selector(
    prices: pd.DataFrame,
    selected_asset: pd.Series,
    *,
    cost_per_turnover: float = 0.0005,
    decision_delay: int = 1,
) -> dict:
    """Backtest a SPY/QQQ/CASH selector with next-bar implementation.

    `selected_asset[t]` must contain only evidence calculable as of t. The
    decision is shifted by `decision_delay`, preventing same-bar execution.
    """
    prices = prices.copy()
    prices.columns = [str(c).upper() for c in prices.columns]
    selected = selected_asset.reindex(prices.index).ffill().fillna("CASH").astype(str).str.upper()
    implemented = selected.shift(decision_delay).fillna("CASH")
    asset_returns = prices.pct_change().fillna(0.0)

    strategy = pd.Series(0.0, index=prices.index, dtype=float)
    for asset in prices.columns:
        active = implemented.shift(1).fillna("CASH").eq(asset)
        strategy = strategy.add(asset_returns[asset].where(active, 0.0), fill_value=0.0)

    turnover = implemented.ne(implemented.shift(1)).astype(float)
    strategy -= turnover * cost_per_turnover

    positions = pd.DataFrame(0.0, index=prices.index, columns=list(prices.columns) + ["CASH"])
    for col in positions.columns:
        positions[col] = implemented.eq(col).astype(float)

    metrics = _metrics(strategy, (implemented != "CASH").astype(float))
    metrics["switches"] = int(turnover.sum())
    metrics["cash_fraction"] = float((implemented == "CASH").mean())
    return {
        "returns": strategy,
        "selected_asset": selected,
        "implemented_asset": implemented,
        "positions": positions,
        "metrics": metrics,
    }
