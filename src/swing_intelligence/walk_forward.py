from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from .autonomous_lab import HypothesisRule, RuleTerm, _forward_path_table
from .market_state_hypotheses import learn_market_state_hypotheses


@dataclass(frozen=True)
class WalkForwardConfig:
    first_test_year: int = 2010
    fold_years: int = 2
    horizon: int = 30
    min_gap: int = 30
    transaction_cost_bps_round_trip: float = 2.0
    min_trades_total: int = 20
    min_folds_with_trades: int = 3
    min_positive_fold_fraction: float = 0.60


def _to_rule(state_rule) -> HypothesisRule:
    return HypothesisRule(
        name=f"state__{state_rule.name}",
        terms=tuple(RuleTerm(t.feature, t.op, t.threshold) for t in state_rule.terms),
        rationale=f"[{state_rule.family}] {state_rule.rationale}",
    )


def _event_positions(mask: pd.Series, min_gap: int) -> list[int]:
    positions = np.flatnonzero(mask.fillna(False).to_numpy(dtype=bool))
    chosen: list[int] = []
    last = None
    for pos in positions:
        if last is None or pos - last >= min_gap:
            chosen.append(int(pos))
            last = int(pos)
    return chosen


def _trade_returns(test: pd.DataFrame, rule: HypothesisRule, config: WalkForwardConfig) -> pd.Series:
    paths = _forward_path_table(test, config.horizon)
    if paths.empty:
        return pd.Series(dtype=float)
    mask = rule.mask(test).reindex(paths.index).fillna(False)
    positions = _event_positions(mask, config.min_gap)
    if not positions:
        return pd.Series(dtype=float)
    dates = paths.index[positions]
    returns = paths.loc[dates, "forward_return"].astype(float) - config.transaction_cost_bps_round_trip / 10000.0
    returns.index = dates
    return returns


def _baseline_returns(test: pd.DataFrame, config: WalkForwardConfig) -> pd.Series:
    paths = _forward_path_table(test, config.horizon)
    if paths.empty:
        return pd.Series(dtype=float)
    return paths["forward_return"].astype(float) - config.transaction_cost_bps_round_trip / 10000.0


def _folds(index: pd.DatetimeIndex, config: WalkForwardConfig):
    max_year = int(index.max().year)
    year = config.first_test_year
    while year <= max_year:
        start = pd.Timestamp(f"{year}-01-01")
        end_year = min(year + config.fold_years - 1, max_year)
        end = min(pd.Timestamp(f"{end_year}-12-31"), index.max())
        yield year, end_year, start, end
        year += config.fold_years


def run_semantic_walk_forward(
    features: pd.DataFrame,
    target: str,
    config: WalkForwardConfig = WalkForwardConfig(),
) -> dict:
    """Expanding-window out-of-sample test of semantic strategy templates.

    Each fold relearns template thresholds from data strictly before the test
    window. Signals become non-overlapping fixed-horizon trades. A rule must beat
    the fold's unconditional forward-return distribution, not merely make money in
    an upward-drifting equity market.
    """
    features = features.sort_index()
    by_rule: dict[str, dict] = {}

    for start_year, end_year, test_start, test_end in _folds(pd.DatetimeIndex(features.index), config):
        train = features.loc[features.index < test_start]
        test = features.loc[(features.index >= test_start) & (features.index <= test_end)]
        if len(train) < 252 * 5 or len(test) <= config.horizon:
            continue

        baseline = _baseline_returns(test, config)
        baseline_median = float(baseline.median()) if len(baseline) else None
        baseline_win = float((baseline > 0).mean()) if len(baseline) else None
        rules = [_to_rule(r) for r in learn_market_state_hypotheses(train, target)]

        for rule in rules:
            returns = _trade_returns(test, rule, config)
            median_return = float(returns.median()) if len(returns) else None
            win_rate = float((returns > 0).mean()) if len(returns) else None
            median_excess = (
                float(median_return - baseline_median)
                if median_return is not None and baseline_median is not None else None
            )
            win_edge = (
                float(win_rate - baseline_win)
                if win_rate is not None and baseline_win is not None else None
            )
            row = by_rule.setdefault(rule.name, {
                "name": rule.name,
                "rationale": rule.rationale,
                "folds": [],
                "all_returns": [],
                "all_excess": [],
            })
            fold = {
                "start_year": start_year,
                "end_year": end_year,
                "test_start": str(test_start.date()),
                "test_end": str(test_end.date()),
                "n": int(len(returns)),
                "mean_return": float(returns.mean()) if len(returns) else None,
                "median_return": median_return,
                "win_rate": win_rate,
                "baseline_median_return": baseline_median,
                "baseline_win_rate": baseline_win,
                "median_excess_edge": median_excess,
                "win_probability_edge": win_edge,
                "compounded_return": float((1.0 + returns).prod() - 1.0) if len(returns) else None,
            }
            row["folds"].append(fold)
            row["all_returns"].extend(float(x) for x in returns.to_numpy())
            if baseline_median is not None:
                row["all_excess"].extend(float(x - baseline_median) for x in returns.to_numpy())

    rows = []
    for row in by_rule.values():
        returns = np.asarray(row.pop("all_returns"), dtype=float)
        excess = np.asarray(row.pop("all_excess"), dtype=float)
        trade_folds = [f for f in row["folds"] if f["n"] > 0]
        edge_positive_folds = [
            f for f in trade_folds
            if f["median_excess_edge"] is not None and f["median_excess_edge"] > 0
            and f["win_probability_edge"] is not None and f["win_probability_edge"] >= 0
        ]
        n = int(len(returns))
        fold_fraction = float(len(edge_positive_folds) / len(trade_folds)) if trade_folds else 0.0
        mean_return = float(np.mean(returns)) if n else None
        median_return = float(np.median(returns)) if n else None
        win_rate = float((returns > 0).mean()) if n else None
        mean_excess = float(np.mean(excess)) if len(excess) else None
        median_excess = float(np.median(excess)) if len(excess) else None
        excess_hit_rate = float((excess > 0).mean()) if len(excess) else None

        profitable = bool(
            n >= config.min_trades_total
            and len(trade_folds) >= config.min_folds_with_trades
            and fold_fraction >= config.min_positive_fold_fraction
            and mean_return is not None and mean_return > 0
            and median_return is not None and median_return > 0
            and win_rate is not None and win_rate > 0.50
            and mean_excess is not None and mean_excess > 0
            and median_excess is not None and median_excess > 0
            and excess_hit_rate is not None and excess_hit_rate > 0.50
        )
        row.update({
            "trades": n,
            "folds_with_trades": len(trade_folds),
            "positive_edge_folds": len(edge_positive_folds),
            "positive_edge_fold_fraction": fold_fraction,
            "mean_trade_return": mean_return,
            "median_trade_return": median_return,
            "win_rate": win_rate,
            "mean_excess_edge": mean_excess,
            "median_excess_edge": median_excess,
            "excess_hit_rate": excess_hit_rate,
            "compounded_trade_return": float(np.prod(1.0 + returns) - 1.0) if n else None,
            "profitable_walk_forward": profitable,
        })
        rows.append(row)

    rows.sort(
        key=lambda r: (
            r["profitable_walk_forward"],
            r["positive_edge_fold_fraction"],
            r["median_excess_edge"] if r["median_excess_edge"] is not None else -999.0,
        ),
        reverse=True,
    )
    return {
        "target": target.upper(),
        "config": asdict(config),
        "profitable_count": sum(1 for r in rows if r["profitable_walk_forward"]),
        "rows": rows,
    }
