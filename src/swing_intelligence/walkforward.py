from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from .tournament import default_candidate_signals, evaluate_signal


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def expanding_windows(index, *, first_train_end="2012-12-31", test_years=2, step_years=2):
    idx = pd.DatetimeIndex(index)
    start = idx.min()
    end = idx.max()
    train_end = pd.Timestamp(first_train_end)
    windows = []
    while train_end < end:
        test_start = train_end + pd.Timedelta(days=1)
        test_end = min(test_start + pd.DateOffset(years=test_years) - pd.Timedelta(days=1), end)
        if test_start > end:
            break
        windows.append(WalkForwardWindow(start, train_end, test_start, test_end))
        train_end = train_end + pd.DateOffset(years=step_years)
    return windows


def walk_forward_signal_table(df: pd.DataFrame, *, horizon=10, min_n=20, first_train_end="2012-12-31") -> pd.DataFrame:
    """Evaluate frozen hypotheses on sequential unseen test windows. No threshold optimization."""
    rows = []
    for wid, window in enumerate(expanding_windows(df.index, first_train_end=first_train_end), start=1):
        test = df.loc[(df.index >= window.test_start) & (df.index <= window.test_end)]
        for spec in default_candidate_signals(test):
            result = evaluate_signal(test, spec, horizons=(horizon,), min_n=min_n)
            h = result.get("horizons", {}).get(horizon)
            if not h:
                continue
            rows.append({
                "window": wid,
                "test_start": str(window.test_start.date()),
                "test_end": str(window.test_end.date()),
                "signal": spec.name,
                "n": h["n"],
                "median_excess_edge": h["median_excess_edge"],
                "win_probability_edge": h["win_probability_edge"],
                "median_mae": h["median_mae"],
                "median_mfe": h["median_mfe"],
                "sample_ok": h["n"] >= min_n,
            })
    return pd.DataFrame(rows)
