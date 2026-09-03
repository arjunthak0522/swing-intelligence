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
COOLDOWN_TRADING_DAYS = 10


def fetch_fred(series_id: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    with urlopen(url, timeout=30) as resp:  # nosec - fixed HTTPS FRED endpoint
        text = resp.read().decode("utf-8")
    df = pd.read_csv(StringIO(text))
    df.columns = ["date", series_id]
    df["date"] = pd.to_datetime(df["date"])
    df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
    return df.dropna().set_index("date")[series_id].sort_index()


def fetch_twelve_close(symbol: str, start: str = "2007-12-01") -> pd.Series:
    key = os.environ["TWELVE_DATA_API_KEY"]
    params = {
        "symbol": symbol,
        "interval": "1day",
        "start_date": start,
        "outputsize": 5000,
        "apikey": key,
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


def crossing_mask(ratio: pd.Series, threshold: float, direction: str) -> pd.Series:
    prior = ratio.shift(1)
    if direction == "up":
        return (prior <= threshold) & (ratio > threshold)
    if direction == "down":
        return (prior > threshold) & (ratio <= threshold)
    raise ValueError(direction)


def cooldown(mask: pd.Series, trading_index: pd.DatetimeIndex, days: int = COOLDOWN_TRADING_DAYS) -> pd.Series:
    aligned = mask.reindex(trading_index).fillna(False).astype(bool)
    keep = pd.Series(False, index=trading_index)
    last_kept = -10_000
    for i, flag in enumerate(aligned.to_numpy()):
        if flag and i - last_kept > days:
            keep.iloc[i] = True
            last_kept = i
    return keep


def path_stats(price: pd.Series, event_dates: pd.DatetimeIndex, horizon: int) -> pd.DataFrame:
    rows = []
    idx = price.index
    for d in event_dates:
        if d not in idx:
            continue
        i = idx.get_loc(d)
        if not isinstance(i, (int, np.integer)) or i + horizon >= len(idx):
            continue
        start = float(price.iloc[i])
        path = price.iloc[i + 1 : i + horizon + 1].astype(float) / start - 1.0
        rows.append({
            "date": d,
            "fwd_return": float(price.iloc[i + horizon] / start - 1.0),
            "mae": float(path.min()),
            "mfe": float(path.max()),
        })
    if not rows:
        return pd.DataFrame(columns=["fwd_return", "mae", "mfe"])
    return pd.DataFrame(rows).set_index("date")


def unconditional(price: pd.Series, horizon: int) -> pd.Series:
    return (price.shift(-horizon) / price - 1.0).dropna()


def bootstrap_median_excess(event_returns: np.ndarray, base_median: float, rng: np.random.Generator) -> dict:
    if len(event_returns) < 2:
        return {"ci_low": None, "ci_high": None, "p_one_sided": None}
    draws = rng.choice(event_returns, size=(BOOTSTRAPS, len(event_returns)), replace=True)
    excess = np.median(draws, axis=1) - base_median
    return {
        "ci_low": float(np.quantile(excess, 0.025)),
        "ci_high": float(np.quantile(excess, 0.975)),
        "p_one_sided": float((np.count_nonzero(excess <= 0.0) + 1) / (BOOTSTRAPS + 1)),
    }


def bh_adjust(pvals: dict[str, float | None]) -> dict[str, float | None]:
    valid = [(k, p) for k, p in pvals.items() if p is not None and math.isfinite(p)]
    if not valid:
        return {k: None for k in pvals}
    valid.sort(key=lambda x: x[1])
    m = len(valid)
    raw = [min(1.0, p * m / rank) for rank, (_, p) in enumerate(valid, start=1)]
    adj = raw[:]
    for i in range(m - 2, -1, -1):
        adj[i] = min(adj[i], adj[i + 1])
    out = {k: None for k in pvals}
    for (k, _), q in zip(valid, adj):
        out[k] = float(q)
    return out


def era_label(d: pd.Timestamp) -> str:
    y = d.year
    if y <= 2015:
        return "2007-2015_development"
    if y <= 2020:
        return "2016-2020_validation"
    return "2021-2026_recent"


def matched_control_excess(price: pd.Series, events: pd.DatetimeIndex, horizon: int, neighbors: int = 20) -> dict:
    frame = pd.DataFrame({"px": price})
    frame["prior5"] = frame["px"] / frame["px"].shift(5) - 1.0
    frame["fwd"] = frame["px"].shift(-horizon) / frame["px"] - 1.0
    frame = frame.dropna()
    event_set = set(events)
    controls = []
    event_vals = []
    positions = {d: i for i, d in enumerate(frame.index)}
    for d in events:
        if d not in frame.index:
            continue
        target = float(frame.at[d, "prior5"])
        pos = positions[d]
        candidates = frame.copy()
        # Exclude event dates and a +/-20-row neighborhood around this event.
        exclude = set(frame.index[max(0, pos - 20) : min(len(frame), pos + 21)]) | event_set
        candidates = candidates.loc[~candidates.index.isin(exclude)]
        if candidates.empty:
            continue
        nearest = (candidates["prior5"] - target).abs().nsmallest(neighbors).index
        controls.extend(candidates.loc[nearest, "fwd"].tolist())
        event_vals.append(float(frame.at[d, "fwd"]))
    if not event_vals or not controls:
        return {"event_median": None, "matched_median": None, "matched_excess": None, "event_n": 0, "control_n": 0}
    return {
        "event_median": float(np.median(event_vals)),
        "matched_median": float(np.median(controls)),
        "matched_excess": float(np.median(event_vals) - np.median(controls)),
        "event_n": len(event_vals),
        "control_n": len(controls),
    }


def summarize_candidate(name: str, price: pd.Series, mask: pd.Series, horizon: int, rng: np.random.Generator) -> dict:
    dedup = cooldown(mask, price.index)
    events = dedup[dedup].index
    paths = path_stats(price, events, horizon)
    base = unconditional(price, horizon)
    vals = paths["fwd_return"].dropna().to_numpy(dtype=float)
    base_median = float(base.median())
    boot = bootstrap_median_excess(vals, base_median, rng)
    eras = {}
    for era in ["2007-2015_development", "2016-2020_validation", "2021-2026_recent"]:
        subset = paths[[era_label(d) == era for d in paths.index]]
        eras[era] = {
            "n": int(len(subset)),
            "median_return": float(subset["fwd_return"].median()) if len(subset) else None,
            "positive_rate": float((subset["fwd_return"] > 0).mean()) if len(subset) else None,
            "median_mae": float(subset["mae"].median()) if len(subset) else None,
            "median_mfe": float(subset["mfe"].median()) if len(subset) else None,
        }
    matched = matched_control_excess(price, paths.index, horizon)
    return {
        "name": name,
        "horizon": horizon,
        "cooldown_trading_days": COOLDOWN_TRADING_DAYS,
        "n": int(len(paths)),
        "median_return": float(paths["fwd_return"].median()) if len(paths) else None,
        "mean_return": float(paths["fwd_return"].mean()) if len(paths) else None,
        "positive_rate": float((paths["fwd_return"] > 0).mean()) if len(paths) else None,
        "median_mae": float(paths["mae"].median()) if len(paths) else None,
        "median_mfe": float(paths["mfe"].median()) if len(paths) else None,
        "unconditional_median": base_median,
        "median_excess": float(np.median(vals) - base_median) if len(vals) else None,
        "bootstrap": boot,
        "eras": eras,
        "matched_control": matched,
        "event_dates": [str(d.date()) for d in paths.index],
    }


def threshold_stability(ratio: pd.Series, price: pd.Series, direction: str, thresholds: list[float], horizon: int) -> list[dict]:
    base_median = float(unconditional(price, horizon).median())
    rows = []
    for t in thresholds:
        mask = crossing_mask(ratio, t, direction)
        events = cooldown(mask, price.index)
        paths = path_stats(price, events[events].index, horizon)
        rows.append({
            "threshold": t,
            "n": int(len(paths)),
            "median_return": float(paths["fwd_return"].median()) if len(paths) else None,
            "positive_rate": float((paths["fwd_return"] > 0).mean()) if len(paths) else None,
            "median_excess": float(paths["fwd_return"].median() - base_median) if len(paths) else None,
        })
    return rows


def main() -> None:
    rng = np.random.default_rng(RNG_SEED)
    vix = fetch_fred("VIXCLS").rename("VIX")
    vix3m = fetch_fred("VXVCLS").rename("VIX3M")
    curve = pd.concat([vix, vix3m], axis=1).dropna()
    ratio = curve["VIX"] / curve["VIX3M"]

    spy = fetch_twelve_close("SPY")
    qqq = fetch_twelve_close("QQQ")

    strong_mask = crossing_mask(ratio, 1.10, "up")
    norm_mask = crossing_mask(ratio, 1.00, "down")

    candidates = {
        "SPY_5D_strong_inversion": summarize_candidate("SPY_5D_strong_inversion", spy, strong_mask, 5, rng),
        "QQQ_10D_normalization": summarize_candidate("QQQ_10D_normalization", qqq, norm_mask, 10, rng),
    }

    pvals = {k: v["bootstrap"]["p_one_sided"] for k, v in candidates.items()}
    qvals = bh_adjust(pvals)
    for k, q in qvals.items():
        candidates[k]["bootstrap"]["fdr_q"] = q

    stability = {
        "SPY_5D_strong_inversion": threshold_stability(ratio, spy, "up", [1.05, 1.075, 1.10, 1.125, 1.15], 5),
        "QQQ_10D_normalization": threshold_stability(ratio, qqq, "down", [0.975, 0.99, 1.00, 1.01, 1.025], 10),
    }

    def passes(c: dict) -> bool:
        recent = c["eras"]["2021-2026_recent"]
        valid = c["eras"]["2016-2020_validation"]
        ci_low = c["bootstrap"]["ci_low"]
        q = c["bootstrap"].get("fdr_q")
        matched = c["matched_control"]["matched_excess"]
        return bool(
            c["n"] >= 20
            and c["median_excess"] is not None and c["median_excess"] > 0
            and ci_low is not None and ci_low > 0
            and q is not None and q <= 0.05
            and matched is not None and matched > 0
            and valid["n"] >= 5 and valid["median_return"] is not None and valid["median_return"] > 0
            and recent["n"] >= 5 and recent["median_return"] is not None and recent["median_return"] > 0
        )

    verdicts = {k: ("GO" if passes(v) else "STOP") for k, v in candidates.items()}
    overall = "GO" if any(v == "GO" for v in verdicts.values()) else "STOP"

    result = {
        "methodology": {
            "primary_candidates_frozen_before_this_run": [
                "SPY 5D after VIX/VIX3M crosses above 1.10",
                "QQQ 10D after VIX/VIX3M crosses back below 1.00",
            ],
            "event_cooldown": f"one signal per {COOLDOWN_TRADING_DAYS + 1} trading days",
            "eras": ["2007-2015 development", "2016-2020 validation", "2021-2026 recent"],
            "bootstrap_resamples": BOOTSTRAPS,
            "multiple_testing": "Benjamini-Hochberg FDR across the two frozen primary hypotheses",
            "matched_control": "nearest non-event days by prior 5-day return; excludes event dates and +/-20 rows around each event",
            "important_caveat": "2021-2026 is not pristine human-blind OOS because the exploratory full-sample result was viewed before this falsification run",
        },
        "sample": {
            "curve_first": str(curve.index.min().date()),
            "curve_last": str(curve.index.max().date()),
            "curve_rows": int(len(curve)),
            "spy_first": str(spy.index.min().date()),
            "spy_last": str(spy.index.max().date()),
            "qqq_first": str(qqq.index.min().date()),
            "qqq_last": str(qqq.index.max().date()),
        },
        "candidates": candidates,
        "threshold_stability": stability,
        "verdicts": verdicts,
        "overall_verdict": overall,
    }

    out = Path("artifacts/vix_term_worthiness")
    out.mkdir(parents=True, exist_ok=True)
    (out / "vix_term_worthiness.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
