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
OVERSOLD_THRESHOLDS = (20.0, 25.0, 30.0)
TURN_1D = (3.0, 5.0, 7.0)
TURN_2D = (6.0, 10.0, 14.0)


def fetch_csv(url: str) -> pd.DataFrame:
    with urlopen(url, timeout=30) as resp:  # nosec - fixed HTTPS research source
        return pd.read_csv(StringIO(resp.read().decode("utf-8")))


def load_mmtw() -> pd.Series:
    df = fetch_csv(MMTW_URL)
    if not {"time", "close"}.issubset(df.columns):
        raise RuntimeError(f"Unexpected MMTW schema: {list(df.columns)}")
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    s = pd.Series(pd.to_numeric(df["close"], errors="coerce").values, index=dt, name="MMTW").dropna().sort_index()
    return s[~s.index.duplicated(keep="last")]


def weakness_mask(df: pd.DataFrame) -> pd.Series:
    return ((df["spy_dd20"] <= -0.01) | (df["B50"] <= 0.50) | (df["vix_change5"] >= 0.10) | (df["curve_ratio"] >= 1.0))


def episode_ids(mask: pd.Series) -> pd.Series:
    starts = mask & ~mask.shift(1, fill_value=False)
    return starts.cumsum().where(mask, 0)


def execution_return(df: pd.DataFrame, symbol: str, signal_date: pd.Timestamp, horizon: int) -> float | None:
    if signal_date not in df.index:
        return None
    loc = df.index.get_loc(signal_date)
    if not isinstance(loc, (int, np.integer)):
        return None
    entry_i = int(loc) + 1
    exit_i = entry_i + horizon
    if exit_i >= len(df):
        return None
    a = df[symbol].iloc[entry_i]
    b = df[symbol].iloc[exit_i]
    if pd.isna(a) or pd.isna(b):
        return None
    return float(b / a - 1.0 - ROUND_TRIP_COST)


def summarize(values: list[float]) -> dict:
    a = np.asarray(values, dtype=float)
    if not len(a):
        return {"n": 0, "mean": None, "median": None, "positive_rate": None, "p25": None, "p10": None}
    return {
        "n": int(len(a)), "mean": float(np.mean(a)), "median": float(np.median(a)),
        "positive_rate": float(np.mean(a > 0)), "p25": float(np.quantile(a, 0.25)), "p10": float(np.quantile(a, 0.10)),
    }


def first_date(mask: pd.Series) -> pd.Timestamp | None:
    x = mask.fillna(False)
    hits = x[x].index
    return pd.Timestamp(hits[0]) if len(hits) else None


def build_common_frame() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, dict]:
    frame = feature_frame()
    decisions = generate_decisions(frame)
    mmtw = load_mmtw()
    common_start = max(frame.index.min(), decisions.index.min(), mmtw.index.min())
    common_end = min(frame.index.max(), decisions.index.max(), mmtw.index.max())
    common_idx = frame.loc[common_start:common_end].index.intersection(mmtw.index)
    data = frame.loc[common_idx, ["SPY", "QQQ", "spy_dd20", "B50", "B200", "VIX", "vix_change5", "curve_ratio"]].copy()
    data["MMTW"] = mmtw.reindex(common_idx)
    decisions = decisions.reindex(common_idx).dropna(subset=["decision"])
    data = data.reindex(decisions.index).dropna(subset=["MMTW"])
    decisions = decisions.reindex(data.index)
    coverage = {
        "mmtw_start": str(mmtw.index.min().date()), "mmtw_end": str(mmtw.index.max().date()),
        "common_start": str(data.index.min().date()), "common_end": str(data.index.max().date()),
        "common_sessions": int(len(data)), "mmtw_missing_rate_on_common": float(data["MMTW"].isna().mean()),
    }
    return data, decisions, mmtw, coverage


