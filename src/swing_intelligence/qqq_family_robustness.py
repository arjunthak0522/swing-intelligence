from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .autonomous_lab import HypothesisRule, RuleTerm, _forward_path_table
from .market_state_hypotheses import learn_market_state_hypotheses
from .walk_forward import _event_positions, _folds


@dataclass(frozen=True)
class QQQFamilyConfig:
    first_test_year: int = 2010
    fold_years: int = 2
    horizons: tuple[int, ...] = (20, 30, 40, 60)
    min_gaps: tuple[int, ...] = (20, 30, 40)
    cost_bps: tuple[float, ...] = (2.0, 5.0, 10.0)
    vix_cooling_quantiles: tuple[float, ...] = (0.50, 0.60, 0.70)
    min_total_trades: int = 20
    min_folds: int = 3
    min_positive_fold_fraction: float = 0.60
    min_excess_hit_rate: float = 0.50


def _q(frame: pd.DataFrame, feature: str, q: float) -> float | None:
    if feature not in frame:
        return None
    s = pd.to_numeric(frame[feature], errors="coerce").dropna()
    if len(s) < 100 or s.nunique() < 20:
        return None
    return float(s.quantile(q))


def _family_rule(train: pd.DataFrame, vix_q: float) -> HypothesisRule | None:
    base = None
    for state in learn_market_state_hypotheses(train, "QQQ"):
        if state.name == "qqq_rebound_with_semiconductor_confirmation":
            base = state
            break
    if base is None:
        return None
    vix_threshold = _q(train, "vix_cooling_5d", vix_q)
    if vix_threshold is None:
        return None
    terms = tuple(RuleTerm(t.feature, t.op, t.threshold) for t in base.terms)
    terms += (RuleTerm("vix_cooling_5d", ">=", vix_threshold),)
    return HypothesisRule(
        name=f"qqq_rebound_semis_vixcool_q{vix_q:.2f}",
        terms=terms,
        rationale=(
            "QQQ rebound with semiconductor confirmation while VIX is cooling; "
            "all thresholds relearned strictly from prior data."
        ),
    )


def _trade_returns(test: pd.DataFrame, rule: HypothesisRule, horizon: int, gap: int, cost_bps: float):
    paths = _forward_path_table(test, horizon)
    if paths.empty:
        return pd.DataFrame(columns=["return", "excess"])
    mask = rule.mask(test).reindex(paths.index).fillna(False)
    pos = _event_positions(mask, gap)
    if not pos:
        return pd.DataFrame(columns=["return", "excess"])
    all_returns = paths["forward_return"].astype(float) - cost_bps / 10000.0
    baseline_median = float(all_returns.median())
    dates = paths.index[pos]
    selected = all_returns.loc[dates]
    return pd.DataFrame({"return": selected, "excess": selected - baseline_median}, index=dates)


def _max_drawdown(returns: np.ndarray) -> float | None:
    if not len(returns):
        return None
    equity = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(equity)
    return float(np.min(equity / peak - 1.0))


def _max_loss_streak(returns: np.ndarray) -> int:
    best = cur = 0
    for value in returns:
        if value < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return int(best)


