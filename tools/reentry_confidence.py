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
CBOE_VIX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
CBOE_VIX3M_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv"
SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
ROUND_TRIP_COST = 0.001
K_ANALOGS = 40
EXCLUSION_SESSIONS = 20
HORIZONS = (5, 7, 10)
MIN_LIVE_BREADTH_NAMES = 450


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


def fetch_cboe_close(symbol: str, url: str) -> pd.Series:
    df = fetch_csv(url)
    date_col = next((c for c in df.columns if c.strip().lower() in {"date", "trade date", "tradedate"}), None)
    close_col = next((c for c in df.columns if c.strip().lower() in {"close", "closing value", "close value"}), None)
    if date_col is None or close_col is None:
        raise RuntimeError(f"Unexpected Cboe {symbol} schema: {list(df.columns)}")
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[close_col] = pd.to_numeric(df[close_col], errors="coerce")
    return df.dropna(subset=[date_col, close_col]).set_index(date_col)[close_col].sort_index().rename(symbol)


def fetch_volatility_history(symbol: str) -> tuple[pd.Series, str]:
    if symbol == "VIX":
        try:
            return fetch_cboe_close("VIX", CBOE_VIX_URL), "Cboe VIX daily history"
        except Exception:
            return fetch_fred("VIXCLS").rename("VIX"), "FRED VIXCLS fallback"
    if symbol == "VIX3M":
        try:
            return fetch_cboe_close("VIX3M", CBOE_VIX3M_URL), "Cboe VIX3M daily history"
        except Exception:
            return fetch_fred("VXVCLS").rename("VIX3M"), "FRED VXVCLS fallback"
    raise ValueError(symbol)


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


