from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .autonomous_lab import HypothesisRule, RuleTerm, _forward_path_table
from .market_state_hypotheses import learn_market_state_hypotheses
from .walk_forward import _event_positions, _folds


CRISIS_WINDOWS = {
    "gfc_2008_2009": (pd.Timestamp("2008-01-01"), pd.Timestamp("2009-12-31")),
    "covid_2020": (pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-31")),
    "bear_2022": (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31")),
}


@dataclass(frozen=True)
class QQQFamilyConfig:
    first_test_year: int = 2008
    fold_years: int = 2
    horizons: tuple[int, ...] = (20, 30, 40, 60)
    min_gaps: tuple[int, ...] = (20, 30, 40)
    cost_bps: tuple[float, ...] = (2.0, 5.0, 10.0)
    vix_cooling_quantiles: tuple[float, ...] = (0.50, 0.60, 0.70)
    min_total_trades: int = 20
    min_folds: int = 3
    min_positive_fold_fraction: float = 0.60
    min_excess_hit_rate: float = 0.50
    random_iterations: int = 100
    min_random_percentile: float = 0.90
    min_leave_crisis_trades: int = 15


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
        return pd.DataFrame(columns=["return", "excess"]), paths
    mask = rule.mask(test).reindex(paths.index).fillna(False)
    pos = _event_positions(mask, gap)
    all_returns = paths["forward_return"].astype(float) - cost_bps / 10000.0
    if not pos:
        return pd.DataFrame(columns=["return", "excess"]), paths
    baseline_median = float(all_returns.median())
    dates = paths.index[pos]
    selected = all_returns.loc[dates]
    return pd.DataFrame({"return": selected, "excess": selected - baseline_median}, index=dates), paths


def _sample_spaced_positions(length: int, n: int, gap: int, rng: np.random.Generator) -> list[int]:
    if n <= 0 or length <= 0:
        return []
    order = rng.permutation(length)
    chosen: list[int] = []
    for pos in order:
        if all(abs(int(pos) - existing) >= gap for existing in chosen):
            chosen.append(int(pos))
            if len(chosen) >= n:
                break
    return sorted(chosen)


def _matched_random_percentile(
    paths: pd.DataFrame,
    observed_median_excess: float | None,
    n: int,
    gap: int,
    cost_bps: float,
    iterations: int,
    seed: int,
) -> float | None:
    if paths.empty or observed_median_excess is None or n <= 0 or iterations <= 0:
        return None
    all_returns = paths["forward_return"].astype(float) - cost_bps / 10000.0
    baseline_median = float(all_returns.median())
    rng = np.random.default_rng(seed)
    random_edges = []
    for _ in range(iterations):
        pos = _sample_spaced_positions(len(paths), n, gap, rng)
        if len(pos) < n:
            continue
        sampled = all_returns.iloc[pos]
        random_edges.append(float(sampled.median() - baseline_median))
    if not random_edges:
        return None
    return float(np.mean(np.asarray(random_edges) <= observed_median_excess))


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


def _leave_crisis_out(dates: pd.DatetimeIndex, returns: np.ndarray, excess: np.ndarray, config: QQQFamilyConfig) -> dict:
    out = {}
    for name, (start, end) in CRISIS_WINDOWS.items():
        keep = ~((dates >= start) & (dates <= end))
        kept_returns = returns[keep]
        kept_excess = excess[keep]
        n = len(kept_returns)
        med_excess = float(np.median(kept_excess)) if n else None
        excess_hit = float((kept_excess > 0).mean()) if n else None
        out[name] = {
            "trades": int(n),
            "median_return": float(np.median(kept_returns)) if n else None,
            "median_excess_edge": med_excess,
            "excess_hit_rate": excess_hit,
            "passes": bool(
                n >= config.min_leave_crisis_trades
                and med_excess is not None and med_excess > 0
                and excess_hit is not None and excess_hit > 0.50
            ),
        }
    return out


def run_qqq_family_robustness(features: pd.DataFrame, config: QQQFamilyConfig = QQQFamilyConfig()) -> dict:
    """Predeclared Phase 3B stress test of the QQQ rebound/semiconductor/VIX-cooling family.

    No variant is chosen from the test fold. Every fold relearns thresholds from prior data.
    The full neighborhood is tested against matched random entries and leave-crisis-out checks.
    """
    features = features.sort_index()
    variants: dict[str, dict] = {}

    fold_cfg = type("Cfg", (), {"first_test_year": config.first_test_year, "fold_years": config.fold_years})()
    for start_year, end_year, test_start, test_end in _folds(pd.DatetimeIndex(features.index), fold_cfg):
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
                        trades, paths = _trade_returns(test, rule, horizon, gap, cost)
                        med_excess = float(trades["excess"].median()) if len(trades) else None
                        seed = int(start_year * 100000 + horizon * 1000 + gap * 10 + round(cost) + round(vix_q * 100))
                        random_pct = _matched_random_percentile(
                            paths, med_excess, len(trades), gap, cost, config.random_iterations, seed
                        )
                        row = variants.setdefault(key, {
                            "variant": key,
                            "vix_quantile": vix_q,
                            "horizon": horizon,
                            "gap": gap,
                            "cost_bps": cost,
                            "folds": [],
                            "returns": [],
                            "excess": [],
                            "dates": [],
                        })
                        fold = {
                            "start_year": start_year,
                            "end_year": end_year,
                            "n": int(len(trades)),
                            "median_return": float(trades["return"].median()) if len(trades) else None,
                            "median_excess_edge": med_excess,
                            "win_rate": float((trades["return"] > 0).mean()) if len(trades) else None,
                            "excess_hit_rate": float((trades["excess"] > 0).mean()) if len(trades) else None,
                            "matched_random_percentile": random_pct,
                        }
                        row["folds"].append(fold)
                        row["returns"].extend(float(x) for x in trades["return"].to_numpy())
                        row["excess"].extend(float(x) for x in trades["excess"].to_numpy())
                        row["dates"].extend(str(pd.Timestamp(x).date()) for x in trades.index)

    rows = []
    for row in variants.values():
        returns = np.asarray(row.pop("returns"), dtype=float)
        excess = np.asarray(row.pop("excess"), dtype=float)
        dates = pd.DatetimeIndex(pd.to_datetime(row.pop("dates")))
        trade_folds = [f for f in row["folds"] if f["n"] > 0]
        positive_folds = [f for f in trade_folds if f["median_excess_edge"] is not None and f["median_excess_edge"] > 0]
        random_tested = [f for f in trade_folds if f["matched_random_percentile"] is not None]
        random_strong = [f for f in random_tested if f["matched_random_percentile"] >= config.min_random_percentile]
        fold_fraction = len(positive_folds) / len(trade_folds) if trade_folds else 0.0
        random_fraction = len(random_strong) / len(random_tested) if random_tested else 0.0
        median_return = float(np.median(returns)) if len(returns) else None
        median_excess = float(np.median(excess)) if len(excess) else None
        excess_hit = float((excess > 0).mean()) if len(excess) else None
        win_rate = float((returns > 0).mean()) if len(returns) else None
        leave_crisis = _leave_crisis_out(dates, returns, excess, config)
        crisis_pass_fraction = float(np.mean([x["passes"] for x in leave_crisis.values()])) if leave_crisis else 0.0

        passes = bool(
            len(returns) >= config.min_total_trades
            and len(trade_folds) >= config.min_folds
            and fold_fraction >= config.min_positive_fold_fraction
            and median_return is not None and median_return > 0
            and median_excess is not None and median_excess > 0
            and excess_hit is not None and excess_hit > config.min_excess_hit_rate
            and win_rate is not None and win_rate > 0.50
        )
        passes_random = bool(random_tested and random_fraction >= 0.50)
        passes_crisis = bool(leave_crisis and crisis_pass_fraction >= 2 / 3)
        passes_full_stress = bool(passes and passes_random and passes_crisis)

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
            "matched_random_strong_fold_fraction": float(random_fraction),
            "leave_crisis_out": leave_crisis,
            "leave_crisis_pass_fraction": crisis_pass_fraction,
            "passes_variant_gate": passes,
            "passes_matched_random": passes_random,
            "passes_leave_crisis_out": passes_crisis,
            "passes_full_stress": passes_full_stress,
        })
        rows.append(row)

    rows.sort(key=lambda r: (
        r["passes_full_stress"],
        r["passes_variant_gate"],
        r["positive_edge_fold_fraction"],
        r["median_excess_edge"] if r["median_excess_edge"] is not None else -999.0,
    ), reverse=True)

    valid = [r for r in rows if r["trades"] >= config.min_total_trades]
    pass_count = sum(1 for r in valid if r["passes_variant_gate"])
    stress_pass_count = sum(1 for r in valid if r["passes_full_stress"])
    pass_fraction = pass_count / len(valid) if valid else 0.0
    stress_fraction = stress_pass_count / len(valid) if valid else 0.0

    family_robust = bool(len(valid) >= 12 and pass_fraction >= 0.50)
    family_full_stress_robust = bool(len(valid) >= 12 and stress_fraction >= 0.50)
    return {
        "target": "QQQ",
        "config": asdict(config),
        "valid_variant_count": len(valid),
        "passing_variant_count": pass_count,
        "passing_variant_fraction": float(pass_fraction),
        "full_stress_passing_variant_count": stress_pass_count,
        "full_stress_passing_variant_fraction": float(stress_fraction),
        "family_robust": family_robust,
        "family_full_stress_robust": family_full_stress_robust,
        "rows": rows,
    }
