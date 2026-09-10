from __future__ import annotations

import json
import os
from pathlib import Path

from swing_intelligence.correction_reentry import CorrectionReentryConfig, run_correction_reentry_validation
from swing_intelligence.data import DataRequest, fetch_fred_series, fetch_fred_vix, fetch_twelve_data_daily
from swing_intelligence.semantic_lab import build_semantic_features


OUT = Path("artifacts/autonomous_lab/correction_reentry.json")


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
    frames["DGS2"] = fetch_fred_series("DGS2", start="2000-01-01")
    frames["DGS10"] = fetch_fred_series("DGS10", start="2000-01-01")
    frames["HY_SPREAD"] = fetch_fred_series("BAMLH0A0HYM2", start="2000-01-01")

    features = build_semantic_features(frames, "SPY")
    result = run_correction_reentry_validation(features, CorrectionReentryConfig())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True))

    s = result["summary"]
    print(
        "Phase 7 correction-only re-entry: "
        f"episodes={s.get('episode_count')} / signaled={s.get('signal_episode_count')} / "
        f"signal_fraction={s.get('signal_fraction')} / median_delay={s.get('median_signal_delay_days')} / "
        f"median_from_low={s.get('median_signal_distance_from_low_days')} / types={s.get('type_counts')}"
    )
    for h, stats in s.get("horizons", {}).items():
        print(
            f"Phase 7 {h}d: median={stats.get('median_signal_return')} / win={stats.get('win_rate')} / "
            f"mae={stats.get('median_mae')} / edge_vs_0={stats.get('median_edge_vs_delay_0')} / "
            f"edge_vs_3={stats.get('median_edge_vs_delay_3')} / edge_vs_5={stats.get('median_edge_vs_delay_5')} / "
            f"edge_vs_10={stats.get('median_edge_vs_delay_10')}"
        )


if __name__ == "__main__":
    main()
