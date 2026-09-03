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

BREADTH_URL = "https://tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv"
RNG_SEED = 20260903
BOOTSTRAPS = 10000
ROUND_TRIP_COST = 0.001
COOLDOWN = 15
HORIZONS = (3, 5, 7, 10)
PRIMARY_HORIZON = {"mini": 7, "normal": 10, "rolling": 7}


def fetch_csv(url: str) -> pd.DataFrame:
    with urlopen(url, timeout=30) as resp:  # nosec - fixed HTTPS source
        return pd.read_csv(StringIO(resp.read().decode("utf-8")))


def fetch_fred(series_id: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    df = fetch_csv(url)
    df.columns = ["date", series_id]
    df["date"] = pd.to_datetime(df["date"])
    df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
    return df.dropna().set_index("date")[series_id].sort_index()


def fetch_twelve_close(symbol: str, start: str = "2016-09-01") -> pd.Series:
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


def cooldown(mask: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    aligned = mask.reindex(index).fillna(False).astype(bool)
    keep = pd.Series(False, index=index)
    last = -10000
    for i, flag in enumerate(aligned.to_numpy()):
        if flag and i - last > COOLDOWN:
            keep.iloc[i] = True
            last = i
    return keep


def build_states(frame: pd.DataFrame, breadth_cut: float = 0.40, rebound: float = 0.03) -> dict[str, pd.Series]:
    dd20 = frame["SPY"] / frame["SPY"].rolling(20).max() - 1.0
    b50 = frame["B50"]
    b200 = frame["B200"]
    breadth_rebound = b50.diff() >= rebound
    stabilize = breadth_rebound & (frame["SPY"].pct_change() > 0) & (frame["VIX"].pct_change() < 0)

    prior_dd = dd20.shift(1)
    prior_b50 = b50.shift(1)
    prior_b200 = b200.shift(1)

    # Frozen categories aimed at re-entry after visible or internal corrections.
    mini_state = (prior_dd <= -0.02) & (prior_dd > -0.05) & (prior_b50 <= max(0.45, breadth_cut))
    normal_state = (prior_dd <= -0.05) & (prior_b50 <= breadth_cut)
    rolling_state = (prior_dd > -0.03) & (prior_b50 <= 0.35) & (prior_b200 <= 0.55)

    return {
        "mini": mini_state & stabilize,
        "normal": normal_state & stabilize,
        "rolling": rolling_state & stabilize,
    }


def trade_paths(price: pd.Series, signal_dates: pd.DatetimeIndex, horizon: int) -> pd.DataFrame:
    idx = price.index
    rows = []
    for signal in signal_dates:
        if signal not in idx:
            continue
        s = idx.get_loc(signal)
        if not isinstance(s, (int, np.integer)):
            continue
        entry_i = s + 1
        exit_i = entry_i + horizon
        if exit_i >= len(idx):
            continue
        entry = float(price.iloc[entry_i])
        path = price.iloc[entry_i + 1 : exit_i + 1].astype(float) / entry - 1.0
        gross = float(price.iloc[exit_i] / entry - 1.0)
        rows.append({
            "signal_date": signal,
            "entry_date": idx[entry_i],
            "exit_date": idx[exit_i],
            "net_return": gross - ROUND_TRIP_COST,
            "mae": float(path.min()) if len(path) else 0.0,
            "mfe": float(path.max()) if len(path) else 0.0,
        })
    if not rows:
        return pd.DataFrame(columns=["net_return", "mae", "mfe"])
    return pd.DataFrame(rows).set_index("signal_date")


def unconditional(price: pd.Series, horizon: int) -> pd.Series:
    # Same executable timing shape: hypothetical entry next close, hold h sessions, include costs.
    return (price.shift(-(horizon + 1)) / price.shift(-1) - 1.0 - ROUND_TRIP_COST).dropna()


def bootstrap(event_returns: np.ndarray, base_median: float, rng: np.random.Generator) -> dict:
    if len(event_returns) < 2:
        return {"ci_low": None, "ci_high": None, "p_one_sided": None}
    draws = rng.choice(event_returns, size=(BOOTSTRAPS, len(event_returns)), replace=True)
    ex = np.median(draws, axis=1) - base_median
    return {
        "ci_low": float(np.quantile(ex, 0.025)),
        "ci_high": float(np.quantile(ex, 0.975)),
        "p_one_sided": float((np.count_nonzero(ex <= 0) + 1) / (BOOTSTRAPS + 1)),
    }


def bh_adjust(pvals: dict[str, float | None]) -> dict[str, float | None]:
    valid = sorted([(k, p) for k, p in pvals.items() if p is not None and math.isfinite(p)], key=lambda x: x[1])
    out = {k: None for k in pvals}
    if not valid:
        return out
    m = len(valid)
    raw = [min(1.0, p * m / i) for i, (_, p) in enumerate(valid, 1)]
    for i in range(len(raw) - 2, -1, -1):
        raw[i] = min(raw[i], raw[i + 1])
    for (k, _), q in zip(valid, raw):
        out[k] = float(q)
    return out


def matched_controls(frame: pd.DataFrame, price: pd.Series, events: pd.DatetimeIndex, horizon: int) -> dict:
    dd = frame["SPY"] / frame["SPY"].rolling(20).max() - 1.0
    base = pd.DataFrame({"dd": dd, "b50": frame["B50"]}).reindex(price.index)
    fwd = price.shift(-(horizon + 1)) / price.shift(-1) - 1.0 - ROUND_TRIP_COST
    base["fwd"] = fwd
    base = base.dropna()
    event_set = set(events)
    ev, ctrl = [], []
    positions = {d: i for i, d in enumerate(base.index)}
    for d in events:
        if d not in base.index:
            continue
        pos = positions[d]
        candidates = base.copy()
        nearby = set(base.index[max(0, pos - 20): min(len(base), pos + 21)]) | event_set
        candidates = candidates.loc[~candidates.index.isin(nearby)]
        if candidates.empty:
            continue
        scale_dd = max(float(base["dd"].std()), 1e-6)
        scale_b = max(float(base["b50"].std()), 1e-6)
        dist = ((candidates["dd"] - base.at[d, "dd"]) / scale_dd) ** 2 + ((candidates["b50"] - base.at[d, "b50"]) / scale_b) ** 2
        nearest = dist.nsmallest(20).index
        ev.append(float(base.at[d, "fwd"]))
        ctrl.extend(candidates.loc[nearest, "fwd"].tolist())
    if not ev or not ctrl:
        return {"event_median": None, "matched_median": None, "matched_excess": None, "event_n": 0, "control_n": 0}
    return {
        "event_median": float(np.median(ev)),
        "matched_median": float(np.median(ctrl)),
        "matched_excess": float(np.median(ev) - np.median(ctrl)),
        "event_n": len(ev),
        "control_n": len(ctrl),
    }


def summarize(frame: pd.DataFrame, price: pd.Series, mask: pd.Series, horizon: int, rng: np.random.Generator) -> dict:
    dedup = cooldown(mask, price.index)
    events = dedup[dedup].index
    trades = trade_paths(price, events, horizon)
    vals = trades["net_return"].to_numpy(dtype=float) if len(trades) else np.array([])
    base = unconditional(price, horizon)
    base_median = float(base.median())
    eras = {}
    for name, start, end in [
        ("2016-2020", "2016-09-01", "2020-12-31"),
        ("2021-2026", "2021-01-01", "2026-12-31"),
    ]:
        sub = trades.loc[(trades.index >= start) & (trades.index <= end)] if len(trades) else trades
        eras[name] = {
            "n": int(len(sub)),
            "median_return": float(sub["net_return"].median()) if len(sub) else None,
            "positive_rate": float((sub["net_return"] > 0).mean()) if len(sub) else None,
            "median_mae": float(sub["mae"].median()) if len(sub) else None,
            "median_mfe": float(sub["mfe"].median()) if len(sub) else None,
        }
    return {
        "n": int(len(trades)),
        "median_return": float(np.median(vals)) if len(vals) else None,
        "positive_rate": float(np.mean(vals > 0)) if len(vals) else None,
        "median_mae": float(trades["mae"].median()) if len(trades) else None,
        "median_mfe": float(trades["mfe"].median()) if len(trades) else None,
        "unconditional_median": base_median,
        "median_excess": float(np.median(vals) - base_median) if len(vals) else None,
        "bootstrap": bootstrap(vals, base_median, rng),
        "matched_control": matched_controls(frame, price, trades.index, horizon),
        "eras": eras,
        "event_dates": [str(d.date()) for d in trades.index],
    }


def main() -> None:
    rng = np.random.default_rng(RNG_SEED)
    b = fetch_csv(BREADTH_URL)
    b["Date"] = pd.to_datetime(b["Date"])
    b = b.set_index("Date").sort_index()
    breadth = b[["Breadth_50_Index_Raw", "Breadth_Index_Raw"]].rename(columns={"Breadth_50_Index_Raw": "B50", "Breadth_Index_Raw": "B200"})
    spy = fetch_twelve_close("SPY")
    qqq = fetch_twelve_close("QQQ")
    vix = fetch_fred("VIXCLS").rename("VIX")
    frame = pd.concat([spy.rename("SPY"), qqq.rename("QQQ"), vix, breadth], axis=1).dropna()

    states = build_states(frame)
    results = {}
    primary_p = {}
    for state, mask in states.items():
        results[state] = {}
        for symbol in ("SPY", "QQQ"):
            results[state][symbol] = {}
            for h in HORIZONS:
                s = summarize(frame, frame[symbol], mask, h, rng)
                results[state][symbol][str(h)] = s
                if h == PRIMARY_HORIZON[state]:
                    primary_p[f"{state}_{symbol}_{h}D"] = s["bootstrap"]["p_one_sided"]

    qvals = bh_adjust(primary_p)
    for key, q in qvals.items():
        state, symbol, htag = key.split("_")
        h = htag.replace("D", "")
        results[state][symbol][h]["bootstrap"]["fdr_q_primary"] = q

    robustness = {}
    for label, cut, rebound in [("looser", 0.45, 0.02), ("primary", 0.40, 0.03), ("tighter", 0.35, 0.05)]:
        st = build_states(frame, breadth_cut=cut, rebound=rebound)
        robustness[label] = {}
        for state, mask in st.items():
            robustness[label][state] = {"events": int(cooldown(mask, frame.index).sum())}
            for symbol in ("SPY", "QQQ"):
                h = PRIMARY_HORIZON[state]
                tr = trade_paths(frame[symbol], cooldown(mask, frame.index)[lambda x: x].index, h)
                robustness[label][state][symbol] = {
                    "n": int(len(tr)),
                    "median_return": float(tr["net_return"].median()) if len(tr) else None,
                    "positive_rate": float((tr["net_return"] > 0).mean()) if len(tr) else None,
                }

    statuses = {}
    for state in states:
        h = PRIMARY_HORIZON[state]
        for symbol in ("SPY", "QQQ"):
            r = results[state][symbol][str(h)]
            recent = r["eras"]["2021-2026"]
            old = r["eras"]["2016-2020"]
            q = r["bootstrap"].get("fdr_q_primary")
            matched = r["matched_control"]["matched_excess"]
            ci = r["bootstrap"]["ci_low"]
            passed = bool(
                r["n"] >= 20
                and r["median_excess"] is not None and r["median_excess"] > 0
                and ci is not None and ci > 0
                and q is not None and q <= 0.10
                and matched is not None and matched > 0
                and old["n"] >= 5 and old["median_return"] is not None and old["median_return"] > 0
                and recent["n"] >= 5 and recent["median_return"] is not None and recent["median_return"] > 0
            )
            statuses[f"{state}_{symbol}_{h}D"] = "GO" if passed else "STOP"

    payload = {
        "methodology": {
            "breadth_source": BREADTH_URL,
            "breadth_history": [str(frame.index.min().date()), str(frame.index.max().date())],
            "mini": "prior SPY 20d drawdown 2-5%, <=45% of S&P stocks above 50DMA; then breadth +>=3pp, SPY up, VIX down",
            "normal": "prior SPY 20d drawdown >=5%, <=40% of S&P stocks above 50DMA; then breadth +>=3pp, SPY up, VIX down",
            "rolling": "prior SPY drawdown <3% while <=35% above 50DMA and <=55% above 200DMA; then breadth +>=3pp, SPY up, VIX down",
            "execution": "signal at close t, enter at close t+1",
            "round_trip_cost": ROUND_TRIP_COST,
            "cooldown_trading_days": COOLDOWN,
            "primary_horizons": PRIMARY_HORIZON,
            "other_horizons": list(HORIZONS),
            "multiple_testing": "BH FDR across six frozen primary state x instrument hypotheses",
            "caveat": "2016-2026 is historical validation, not pristine human-blind OOS",
        },
        "results": results,
        "robustness": robustness,
        "statuses": statuses,
    }
    out = Path("artifacts/true_breadth_reentry")
    out.mkdir(parents=True, exist_ok=True)
    (out / "true_breadth_reentry_worthiness.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
