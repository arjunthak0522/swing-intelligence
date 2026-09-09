from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .autonomous_lab import HypothesisRule, RuleTerm, _forward_path_table
from .market_state_hypotheses import learn_market_state_hypotheses
from .walk_forward import WalkForwardConfig, _event_positions, _folds


BASE_FAMILIES = {
    "state__pullback_with_rebound",
    "state__volatility_shock_cooling",
    "state__price_weakness_with_vol_cooling",
    "state__spy_rebound_with_breadth_confirmation",
    "state__qqq_rebound_with_semiconductor_confirmation",
    "state__qqq_pullback_semiconductor_resilience",
}

# Predeclared contextual conditioners. Numeric cutoffs are learned from inner-fit data only.
CONDITIONERS = (
    ("vix_cooling_5d", ">=", 0.60),
    ("vix_cooling_5d", ">=", 0.75),
    ("trend_repair_5d", ">=", 0.60),
    ("trend_repair_5d", ">=", 0.75),
    ("vol_expansion_ratio", "<=", 0.40),
    ("drawdown_60d", "<=", 0.30),
    ("rsp_spy_ret_5d", ">=", 0.60),
    ("rsp_spy_ret_20d", ">=", 0.60),
    ("iwm_spy_ret_5d", ">=", 0.60),
    ("iwm_spy_ret_20d", ">=", 0.60),
    ("smh_qqq_ret_5d", ">=", 0.60),
    ("smh_qqq_ret_20d", ">=", 0.60),
)


@dataclass(frozen=True)
class ConditionalSearchConfig:
    walk_forward: WalkForwardConfig = WalkForwardConfig()
    inner_validation_years: int = 2
    min_inner_trades: int = 3
    max_selected_per_fold: int = 4
    min_outer_trades_total: int = 20
    min_outer_folds: int = 3
    min_positive_edge_fold_fraction: float = 0.60


def _to_rule(state_rule) -> HypothesisRule:
    return HypothesisRule(
        name=f"state__{state_rule.name}",
        terms=tuple(RuleTerm(t.feature, t.op, t.threshold) for t in state_rule.terms),
        rationale=f"[{state_rule.family}] {state_rule.rationale}",
    )


def _threshold(frame: pd.DataFrame, feature: str, q: float) -> float | None:
    if feature not in frame:
        return None
    s = pd.to_numeric(frame[feature], errors="coerce").dropna()
    if len(s) < 100 or s.nunique() < 20:
        return None
    return float(s.quantile(q))


def _candidate_rules(inner_fit: pd.DataFrame, target: str) -> list[tuple[str, HypothesisRule]]:
    bases = [_to_rule(x) for x in learn_market_state_hypotheses(inner_fit, target)]
    bases = [b for b in bases if b.name in BASE_FAMILIES]
    out: list[tuple[str, HypothesisRule]] = []
    for base in bases:
        for feature, op, q in CONDITIONERS:
            threshold = _threshold(inner_fit, feature, q)
            if threshold is None:
                continue
            template_id = f"{base.name}__{feature}_{op}_q{q:.2f}"
            out.append((template_id, HypothesisRule(
                name=template_id,
                terms=base.terms + (RuleTerm(feature, op, threshold),),
                rationale=f"{base.rationale} + context {feature} {op} train q{q:.2f}.",
            )))
    return out


def _trade_table(test: pd.DataFrame, rule: HypothesisRule, cfg: WalkForwardConfig) -> pd.DataFrame:
    paths = _forward_path_table(test, cfg.horizon)
    if paths.empty:
        return pd.DataFrame(columns=["return", "excess"])
    mask = rule.mask(test).reindex(paths.index).fillna(False)
    pos = _event_positions(mask, cfg.min_gap)
    if not pos:
        return pd.DataFrame(columns=["return", "excess"])
    baseline = paths["forward_return"].astype(float) - cfg.transaction_cost_bps_round_trip / 10000.0
    baseline_median = float(baseline.median())
    dates = paths.index[pos]
    ret = baseline.loc[dates]
    return pd.DataFrame({"return": ret, "excess": ret - baseline_median}, index=dates)


def _inner_score(inner_val: pd.DataFrame, rule: HypothesisRule, cfg: ConditionalSearchConfig) -> dict | None:
    trades = _trade_table(inner_val, rule, cfg.walk_forward)
    if len(trades) < cfg.min_inner_trades:
        return None
    median_excess = float(trades["excess"].median())
    excess_hit = float((trades["excess"] > 0).mean())
    win_rate = float((trades["return"] > 0).mean())
    if median_excess <= 0 or excess_hit <= 0.50:
        return None
    return {
        "n": int(len(trades)),
        "median_excess": median_excess,
        "excess_hit_rate": excess_hit,
        "win_rate": win_rate,
        "score": median_excess * (0.5 + excess_hit),
    }


def _max_drawdown_from_trade_returns(returns: np.ndarray) -> float | None:
    if len(returns) == 0:
        return None
    equity = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1.0
    return float(dd.min())


def _max_consecutive_losses(returns: np.ndarray) -> int:
    best = cur = 0
    for x in returns:
        if x < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return int(best)