def evaluate_rule(data: pd.DataFrame, decisions: pd.DataFrame, oversold_level: float, turn1: float, turn2: float) -> dict:
    weak = weakness_mask(decisions)
    ids = episode_ids(weak)
    records = []
    buckets = {k: {s: {h: [] for h in HORIZONS} for s in ("SPY", "QQQ")} for k in ("washout", "model")}

    for eid in sorted(int(x) for x in ids.unique() if x > 0):
        dates = ids.index[ids == eid].intersection(data.index)
        if len(dates) < 2:
            continue
        sub = data.loc[dates]
        oversold = sub["MMTW"] <= oversold_level
        had_oversold = oversold.cummax().shift(1, fill_value=False)
        turn = (sub["MMTW"].diff() >= turn1) | (sub["MMTW"].diff(2) >= turn2)
        washout_date = first_date(had_oversold & turn)
        model_rows = decisions.loc[dates]
        model_rows = model_rows[model_rows["decision"].isin(["CAUTIOUS YES", "YES", "STRONG YES"])]
        model_date = pd.Timestamp(model_rows.index[0]) if not model_rows.empty else None
        if washout_date is None and model_date is None:
            continue
        rec = {"episode": eid, "weakness_start": str(pd.Timestamp(dates[0]).date()),
               "washout_date": str(washout_date.date()) if washout_date is not None else None,
               "model_date": str(model_date.date()) if model_date is not None else None}
        if washout_date is not None and model_date is not None:
            rec["lead_sessions_vs_model"] = int(data.index.get_loc(model_date) - data.index.get_loc(washout_date))
        records.append(rec)
        for label, dt in (("washout", washout_date), ("model", model_date)):
            if dt is None:
                continue
            for symbol in ("SPY", "QQQ"):
                for h in HORIZONS:
                    r = execution_return(data, symbol, dt, h)
                    if r is not None:
                        buckets[label][symbol][h].append(r)

    paired = [r["lead_sessions_vs_model"] for r in records if "lead_sessions_vs_model" in r]
    metrics = {label: {s: {f"{h}D": summarize(v[h]) for h in HORIZONS} for s, v in sym.items()} for label, sym in buckets.items()}
    return {
        "params": {"oversold_level": oversold_level, "turn_1d": turn1, "turn_2d": turn2},
        "episodes": len(records), "paired_n": len(paired),
        "median_lead_sessions": float(np.median(paired)) if paired else None,
        "share_before_model": float(np.mean(np.asarray(paired) > 0)) if paired else None,
        "share_same_or_before_model": float(np.mean(np.asarray(paired) >= 0)) if paired else None,
        "metrics": metrics,
        "records": records,
    }


def score(result: dict) -> tuple:
    paired_n = result["paired_n"]
    if paired_n < 10:
        return (-999, -999, -999)
    lead = result["median_lead_sessions"] if result["median_lead_sessions"] is not None else -999
    spy10 = result["metrics"]["washout"]["SPY"]["10D"]
    qqq10 = result["metrics"]["washout"]["QQQ"]["10D"]
    tail = min(spy10["p10"] if spy10["p10"] is not None else -999, qqq10["p10"] if qqq10["p10"] is not None else -999)
    pos = min(spy10["positive_rate"] or 0, qqq10["positive_rate"] or 0)
    return (lead, pos, tail)


def main() -> None:
    data, decisions, mmtw, coverage = build_common_frame()
    results = []
    for o in OVERSOLD_THRESHOLDS:
        for t1 in TURN_1D:
            for t2 in TURN_2D:
                results.append(evaluate_rule(data, decisions, o, t1, t2))
    ranked = sorted(results, key=score, reverse=True)
    payload = {
        "verdict": "RESEARCH_ONLY_DO_NOT_PROMOTE",
        "question": "Does first MMTW turn after an oversold condition provide a useful earlier GO than the existing RE-ENTRY model?",
        "methodology": {
            "official_engine_changed": False,
            "common_coverage_only": True,
            "matched_episode_comparison": True,
            "execution": "signal at completed close t; hypothetical entry at next completed close t+1; 10 bps round-trip cost",
            "washout_semantics": "OVERSOLD first, then first MMTW turn is the early GO candidate",
            "parameter_grid": {"oversold": list(OVERSOLD_THRESHOLDS), "turn_1d": list(TURN_1D), "turn_2d": list(TURN_2D)},
            "anti_overfit": "Report full predeclared grid. No threshold is promoted from this one proxy family.",
        },
        "coverage": coverage,
        "source_audit": {
            "MMTW": {"status": "RESEARCH_PROXY_ONLY", "source": MMTW_URL,
                     "note": "Public third-party TradingView export. Useful for historical screening, not canonical production data."},
            "MMFD": {"status": "NOT_IN_THIS_HISTORICAL_TEST"},
            "NYMO_NAMO": {"status": "LIVE_AVAILABLE_HISTORICAL_SOURCE_STILL_BEING_VALIDATED"},
            "NYUD_NAUD": {"status": "LIVE_AVAILABLE_HISTORICAL_SOURCE_STILL_BEING_VALIDATED"},
        },
        "top_by_early_timing_with_tail_check": [{k: v for k, v in r.items() if k != "records"} for r in ranked[:10]],
        "all_rules": [{k: v for k, v in r.items() if k != "records"} for r in results],
        "best_rule_records": ranked[0]["records"] if ranked else [],
    }
    out = Path("artifacts/selling_exhaustion_research")
    out.mkdir(parents=True, exist_ok=True)
    (out / "selling_exhaustion_hardened.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    pd.DataFrame(payload["best_rule_records"]).to_csv(out / "best_rule_episode_pairs.csv", index=False)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
