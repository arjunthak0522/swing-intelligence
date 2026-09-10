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


def fetch_csv(url: str) -> pd.DataFrame:
    with urlopen(url, timeout=30) as resp:  # nosec - fixed HTTPS research source
        return pd.read_csv(StringIO(resp.read().decode("utf-8")))


def load_mmtw() -> pd.Series:
    df = fetch_csv(MMTW_URL)
    if not {"time", "close"}.issubset(df.columns):
        raise RuntimeError(f"Unexpected MMTW schema: {list(df.columns)}")
    dt = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert(None).dt.normalize()
    s = pd.Series(pd.to_numeric(df["close"], errors="coerce").values, index=dt, name="MMTW")
    return s.dropna().sort_index()[~s.dropna().sort_index().index.duplicated(keep="last")]


def weakness_mask(df: pd.DataFrame) -> pd.Series:
    return (
        (df["spy_dd20"] <= -0.01)
        | (df["B50"] <= 0.50)
        | (df["vix_change5"] >= 0.10)
        | (df["curve_ratio"] >= 1.0)
    )


def episode_ids(mask: pd.Series) -> pd.Series:
    starts = mask & ~mask.shift(1, fill_value=False)
    return starts.cumsum().where(mask, 0)


def forward_return(df: pd.DataFrame, symbol: str, date: pd.Timestamp, horizon: int) -> float | None:
    if date not in df.index:
        return None
    loc = df.index.get_loc(date)
    if not isinstance(loc, (int, np.integer)):
        return None
    exit_i = loc + horizon
    if exit_i >= len(df):
        return None
    return float(df[symbol].iloc[exit_i] / df[symbol].iloc[loc] - 1.0 - ROUND_TRIP_COST)


def summarize(values: list[float]) -> dict:
    a = np.asarray(values, dtype=float)
    if not len(a):
        return {"n": 0, "mean": None, "median": None, "positive_rate": None, "p25": None, "p10": None}
    return {
        "n": int(len(a)),
        "mean": float(np.mean(a)),
        "median": float(np.median(a)),
        "positive_rate": float(np.mean(a > 0)),
        "p25": float(np.quantile(a, 0.25)),
        "p10": float(np.quantile(a, 0.10)),
    }


def prior_percentile(series: pd.Series, lookback: int = 252) -> pd.Series:
    def pct_rank(x: pd.Series) -> float:
        if len(x) < 60:
            return np.nan
        current = x.iloc[-1]
        prior = x.iloc[:-1]
        if len(prior) < 59:
            return np.nan
        return float(np.mean(prior <= current))
    return series.rolling(lookback + 1, min_periods=61).apply(lambda x: pct_rank(pd.Series(x)), raw=False)


def build_candidate_frame(frame: pd.DataFrame, mmtw: pd.Series) -> pd.DataFrame:
    out = frame[["SPY", "QQQ", "spy_dd20", "B50", "B200", "VIX", "vix_change5", "curve_ratio"]].join(mmtw, how="left")
    out["MMTW"] = out["MMTW"].ffill(limit=1)
    out["mmtw_pctile_1y_prior"] = prior_percentile(out["MMTW"])
    out["mmtw_oversold_abs"] = out["MMTW"] <= 25.0
    out["mmtw_oversold_rel"] = out["mmtw_pctile_1y_prior"] <= 0.15
    out["mmtw_oversold"] = out["mmtw_oversold_abs"] | out["mmtw_oversold_rel"]
    out["mmtw_recovery_1d"] = out["MMTW"].diff() >= 5.0
    out["mmtw_recovery_2d"] = out["MMTW"].diff(2) >= 10.0
    out["mmtw_recovery"] = out["mmtw_recovery_1d"] | out["mmtw_recovery_2d"]
    prior_low = out["MMTW"].shift(1).rolling(5, min_periods=3).min()
    spy_prior_low = out["SPY"].shift(1).rolling(5, min_periods=3).min()
    out["breadth_positive_divergence"] = (out["SPY"] <= spy_prior_low) & (out["MMTW"] > prior_low)
    out["exhaustion_developing"] = out["mmtw_oversold"] & (out["mmtw_recovery"] | out["breadth_positive_divergence"])
    out["exhaustion_confirmed"] = out["mmtw_oversold"] & out["mmtw_recovery"] & (out["vix_change5"] <= 0.10)
    return out


def first_date(mask: pd.Series) -> pd.Timestamp | None:
    hits = mask[mask].index
    return pd.Timestamp(hits[0]) if len(hits) else None


