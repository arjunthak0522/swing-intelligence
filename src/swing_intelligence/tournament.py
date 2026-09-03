from dataclasses import dataclass
import pandas as pd

from .outcomes import forward_path_stats, summarize_forward_paths


@dataclass(frozen=True)
class SignalSpec:
    name: str
    mask: pd.Series
    rationale: str = ""


def evaluate_signal(df: pd.DataFrame, signal: SignalSpec, horizons=(3, 5, 10, 20), min_n=30) -> dict:
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
        result["horizons"][h] = {**cs, "normal_median_return": bs["median_return"], "median_excess_edge": float(cs["median_return"] - bs["median_return"]), "normal_win_probability": bs["win_probability"], "win_probability_edge": float(cs["win_probability"] - bs["win_probability"]), "sample_ok": bool(cs["n"] >= min_n)}
    return result


def rank_signals(results: list[dict], horizon=10, min_n=30) -> pd.DataFrame:
    rows = []
    for r in results:
        h = r.get("horizons", {}).get(horizon)
        if not h or h["n"] < min_n:
            continue
        rows.append({"signal": r["name"], "n": h["n"], "median_return": h["median_return"], "median_excess_edge": h["median_excess_edge"], "win_probability": h["win_probability"], "win_probability_edge": h["win_probability_edge"], "median_mae": h["median_mae"], "median_mfe": h["median_mfe"]})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["median_excess_edge", "win_probability_edge", "median_mae"], ascending=[False, False, False]).reset_index(drop=True)


def default_candidate_signals(f: pd.DataFrame) -> list[SignalSpec]:
    above_rising_200 = (f["gap_sma_200"] > 0) & (f["sma_200"].pct_change(20) > 0)
    signals = [
        SignalSpec("rsi14_oversold", f["rsi_14"] < 35),
        SignalSpec("rsi5_extreme", f["rsi_5"] < 20),
        SignalSpec("zscore_deep", f["zscore_20"] < -1.5),
        SignalSpec("bull_pullback_rsi", above_rising_200 & (f["rsi_14"] < 40)),
        SignalSpec("bull_pullback_z", above_rising_200 & (f["zscore_20"] < -1)),
        SignalSpec("donchian_breakout", f["donchian_breakout_up_20"] == 1),
        SignalSpec("momentum_20d", (f["return_20d"] > 0.05) & (f["gap_sma_200"] > 0)),
        SignalSpec("volatility_pullback", above_rising_200 & (f["return_5d"] < -0.03) & (f["atr_pct_rank_252"] > .70)),
    ]
    if "vix_shock" in f:
        signals += [SignalSpec("vix_shock_pullback", (f["vix_shock"] == 1) & (f["return_5d"] < -0.02)), SignalSpec("bull_vix_shock_pullback", above_rising_200 & (f["vix_shock"] == 1) & (f["rsi_14"] < 45))]
    if "rsp_spy_ret_20d" in f:
        signals += [SignalSpec("breadth_confirmed_breakout", (f["donchian_breakout_up_20"] == 1) & (f["rsp_spy_ret_20d"] > 0)), SignalSpec("breadth_stabilized_pullback", above_rising_200 & (f["rsi_14"] < 45) & (f["rsp_spy_ret_5d"] > 0))]
    if "qqq_spy_ret_20d" in f:
        signals.append(SignalSpec("qqq_leadership_momentum", (f["return_20d"] > 0.03) & (f["qqq_spy_ret_20d"] > 0.02)))
    if "smh_qqq_ret_20d" in f:
        signals.append(SignalSpec("semis_leadership_pullback", above_rising_200 & (f["rsi_14"] < 45) & (f["smh_qqq_ret_20d"] > 0)))
    return signals
