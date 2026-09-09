from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .autonomous_lab import _forward_path_table
from .opportunity_score import calibrated_opportunity_score
from .walk_forward import _event_positions, _folds, _matched_random_percentile


@dataclass(frozen=True)
class OpportunityStressConfig:
    first_test_year: int = 2008
    fold_years: int = 2
    trigger_levels: tuple[int, ...] = (65, 70, 75)
    horizons: tuple[int, ...] = (20, 30, 40, 60)
    min_gaps: tuple[int, ...] = (20, 30, 40)
    cost_bps: tuple[float, ...] = (5.0, 10.0, 20.0)
    min_trades_total: int = 25
    min_folds_with_trades: int = 4
    min_positive_edge_fold_fraction: float = 0.60
    random_iterations: int = 100
    min_random_percentile: float = 0.80
    min_random_superiority_fold_fraction: float = 0.60
    min_leave_crisis_trades: int = 20


CRISIS_WINDOWS = {
    "gfc_2008_2009": (2008, 2009),
    "covid_2020": (2020, 2020),
    "bear_2022": (2022, 2022),
}


def _trades(test: pd.DataFrame, score: pd.Series, threshold: int, horizon: int, gap: int, cost: float) -> pd.DataFrame:
    paths = _forward_path_table(test, horizon)
    if paths.empty:
        return pd.DataFrame(columns=["return", "excess"])
    mask = (score >= threshold).reindex(paths.index).fillna(False)
    pos = _event_positions(mask, gap)
    if not pos:
        return pd.DataFrame(columns=["return", "excess"])
    baseline = paths["forward_return"].astype(float) - cost / 10000.0
    baseline_median = float(baseline.median())
    dates = paths.index[pos]
    ret = baseline.loc[dates]
    return pd.DataFrame({"return": ret, "excess": ret - baseline_median}, index=dates)


def stress_grid(config: OpportunityStressConfig = OpportunityStressConfig()) -> list[tuple[int, int, int, float]]:
    return [(t, h, g, c) for t in config.trigger_levels for h in config.horizons for g in config.min_gaps for c in config.cost_bps]


def _leave_crisis_checks(trades: pd.DataFrame, min_trades: int) -> dict:
    out = {}
    for name, (start_year, end_year) in CRISIS_WINDOWS.items():
        kept = trades.loc[~trades.index.year.astype(int).astype(str).isin([])].copy()
        keep_mask = ~((trades.index.year >= start_year) & (trades.index.year <= end_year))
        kept = trades.loc[keep_mask]
        n = len(kept)
        out[name] = {
            "n": int(n),
            "median_return": float(kept["return"].median()) if n else None,
            "median_excess_edge": float(kept["excess"].median()) if n else None,
            "win_rate": float((kept["return"] > 0).mean()) if n else None,
            "excess_hit_rate": float((kept["excess"] > 0).mean()) if n else None,
            "passes": bool(
                n >= min_trades
                and float(kept["return"].median()) > 0
                and float(kept["excess"].median()) > 0
                and float((kept["return"] > 0).mean()) > 0.50
                and float((kept["excess"] > 0).mean()) > 0.50
            ) if n else False,
        }
    return out


