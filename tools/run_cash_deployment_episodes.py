from __future__ import annotations

import json
import os
from pathlib import Path

from swing_intelligence.cash_deployment_episodes import CashEpisodeConfig, run_cash_deployment_episodes
from swing_intelligence.data import DataRequest, fetch_fred_series, fetch_fred_vix, fetch_twelve_data_daily
from swing_intelligence.semantic_lab import build_semantic_features

OUT_DIR = Path("artifacts/autonomous_lab")


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
    for name, fred_id in {"DGS2":"DGS2", "DGS10":"DGS10", "HY_SPREAD":"BAMLH0A0HYM2"}.items():
        frames[name] = fetch_fred_series(fred_id, start="2000-01-01")

    features = build_semantic_features(frames, "SPY")
    config = CashEpisodeConfig(
        first_test_year=2010,
        fold_years=2,
        trigger=70.0,
        dca_days=30,
        max_wait_days=(63, 126),
        outcome_days=126,
        episode_spacing_days=21,
        transaction_cost_bps=10.0,
    )
    result = run_cash_deployment_episodes(features, config)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "cash_deployment_episodes.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    for wait, row in result["waits"].items():
        print(
            f"Phase 5B wait={wait}: episodes={row['episodes']} trigger_fraction={row['trigger_fraction']:.3f} "
            f"median_score={row['median_score_return']:.6f} median_immediate={row['median_immediate_return']:.6f} "
            f"median_dca={row['median_dca_return']:.6f} score_minus_immediate={row['median_score_minus_immediate']:.6f} "
            f"win_vs_immediate={row['win_rate_vs_immediate']:.3f} score_minus_dca={row['median_score_minus_dca']:.6f} "
            f"win_vs_dca={row['win_rate_vs_dca']:.3f}"
        )


if __name__ == "__main__":
    main()
