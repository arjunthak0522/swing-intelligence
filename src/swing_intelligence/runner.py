from __future__ import annotations

import json
from pathlib import Path
from datetime import date, datetime, timezone
import time

import pandas as pd

from .data import DataRequest, fetch_twelve_data_daily, save_cache
from .validation import build_manifest, validate_market_history, write_manifest
from .research import add_research_features, evaluate_frozen_signals, survivor_table
from .walkforward import walk_forward_signal_table
from .phase2 import run_phase2


UNIVERSE = ("SPY", "QQQ", "RSP", "IWM", "SMH")


def _reject_stale_history(df: pd.DataFrame, symbol: str, max_calendar_days: int = 10) -> None:
    last = pd.Timestamp(df.index.max()).date()
    age = (date.today() - last).days
    if age < 0 or age > max_calendar_days:
        raise ValueError(f"{symbol} history is stale or truncated: last bar {last}, age {age} days")


def fetch_universe(cache_dir: str | Path, start="2000-01-01") -> dict[str, pd.DataFrame]:
    cache_dir = Path(cache_dir)
    frames = {}
    now = datetime.now(timezone.utc).isoformat()
    for i, symbol in enumerate(UNIVERSE):
        if i:
            time.sleep(8.0)
        df = fetch_twelve_data_daily(DataRequest(symbol, start=start), min_interval_seconds=8.0)
        validate_market_history(df, min_rows=1000)
        _reject_stale_history(df, symbol)
        save_cache(df, cache_dir / f"{symbol}.csv")
        write_manifest(build_manifest(df, symbol, "Twelve Data", now), cache_dir / f"{symbol}.manifest.json")
        frames[symbol] = df
    return frames


def run_research(frames: dict[str, pd.DataFrame], output_dir: str | Path, *, min_n=30) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {}
    for target in ("SPY", "QQQ"):
        features = add_research_features(frames, target)
        evaluation = evaluate_frozen_signals(features, min_n=min_n)
        survivors = survivor_table(evaluation, min_n=min_n)
        walk = walk_forward_signal_table(features, horizon=10, min_n=max(10, min_n // 2))
        survivors.to_csv(output_dir / f"{target}_survivors.csv", index=False)
        walk.to_csv(output_dir / f"{target}_walkforward.csv", index=False)
        summary[target] = {
            "survivor_count": int(survivors["survives"].sum()) if not survivors.empty else 0,
            "signals_tested": int(len(survivors)),
            "walkforward_rows": int(len(walk)),
        }
    (output_dir / "research_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    summary["phase2"] = run_phase2(frames, output_dir / "phase2", horizon=10, min_n=min_n)
    (output_dir / "research_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
