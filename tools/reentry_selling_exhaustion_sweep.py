from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd

from reentry_confidence import feature_frame
from reentry_walkforward_validation import generate_decisions

MMTW_URL = "https://raw.githubusercontent.com/MiggoyGHP/Regime-dashboard/master/INDEX_MMTW%2C%201D_9513e.csv"
HORIZONS = (5, 10, 30, 60)
ROUND_TRIP_COST = 0.001
FALSE_START_HORIZON = 5
FALSE_START_RETURN = -0.02


def fetch_csv(url: str) -> pd.DataFrame:
    with urlopen(url, timeout=30) as resp:  # nosec - fixed research source
        return pd.read_csv(StringIO(resp.read().decode("utf-8")))


def load_mmtw() -> pd.Series:
    df = fetch_csv(MMTW_URL)
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert(None).dt.normalize()
    s = pd.Series(pd.to_numeric(df["close"], errors="coerce").values, index=dt, name="MMTW")
    s = s.dropna().sort_index()
    return s[~s.index.duplicated(keep="last")]


def weakness_mask(df: pd.DataFrame) -> pd.Series:
    return ((df["spy_dd20"] <= -0.01) | (df["B50"] <= 0.50) | (df["vix_change5"] >= 0.10) | (df["curve_ratio"] >= 1.0))


def episode_ids(mask: pd.Series) -> pd.Series:
    starts = mask & ~mask.shift(1, fill_value=False)
    return starts.cumsum().where(mask, 0)


def executable_fwd(df: pd.DataFrame, symbol: str, signal_date: pd.Timestamp, h: int) -> float | None:
    """Signal on completed close t, hypothetical execution on next completed close t+1."""
    if signal_date not in df.index:
        return None
    pos = df.index.get_loc(signal_date)
    if not isinstance(pos, (int, np.integer)):
        return None
    entry_i = int(pos) + 1
    exit_i = entry_i + h
    if exit_i >= len(df):
        return None
    entry = df[symbol].iloc[entry_i]
    exit_px = df[symbol].iloc[exit_i]
    if pd.isna(entry) or pd.isna(exit_px):
        return None
    return float(exit_px / entry - 1.0 - ROUND_TRIP_COST)


def adverse_excursion(df: pd.DataFrame, symbol: str, signal_date: pd.Timestamp, h: int = 10) -> float | None:
    if signal_date not in df.index:
        return None
    pos = df.index.get_loc(signal_date)
    if not isinstance(pos, (int, np.integer)):
        return None
    entry_i = int(pos) + 1
    end_i = min(entry_i + h, len(df) - 1)
    if entry_i >= len(df) or end_i <= entry_i:
        return None
    entry = df[symbol].iloc[entry_i]
    path = df[symbol].iloc[entry_i : end_i + 1]
    if pd.isna(entry) or path.dropna().empty:
        return None
    return float(path.min() / entry - 1.0)


def summary(vals: list[float]) -> dict:
    a = np.asarray(vals, float)
    if not len(a):
        return {"n": 0, "mean": None, "median": None, "positive_rate": None, "p10": None}
    return {"n": int(len(a)), "mean": float(a.mean()), "median": float(np.median(a)), "positive_rate": float((a > 0).mean()), "p10": float(np.quantile(a, 0.10))}


def first_true(s: pd.Series) -> pd.Timestamp | None:
    hits = s.fillna(False)
    idx = hits[hits].index
    return pd.Timestamp(idx[0]) if len(idx) else None


def candidate_masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    masks = {}
    for threshold in (20.0, 25.0, 30.0):
        oversold = df["MMTW"] <= threshold
        for turn in (2.0, 5.0, 8.0):
            masks[f"washout_le_{int(threshold)}_turn_{int(turn)}"] = oversold.shift(1, fill_value=False) & (df["MMTW"].diff() >= turn)
        masks[f"washout_le_{int(threshold)}_divergence"] = (
            oversold.shift(1, fill_value=False)
            & (df["SPY"] <= df["SPY"].shift(1).rolling(5, min_periods=3).min())
            & (df["MMTW"] > df["MMTW"].shift(1).rolling(5, min_periods=3).min())
        )
        masks[f"washout_le_{int(threshold)}_turn2_vix_easing"] = oversold.shift(1, fill_value=False) & (df["MMTW"].diff() >= 2.0) & (df["VIX"].diff() < 0)
        masks[f"washout_le_{int(threshold)}_turn2_b50_improving"] = oversold.shift(1, fill_value=False) & (df["MMTW"].diff() >= 2.0) & (df["B50"].diff() > 0)
    return masks


