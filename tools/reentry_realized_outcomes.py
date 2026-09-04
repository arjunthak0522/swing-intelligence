from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_confidence import ROUND_TRIP_COST, fetch_twelve_close
from reentry_evidence import EVIDENCE_HORIZONS

DATA_ROOT = Path("data/reentry")
HISTORY_ROOT = DATA_ROOT / "history"
REALIZED_ROOT = DATA_ROOT / "realized"


def realized_path(price: pd.Series, signal_date: pd.Timestamp, horizon: int) -> dict | None:
    signal_date = pd.Timestamp(signal_date).normalize()
    if signal_date not in price.index:
        return None
    pos = price.index.get_loc(signal_date)
    if not isinstance(pos, (int, np.integer)):
        return None
    entry_i = int(pos) + 1
    exit_i = entry_i + horizon
    if exit_i >= len(price):
        return None
    entry = float(price.iloc[entry_i])
    path = price.iloc[entry_i : exit_i + 1].astype(float)
    if not np.isfinite(entry) or entry <= 0 or path.empty:
        return None
    return {
        "entry_date": str(path.index[0].date()),
        "exit_date": str(path.index[-1].date()),
        "entry_close": entry,
        "exit_close": float(path.iloc[-1]),
        "realized_return": float(path.iloc[-1] / entry - 1.0 - ROUND_TRIP_COST),
        "max_drawdown": float(path.min() / entry - 1.0),
        "max_favorable_excursion": float(path.max() / entry - 1.0),
        "round_trip_cost": ROUND_TRIP_COST,
    }


def update_realized() -> dict:
    REALIZED_ROOT.mkdir(parents=True, exist_ok=True)
    snapshots = sorted(HISTORY_ROOT.glob("*.json")) if HISTORY_ROOT.exists() else []
    if not snapshots:
        return {"snapshots": 0, "completed_cells": 0, "files_written": 0}

    prices = {symbol: fetch_twelve_close(symbol) for symbol in ("SPY", "QQQ")}
    completed_cells = 0
    files_written = 0

    for snapshot_path in snapshots:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        signal_date = pd.Timestamp(snapshot["as_of"])
        out_path = REALIZED_ROOT / snapshot_path.name
        existing = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
        payload = {
            "as_of": snapshot["as_of"],
            "engine_version": snapshot["engine_version"],
            "signal": snapshot["signal"],
            "analog_decision": snapshot["analog_decision"],
            "outcomes": existing.get("outcomes", {}),
        }

        changed = not out_path.exists()
        for symbol in ("SPY", "QQQ"):
            payload["outcomes"].setdefault(symbol, {})
            for horizon in EVIDENCE_HORIZONS:
                key = str(horizon)
                if key in payload["outcomes"][symbol]:
                    completed_cells += 1
                    continue
                result = realized_path(prices[symbol], signal_date, horizon)
                if result is not None:
                    payload["outcomes"][symbol][key] = result
                    completed_cells += 1
                    changed = True

        if changed:
            out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            files_written += 1

    summary = {
        "snapshots": len(snapshots),
        "completed_cells": completed_cells,
        "files_written": files_written,
        "horizons": list(EVIDENCE_HORIZONS),
        "definition": "signal close t, entry close t+1, horizon trading sessions after entry, 10 bps round-trip cost; drawdown uses daily closes",
    }
    (DATA_ROOT / "realized_index.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    print(json.dumps(update_realized(), indent=2))


if __name__ == "__main__":
    main()