def run_opportunity_score_stress(features: pd.DataFrame, target: str, config: OpportunityStressConfig = OpportunityStressConfig()) -> dict:
    features = features.sort_index()
    variants = {key: {"trigger": key[0], "horizon": key[1], "gap": key[2], "cost_bps": key[3], "folds": [], "trades": []} for key in stress_grid(config)}

    fold_cfg = type("FoldCfg", (), {"first_test_year": config.first_test_year, "fold_years": config.fold_years})()
    for start_year, end_year, test_start, test_end in _folds(pd.DatetimeIndex(features.index), fold_cfg):
        train = features.loc[features.index < test_start]
        test = features.loc[(features.index >= test_start) & (features.index <= test_end)]
        if len(train) < 252 * 5 or len(test) < 100:
            continue
        scored = calibrated_opportunity_score(train, test, target)["opportunity_score"]
        path_cache = {h: _forward_path_table(test, h) for h in config.horizons}
        baseline_cache = {h: path_cache[h]["forward_return"].astype(float) for h in config.horizons if not path_cache[h].empty}

        for trigger, horizon, gap, cost in stress_grid(config):
            key = (trigger, horizon, gap, cost)
            trades = _trades(test, scored, trigger, horizon, gap, cost)
            baseline = baseline_cache.get(horizon, pd.Series(dtype=float)) - cost / 10000.0
            med = float(trades["return"].median()) if len(trades) else None
            seed = start_year * 2017 + trigger * 41 + horizon * 13 + gap * 7 + int(cost * 3) + (1 if target.upper() == "QQQ" else 0)
            random_pct = _matched_random_percentile(baseline, len(trades), med, gap, config.random_iterations, seed)
            fold = {
                "start_year": start_year, "end_year": end_year, "n": int(len(trades)),
                "median_return": med,
                "median_excess_edge": float(trades["excess"].median()) if len(trades) else None,
                "win_rate": float((trades["return"] > 0).mean()) if len(trades) else None,
                "excess_hit_rate": float((trades["excess"] > 0).mean()) if len(trades) else None,
                "matched_random_percentile": random_pct,
            }
            variants[key]["folds"].append(fold)
            if len(trades):
                tagged = trades.copy()
                tagged["fold_start_year"] = start_year
                variants[key]["trades"].append(tagged)

    rows = []
    for row in variants.values():
        pieces = row.pop("trades")
        trades = pd.concat(pieces).sort_index() if pieces else pd.DataFrame(columns=["return", "excess", "fold_start_year"])
        trade_folds = [f for f in row["folds"] if f["n"] > 0]
        positive = [f for f in trade_folds if f["median_excess_edge"] is not None and f["median_excess_edge"] > 0]
        random_tested = [f for f in trade_folds if f["matched_random_percentile"] is not None]
        random_good = [f for f in random_tested if f["matched_random_percentile"] >= config.min_random_percentile]
        fold_fraction = len(positive) / len(trade_folds) if trade_folds else 0.0
        random_fraction = len(random_good) / len(random_tested) if random_tested else 0.0
        median_random = float(np.median([f["matched_random_percentile"] for f in random_tested])) if random_tested else None
        n = len(trades)
        base_pass = bool(
            n >= config.min_trades_total
            and len(trade_folds) >= config.min_folds_with_trades
            and fold_fraction >= config.min_positive_edge_fold_fraction
            and len(random_tested) >= config.min_folds_with_trades
            and random_fraction >= config.min_random_superiority_fold_fraction
            and median_random is not None and median_random >= config.min_random_percentile
            and float(trades["return"].median()) > 0
            and float(trades["excess"].median()) > 0
            and float((trades["return"] > 0).mean()) > 0.50
            and float((trades["excess"] > 0).mean()) > 0.50
        ) if n else False
        crisis = _leave_crisis_checks(trades, config.min_leave_crisis_trades)
        crisis_pass = all(x["passes"] for x in crisis.values())
        row.update({
            "trades": int(n), "folds_with_trades": len(trade_folds),
            "positive_edge_fold_fraction": float(fold_fraction),
            "matched_random_superiority_fold_fraction": float(random_fraction),
            "median_matched_random_percentile": median_random,
            "median_trade_return": float(trades["return"].median()) if n else None,
            "median_excess_edge": float(trades["excess"].median()) if n else None,
            "win_rate": float((trades["return"] > 0).mean()) if n else None,
            "excess_hit_rate": float((trades["excess"] > 0).mean()) if n else None,
            "base_pass": base_pass,
            "leave_crisis": crisis,
            "full_stress_pass": bool(base_pass and crisis_pass),
        })
        rows.append(row)

    valid = [r for r in rows if r["trades"] >= config.min_trades_total]
    base_count = sum(1 for r in valid if r["base_pass"])
    full_count = sum(1 for r in valid if r["full_stress_pass"])
    rows.sort(key=lambda r: (r["full_stress_pass"], r["base_pass"], r["matched_random_superiority_fold_fraction"], r["median_excess_edge"] or -999.0), reverse=True)
    return {
        "target": target.upper(), "config": asdict(config),
        "valid_variant_count": len(valid),
        "base_passing_variant_count": base_count,
        "base_passing_variant_fraction": base_count / len(valid) if valid else 0.0,
        "full_stress_passing_variant_count": full_count,
        "full_stress_passing_variant_fraction": full_count / len(valid) if valid else 0.0,
        "family_robust": bool(len(valid) >= 12 and base_count / len(valid) >= 0.50) if valid else False,
        "family_full_stress_robust": bool(len(valid) >= 12 and full_count / len(valid) >= 0.50) if valid else False,
        "rows": rows,
    }
