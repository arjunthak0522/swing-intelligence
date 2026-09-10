from __future__ import annotations

import json
import os
from pathlib import Path

from swing_intelligence.data import DataRequest, fetch_fred_series, fetch_fred_vix, fetch_twelve_data_daily
from swing_intelligence.semantic_lab import build_semantic_features
from swing_intelligence.score_accelerated_dca import AcceleratedDCAConfig, run_score_accelerated_dca

OUT = Path("artifacts/autonomous_lab/score_accelerated_dca.json")


def main():
    key = os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        raise RuntimeError("TWELVE_DATA_API_KEY is required")
    frames = {}
    for symbol in ("SPY", "QQQ", "RSP", "IWM", "SMH"):
        frames[symbol] = fetch_twelve_data_daily(
            DataRequest(symbol=symbol, start="2000-01-01"), api_key=key,
            years_per_chunk=14, min_interval_seconds=8.0,
        )
    frames["VIX"] = fetch_fred_vix(start="2000-01-01")
    for name, fred_id in {
        "DGS2": "DGS2", "DGS10": "DGS10", "HY_SPREAD": "BAMLH0A0HYM2", "DGS3MO": "DGS3MO"
    }.items():
        frames[name] = fetch_fred_series(fred_id, start="2000-01-01")

    features = build_semantic_features(frames, "SPY")
    cfg = AcceleratedDCAConfig(
        first_test_year=2010, fold_years=2, trigger=70.0,
        dca_days=30, outcome_days=126, episode_spacing_days=21,
        transaction_cost_bps=10.0,
    )
    result = run_score_accelerated_dca(features, cfg)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True))
    s = result["summary"]
    print(
        "Phase 6A score-accelerated DCA: "
        f"episodes={s.get('episodes')} acceleration_fraction={s.get('acceleration_fraction'):.3f} "
        f"median_accel={s.get('median_accelerated_return'):.6f} median_dca={s.get('median_dca_return'):.6f} "
        f"median_immediate={s.get('median_immediate_return'):.6f} "
        f"accel_minus_dca={s.get('median_accelerated_minus_dca'):.6f} "
        f"win_vs_dca={s.get('win_rate_vs_dca'):.3f} "
        f"accel_minus_immediate={s.get('median_accelerated_minus_immediate'):.6f} "
        f"win_vs_immediate={s.get('win_rate_vs_immediate'):.3f}"
    )


if __name__ == "__main__":
    main()
