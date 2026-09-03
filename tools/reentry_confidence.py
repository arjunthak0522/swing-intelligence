from __future__ import annotations

from io import StringIO
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd

BREADTH_URL = "https://tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv"
ROUND_TRIP_COST = 0.001
K_ANALOGS = 40
EXCLUSION_SESSIONS = 20
HORIZONS = (5, 7, 10)


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


def feature_frame() -> pd.DataFrame:
    b = fetch_csv(BREADTH_URL)
    b["Date"] = pd.to_datetime(b["Date"])
    b = b.set_index("Date").sort_index()
    breadth = b[["Breadth_50_Index_Raw", "Breadth_Index_Raw"]].rename(
        columns={"Breadth_50_Index_Raw": "B50", "Breadth_Index_Raw": "B200"}
    )
    spy = fetch_twelve_close("SPY")
    qqq = fetch_twelve_close("QQQ")
    vix = fetch_fred("VIXCLS").rename("VIX")
    vix3m = fetch_fred("VXVCLS").rename("VIX3M")
    frame = pd.concat([spy, qqq, vix, vix3m, breadth], axis=1).dropna()

    frame["spy_dd20"] = frame["SPY"] / frame["SPY"].rolling(20).max() - 1.0
    frame["spy_ret5"] = frame["SPY"].pct_change(5)
    frame["b50_change1"] = frame["B50"].diff()
    frame["b50_change3"] = frame["B50"].diff(3)
    frame["vix_change5"] = frame["VIX"].pct_change(5)
    frame["curve_ratio"] = frame["VIX"] / frame["VIX3M"]
    return frame.dropna()


def empirical_state(row: pd.Series) -> str:
    dd = float(row["spy_dd20"])
    b50 = float(row["B50"])
    b200 = float(row["B200"])
    b1 = float(row["b50_change1"])
    vix5 = float(row["vix_change5"])
    curve = float(row["curve_ratio"])

    if dd <= -0.05:
        base = "normal correction"
    elif dd <= -0.02:
        base = "mini correction"
    elif b50 <= 0.35 and b200 <= 0.55:
        base = "rolling/internal correction"
    else:
        base = "no material correction"

    if b1 > 0 and vix5 <= 0 and curve <= 1.0:
        phase = "stabilizing"
    elif b1 > 0:
        phase = "breadth improving"
    elif b50 <= 0.40 or vix5 > 0.15 or curve > 1.0:
        phase = "still stressed"
    else:
        phase = "neutral"
    return f"{base} / {phase}"


def forward_return(price: pd.Series, horizon: int) -> pd.Series:
    # Decision at close t, implementation at close t+1, hold h sessions, cost included.
    return price.shift(-(horizon + 1)) / price.shift(-1) - 1.0 - ROUND_TRIP_COST


