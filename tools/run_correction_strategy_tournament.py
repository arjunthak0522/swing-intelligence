from __future__ import annotations

import json
import os
from pathlib import Path

from swing_intelligence.correction_strategy_tournament import CorrectionTournamentConfig, run_correction_strategy_tournament
from swing_intelligence.data import DataRequest, fetch_fred_series, fetch_fred_vix, fetch_twelve_data_daily
from swing_intelligence.semantic_lab import build_semantic_features


OUT = Path("artifacts/autonomous_lab/correction_strategy_tournament.json")


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
    result = run_correction_strategy_tournament(features, CorrectionTournamentConfig())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True))

    print(
        "Phase 8 correction strategy tournament: "
        f"episodes={result.get('episode_count')} / qualifiers={result.get('qualifying_strategy_count')}"
    )
    for row in result.get("results", []):
        h30 = (row.get("horizons") or {}).get("30", {})
        print(
            f"Phase 8 {row.get('name')}: qualifies={row.get('qualifies')} / signals={row.get('signals')} / "
            f"median_delay={row.get('median_delay_days')} / median30={h30.get('median_return')} / "
            f"win30={h30.get('win_rate')} / edge30={h30.get('median_edge_vs_onset')} / "
            f"edge_win30={h30.get('edge_win_rate')} / positive_folds={row.get('positive_fold_fraction')}"
        )


if __name__ == "__main__":
    main()