def _normalize_daily_index(obj):
    out = obj.copy()
    idx = pd.to_datetime(out.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    out.index = idx.normalize()
    return out[~out.index.duplicated(keep="last")].sort_index()


def fetch_yahoo_same_day_vol(target: pd.Timestamp) -> tuple[float, float]:
    """Fetch completed same-day VIX/VIX3M closes only as a live overlay."""
    import yfinance as yf

    raw = yf.download(
        ["^VIX", "^VIX3M"],
        period="1mo",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
        group_by="column",
    )
    if raw.empty:
        raise RuntimeError("Yahoo volatility overlay returned no rows")
    raw = _normalize_daily_index(raw)
    target = pd.Timestamp(target).normalize()
    if target not in raw.index:
        raise RuntimeError(f"Yahoo volatility overlay has no completed row for {target.date()}")

    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    if isinstance(close, pd.Series):
        raise RuntimeError("Yahoo volatility overlay schema missing both VIX series")
    vix = float(pd.to_numeric(close["^VIX"], errors="coerce").loc[target])
    vix3m = float(pd.to_numeric(close["^VIX3M"], errors="coerce").loc[target])
    if not np.isfinite(vix) or not np.isfinite(vix3m) or vix <= 0 or vix3m <= 0:
        raise RuntimeError("Yahoo volatility overlay returned invalid close values")
    return vix, vix3m


def current_sp500_symbols() -> list[str]:
    tables = pd.read_html(SP500_WIKI_URL, attrs={"id": "constituents"})
    if not tables or "Symbol" not in tables[0].columns:
        raise RuntimeError("Could not retrieve current S&P 500 constituent table")
    symbols = [str(x).strip().replace(".", "-") for x in tables[0]["Symbol"].dropna()]
    symbols = sorted(set(s for s in symbols if s))
    if len(symbols) < MIN_LIVE_BREADTH_NAMES:
        raise RuntimeError(f"Only {len(symbols)} S&P 500 constituents were retrieved")
    return symbols


def compute_same_day_breadth(target: pd.Timestamp) -> tuple[float, float, int, int]:
    """Compute only the current session breadth from today's actual constituents.

    Historical breadth remains the point-in-time precomputed series, so this live
    overlay does not retrospectively apply today's membership to history.
    """
    import yfinance as yf

    symbols = current_sp500_symbols()
    raw = yf.download(
        symbols,
        period="18mo",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw.empty:
        raise RuntimeError("Yahoo live breadth download returned no rows")
    raw = _normalize_daily_index(raw)
    target = pd.Timestamp(target).normalize()
    if target not in raw.index:
        raise RuntimeError(f"Live breadth prices have no completed row for {target.date()}")

    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" not in raw.columns.get_level_values(0):
            raise RuntimeError("Live breadth download has no Close field")
        closes = raw["Close"].copy()
    else:
        raise RuntimeError("Unexpected live breadth download schema")
    closes = closes.apply(pd.to_numeric, errors="coerce")
    closes = closes.loc[:target]
    ma50 = closes.rolling(50, min_periods=50).mean().loc[target]
    ma200 = closes.rolling(200, min_periods=200).mean().loc[target]
    latest = closes.loc[target]
    valid = latest.notna() & ma50.notna() & ma200.notna()
    valid_n = int(valid.sum())
    minimum = max(MIN_LIVE_BREADTH_NAMES, int(np.floor(len(symbols) * 0.90)))
    if valid_n < minimum:
        raise RuntimeError(
            f"Live breadth coverage insufficient: {valid_n}/{len(symbols)} valid; need at least {minimum}"
        )
    b50 = float((latest[valid] > ma50[valid]).mean())
    b200 = float((latest[valid] > ma200[valid]).mean())
    return b50, b200, valid_n, len(symbols)


def load_inputs() -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.DataFrame, dict]:
    b = fetch_csv(BREADTH_URL)
    b["Date"] = pd.to_datetime(b["Date"])
    b = b.set_index("Date").sort_index()
    breadth = b[["Breadth_50_Index_Raw", "Breadth_Index_Raw"]].rename(
        columns={"Breadth_50_Index_Raw": "B50", "Breadth_Index_Raw": "B200"}
    )
    spy = fetch_twelve_close("SPY")
    qqq = fetch_twelve_close("QQQ")
    vix, vix_source = fetch_volatility_history("VIX")
    vix3m, vix3m_source = fetch_volatility_history("VIX3M")
    meta = {
        "SPY": {"source": "Twelve Data", "latest": str(spy.index.max().date())},
        "QQQ": {"source": "Twelve Data", "latest": str(qqq.index.max().date())},
        "VIX": {"source": vix_source, "latest": str(vix.index.max().date())},
        "VIX3M": {"source": vix3m_source, "latest": str(vix3m.index.max().date())},
        "breadth": {"source": BREADTH_URL, "latest": str(breadth.index.max().date())},
        "live_overlay_used": False,
    }
    return spy, qqq, vix, vix3m, breadth, meta


def apply_live_overlays(
    target: pd.Timestamp,
    vix: pd.Series,
    vix3m: pd.Series,
    breadth: pd.DataFrame,
    meta: dict,
) -> tuple[pd.Series, pd.Series, pd.DataFrame, dict]:
    target = pd.Timestamp(target).normalize()

    if vix.index.max() < target or vix3m.index.max() < target:
        live_vix, live_vix3m = fetch_yahoo_same_day_vol(target)
        if vix.index.max() < target:
            vix.loc[target] = live_vix
            vix = vix.sort_index()
            meta["VIX"] = {"source": meta["VIX"]["source"] + " + Yahoo same-day overlay", "latest": str(target.date())}
        if vix3m.index.max() < target:
            vix3m.loc[target] = live_vix3m
            vix3m = vix3m.sort_index()
            meta["VIX3M"] = {"source": meta["VIX3M"]["source"] + " + Yahoo same-day overlay", "latest": str(target.date())}
        meta["live_overlay_used"] = True

    if breadth.index.max() < target:
        b50, b200, valid_n, universe_n = compute_same_day_breadth(target)
        breadth.loc[target, ["B50", "B200"]] = [b50, b200]
        breadth = breadth.sort_index()
        meta["breadth"] = {
            "source": "historical GitHub Pages + same-day current-constituent Yahoo overlay",
            "latest": str(target.date()),
            "valid_constituents": valid_n,
            "constituent_universe": universe_n,
        }
        meta["live_overlay_used"] = True

    return vix, vix3m, breadth, meta


def feature_frame(return_metadata: bool = False, require_same_day: bool = False):
    spy, qqq, vix, vix3m, breadth, meta = load_inputs()
    equity_target = min(spy.index.max(), qqq.index.max())

    if require_same_day:
        vix, vix3m, breadth, meta = apply_live_overlays(equity_target, vix, vix3m, breadth, meta)

    required_latest = {
        "SPY": spy.index.max(),
        "QQQ": qqq.index.max(),
        "VIX": vix.index.max(),
        "VIX3M": vix3m.index.max(),
        "breadth": breadth.index.max(),
    }
    if require_same_day:
        target = equity_target
        stale = {name: str(dt.date()) for name, dt in required_latest.items() if dt < target}
        if stale:
            raise RuntimeError(
                "Same-day input freshness check failed for equity session "
                f"{target.date()}: stale inputs={stale}. Refusing to emit a current re-entry signal."
            )
    else:
        target = min(required_latest.values())
        stale = {name: str(dt.date()) for name, dt in required_latest.items() if dt < equity_target}

    frame = pd.concat(
        [spy.loc[:target], qqq.loc[:target], vix.loc[:target], vix3m.loc[:target], breadth.loc[:target]],
        axis=1,
    ).dropna()
    if frame.empty or frame.index.max() != target:
        raise RuntimeError(
            f"Unable to construct feature row for {target.date()}; latest common row is "
            f"{None if frame.empty else frame.index.max().date()}"
        )

    frame["spy_dd20"] = frame["SPY"] / frame["SPY"].rolling(20).max() - 1.0
    frame["spy_ret5"] = frame["SPY"].pct_change(5)
    frame["b50_change1"] = frame["B50"].diff()
    frame["b50_change3"] = frame["B50"].diff(3)
    frame["vix_change5"] = frame["VIX"].pct_change(5)
    frame["curve_ratio"] = frame["VIX"] / frame["VIX3M"]
    frame = frame.dropna()
    if frame.index.max() != target:
        raise RuntimeError(f"Feature calculation lost target session {target.date()}")

    meta["equity_target_session"] = str(equity_target.date())
    meta["target_session"] = str(target.date())
    meta["same_day_required"] = require_same_day
    meta["same_day_complete"] = bool(target == equity_target and not stale)
    meta["stale_inputs_vs_equity_target"] = stale
    if return_metadata:
        return frame, meta
    return frame


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
    return price.shift(-(horizon + 1)) / price.shift(-1) - 1.0 - ROUND_TRIP_COST


def rank_scale(history: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = pd.DataFrame(index=history.index)
    for c in cols:
        out[c] = history[c].rank(method="average", pct=True)
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
    q7 = stats["QQQ"]["7"]
    s7 = stats["SPY"]["7"]
    best = q7 if q7["median_excess"] >= s7["median_excess"] else s7
    stressed = not state.startswith("no material correction")
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
    frame, freshness = feature_frame(return_metadata=True, require_same_day=True)
    target = frame.index.max()
    analogs = analogs_for_date(frame, target)
    stats = summarize_analogs(frame, analogs)
    state = empirical_state(frame.loc[target])
    label, interpretation = confidence_label(stats, state)
    current = frame.loc[target]
    payload = {
        "as_of": str(target.date()),
        "data_freshness": freshness,
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
        "closest_analog_dates": [str(d.date()) for d in analogs.index[:10]],
        "forward_outcomes": stats,
        "methodology": {
            "features": ["SPY 20d drawdown", "SPY 5d return", "% S&P above 50DMA", "% S&P above 200DMA", "1d/3d breadth change", "VIX 5d change", "VIX/VIX3M"],
            "normalization": "historical percentile ranks",
            "analog_selection": f"{K_ANALOGS} nearest prior dates",
            "lookahead_guard": f"prior data only; exclude latest {EXCLUSION_SESSIONS} sessions around target",
            "execution": "signal close t, hypothetical entry close t+1",
            "round_trip_cost": ROUND_TRIP_COST,
            "breadth_source": BREADTH_URL,
            "freshness_policy": "live mode anchors to latest completed SPY/QQQ session; lagging volatility/breadth publishers are overlaid from same-day completed market data; engine still fails closed if exact-session data cannot be built",
            "caveat": "historical breadth starts 2016-09; current-session breadth overlay uses current constituents only for the current date, never retrospectively",
        },
    }
    out = Path("artifacts/reentry_confidence")
    out.mkdir(parents=True, exist_ok=True)
    (out / "reentry_confidence.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