def main() -> None:
    frame = feature_frame()
    decisions = generate_decisions(frame)
    mmtw = load_mmtw()
    data = build_candidate_frame(frame, mmtw)
    weak = weakness_mask(decisions)
    ids = episode_ids(weak)

    episode_records = []
    buckets: dict[str, dict[str, dict[int, list[float]]]] = {}
    for label in ("model", "oversold", "developing", "confirmed"):
        buckets[label] = {s: {h: [] for h in HORIZONS} for s in ("SPY", "QQQ")}

    for eid in sorted(int(x) for x in ids.unique() if x > 0):
        dates = ids.index[ids == eid]
        dates = dates.intersection(data.index)
        if len(dates) == 0:
            continue
        sub_dec = decisions.loc[dates]
        model_rows = sub_dec[sub_dec["decision"].isin(["CAUTIOUS YES", "YES", "STRONG YES"])]
        model_date = pd.Timestamp(model_rows.index[0]) if not model_rows.empty else None
        sub = data.loc[dates]
        candidates = {
            "oversold": first_date(sub["mmtw_oversold"].fillna(False)),
            "developing": first_date(sub["exhaustion_developing"].fillna(False)),
            "confirmed": first_date(sub["exhaustion_confirmed"].fillna(False)),
        }
        record = {
            "episode": eid,
            "weakness_start": str(pd.Timestamp(dates[0]).date()),
            "model_date": str(model_date.date()) if model_date is not None else None,
            **{f"{k}_date": str(v.date()) if v is not None else None for k, v in candidates.items()},
        }
        if model_date is not None:
            for k, v in candidates.items():
                if v is not None:
                    record[f"{k}_lead_sessions_vs_model"] = int(data.index.get_loc(model_date) - data.index.get_loc(v))
        episode_records.append(record)

        dates_by_label = {"model": model_date, **candidates}
        for label, dt in dates_by_label.items():
            if dt is None:
                continue
            for symbol in ("SPY", "QQQ"):
                for h in HORIZONS:
                    r = forward_return(data, symbol, dt, h)
                    if r is not None:
                        buckets[label][symbol][h].append(r)

    results = {
        label: {
            symbol: {f"{h}D": summarize(vals[h]) for h in HORIZONS}
            for symbol, vals in sym.items()
        }
        for label, sym in buckets.items()
    }

    lead_stats = {}
    for key in ("oversold", "developing", "confirmed"):
        vals = [r.get(f"{key}_lead_sessions_vs_model") for r in episode_records if r.get(f"{key}_lead_sessions_vs_model") is not None]
        lead_stats[key] = {
            "n": len(vals),
            "median_sessions_earlier_than_model": float(np.median(vals)) if vals else None,
            "share_before_model": float(np.mean(np.asarray(vals) > 0)) if vals else None,
        }

    source_audit = {
        "MMTW": {
            "status": "USABLE_FIRST_PASS",
            "definition": "Percent of stocks above 20-day moving average",
            "source": MMTW_URL,
            "coverage_start": str(mmtw.index.min().date()),
            "coverage_end": str(mmtw.index.max().date()),
            "note": "Public TradingView-exported dataset from third-party GitHub repository. Research only, not production-grade canonical data.",
        },
        "MMFD": {
            "status": "HISTORICAL_SOURCE_NOT_YET_CANONICAL",
            "definition": "Percent of stocks above 5-day moving average",
            "note": "Current/delayed values are publicly visible, but free machine-readable long history has not yet been validated for reproducible backtesting. Do not reconstruct from today's constituents.",
        },
        "SPXA20R": {"status": "HISTORICAL_SOURCE_NOT_YET_CANONICAL"},
        "BPSPX": {"status": "HISTORICAL_SOURCE_NOT_YET_CANONICAL"},
        "NYMO_NAMO": {"status": "HISTORICAL_SOURCE_NOT_YET_CANONICAL"},
        "ADV_DEC_VOLUME": {"status": "LIVE_CONTEXT_AVAILABLE_HISTORICAL_BACKTEST_PENDING"},
    }

    payload = {
        "verdict": "RESEARCH_ONLY_DO_NOT_PROMOTE",
        "question": "Can breadth oversold/exhaustion evidence identify useful earlier re-entry timing without materially worsening outcomes?",
        "methodology": {
            "official_engine_changed": False,
            "first_pass_indicator": "MMTW short-term breadth proxy",
            "absolute_oversold": "MMTW <= 25%",
            "relative_oversold": "MMTW <= prior-only 15th percentile over trailing ~1y",
            "developing": "oversold AND (1d/2d recovery OR positive breadth divergence vs SPY)",
            "confirmed": "oversold AND recovery AND 5d VIX change <= 10%",
            "horizons": list(HORIZONS),
            "round_trip_cost": ROUND_TRIP_COST,
            "important_limit": "Full MMFD/BPSPX/McClellan/advance-decline-volume historical family is not yet sourced reproducibly, so this pass cannot justify engine promotion.",
        },
        "source_audit": source_audit,
        "episode_count": len(episode_records),
        "lead_time_vs_existing_reentry": lead_stats,
        "forward_results": results,
        "episodes": episode_records,
    }

    out = Path("artifacts/selling_exhaustion_research")
    out.mkdir(parents=True, exist_ok=True)
    (out / "selling_exhaustion_first_pass.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    pd.DataFrame(episode_records).to_csv(out / "episode_timing_comparison.csv", index=False)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
