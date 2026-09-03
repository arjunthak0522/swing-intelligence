from __future__ import annotations

from io import StringIO
import json
import math
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd

RNG_SEED = 20260903
BOOTSTRAPS = 10000
COOLDOWN = 15
COST_RT = 0.0010  # 10 bps round trip
HORIZONS = [3, 5, 7, 10, 20]

PRIMARY = {
    "spy_5d_max": -0.05,
    "vix_5d_min": 0.25,
    "breadth_5d_max": -0.01,
}
ROBUSTNESS = {
    "looser": {"spy_5d_max": -0.04, "vix_5d_min": 0.20, "breadth_5d_max": -0.0075},
    "primary": PRIMARY,
    "tighter": {"spy_5d_max": -0.06, "vix_5d_min": 0.30, "breadth_5d_max": -0.0125},
}


def fetch_fred(series_id: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    with urlopen(url, timeout=30) as resp:  # nosec - fixed HTTPS FRED endpoint
        text = resp.read().decode("utf-8")
    df = pd.read_csv(StringIO(text))
    df.columns = ["date", series_id]
    df["date"] = pd.to_datetime(df["date"])
    df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
    return df.dropna().set_index("date")[series_id].sort_index()


def fetch_close(symbol: str, start: str = "2008-01-01") -> pd.Series:
    params = {
        "symbol": symbol,
        "interval": "1day",
        "start_date": start,
        "outputsize": 5000,
        "apikey": os.environ["TWELVE_DATA_API_KEY"],
        "format": "JSON",
        "order": "ASC",
    }
    url = "https://api.twelvedata.com/time_series?" + urlencode(params)
    with urlopen(url, timeout=60) as resp:  # nosec - fixed HTTPS Twelve Data endpoint
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("status") == "error" or "values" not in payload:
        raise RuntimeError(payload.get("message", f"No data for {symbol}"))
    df = pd.DataFrame(payload["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna(subset=["close"]).set_index("datetime")["close"].sort_index().rename(symbol)


def market_frame() -> pd.DataFrame:
    spy = fetch_close("SPY")
    qqq = fetch_close("QQQ")
    rsp = fetch_close("RSP")
    vix = fetch_fred("VIXCLS").rename("VIX")
    x = pd.concat([spy, qqq, rsp, vix], axis=1).dropna()
    x["breadth_ratio"] = x["RSP"] / x["SPY"]
    x["spy_5d"] = x["SPY"].pct_change(5)
    x["vix_5d"] = x["VIX"].pct_change(5)
    x["breadth_5d"] = x["breadth_ratio"].pct_change(5)
    x["spy_1d"] = x["SPY"].pct_change()
    x["vix_1d"] = x["VIX"].pct_change()
    x["breadth_1d"] = x["breadth_ratio"].pct_change()
    return x.dropna()


def washout_signal(x: pd.DataFrame, cfg: dict) -> pd.Series:
    washout = (
        (x["spy_5d"] <= cfg["spy_5d_max"])
        & (x["vix_5d"] >= cfg["vix_5d_min"])
        & (x["breadth_5d"] <= cfg["breadth_5d_max"])
    )
    # Frozen two-stage event: washout at t-1, stabilization at t.
    stabilization = (x["spy_1d"] > 0) & (x["breadth_1d"] > 0) & (x["vix_1d"] < 0)
    return washout.shift(1, fill_value=False) & stabilization


def dedup(mask: pd.Series, cooldown: int = COOLDOWN) -> pd.Series:
    out = pd.Series(False, index=mask.index)
    last = -10_000
    for i, flag in enumerate(mask.fillna(False).to_numpy(bool)):
        if flag and i - last > cooldown:
            out.iloc[i] = True
            last = i
    return out


def trade_paths(price: pd.Series, signals: pd.DatetimeIndex, horizon: int) -> pd.DataFrame:
    rows = []
    idx = price.index
    for signal_date in signals:
        if signal_date not in idx:
            continue
        s = idx.get_loc(signal_date)
        if not isinstance(s, (int, np.integer)):
            continue
        entry_i = s + 1  # next-close execution
        exit_i = entry_i + horizon
        if exit_i >= len(idx):
            continue
        entry = float(price.iloc[entry_i])
        exit_px = float(price.iloc[exit_i])
        path = price.iloc[entry_i + 1 : exit_i + 1].astype(float) / entry - 1.0
        gross = exit_px / entry - 1.0
        rows.append({
            "signal_date": signal_date,
            "entry_date": idx[entry_i],
            "exit_date": idx[exit_i],
            "gross_return": gross,
            "net_return": gross - COST_RT,
            "mae": float(path.min()) if len(path) else gross,
            "mfe": float(path.max()) if len(path) else gross,
        })
    return pd.DataFrame(rows).set_index("signal_date") if rows else pd.DataFrame()


def unconditional_next_close(price: pd.Series, horizon: int) -> pd.Series:
    # Comparable next-close entry and horizon hold from every possible signal day.
    entry = price.shift(-1)
    exit_px = price.shift(-(horizon + 1))
    return (exit_px / entry - 1.0 - COST_RT).dropna()


def bootstrap_excess(vals: np.ndarray, base_median: float, rng: np.random.Generator) -> dict:
    if len(vals) < 2:
        return {"ci_low": None, "ci_high": None, "p_one_sided": None}
    draws = rng.choice(vals, size=(BOOTSTRAPS, len(vals)), replace=True)
    excess = np.median(draws, axis=1) - base_median
    return {
        "ci_low": float(np.quantile(excess, 0.025)),
        "ci_high": float(np.quantile(excess, 0.975)),
        "p_one_sided": float((np.count_nonzero(excess <= 0) + 1) / (BOOTSTRAPS + 1)),
    }


def bh_adjust(pvals: dict[str, float | None]) -> dict[str, float | None]:
    valid = sorted((k, p) for k, p in pvals.items() if p is not None and math.isfinite(p))
    if not valid:
        return {k: None for k in pvals}
    valid.sort(key=lambda kv: kv[1])
    m = len(valid)
    raw = [min(1.0, p * m / i) for i, (_, p) in enumerate(valid, 1)]
    adj = raw[:]
    for i in range(m - 2, -1, -1):
        adj[i] = min(adj[i], adj[i + 1])
    out = {k: None for k in pvals}
    for (k, _), q in zip(valid, adj):
        out[k] = float(q)
    return out


def era(d: pd.Timestamp) -> str:
    if d.year <= 2015:
        return "2008-2015_development"
    if d.year <= 2020:
        return "2016-2020_validation"
    return "2021-2026_recent"


def matched_selloff_control(x: pd.DataFrame, symbol: str, paths: pd.DataFrame, horizon: int) -> dict:
    if paths.empty:
        return {"event_median": None, "matched_median": None, "matched_excess": None, "event_n": 0, "control_n": 0}
    price = x[symbol]
    frame = pd.DataFrame(index=x.index)
    frame["prior5"] = x["spy_5d"]
    frame["entry"] = price.shift(-1)
    frame["exit"] = price.shift(-(horizon + 1))
    frame["fwd"] = frame["exit"] / frame["entry"] - 1.0 - COST_RT
    frame = frame.dropna()
    event_dates = set(paths.index)
    controls = []
    event_vals = []
    for d in paths.index:
        if d not in frame.index:
            continue
        target = float(frame.at[d, "prior5"])
        candidates = frame.loc[~frame.index.isin(event_dates)].copy()
        # Match only genuine selloffs and exclude +/-20 trading days around event.
        pos = frame.index.get_loc(d)
        nearby = set(frame.index[max(0, pos - 20): min(len(frame), pos + 21)])
        candidates = candidates.loc[~candidates.index.isin(nearby)]
        candidates = candidates[candidates["prior5"] <= -0.025]
        if candidates.empty:
            continue
        nearest = (candidates["prior5"] - target).abs().nsmallest(20).index
        controls.extend(candidates.loc[nearest, "fwd"].tolist())
        event_vals.append(float(frame.at[d, "fwd"]))
    if not event_vals or not controls:
        return {"event_median": None, "matched_median": None, "matched_excess": None, "event_n": len(event_vals), "control_n": len(controls)}
    return {
        "event_median": float(np.median(event_vals)),
        "matched_median": float(np.median(controls)),
        "matched_excess": float(np.median(event_vals) - np.median(controls)),
        "event_n": len(event_vals),
        "control_n": len(controls),
    }


def summarize(x: pd.DataFrame, symbol: str, signals: pd.DatetimeIndex, horizon: int, rng: np.random.Generator) -> dict:
    paths = trade_paths(x[symbol], signals, horizon)
    base = unconditional_next_close(x[symbol], horizon)
    vals = paths["net_return"].to_numpy(float) if not paths.empty else np.array([])
    base_med = float(base.median())
    eras = {}
    for label in ["2008-2015_development", "2016-2020_validation", "2021-2026_recent"]:
        sub = paths[[era(d) == label for d in paths.index]] if not paths.empty else paths
        eras[label] = {
            "n": int(len(sub)),
            "median_return": float(sub["net_return"].median()) if len(sub) else None,
            "positive_rate": float((sub["net_return"] > 0).mean()) if len(sub) else None,
            "median_mae": float(sub["mae"].median()) if len(sub) else None,
            "median_mfe": float(sub["mfe"].median()) if len(sub) else None,
        }
    return {
        "symbol": symbol,
        "horizon": horizon,
        "n": int(len(paths)),
        "median_return": float(np.median(vals)) if len(vals) else None,
        "mean_return": float(np.mean(vals)) if len(vals) else None,
        "positive_rate": float(np.mean(vals > 0)) if len(vals) else None,
        "median_mae": float(paths["mae"].median()) if len(paths) else None,
        "median_mfe": float(paths["mfe"].median()) if len(paths) else None,
        "unconditional_median": base_med,
        "median_excess": float(np.median(vals) - base_med) if len(vals) else None,
        "bootstrap": bootstrap_excess(vals, base_med, rng),
        "eras": eras,
        "matched_selloff": matched_selloff_control(x, symbol, paths, horizon),
        "event_dates": [str(d.date()) for d in paths.index] if not paths.empty else [],
    }


def main() -> None:
    rng = np.random.default_rng(RNG_SEED)
    x = market_frame()
    primary_mask = dedup(washout_signal(x, PRIMARY))
    primary_dates = primary_mask[primary_mask].index

    results = {}
    pvals = {}
    for symbol in ["SPY", "QQQ"]:
        results[symbol] = {}
        for h in HORIZONS:
            key = f"{symbol}_{h}D"
            r = summarize(x, symbol, primary_dates, h, rng)
            results[symbol][str(h)] = r
            pvals[key] = r["bootstrap"]["p_one_sided"]

    qvals = bh_adjust(pvals)
    for symbol in ["SPY", "QQQ"]:
        for h in HORIZONS:
            results[symbol][str(h)]["bootstrap"]["fdr_q"] = qvals[f"{symbol}_{h}D"]

    robustness = {}
    for name, cfg in ROBUSTNESS.items():
        dates = dedup(washout_signal(x, cfg))
        d = dates[dates].index
        robustness[name] = {"event_count": int(len(d)), "SPY": {}, "QQQ": {}}
        for symbol in ["SPY", "QQQ"]:
            for h in [5, 7, 10]:
                p = trade_paths(x[symbol], d, h)
                robustness[name][symbol][str(h)] = {
                    "n": int(len(p)),
                    "median_return": float(p["net_return"].median()) if len(p) else None,
                    "positive_rate": float((p["net_return"] > 0).mean()) if len(p) else None,
                }

    def candidate_status(r: dict) -> str:
        recent = r["eras"]["2021-2026_recent"]
        matched = r["matched_selloff"]["matched_excess"]
        ci = r["bootstrap"]["ci_low"]
        q = r["bootstrap"]["fdr_q"]
        if (
            r["n"] >= 30
            and r["median_excess"] is not None and r["median_excess"] > 0
            and ci is not None and ci > 0
            and q is not None and q <= 0.10
            and recent["n"] >= 8
            and recent["median_return"] is not None and recent["median_return"] > 0
            and matched is not None and matched > 0
        ):
            return "GO"
        if r["n"] >= 15 and r["median_excess"] is not None and r["median_excess"] > 0:
            return "MAYBE"
        return "STOP"

    statuses = {
        f"{symbol}_{h}D": candidate_status(results[symbol][str(h)])
        for symbol in ["SPY", "QQQ"] for h in HORIZONS
    }

    out = {
        "methodology": {
            "primary_washout": PRIMARY,
            "stabilization": "washout on t-1; on t SPY 1D > 0, RSP/SPY 1D > 0, VIX 1D < 0",
            "breadth_proxy": "RSP/SPY relative-performance deterioration",
            "execution": "signal at close t, enter at close t+1",
            "round_trip_cost": COST_RT,
            "episode_cooldown_trading_days": COOLDOWN,
            "horizons": HORIZONS,
            "purpose": "frozen worthiness/falsification test, not parameter search",
        },
        "sample": {
            "start": str(x.index.min().date()),
            "end": str(x.index.max().date()),
            "rows": int(len(x)),
            "primary_event_count": int(len(primary_dates)),
        },
        "results": results,
        "robustness": robustness,
        "statuses": statuses,
    }

    outdir = Path("artifacts/washout_worthiness")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "washout_worthiness.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
