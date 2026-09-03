from __future__ import annotations

import numpy as np
import pandas as pd

from reentry_confidence import ROUND_TRIP_COST

EVIDENCE_HORIZONS = (5, 7, 10, 15, 30, 60)


def _entry_and_path(price: pd.Series, event_date: pd.Timestamp, horizon: int):
    pos = price.index.get_loc(event_date)
    entry_pos = pos + 1
    exit_pos = entry_pos + horizon
    if entry_pos >= len(price) or exit_pos >= len(price):
        return None
    entry = float(price.iloc[entry_pos])
    path = price.iloc[entry_pos : exit_pos + 1].astype(float)
    if not np.isfinite(entry) or entry <= 0 or path.empty:
        return None
    ret = float(path.iloc[-1] / entry - 1.0 - ROUND_TRIP_COST)
    mae = float(path.min() / entry - 1.0)
    mfe = float(path.max() / entry - 1.0)
    return ret, mae, mfe


def summarize_extended_evidence(frame: pd.DataFrame, analogs: pd.DataFrame) -> dict:
    """Permanent forward-evidence block for the re-entry engine.

    Entry convention matches the validated implementation: signal at close t,
    hypothetical entry at close t+1. Drawdown is close-to-close maximum adverse
    excursion from that entry through the requested horizon.
    """
    output: dict[str, dict] = {}
    for symbol in ("SPY", "QQQ"):
        price = frame[symbol].dropna()
        output[symbol] = {}
        for horizon in EVIDENCE_HORIZONS:
            rows = []
            for event_date in analogs.index:
                if event_date not in price.index:
                    continue
                result = _entry_and_path(price, event_date, horizon)
                if result is not None:
                    rows.append(result)
            if not rows:
                output[symbol][str(horizon)] = {"n": 0}
                continue
            arr = np.asarray(rows, dtype=float)
            returns, maes, mfes = arr[:, 0], arr[:, 1], arr[:, 2]
            output[symbol][str(horizon)] = {
                "n": int(len(returns)),
                "median_return": float(np.median(returns)),
                "mean_return": float(np.mean(returns)),
                "positive_rate": float(np.mean(returns > 0)),
                "p25_return": float(np.quantile(returns, 0.25)),
                "p75_return": float(np.quantile(returns, 0.75)),
                "median_max_drawdown": float(np.median(maes)),
                "p25_max_drawdown": float(np.quantile(maes, 0.25)),
                "p10_max_drawdown": float(np.quantile(maes, 0.10)),
                "worst_max_drawdown": float(np.min(maes)),
                "median_max_favorable_excursion": float(np.median(mfes)),
                "worst_final_return": float(np.min(returns)),
                "best_final_return": float(np.max(returns)),
            }
    return output