def rank_scale(history: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = pd.DataFrame(index=history.index)
    for c in cols:
        ranks = history[c].rank(method="average", pct=True)
        out[c] = ranks
    return out


def analogs_for_date(frame: pd.DataFrame, target_date: pd.Timestamp) -> pd.DataFrame:
    cols = ["spy_dd20", "spy_ret5", "B50", "B200", "b50_change1", "b50_change3", "vix_change5", "curve_ratio"]
    if target_date not in frame.index:
        raise KeyError(target_date)
    pos = frame.index.get_loc(target_date)
    cutoff = pos - EXCLUSION_SESSIONS
    if cutoff <= K_ANALOGS:
        raise RuntimeError("Insufficient trailing history for analog analysis")
    hist = frame.iloc[:cutoff].copy()
    combo = pd.concat([hist[cols], frame.loc[[target_date], cols]])
    scaled = rank_scale(combo, cols)
    target = scaled.loc[target_date]
    dist = ((scaled.loc[hist.index] - target) ** 2).mean(axis=1) ** 0.5
    nearest = dist.nsmallest(min(K_ANALOGS, len(dist))).index
    result = hist.loc[nearest].copy()
    result["distance"] = dist.loc[nearest]
    return result.sort_values("distance")


def summarize_analogs(frame: pd.DataFrame, analogs: pd.DataFrame) -> dict:
    output: dict[str, dict] = {}
    for symbol in ("SPY", "QQQ"):
        output[symbol] = {}
        for h in HORIZONS:
            fwd = forward_return(frame[symbol], h).reindex(analogs.index).dropna()
            unconditional = forward_return(frame[symbol], h).loc[: analogs.index.max()].dropna()
            med = float(fwd.median())
            base = float(unconditional.median())
            output[symbol][str(h)] = {
                "n": int(len(fwd)),
                "median_return": med,
                "positive_rate": float((fwd > 0).mean()),
                "unconditional_median": base,
                "median_excess": med - base,
                "p25": float(fwd.quantile(0.25)),
                "p75": float(fwd.quantile(0.75)),
            }
    return output


def confidence_label(stats: dict, state: str) -> tuple[str, str]:
    # Decision thresholds are frozen policy thresholds, not optimized to the sample.
    q7 = stats["QQQ"]["7"]
    s7 = stats["SPY"]["7"]
    best = q7 if q7["median_excess"] >= s7["median_excess"] else s7
    stressed = "correction" in state
    if stressed and best["n"] >= 30 and best["positive_rate"] >= 0.65 and best["median_excess"] >= 0.005 and best["p25"] > -0.015:
        return "STRONG", "historically favorable re-entry environment"
    if stressed and best["n"] >= 25 and best["positive_rate"] >= 0.60 and best["median_excess"] >= 0.0025:
        return "FAVORABLE", "historical analogs lean toward re-entry"
    if stressed and best["median_excess"] > 0 and best["positive_rate"] >= 0.55:
        return "IMPROVING", "conditions are improving but evidence is not yet strong"
    if stressed:
        return "POOR", "historical analogs do not yet support aggressive re-entry"
    return "NEUTRAL", "no material correction is currently present"


def main() -> None:
    frame = feature_frame()
    target = frame.index.max()
    analogs = analogs_for_date(frame, target)
    stats = summarize_analogs(frame, analogs)
    state = empirical_state(frame.loc[target])
    label, interpretation = confidence_label(stats, state)

    top_dates = [str(d.date()) for d in analogs.index[:10]]
    current = frame.loc[target]
    payload = {
        "as_of": str(target.date()),
        "framework": "empirical historical analogs; not a claim of proven alpha",
        "current_state": state,
        "confidence": label,
        "interpretation": interpretation,
        "current_inputs": {
            "spy_drawdown_20d": float(current["spy_dd20"]),
            "spy_return_5d": float(current["spy_ret5"]),
            "pct_sp500_above_50dma": float(current["B50"]),
            "pct_sp500_above_200dma": float(current["B200"]),
            "breadth_1d_change": float(current["b50_change1"]),
            "breadth_3d_change": float(current["b50_change3"]),
            "vix_5d_change": float(current["vix_change5"]),
            "vix_vix3m_ratio": float(current["curve_ratio"]),
        },
        "analog_count": int(len(analogs)),
        "closest_analog_dates": top_dates,
        "forward_outcomes": stats,
        "methodology": {
            "features": ["SPY 20d drawdown", "SPY 5d return", "% S&P above 50DMA", "% S&P above 200DMA", "1d/3d breadth change", "VIX 5d change", "VIX/VIX3M"],
            "normalization": "historical percentile ranks",
            "analog_selection": f"{K_ANALOGS} nearest prior dates",
            "lookahead_guard": f"prior data only; exclude latest {EXCLUSION_SESSIONS} sessions around target",
            "execution": "signal close t, hypothetical entry close t+1",
            "round_trip_cost": ROUND_TRIP_COST,
            "breadth_source": BREADTH_URL,
            "caveat": "breadth history starts 2016-09; output is a decision-support analog framework, not a statistically proven standalone trading strategy",
        },
    }
    out = Path("artifacts/reentry_confidence")
    out.mkdir(parents=True, exist_ok=True)
    (out / "reentry_confidence.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
