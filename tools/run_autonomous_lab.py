from __future__ import annotations

import json
import os
from pathlib import Path

from swing_intelligence.autonomous_lab import LabConfig, run_autonomous_lab
from swing_intelligence.autonomous_robustness import RobustnessConfig, robustness_report
from swing_intelligence.conditional_search import ConditionalSearchConfig, run_conditional_walk_forward
from swing_intelligence.data import DataRequest, fetch_fred_series, fetch_fred_vix, fetch_twelve_data_daily
from swing_intelligence.opportunity_score import OpportunityScoreConfig, run_opportunity_score_walk_forward
from swing_intelligence.phase2b_validation import Phase2BConfig, phase2b_report
from swing_intelligence.qqq_family_robustness import QQQFamilyConfig, run_qqq_family_robustness
from swing_intelligence.research import add_research_features, split_periods
from swing_intelligence.semantic_lab import build_semantic_features, run_semantic_lab
from swing_intelligence.walk_forward import WalkForwardConfig, run_semantic_walk_forward


OUT_DIR = Path("artifacts/autonomous_lab")
TARGETS = ("SPY", "QQQ")
CONTEXT_SYMBOLS = ("RSP", "IWM", "SMH")
MACRO_CONTEXT = {
    "DGS2": "DGS2",
    "DGS10": "DGS10",
    "HY_SPREAD": "BAMLH0A0HYM2",
}


def _load_frames():
    key = os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        raise RuntimeError("TWELVE_DATA_API_KEY is required")
    frames = {}
    for symbol in TARGETS + CONTEXT_SYMBOLS:
        frames[symbol] = fetch_twelve_data_daily(
            DataRequest(symbol=symbol, start="2000-01-01"), api_key=key,
            years_per_chunk=14, min_interval_seconds=8.0,
        )
    frames["VIX"] = fetch_fred_vix(start="2000-01-01")
    for name, fred_id in MACRO_CONTEXT.items():
        frames[name] = fetch_fred_series(fred_id, start="2000-01-01")
    return frames


def _compact_target(target: dict) -> dict:
    def compact_row(row: dict) -> dict:
        periods = row.get("periods", {})
        return {
            "name": row["name"], "rationale": row.get("rationale", ""),
            "terms": row.get("terms", []), "score": row.get("skeptic", {}).get("score"),
            "live_active": row.get("live_active", False),
            "validation_30d": periods.get("validation", {}).get("horizons", {}).get(30),
            "holdout_30d": periods.get("holdout", {}).get("horizons", {}).get(30),
        }
    return {
        "target": target["target"], "as_of": target["as_of"],
        "candidate_count": target["candidate_count"], "survivor_count": target["survivor_count"],
        "live_survivor_count": target["live_survivor_count"],
        "top_survivors": [compact_row(x) for x in target["survivors"][:20]],
        "live": [compact_row(x) for x in target["live"][:20]],
    }


def _run_robustness(frames, result, robust_config, semantic=False):
    robustness = {"config": robust_config.__dict__, "targets": {}}
    for symbol in TARGETS:
        features = build_semantic_features(frames, symbol) if semantic else add_research_features(frames, symbol)
        holdout = split_periods(features)["holdout"]
        robustness["targets"][symbol] = robustness_report(
            holdout, result["targets"][symbol]["survivors"], config=robust_config,
        )
    return robustness


def _run_phase2b(frames, result, robustness, phase2b_config, semantic=False):
    report = {"config": phase2b_config.__dict__, "targets": {}}
    for symbol in TARGETS:
        features = build_semantic_features(frames, symbol) if semantic else add_research_features(frames, symbol)
        holdout = split_periods(features)["holdout"]
        report["targets"][symbol] = phase2b_report(
            holdout, result["targets"][symbol]["survivors"], robustness["targets"][symbol]["rows"],
            config=phase2b_config,
        )
    return report


