from __future__ import annotations

from io import StringIO
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
import time

import numpy as np
import pandas as pd

RNG_SEED = 20260903
BOOTSTRAPS = 5000
COOLDOWN = 10
ROUND_TRIP_COST = 0.001
INTERNALS = ["RSP","IWM","SMH","XLB","XLE","XLF","XLI","XLK","XLP","XLU","XLV","XLY"]
TARGETS = ["SPY","QQQ"]
HORIZONS = [3,5,7,10,20]


def fetch_fred(series_id: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    with urlopen(url, timeout=30) as resp:
        text = resp.read().decode("utf-8")
    df = pd.read_csv(StringIO(text))
    df.columns = ["date", series_id]
    df["date"] = pd.to_datetime(df["date"])
    df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
    return df.dropna().set_index("date")[series_id].sort_index()


def fetch_close(symbol: str, start: str = "2008-01-01") -> pd.Series:
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
    last = None
    for attempt in range(7):
        try:
            with urlopen(url, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("status") == "error" or "values" not in payload:
                msg = payload.get("message", f"No data for {symbol}")
                if "429" in msg or "rate" in msg.lower() or "minute" in msg.lower():
                    raise RuntimeError(msg)
                raise ValueError(msg)
            df = pd.DataFrame(payload["values"])
            df["datetime"] = pd.to_datetime(df["datetime"])
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            return df.dropna(subset=["close"]).set_index("datetime")["close"].sort_index().rename(symbol)
        except Exception as e:
            last = e
            if attempt == 6:
                break
            time.sleep(9 + attempt * 5)
    raise RuntimeError(f"Failed {symbol}: {last}")


def cool(mask: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    m = mask.reindex(idx).fillna(False).astype(bool)
    out = pd.Series(False, index=idx)
    last = -10000
    for i, flag in enumerate(m.to_numpy()):
        if flag and i - last > COOLDOWN:
            out.iloc[i] = True
            last = i
    return out


def build_state(px: pd.DataFrame, vix: pd.Series) -> pd.DataFrame:
    x = px.join(vix.rename("VIX"), how="inner").dropna(subset=["SPY","QQQ","VIX"])
    spy = x["SPY"]
    spy_dd20 = spy / spy.rolling(20, min_periods=20).max() - 1
    qqq_dd20 = x["QQQ"] / x["QQQ"].rolling(20, min_periods=20).max() - 1
    under20 = pd.DataFrame(index=x.index)
    under50 = pd.DataFrame(index=x.index)
    dd20 = pd.DataFrame(index=x.index)
    for s in INTERNALS:
        if s not in x:
            continue
        under20[s] = x[s] < x[s].rolling(20, min_periods=20).mean()
        under50[s] = x[s] < x[s].rolling(50, min_periods=50).mean()
        dd20[s] = x[s] / x[s].rolling(20, min_periods=20).max() - 1
    breadth20 = under20.mean(axis=1)
    breadth50 = under50.mean(axis=1)
    median_internal_dd20 = dd20.median(axis=1)

    # Frozen states aimed at correction depth, not crash-only events.
    mini = (spy_dd20 <= -0.02) & (spy_dd20 > -0.05) & (breadth20 >= 0.50)
    normal = (spy_dd20 <= -0.05) & (breadth20 >= 0.50)
    hidden = (spy_dd20 > -0.03) & (breadth20 >= (2/3)) & (median_internal_dd20 <= -0.05)

    # Stabilization/re-entry trigger: prior day in correction state, then market + internals improve and VIX falls.
    breadth_improves = breadth20.diff() <= -(1/len(INTERNALS))
    price_up = spy.pct_change() > 0
    vix_down = x["VIX"].pct_change() < 0

    for name, state in {"mini": mini, "normal": normal, "hidden": hidden}.items():
        x[f"state_{name}"] = state
        x[f"signal_{name}"] = state.shift(1).fillna(False) & breadth_improves & price_up & vix_down

    x["spy_dd20"] = spy_dd20
    x["qqq_dd20"] = qqq_dd20
    x["breadth20"] = breadth20
    x["breadth50"] = breadth50
    x["median_internal_dd20"] = median_internal_dd20
    return x


def path_stats(price: pd.Series, signal_dates: pd.DatetimeIndex, horizon: int) -> pd.DataFrame:
    rows = []
    idx = price.index
    for d in signal_dates:
        if d not in idx:
            continue
        i = idx.get_loc(d)
        if not isinstance(i, (int, np.integer)) or i + 1 + horizon >= len(idx):
            continue
        entry_i = i + 1
        entry = float(price.iloc[entry_i])
        exit_i = entry_i + horizon
        path = price.iloc[entry_i + 1: exit_i + 1].astype(float) / entry - 1
        gross = float(price.iloc[exit_i] / entry - 1)
        rows.append({
            "signal_date": d,
            "entry_date": idx[entry_i],
            "exit_date": idx[exit_i],
            "net_return": gross - ROUND_TRIP_COST,
            "mae": float(path.min()) if len(path) else 0.0,
            "mfe": float(path.max()) if len(path) else 0.0,
        })
    return pd.DataFrame(rows).set_index("signal_date") if rows else pd.DataFrame(columns=["net_return","mae","mfe"])


def bootstrap_excess(vals: np.ndarray, base: float, rng: np.random.Generator) -> dict:
    if len(vals) < 2:
        return {"ci_low":None,"ci_high":None,"p_one_sided":None}
    draws = rng.choice(vals, size=(BOOTSTRAPS, len(vals)), replace=True)
    ex = np.median(draws, axis=1) - base
    return {
        "ci_low": float(np.quantile(ex, .025)),
        "ci_high": float(np.quantile(ex, .975)),
        "p_one_sided": float((np.count_nonzero(ex <= 0)+1)/(BOOTSTRAPS+1)),
    }


def era(d: pd.Timestamp) -> str:
    if d.year <= 2015: return "2008-2015"
    if d.year <= 2020: return "2016-2020"
    return "2021-2026"


def matched_control(state: pd.DataFrame, price: pd.Series, events: pd.DatetimeIndex, horizon: int) -> dict:
    frame = state[["spy_dd20","breadth20"]].join(price.rename("px"), how="inner").dropna()
    frame["fwd"] = frame["px"].shift(-(horizon+1)) / frame["px"].shift(-1) - 1 - ROUND_TRIP_COST
    frame = frame.dropna()
    event_set = set(events)
    ev, ctl = [], []
    for d in events:
        if d not in frame.index: continue
        target_dd = float(frame.at[d,"spy_dd20"])
        target_b = float(frame.at[d,"breadth20"])
        candidates = frame.loc[~frame.index.isin(event_set)].copy()
        if candidates.empty: continue
        score = ((candidates["spy_dd20"]-target_dd)/0.02).abs() + ((candidates["breadth20"]-target_b)/0.20).abs()
        nearest = score.nsmallest(20).index
        ev.append(float(frame.at[d,"fwd"]))
        ctl.extend(candidates.loc[nearest,"fwd"].tolist())
    if not ev or not ctl:
        return {"event_median":None,"matched_median":None,"matched_excess":None}
    return {"event_median":float(np.median(ev)),"matched_median":float(np.median(ctl)),"matched_excess":float(np.median(ev)-np.median(ctl)),"event_n":len(ev),"control_n":len(ctl)}


def summarize(state: pd.DataFrame, symbol: str, signal: pd.Series, horizon: int, rng: np.random.Generator) -> dict:
    dedup = cool(signal, state.index)
    events = dedup[dedup].index
    paths = path_stats(state[symbol], events, horizon)
    base = (state[symbol].shift(-(horizon+1))/state[symbol].shift(-1)-1-ROUND_TRIP_COST).dropna()
    vals = paths["net_return"].to_numpy(dtype=float) if len(paths) else np.array([])
    base_med = float(base.median())
    eras = {}
    for e in ["2008-2015","2016-2020","2021-2026"]:
        sub = paths[[era(d)==e for d in paths.index]] if len(paths) else paths
        eras[e] = {"n":int(len(sub)),"median_return":float(sub["net_return"].median()) if len(sub) else None,"positive_rate":float((sub["net_return"]>0).mean()) if len(sub) else None}
    return {
        "n":int(len(paths)),
        "median_return":float(paths["net_return"].median()) if len(paths) else None,
        "positive_rate":float((paths["net_return"]>0).mean()) if len(paths) else None,
        "median_mae":float(paths["mae"].median()) if len(paths) else None,
        "median_mfe":float(paths["mfe"].median()) if len(paths) else None,
        "unconditional_median":base_med,
        "median_excess":float(np.median(vals)-base_med) if len(vals) else None,
        "bootstrap":bootstrap_excess(vals, base_med, rng),
        "eras":eras,
        "matched_control":matched_control(state, state[symbol], paths.index, horizon),
        "event_dates":[str(d.date()) for d in paths.index],
    }


def bh_adjust(pairs: dict[str,float|None]) -> dict[str,float|None]:
    valid = sorted([(k,p) for k,p in pairs.items() if p is not None], key=lambda z:z[1])
    m=len(valid); out={k:None for k in pairs}
    if not m: return out
    q=[min(1.0,p*m/(i+1)) for i,(_,p) in enumerate(valid)]
    for i in range(m-2,-1,-1): q[i]=min(q[i],q[i+1])
    for (k,_),v in zip(valid,q): out[k]=float(v)
    return out


def main() -> None:
    rng=np.random.default_rng(RNG_SEED)
    symbols=TARGETS+INTERNALS
    data={}
    for n,s in enumerate(symbols):
        data[s]=fetch_close(s)
        time.sleep(8)
    px=pd.concat(data.values(),axis=1,join="outer")
    vix=fetch_fred("VIXCLS")
    state=build_state(px,vix)

    results={}; pvals={}
    for correction in ["mini","normal","hidden"]:
        results[correction]={}
        signal=state[f"signal_{correction}"]
        for symbol in TARGETS:
            results[correction][symbol]={}
            for h in HORIZONS:
                r=summarize(state,symbol,signal,h,rng)
                results[correction][symbol][str(h)]=r
                pvals[f"{correction}_{symbol}_{h}"]=r["bootstrap"]["p_one_sided"]
    q=bh_adjust(pvals)
    statuses={}
    for correction in results:
        for symbol in results[correction]:
            for hs,r in results[correction][symbol].items():
                key=f"{correction}_{symbol}_{hs}"
                r["bootstrap"]["fdr_q"]=q[key]
                recent=r["eras"]["2021-2026"]
                good=(r["n"]>=20 and r["median_excess"] is not None and r["median_excess"]>0 and r["bootstrap"]["ci_low"] is not None and r["bootstrap"]["ci_low"]>0 and q[key] is not None and q[key] <= .10 and recent["n"]>=5 and recent["median_return"] is not None and recent["median_return"]>0 and r["matched_control"]["matched_excess"] is not None and r["matched_control"]["matched_excess"]>0)
                statuses[key]="GO" if good else "STOP"

    output={
        "methodology":{
            "goal":"time re-entry after mini, normal, and rolling/internal corrections",
            "internals_proxy":INTERNALS,
            "states":{
                "mini":"SPY 20D drawdown 2%-5% and >=50% internals below 20DMA",
                "normal":"SPY 20D drawdown >=5% and >=50% internals below 20DMA",
                "hidden":"SPY drawdown <3%, >=2/3 internals below 20DMA, median internal 20D drawdown >=5%",
            },
            "stabilization":"prior day in state; current day SPY up, VIX down, and at least 1/12 of internals recover above 20DMA",
            "execution":"signal close t; enter close t+1",
            "round_trip_cost":ROUND_TRIP_COST,
            "cooldown":COOLDOWN,
            "note":"ETF cross-section breadth proxy; not historical constituent breadth",
        },
        "sample":{"start":str(state.index.min().date()),"end":str(state.index.max().date()),"rows":int(len(state))},
        "signal_counts":{c:int(cool(state[f"signal_{c}"],state.index).sum()) for c in ["mini","normal","hidden"]},
        "results":results,
        "statuses":statuses,
    }
    out=Path("artifacts/reentry_worthiness"); out.mkdir(parents=True,exist_ok=True)
    (out/"reentry_worthiness.json").write_text(json.dumps(output,indent=2)+"\n")
    print(json.dumps(output,indent=2))

if __name__ == "__main__":
    main()
