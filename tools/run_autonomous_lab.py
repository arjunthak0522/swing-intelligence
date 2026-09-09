from __future__ import annotations

import json
import os
from pathlib import Path

from swing_intelligence.autonomous_lab import LabConfig, run_autonomous_lab
from swing_intelligence.data import DataRequest, fetch_fred_vix, fetch_twelve_data_daily


OUT_DIR = Path("artifacts/autonomous_lab")


def _load_frames():
    key = os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        raise RuntimeError("TWELVE_DATA_API_KEY is required")

    frames = {}
    for symbol in ("SPY", "QQQ"):
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


def main():
    frames = _load_frames()
    config = LabConfig(max_pair_rules=80, min_n=25, primary_horizon=30)
    result = run_autonomous_lab(frames, targets=("SPY", "QQQ"), config=config)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "latest.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    summary = {
        "config": result["config"],
        "targets": {symbol: _compact_target(payload) for symbol, payload in result["targets"].items()},
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))

    for symbol, payload in summary["targets"].items():
        print(
            f"{symbol}: {payload['candidate_count']} candidates, "
            f"{payload['survivor_count']} survivors, "
            f"{payload['live_survivor_count']} live"
        )


if __name__ == "__main__":
    main()