def run_qqq_family_robustness(features: pd.DataFrame, config: QQQFamilyConfig = QQQFamilyConfig()) -> dict:
    """Predeclared Phase 3B stress test of the QQQ rebound/semiconductor/VIX-cooling family.

    No variant is chosen from the test fold. Every fold relearns the base-state and
    VIX-cooling thresholds using only data that existed before that fold. The whole
    neighborhood is reported so one lucky threshold cannot masquerade as robustness.
    """
    features = features.sort_index()
    variants: dict[str, dict] = {}

    for start_year, end_year, test_start, test_end in _folds(pd.DatetimeIndex(features.index), type("Cfg", (), {
        "first_test_year": config.first_test_year,
        "fold_years": config.fold_years,
    })()):
        train = features.loc[features.index < test_start]
        test = features.loc[(features.index >= test_start) & (features.index <= test_end)]
        if len(train) < 252 * 5 or len(test) < 100:
            continue

        for vix_q in config.vix_cooling_quantiles:
            rule = _family_rule(train, vix_q)
            if rule is None:
                continue
            for horizon in config.horizons:
                for gap in config.min_gaps:
                    for cost in config.cost_bps:
                        key = f"q{vix_q:.2f}_h{horizon}_g{gap}_c{cost:.0f}"
                        trades = _trade_returns(test, rule, horizon, gap, cost)
                        row = variants.setdefault(key, {
                            "variant": key,
                            "vix_quantile": vix_q,
                            "horizon": horizon,
                            "gap": gap,
                            "cost_bps": cost,
                            "folds": [],
                            "returns": [],
                            "excess": [],
                        })
                        fold = {
                            "start_year": start_year,
                            "end_year": end_year,
                            "n": int(len(trades)),
                            "median_return": float(trades["return"].median()) if len(trades) else None,
                            "median_excess_edge": float(trades["excess"].median()) if len(trades) else None,
                            "win_rate": float((trades["return"] > 0).mean()) if len(trades) else None,
                            "excess_hit_rate": float((trades["excess"] > 0).mean()) if len(trades) else None,
                        }
                        row["folds"].append(fold)
                        row["returns"].extend(float(x) for x in trades["return"].to_numpy())
                        row["excess"].extend(float(x) for x in trades["excess"].to_numpy())

    rows = []
    for row in variants.values():
        returns = np.asarray(row.pop("returns"), dtype=float)
        excess = np.asarray(row.pop("excess"), dtype=float)
        trade_folds = [f for f in row["folds"] if f["n"] > 0]
        positive_folds = [f for f in trade_folds if f["median_excess_edge"] is not None and f["median_excess_edge"] > 0]
        fold_fraction = len(positive_folds) / len(trade_folds) if trade_folds else 0.0
        median_return = float(np.median(returns)) if len(returns) else None
        median_excess = float(np.median(excess)) if len(excess) else None
        excess_hit = float((excess > 0).mean()) if len(excess) else None
        win_rate = float((returns > 0).mean()) if len(returns) else None
        passes = bool(
            len(returns) >= config.min_total_trades
            and len(trade_folds) >= config.min_folds
            and fold_fraction >= config.min_positive_fold_fraction
            and median_return is not None and median_return > 0
            and median_excess is not None and median_excess > 0
            and excess_hit is not None and excess_hit > config.min_excess_hit_rate
            and win_rate is not None and win_rate > 0.50
        )
        row.update({
            "trades": int(len(returns)),
            "folds_with_trades": len(trade_folds),
            "positive_edge_folds": len(positive_folds),
            "positive_edge_fold_fraction": float(fold_fraction),
            "mean_trade_return": float(np.mean(returns)) if len(returns) else None,
            "median_trade_return": median_return,
            "win_rate": win_rate,
            "mean_excess_edge": float(np.mean(excess)) if len(excess) else None,
            "median_excess_edge": median_excess,
            "excess_hit_rate": excess_hit,
            "worst_trade": float(np.min(returns)) if len(returns) else None,
            "max_trade_sequence_drawdown": _max_drawdown(returns),
            "max_consecutive_losses": _max_loss_streak(returns),
            "passes_variant_gate": passes,
        })
        rows.append(row)

    rows.sort(key=lambda r: (
        r["passes_variant_gate"],
        r["positive_edge_fold_fraction"],
        r["median_excess_edge"] if r["median_excess_edge"] is not None else -999.0,
    ), reverse=True)

    valid = [r for r in rows if r["trades"] >= config.min_total_trades]
    pass_count = sum(1 for r in valid if r["passes_variant_gate"])
    pass_fraction = pass_count / len(valid) if valid else 0.0

    # Family-level robustness intentionally demands broad neighborhood support.
    family_robust = bool(len(valid) >= 12 and pass_fraction >= 0.50)
    return {
        "target": "QQQ",
        "config": asdict(config),
        "valid_variant_count": len(valid),
        "passing_variant_count": pass_count,
        "passing_variant_fraction": float(pass_fraction),
        "family_robust": family_robust,
        "rows": rows,
    }