def main():
    frames = _load_frames()
    config = LabConfig(max_pair_rules=80, min_n=25, primary_horizon=30)
    robust_config = RobustnessConfig(horizon=30, min_event_gap=30, min_independent_events=20,
                                     bootstrap_iterations=1000, bootstrap_block=3, fdr_alpha=0.10)
    phase2b_config = Phase2BConfig(horizons=(10, 20, 30, 60), primary_horizon=30,
                                   min_events_per_slice=8, min_positive_horizons=3,
                                   min_positive_eras=2, era_years=2, min_regime_events=8,
                                   transaction_cost_bps_round_trip=2.0)
    wf_config = WalkForwardConfig(
        first_test_year=2010, fold_years=2, horizon=30, min_gap=30,
        transaction_cost_bps_round_trip=2.0, min_trades_total=20,
        min_folds_with_trades=3, min_positive_fold_fraction=0.60,
        matched_random_iterations=200, min_matched_random_percentile=0.80,
        min_random_superiority_fold_fraction=0.60,
    )
    opportunity_config = OpportunityScoreConfig(
        first_test_year=2010, fold_years=2, horizon=30, min_gap=30,
        transaction_cost_bps_round_trip=5.0,
        trigger_levels=(65, 70, 75, 80, 85, 90),
        min_trades_total=25, min_folds_with_trades=4,
        min_positive_edge_fold_fraction=0.60,
        matched_random_iterations=200, min_matched_random_percentile=0.80,
        min_random_superiority_fold_fraction=0.60,
    )
    conditional_config = ConditionalSearchConfig(
        walk_forward=wf_config,
        inner_validation_years=2,
        min_inner_trades=3,
        max_selected_per_fold=4,
        min_outer_trades_total=20,
        min_outer_folds=3,
        min_positive_edge_fold_fraction=0.60,
    )
    qqq_family_config = QQQFamilyConfig(
        first_test_year=2008,
        fold_years=2,
        horizons=(20, 30, 40, 60),
        min_gaps=(20, 30, 40),
        cost_bps=(2.0, 5.0, 10.0),
        vix_cooling_quantiles=(0.50, 0.60, 0.70),
        min_total_trades=20,
        min_folds=3,
        min_positive_fold_fraction=0.60,
        min_excess_hit_rate=0.50,
        random_iterations=100,
        min_random_percentile=0.90,
        min_leave_crisis_trades=15,
    )

    result = run_autonomous_lab(frames, targets=TARGETS, config=config)
    robustness = _run_robustness(frames, result, robust_config, semantic=False)
    phase2b = _run_phase2b(frames, result, robustness, phase2b_config, semantic=False)

    semantic = run_semantic_lab(frames, targets=TARGETS, config=config)
    semantic_robustness = _run_robustness(frames, semantic, robust_config, semantic=True)
    semantic_phase2b = _run_phase2b(frames, semantic, semantic_robustness, phase2b_config, semantic=True)

    walk_forward = {"config": wf_config.__dict__, "targets": {}}
    conditional = {"targets": {}}
    opportunity = {"config": opportunity_config.__dict__, "targets": {}}
    semantic_features = {}
    for symbol in TARGETS:
        features = build_semantic_features(frames, symbol)
        semantic_features[symbol] = features
        walk_forward["targets"][symbol] = run_semantic_walk_forward(features, symbol, config=wf_config)
        conditional["targets"][symbol] = run_conditional_walk_forward(features, symbol, config=conditional_config)
        opportunity["targets"][symbol] = run_opportunity_score_walk_forward(features, symbol, config=opportunity_config)

    qqq_family = run_qqq_family_robustness(semantic_features["QQQ"], qqq_family_config)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payloads = {
        "latest.json": result, "robustness.json": robustness, "phase2b.json": phase2b,
        "semantic_latest.json": semantic, "semantic_robustness.json": semantic_robustness,
        "semantic_phase2b.json": semantic_phase2b, "walk_forward.json": walk_forward,
        "conditional_walk_forward.json": conditional, "qqq_family_robustness.json": qqq_family,
        "opportunity_score.json": opportunity,
    }
    for name, payload in payloads.items():
        (OUT_DIR / name).write_text(json.dumps(payload, indent=2, sort_keys=True))

    summary = {
        "config": result["config"], "research_targets": list(TARGETS),
        "context_only_symbols": list(CONTEXT_SYMBOLS) + ["VIX"] + list(MACRO_CONTEXT),
        "macro_fred_series": MACRO_CONTEXT,
        "targets": {symbol: _compact_target(payload) for symbol, payload in result["targets"].items()},
        "robustness": {symbol: robustness["targets"][symbol] for symbol in TARGETS},
        "phase2b": {symbol: phase2b["targets"][symbol] for symbol in TARGETS},
        "semantic": {
            "targets": {symbol: _compact_target(payload) for symbol, payload in semantic["targets"].items()},
            "robustness": {symbol: semantic_robustness["targets"][symbol] for symbol in TARGETS},
            "phase2b": {symbol: semantic_phase2b["targets"][symbol] for symbol in TARGETS},
        },
        "walk_forward": {symbol: walk_forward["targets"][symbol] for symbol in TARGETS},
        "conditional_walk_forward": {symbol: conditional["targets"][symbol] for symbol in TARGETS},
        "qqq_family_robustness": qqq_family,
        "opportunity_score": {symbol: opportunity["targets"][symbol] for symbol in TARGETS},
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))

    for symbol in TARGETS:
        base = summary["targets"][symbol]
        base_robust = summary["robustness"][symbol]
        base_grades = summary["phase2b"][symbol]["grade_counts"]
        sem = summary["semantic"]["targets"][symbol]
        sem_robust = summary["semantic"]["robustness"][symbol]
        sem_grades = summary["semantic"]["phase2b"][symbol]["grade_counts"]
        wf = summary["walk_forward"][symbol]
        cond = summary["conditional_walk_forward"][symbol]
        opp = summary["opportunity_score"][symbol]
        print(
            f"{symbol}: baseline {base['candidate_count']} candidates / {base['survivor_count']} first-pass / "
            f"{base_robust['robust_count']} robust / grades={base_grades}; semantic {sem['candidate_count']} candidates / "
            f"{sem['survivor_count']} first-pass / {sem_robust['robust_count']} robust / grades={sem_grades}; "
            f"walk-forward matched-random-qualified={wf['profitable_count']}; conditional candidate strategies={cond['candidate_strategy_count']}; "
            f"opportunity-score qualified triggers={opp['qualifying_trigger_count']} latest={opp['latest'].get('opportunity_score')}"
        )

    print(
        "QQQ Phase 3B family: "
        f"valid variants={qqq_family['valid_variant_count']} / "
        f"passing={qqq_family['passing_variant_count']} / "
        f"fraction={qqq_family['passing_variant_fraction']:.3f} / "
        f"full-stress passing={qqq_family['full_stress_passing_variant_count']} / "
        f"full-stress fraction={qqq_family['full_stress_passing_variant_fraction']:.3f} / "
        f"family_robust={qqq_family['family_robust']} / "
        f"family_full_stress_robust={qqq_family['family_full_stress_robust']}"
    )


if __name__ == "__main__":
    main()