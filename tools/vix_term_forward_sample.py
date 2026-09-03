from __future__ import annotations

from io import StringIO
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd


def fetch_fred(series_id: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    with urlopen(url, timeout=30) as resp:  # nosec - fixed HTTPS FRED endpoint
        text = resp.read().decode("utf-8")
    df = pd.read_csv(StringIO(text))
    df.columns = ["date", series_id]
    df["date"] = pd.to_datetime(df["date"])
    df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
    return df.dropna().set_index("date")[series_id].sort_index()


def fetch_twelve_close(symbol: str, start: str = "2008-01-01") -> pd.Series:
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


def event_rows(curve: pd.DataFrame) -> dict[str, pd.Series]:
    ratio = curve["VIX"] / curve["VIX3M"]
    prior = ratio.shift(1)
    return {
        "inversion_onset": (prior <= 1.0) & (ratio > 1.0),
        "strong_inversion_onset": (prior <= 1.10) & (ratio > 1.10),
        "normalization_cross": (prior > 1.0) & (ratio <= 1.0),
    }


def summarize(price: pd.Series, mask: pd.Series, horizons=(3, 5, 10, 20)) -> list[dict]:
    x = pd.concat([price.rename("px"), mask.rename("event")], axis=1).dropna(subset=["px"])
    x["event"] = x["event"].fillna(False)
    out = []
    for h in horizons:
        fwd = x["px"].shift(-h) / x["px"] - 1
        event_fwd = fwd[x["event"]].dropna()
        base = fwd.dropna()
        if event_fwd.empty:
            continue
        out.append({
            "horizon": h,
            "n": int(event_fwd.size),
            "median_return": float(event_fwd.median()),
            "mean_return": float(event_fwd.mean()),
            "positive_rate": float((event_fwd > 0).mean()),
            "unconditional_median": float(base.median()),
            "unconditional_positive_rate": float((base > 0).mean()),
            "median_excess": float(event_fwd.median() - base.median()),
        })
    return out


def main() -> None:
    vix = fetch_fred("VIXCLS").rename("VIX")
    vix3m = fetch_fred("VXVCLS").rename("VIX3M")
    curve = pd.concat([vix, vix3m], axis=1).dropna()
    masks = event_rows(curve)

    prices = {
        "SPY": fetch_twelve_close("SPY"),
        "QQQ": fetch_twelve_close("QQQ"),
    }

    result = {
        "methodology": {
            "curve": "VIXCLS / VXVCLS (30-day VIX vs 3-month VIX)",
            "event_definitions": {
                "inversion_onset": "ratio crosses from <=1.00 to >1.00",
                "strong_inversion_onset": "ratio crosses from <=1.10 to >1.10",
                "normalization_cross": "ratio crosses from >1.00 to <=1.00",
            },
            "forward_return": "close-to-close from event date to h trading days later",
            "purpose": "exploratory event-study sample; not a validated trading strategy",
        },
        "sample": {
            "first_curve_date": str(curve.index.min().date()),
            "last_curve_date": str(curve.index.max().date()),
            "curve_rows": int(len(curve)),
        },
        "results": {},
    }

    for event_name, mask in masks.items():
        result["results"][event_name] = {}
        for symbol, price in prices.items():
            result["results"][event_name][symbol] = summarize(price, mask)

    out = Path("artifacts/vix_term_sample")
    out.mkdir(parents=True, exist_ok=True)
    (out / "vix_term_forward_returns.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