def run_conditional_walk_forward(
    features: pd.DataFrame,
    target: str,
    config: ConditionalSearchConfig = ConditionalSearchConfig(),
) -> dict:
    """Nested expanding-window search for conditional SPY/QQQ strategies.

    Outer folds are never used to choose a combination. Within each outer fold,
    candidate thresholds are learned on inner-fit data, combinations are selected
    using a trailing inner-validation segment, and only those frozen rules are then
    evaluated on the unseen outer fold.
    """
    features = features.sort_index()
    by_template: dict[str, dict] = {}
    evaluated_test_days = 0

    for start_year, end_year, test_start, test_end in _folds(pd.DatetimeIndex(features.index), config.walk_forward):
        prior = features.loc[features.index < test_start]
        test = features.loc[(features.index >= test_start) & (features.index <= test_end)]
        if len(prior) < 252 * 7 or len(test) <= config.walk_forward.horizon:
            continue
        inner_cut = test_start - pd.DateOffset(years=config.inner_validation_years)
        inner_fit = prior.loc[prior.index < inner_cut]
        inner_val = prior.loc[prior.index >= inner_cut]
        if len(inner_fit) < 252 * 5 or len(inner_val) <= config.walk_forward.horizon:
            continue

        scored = []
        for template_id, rule in _candidate_rules(inner_fit, target):
            score = _inner_score(inner_val, rule, config)
            if score is not None:
                scored.append((score["score"], template_id, rule, score))
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = scored[: config.max_selected_per_fold]
        evaluated_test_days += len(test)

        for _, template_id, rule, inner in selected:
            trades = _trade_table(test, rule, config.walk_forward)
            row = by_template.setdefault(template_id, {
                "name": template_id,
                "rationale": rule.rationale,
                "folds": [],
                "returns": [],
                "excess": [],
            })
            fold_payload = {
                "start_year": start_year,
                "end_year": end_year,
                "selected_by_inner_validation": True,
                "inner_validation": inner,
                "n": int(len(trades)),
                "median_return": float(trades["return"].median()) if len(trades) else None,
                "median_excess_edge": float(trades["excess"].median()) if len(trades) else None,
                "win_rate": float((trades["return"] > 0).mean()) if len(trades) else None,
                "excess_hit_rate": float((trades["excess"] > 0).mean()) if len(trades) else None,
            }
            row["folds"].append(fold_payload)
            row["returns"].extend(float(x) for x in trades["return"].to_numpy())
            row["excess"].extend(float(x) for x in trades["excess"].to_numpy())

    rows = []
    for row in by_template.values():
        returns = np.asarray(row.pop("returns"), dtype=float)
        excess = np.asarray(row.pop("excess"), dtype=float)
        trade_folds = [f for f in row["folds"] if f["n"] > 0]
        positive_edge_folds = [
            f for f in trade_folds
            if f["median_excess_edge"] is not None and f["median_excess_edge"] > 0
            and f["excess_hit_rate"] is not None and f["excess_hit_rate"] > 0.50
        ]
        n = len(returns)
        fold_fraction = len(positive_edge_folds) / len(trade_folds) if trade_folds else 0.0
        median_excess = float(np.median(excess)) if len(excess) else None
        excess_hit = float((excess > 0).mean()) if len(excess) else None
        median_return = float(np.median(returns)) if n else None
        win_rate = float((returns > 0).mean()) if n else None
        candidate_strategy = bool(
            n >= config.min_outer_trades_total
            and len(trade_folds) >= config.min_outer_folds
            and fold_fraction >= config.min_positive_edge_fold_fraction
            and median_excess is not None and median_excess > 0
            and excess_hit is not None and excess_hit > 0.50
            and median_return is not None and median_return > 0
            and win_rate is not None and win_rate > 0.50
        )
        exposure = min(1.0, (n * config.walk_forward.horizon) / evaluated_test_days) if evaluated_test_days else 0.0
        ann_while_invested = None
        if n and np.all(returns > -1):
            geometric_trade = float(np.prod(1.0 + returns) ** (1.0 / n) - 1.0)
            ann_while_invested = float((1.0 + geometric_trade) ** (252.0 / config.walk_forward.horizon) - 1.0)
        row.update({
            "trades": int(n),
            "folds_with_trades": len(trade_folds),
            "positive_edge_folds": len(positive_edge_folds),
            "positive_edge_fold_fraction": float(fold_fraction),
            "mean_trade_return": float(np.mean(returns)) if n else None,
            "median_trade_return": median_return,
            "win_rate": win_rate,
            "mean_excess_edge": float(np.mean(excess)) if len(excess) else None,
            "median_excess_edge": median_excess,
            "excess_hit_rate": excess_hit,
            "worst_trade": float(np.min(returns)) if n else None,
            "max_trade_sequence_drawdown": _max_drawdown_from_trade_returns(returns),
            "max_consecutive_losses": _max_consecutive_losses(returns),
            "approx_exposure_fraction": float(exposure),
            "annualized_return_while_invested": ann_while_invested,
            "compounded_trade_return": float(np.prod(1.0 + returns) - 1.0) if n else None,
            "candidate_strategy": candidate_strategy,
        })
        rows.append(row)

    rows.sort(key=lambda r: (
        r["candidate_strategy"],
        r["positive_edge_fold_fraction"],
        r["median_excess_edge"] if r["median_excess_edge"] is not None else -999.0,
    ), reverse=True)
    return {
        "target": target.upper(),
        "config": asdict(config),
        "candidate_strategy_count": sum(1 for r in rows if r["candidate_strategy"]),
        "rows": rows,
    }
