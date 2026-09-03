from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import pandas as pd

from .backtest import _metrics, benchmark_buy_hold
from .evidence import EvidenceConfig, evidence_snapshot, best_asset_evidence
from .outcomes import forward_path_stats
from .research import ResearchSplit, add_research_features, split_periods, run_signal_tournament
from .robustness import block_bootstrap_edge, benjamini_hochberg
from .stability import StabilityGate, evaluate_parameter_neighborhood, standard_parameter_neighborhoods, summarize_parameter_stability
from .tournament import default_candidate_signals


def _result_map(results: list[dict], horizon: int = 10) -> dict[str, dict]:
    out = {}
    for r in results:
        h = r.get("horizons", {}).get(horizon)
        if h:
            out[r["name"]] = h
    return out


def development_candidate_table(features: pd.DataFrame, *, split: ResearchSplit = ResearchSplit(), horizon: int = 10,
                                min_n: int = 30) -> pd.DataFrame:
    """Freeze candidates using train + validation only. Holdout is excluded from promotion."""
    periods = split_periods(features, split)
    train = _result_map(run_signal_tournament(periods["train"], min_n=min_n), horizon)
    val = _result_map(run_signal_tournament(periods["validation"], min_n=min_n), horizon)
    rows = []
    for name in sorted(set(train) & set(val)):
        t, v = train[name], val[name]
        qualifies = (
            v["n"] >= min_n
            and v["median_excess_edge"] > 0
            and v["win_probability_edge"] > 0
        )
        rows.append({
            "signal": name,
            "train_n": t["n"],
            "train_edge": t["median_excess_edge"],
            "train_win_edge": t["win_probability_edge"],
            "validation_n": v["n"],
            "validation_edge": v["median_excess_edge"],
            "validation_win_edge": v["win_probability_edge"],
            "development_candidate": bool(qualifies),
        })
    return pd.DataFrame(rows).sort_values(["development_candidate", "validation_edge"], ascending=[False, False]).reset_index(drop=True)


def _bootstrap_period(frame: pd.DataFrame, signal_name: str, *, horizon: int, iterations: int) -> dict:
    sig = {s.name: s for s in default_candidate_signals(frame)}[signal_name]
    entries = frame.index[sig.mask.reindex(frame.index).fillna(False)]
    cond = forward_path_stats(frame, entries, horizon)
    base = forward_path_stats(frame, frame.index, horizon)
    if len(cond) < 20 or len(base) < 100:
        return {"signal": signal_name, "n": len(cond), "ci_low": np.nan, "ci_high": np.nan, "p_value": np.nan}
    boot = block_bootstrap_edge(cond["forward_return"], base["forward_return"], iterations=iterations, block=5, seed=7)
    return {
        "signal": signal_name,
        "n": len(cond),
        "ci_low": boot.ci_low,
        "ci_high": boot.ci_high,
        "p_value": boot.p_value_one_sided,
    }


