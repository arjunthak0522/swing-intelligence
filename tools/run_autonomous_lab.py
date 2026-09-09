from __future__ import annotations

import json
import os
from pathlib import Path

from swing_intelligence.autonomous_lab import LabConfig, run_autonomous_lab
from swing_intelligence.autonomous_robustness import RobustnessConfig, robustness_report
from swing_intelligence.data import DataRequest, fetch_fred_vix, fetch_twelve_data_daily
from swing_intelligence.phase2b_validation import Phase2BConfig, phase2b_report
from swing_intelligence.research import add_research_features, split_periods
from swing_intelligence.semantic_lab import build_semantic_features, run_semantic_lab


OUT_DIR = Path("artifacts/autonomous_lab")
TARGETS = ("SPY", "QQQ")
CONTEXT_SYMBOLS = ("RSP", "IWM", "SMH")


def _load_frames():
    key = os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        raise RuntimeError("TWELVE_DATA_API_KEY is required")

    frames = {}
    # SPY and QQQ are the only research targets. RSP/IWM/SMH are context-only
    # series used for breadth and leadership confirmation, never trade targets.
    for symbol in TARGETS + CONTEXT_SYMBOLS:
        frames[symbol] = fetch_twelve_data_daily(
            DataRequest(symbol=symbol, start="2000-01-01"),
            api_key=key,
            years_per_chunk=14,
            min_interval_seconds=8.0,
        )
    frames["VIX"] = fetch_fred_vix(start="2000-01-01")
    return frames


def _compact_target(target: dict) -> dict:
    def compact_row(row: dict) -> dict:
        periods = row.get("periods", {})
        return {
            "name": row["name"],
            "rationale": row.get("rationale", ""),
            "terms": row.get("terms", []),
            "score": row.get("skeptic", {}).get("score"),
            "live_active": row.get("live_active", False),
            "validation_30d": periods.get("validation", {}).get("horizons", {}).get(30),
            "holdout_30d": periods.get("holdout", {}).get("horizons", {}).get(30),
        }

    return {
        "target": target["target"],
        "as_of": target["as_of"],
        "candidate_count": target["candidate_count"],
        "survivor_count": target["survivor_count"],
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
            holdout,
            result["targets"][symbol]["survivors"],
            config=robust_config,
        )
    return robustness


def _run_phase2b(frames, result, robustness, phase2b_config, semantic=False):
    report = {"config": phase2b_config.__dict__, "targets": {}}
    for symbol in TARGETS:
        features = build_semantic_features(frames, symbol) if semantic else add_research_features(frames, symbol)
        holdout = split_periods(features)["holdout"]
        report["targets"][symbol] = phase2b_report(
            holdout,
            result["targets"][symbol]["survivors"],
            robustness["targets"][symbol]["rows"],
            config=phase2b_config,
        )
    return report


def main():
    frames = _load_frames()
    config = LabConfig(max_pair_rules=80, min_n=25, primary_horizon=30)
    robust_config = RobustnessConfig(
        horizon=30,
        min_event_gap=30,
        min_independent_events=20,
        bootstrap_iterations=1000,
        bootstrap_block=3,
        fdr_alpha=0.10,
    )
    phase2b_config = Phase2BConfig(
        horizons=(10, 20, 30, 60),
        primary_horizon=30,
        min_events_per_slice=8,
        min_positive_horizons=3,
        min_positive_eras=2,
        era_years=2,
        min_regime_events=8,
        transaction_cost_bps_round_trip=2.0,
    )

    result = run_autonomous_lab(frames, targets=TARGETS, config=config)
    robustness = _run_robustness(frames, result, robust_config, semantic=False)
    phase2b = _run_phase2b(frames, result, robustness, phase2b_config, semantic=False)

    semantic = run_semantic_lab(frames, targets=TARGETS, config=config)
    semantic_robustness = _run_robustness(frames, semantic, robust_config, semantic=True)
    semantic_phase2b = _run_phase2b(frames, semantic, semantic_robustness, phase2b_config, semantic=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "latest.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    (OUT_DIR / "robustness.json").write_text(json.dumps(robustness, indent=2, sort_keys=True))
    (OUT_DIR / "phase2b.json").write_text(json.dumps(phase2b, indent=2, sort_keys=True))
    (OUT_DIR / "semantic_latest.json").write_text(json.dumps(semantic, indent=2, sort_keys=True))
    (OUT_DIR / "semantic_robustness.json").write_text(json.dumps(semantic_robustness, indent=2, sort_keys=True))
    (OUT_DIR / "semantic_phase2b.json").write_text(json.dumps(semantic_phase2b, indent=2, sort_keys=True))

    summary = {
        "config": result["config"],
        "research_targets": list(TARGETS),
        "context_only_symbols": list(CONTEXT_SYMBOLS) + ["VIX"],
        "targets": {symbol: _compact_target(payload) for symbol, payload in result["targets"].items()},
        "robustness": {
            symbol: {
                "tested": payload["tested"],
                "robust_count": payload["robust_count"],
                "rows": payload["rows"],
            }
            for symbol, payload in robustness["targets"].items()
        },
        "phase2b": {
            symbol: phase2b["targets"][symbol]
            for symbol in TARGETS
        },
        "semantic": {
            "targets": {symbol: _compact_target(payload) for symbol, payload in semantic["targets"].items()},
            "robustness": {
                symbol: {
                    "tested": payload["tested"],
                    "robust_count": payload["robust_count"],
                    "rows": payload["rows"],
                }
                for symbol, payload in semantic_robustness["targets"].items()
            },
            "phase2b": {
                symbol: semantic_phase2b["targets"][symbol]
                for symbol in TARGETS
            },
        },
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))

    for symbol in TARGETS:
        base = summary["targets"][symbol]
        base_robust = summary["robustness"][symbol]
        base_grades = summary["phase2b"][symbol]["grade_counts"]
        sem = summary["semantic"]["targets"][symbol]
        sem_robust = summary["semantic"]["robustness"][symbol]
        sem_grades = summary["semantic"]["phase2b"][symbol]["grade_counts"]
        print(
            f"{symbol}: baseline {base['candidate_count']} candidates / "
            f"{base['survivor_count']} first-pass / {base_robust['robust_count']} robust / "
            f"grades={base_grades}; semantic {sem['candidate_count']} candidates / "
            f"{sem['survivor_count']} first-pass / {sem_robust['robust_count']} robust / "
            f"grades={sem_grades}"
        )


if __name__ == "__main__":
    main()