def main() -> None:
    frame = feature_frame()
    decisions = generate_decisions(frame)
    data = frame[["SPY", "QQQ", "B50", "VIX", "spy_dd20", "vix_change5", "curve_ratio"]].join(load_mmtw(), how="left")
    data["MMTW"] = data["MMTW"].ffill(limit=1)

    common_start = max(decisions.index.min(), data["MMTW"].dropna().index.min())
    common_end = min(decisions.index.max(), data["MMTW"].dropna().index.max())
    decisions = decisions.loc[common_start:common_end].copy()
    data = data.loc[common_start:common_end].copy()

    ids = episode_ids(weakness_mask(decisions))
    masks = candidate_masks(data)

    model_dates = {}
    episode_dates = {}
    for eid in sorted(int(x) for x in ids.unique() if x > 0):
        dates = ids.index[ids == eid].intersection(data.index)
        if not len(dates):
            continue
        elig = decisions.loc[dates]
        elig = elig[elig["decision"].isin(["CAUTIOUS YES", "YES", "STRONG YES"])]
        model_dates[eid] = pd.Timestamp(elig.index[0]) if not elig.empty else None
        episode_dates[eid] = dates

    results = {}
    for name, mask in masks.items():
        leads = []
        buckets = {s: {h: [] for h in HORIZONS} for s in ("SPY", "QQQ")}
        maes = {s: [] for s in ("SPY", "QQQ")}
        false_starts = {s: [] for s in ("SPY", "QQQ")}
        by_era = {"2017-2020": [], "2021-2026": []}
        hits = 0
        for eid, dates in episode_dates.items():
            cand = first_true(mask.loc[dates])
            if cand is None:
                continue
            hits += 1
            model = model_dates.get(eid)
            if model is not None:
                lead = int(data.index.get_loc(model) - data.index.get_loc(cand))
                leads.append(lead)
                era = "2017-2020" if cand.year <= 2020 else "2021-2026"
                by_era[era].append(lead)
            for s in ("SPY", "QQQ"):
                mae = adverse_excursion(data, s, cand, 10)
                if mae is not None:
                    maes[s].append(mae)
                r5 = executable_fwd(data, s, cand, FALSE_START_HORIZON)
                if r5 is not None:
                    false_starts[s].append(r5 <= FALSE_START_RETURN)
                for h in HORIZONS:
                    r = executable_fwd(data, s, cand, h)
                    if r is not None:
                        buckets[s][h].append(r)
        results[name] = {
            "episodes_hit": hits,
            "lead": {
                "n": len(leads),
                "median_sessions_earlier": float(np.median(leads)) if leads else None,
                "share_before_model": float((np.asarray(leads) > 0).mean()) if leads else None,
                "share_same_or_before_model": float((np.asarray(leads) >= 0).mean()) if leads else None,
                "eras": {k: {"n": len(v), "median_lead": float(np.median(v)) if v else None, "share_before": float((np.asarray(v) > 0).mean()) if v else None} for k, v in by_era.items()},
            },
            "forward": {s: {f"{h}D": summary(buckets[s][h]) for h in HORIZONS} for s in ("SPY", "QQQ")},
            "risk": {
                s: {
                    "mae_10d_median": float(np.median(maes[s])) if maes[s] else None,
                    "mae_10d_p10": float(np.quantile(maes[s], 0.10)) if maes[s] else None,
                    "false_start_rate_5d_le_minus_2pct": float(np.mean(false_starts[s])) if false_starts[s] else None,
                    "n": len(false_starts[s]),
                }
                for s in ("SPY", "QQQ")
            },
        }

    def score(item):
        _, r = item
        lead = r["lead"]
        spy10 = r["forward"]["SPY"]["10D"]
        qqq10 = r["forward"]["QQQ"]["10D"]
        spy_risk = r["risk"]["SPY"]
        qqq_risk = r["risk"]["QQQ"]
        if lead["n"] < 20 or spy10["n"] < 20 or qqq10["n"] < 20:
            return -999.0
        false_start_penalty = (spy_risk["false_start_rate_5d_le_minus_2pct"] or 0) + (qqq_risk["false_start_rate_5d_le_minus_2pct"] or 0)
        return float(
            lead["share_before_model"] * 2.0
            + max(0.0, lead["median_sessions_earlier"] or 0) * 0.05
            + spy10["positive_rate"]
            + qqq10["positive_rate"]
            + spy10["median"] * 10
            + qqq10["median"] * 10
            - false_start_penalty
        )

    ranked = [{"candidate": n, "screen_score": score((n, r)), **r} for n, r in sorted(results.items(), key=score, reverse=True)]
    payload = {
        "verdict": "RESEARCH_ONLY_DO_NOT_PROMOTE",
        "purpose": "Find the earliest executable first-turn washout candidate that improves timing without unacceptable false starts or downside tails.",
        "methodology": {
            "common_coverage_only": True,
            "common_start": str(common_start.date()),
            "common_end": str(common_end.date()),
            "execution": "completed-close signal t; hypothetical entry next completed close t+1; 10 bps round-trip cost",
            "false_start_definition": "5D return <= -2% from executable t+1 entry",
            "mae_window": "10 sessions from executable t+1 entry",
            "threshold_grid_predeclared": True,
        },
        "important_limit": "This sweep uses historical MMTW plus existing canonical breadth/VIX proxies. Historical MMFD, BPSPX, NYMO/NAMO and NYUD/NAUD remain separate evidence families and are not silently reconstructed.",
        "candidate_count": len(ranked),
        "ranked_candidates": ranked,
    }
    out = Path("artifacts/selling_exhaustion_sweep")
    out.mkdir(parents=True, exist_ok=True)
    (out / "selling_exhaustion_sweep.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
