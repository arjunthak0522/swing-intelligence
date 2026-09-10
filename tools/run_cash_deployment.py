from __future__ import annotations

import json
import os
from pathlib import Path

from swing_intelligence.cash_deployment import CashDeploymentConfig, run_cash_deployment_simulator
from swing_intelligence.data import DataRequest, fetch_fred_series, fetch_fred_vix, fetch_twelve_data_daily
from swing_intelligence.semantic_lab import build_semantic_features


OUT_DIR = Path("artifacts/autonomous_lab")
TARGETS_AND_CONTEXT = ("SPY", "QQQ", "RSP", "IWM", "SMH")
MACRO = {
    "DGS2": "DGS2",
    "DGS10": "DGS10",
    "HY_SPREAD": "BAMLH0A0HYM2",
    "DGS3MO": "DGS3MO",
}


def load_frames():
    key = os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        raise RuntimeError("TWELVE_DATA_API_KEY is required")
    frames = {}
    for symbol in TARGETS_AND_CONTEXT:
        frames[symbol] = fetch_twelve_data_daily(
            DataRequest(symbol=symbol, start="2000-01-01"), api_key=key,
            years_per_chunk=14, min_interval_seconds=8.0,
        )
    frames["VIX"] = fetch_fred_vix(start="2000-01-01")
    for name, fred_id in MACRO.items():
        frames[name] = fetch_fred_series(fred_id, start="2000-01-01")
    return frames


def main():
    frames = load_frames()
    features = build_semantic_features(frames, "SPY")
    cash_yield = frames["DGS3MO"]["close"]

    result = run_cash_deployment_simulator(
        features,
        cash_yield,
        CashDeploymentConfig(
            first_test_year=2010,
            fold_years=2,
            cash_sleeve_fraction=0.10,
            trigger=70.0,
            dca_days=30,
            random_iterations=200,
            transaction_cost_bps=10.0,
            starting_capital=100000.0,
        ),
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "cash_deployment.json").write_text(json.dumps(result, indent=2, sort_keys=True))

    p = result["policies"]
    print(
        "Phase 5A cash deployment: "
        f"immediate_end={p['immediate']['ending_value']} / "
        f"dca_end={p['dca']['ending_value']} / "
        f"score_end={p['score_triggered']['ending_value']} / "
        f"score_date={p['score_triggered']['deployment_date']} / "
        f"random_median_end={p['random']['median_ending_value']} / "
        f"score_vs_immediate={p['score_triggered']['vs_immediate_ending_value']} / "
        f"score_vs_dca={p['score_triggered']['vs_dca_ending_value']} / "
        f"score_vs_random={p['score_triggered']['vs_random_median_ending_value']}"
    )


if __name__ == "__main__":
    main()
