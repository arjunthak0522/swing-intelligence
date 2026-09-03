from dataclasses import dataclass
import numpy as np
import pandas as pd

from .outcomes import forward_path_stats, summarize_forward_paths


@dataclass(frozen=True)
class SignalSpec:
    name: str
    mask: pd.Series
    rationale: str = ""


def evaluate_signal(df: pd.DataFrame, signal: SignalSpec, horizons=(3, 5, 10, 20), min_n=30) -> dict:
    """Evaluate one candidate signal against unconditional forward outcomes."""
    entries = signal.mask.reindex(df.index).fillna(False)
    dates = list(df.index[entries])
    result = {"name": signal.name, "rationale": signal.rationale, "entry_count": len(dates), "horizons": {}}

    for h in horizons:
        conditional = forward_path_stats(df, dates, h)
        baseline = forward_path_stats(df, df.index, h)
        cs = summarize_forward_paths(conditional)
        bs = summarize_forward_paths(baseline)
        if cs.get("n", 0) == 0:
            continue
        median_edge = cs["median_return"] - bs["median_return"]
        win_edge = cs["win_probability"] - bs["win_probability"]
        result["horizons"][h] = {
            **cs,
            "normal_median_return": bs["median_return"],
            "median_excess_edge": float(median_edge),
            "normal_win_probability": bs["win_probability"],
            "win_probability_edge": float(win_edge),
            "sample_ok": bool(cs["n"] >= min_n),
        }
    return result


def rank_signals(results: list[dict], horizon=10, min_n=30) -> pd.DataFrame:
    """Rank by observed benchmark-relative edge, not arbitrary indicator points."""
    rows = []
    for r in results:
        h = r.get("horizons", {}).get(horizon)
        if not h or h["n"] < min_n:
            continue
        rows.append({
            "signal": r["name"],
            "n": h["n"],
            "median_return": h["median_return"],
            "median_excess_edge": h["median_excess_edge"],
            "win_probability": h["win_probability"],
            "win_probability_edge": h["win_probability_edge"],
            "median_mae": h["median_mae"],
            "median_mfe": h["median_mfe"],
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["median_excess_edge", "win_probability_edge", "median_mae"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def default_candidate_signals(f: pd.DataFrame) -> list[SignalSpec]:
    """Initial transparent hypotheses for the signal tournament."""
    above_rising_200 = (f["gap_sma_200"] > 0) & (f["sma_200"].pct_change(20) > 0)
    return [
        SignalSpec("rsi14_oversold", f["rsi_14"] < 35, "Short-term oversold hypothesis"),
        SignalSpec("rsi5_extreme", f["rsi_5"] < 20, "Fast RSI exhaustion hypothesis"),
        SignalSpec("zscore_deep", f["zscore_20"] < -1.5, "Price materially below 20-day distribution"),
        SignalSpec("bull_pullback_rsi", above_rising_200 & (f["rsi_14"] < 40), "Oversold within a rising long-term trend"),
        SignalSpec("bull_pullback_z", above_rising_200 & (f["zscore_20"] < -1), "Mean reversion within a rising long-term trend"),
        SignalSpec("donchian_breakout", f["donchian_breakout_up_20"] == 1, "20-day breakout hypothesis"),
        SignalSpec("momentum_20d", (f["return_20d"] > 0.05) & (f["gap_sma_200"] > 0), "Strong medium-term momentum"),
        SignalSpec("volatility_pullback", above_rising_200 & (f["return_5d"] < -0.03) & (f["atr_pct_rank_252"] > .70), "Sharp pullback with elevated volatility in an uptrend"),
    ]