def development_promotion_table(features: pd.DataFrame, *, split: ResearchSplit = ResearchSplit(), horizon: int = 10,
                                min_n: int = 30, bootstrap_iterations: int = 2000) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply stability + bootstrap/FDR using validation only after predeclared development screening."""
    periods = split_periods(features, split)
    candidates = development_candidate_table(features, split=split, horizon=horizon, min_n=min_n)
    candidate_names = candidates.loc[candidates["development_candidate"], "signal"].tolist()
    neighborhoods = standard_parameter_neighborhoods(periods["validation"])
    stability_rows = []
    boot_rows = []
    for name in candidate_names:
        variants = neighborhoods.get(name)
        if variants:
            table = evaluate_parameter_neighborhood(
                periods["validation"], variants,
                gate=StabilityGate(horizon=horizon, min_n=max(15, min_n // 2)),
            )
            summary = summarize_parameter_stability(table, gate=StabilityGate(horizon=horizon, min_n=max(15, min_n // 2)))
            stability_rows.append({"signal": name, **summary})
        else:
            stability_rows.append({"signal": name, "stable": False, "variants": 0, "eligible_variants": 0,
                                   "positive_fraction": 0.0, "edge_median": np.nan, "edge_min": np.nan,
                                   "edge_max": np.nan, "edge_cv": np.nan})
        boot_rows.append(_bootstrap_period(periods["validation"], name, horizon=horizon, iterations=bootstrap_iterations))

    stability = pd.DataFrame(stability_rows)
    boots = pd.DataFrame(boot_rows)
    if not boots.empty:
        finite = boots.dropna(subset=["p_value"])
        fdr = benjamini_hochberg(dict(zip(finite["signal"], finite["p_value"])), alpha=0.05)
        boots = boots.merge(fdr[["signal", "passes_fdr"]], on="signal", how="left")
        boots["passes_fdr"] = boots["passes_fdr"].fillna(False).astype(bool)
    else:
        boots["passes_fdr"] = pd.Series(dtype=bool)

    promotion = candidates.merge(stability[["signal", "stable", "positive_fraction", "edge_median", "edge_cv"]], on="signal", how="left")
    promotion = promotion.merge(boots[["signal", "ci_low", "ci_high", "p_value", "passes_fdr"]], on="signal", how="left")
    promotion["promoted"] = (
        promotion["development_candidate"]
        & promotion["stable"].fillna(False)
        & promotion["passes_fdr"].fillna(False)
        & (promotion["ci_low"] > 0)
        & (promotion["validation_win_edge"] > 0)
    )
    return promotion, stability


def build_oos_decisions(features_by_asset: dict[str, pd.DataFrame], promoted_by_asset: dict[str, list[str]], *,
                        start="2022-01-01", horizon: int = 10, min_n: int = 30,
                        bootstrap_iterations: int = 500) -> pd.DataFrame:
    """Generate decisions from evidence available strictly before each OOS decision date."""
    rows = []
    all_dates = sorted(set().union(*[set(df.loc[df.index >= pd.Timestamp(start)].index) for df in features_by_asset.values()]))
    config = EvidenceConfig(horizon=horizon, min_n=min_n, bootstrap_iterations=bootstrap_iterations,
                            bootstrap_block=5, fdr_alpha=0.05)
    specs_by_asset = {}
    for asset, f in features_by_asset.items():
        all_specs = {s.name: s for s in default_candidate_signals(f)}
        specs_by_asset[asset] = [all_specs[n] for n in promoted_by_asset.get(asset, []) if n in all_specs]

    for dt in all_dates:
        snapshots = []
        for asset, f in features_by_asset.items():
            if dt not in f.index or not specs_by_asset[asset]:
                continue
            snap = evidence_snapshot(
                f,
                specs_by_asset[asset],
                as_of=dt,
                asset=asset,
                stable_signals={s.name: True for s in specs_by_asset[asset]},
                config=config,
            )
            if not snap.empty:
                snapshots.append(snap)
        if not snapshots:
            continue
        snap = pd.concat(snapshots, ignore_index=True)
        best = best_asset_evidence(snap)
        if best.empty:
            continue
        best = best.sort_values(["ci_low", "median_mae", "asset"], ascending=[False, False, True]).iloc[0]
        rows.append(best.to_dict())
    return pd.DataFrame(rows)


def backtest_fixed_horizon_selector(prices: pd.DataFrame, decisions: pd.DataFrame, *, horizon: int = 10,
                                    cost_per_turnover: float = 0.0005) -> dict:
    """Backtest non-overlapping next-close entries with a fixed close-to-close holding horizon.

    A decision observed at close t is implemented at close t+1. Returns begin from
    close t+1 to t+2, so the signal cannot earn the intervening t-to-t+1 move.
    """
    prices = prices.sort_index().copy()
    prices.columns = [str(c).upper() for c in prices.columns]
    idx = prices.index
    position = pd.Series("CASH", index=idx, dtype=object)
    if decisions.empty:
        decisions = pd.DataFrame(columns=["date", "asset"])
    decisions = decisions.copy()
    decisions["date"] = pd.to_datetime(decisions["date"])
    decision_map = {pd.Timestamp(r.date): str(r.asset).upper() for r in decisions.itertuples()}

    i = 0
    while i < len(idx):
        dt = idx[i]
        asset = decision_map.get(dt)
        if asset not in prices.columns or i + 1 >= len(idx):
            i += 1
            continue
        entry = i + 1
        end = min(len(idx), entry + horizon)
        position.iloc[entry:end] = asset
        i = end

    ret = prices.pct_change().fillna(0.0)
    strategy = pd.Series(0.0, index=idx)
    held_prev = position.shift(1).fillna("CASH")
    for asset in prices.columns:
        strategy += ret[asset].where(held_prev.eq(asset), 0.0)
    turnover = position.ne(position.shift(1).fillna("CASH")).astype(float)
    strategy -= turnover * cost_per_turnover
    metrics = _metrics(strategy, position.ne("CASH").astype(float))
    metrics["switches"] = int(turnover.sum())
    metrics["cash_fraction"] = float(position.eq("CASH").mean())
    return {"returns": strategy, "position": position, "metrics": metrics}


def run_phase2(frames: dict[str, pd.DataFrame], output_dir: str | Path, *, horizon: int = 10, min_n: int = 30) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    features_by_asset = {asset: add_research_features(frames, asset) for asset in ("SPY", "QQQ")}
    promoted_by_asset = {}
    for asset, f in features_by_asset.items():
        promotion, stability = development_promotion_table(f, horizon=horizon, min_n=min_n)
        promotion.to_csv(output_dir / f"{asset}_development_promotion.csv", index=False)
        stability.to_csv(output_dir / f"{asset}_parameter_stability.csv", index=False)
        promoted_by_asset[asset] = promotion.loc[promotion["promoted"], "signal"].tolist()

    decisions = build_oos_decisions(features_by_asset, promoted_by_asset, start="2022-01-01", horizon=horizon,
                                    min_n=min_n, bootstrap_iterations=500)
    decisions.to_csv(output_dir / "oos_decisions.csv", index=False)

    prices = pd.DataFrame({a: frames[a]["close"] for a in ("SPY", "QQQ")}).dropna()
    prices = prices.loc[prices.index >= pd.Timestamp("2022-01-01")]
    strategy = backtest_fixed_horizon_selector(prices, decisions, horizon=horizon)
    pd.DataFrame({"strategy_return": strategy["returns"], "position": strategy["position"]}).to_csv(output_dir / "oos_strategy_daily.csv")

    metrics = {"SPY_QQQ_CASH": strategy["metrics"]}
    for asset in ("SPY", "QQQ"):
        metrics[f"{asset}_BUY_HOLD"] = benchmark_buy_hold(prices[asset])["metrics"]
    summary = {
        "methodology": {
            "development_end": "2021-12-31",
            "oos_start": "2022-01-01",
            "horizon_trading_days": horizon,
            "entry": "decision at close t, implemented at close t+1",
            "cost_per_position_change": 0.0005,
            "note": "Historical OOS simulation. Because prior exploratory reports included post-2021 results, live shadow validation remains required before production use."
        },
        "promoted_signals": promoted_by_asset,
        "decision_count": int(len(decisions)),
        "metrics": metrics,
    }
    (output_dir / "phase2_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
