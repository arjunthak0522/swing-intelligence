#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "data/reentry/exhaustion_intraday_current.json"
HISTORY = ROOT / "data/reentry/skew_intraday_history.csv"
TARGET_DELTA = 0.25
MIN_DTE = 23
MAX_DTE = 37


def finite(x) -> bool:
    try:
        return x is not None and math.isfinite(float(x))
    except Exception:
        return False


def market_is_open(now: datetime) -> bool:
    now = now.astimezone(ET)
    if now.weekday() >= 5:
        return False
    m = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= m < 16 * 60


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def option_delta(spot: float, strike: float, t: float, iv: float, r: float, is_call: bool) -> float | None:
    if not all(finite(x) for x in (spot, strike, t, iv, r)) or min(spot, strike, t, iv) <= 0:
        return None
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t) / (iv * math.sqrt(t))
    return norm_cdf(d1) if is_call else norm_cdf(d1) - 1.0


def last_price(symbol: str) -> float:
    data = yf.download(symbol, period="1d", interval="5m", auto_adjust=False, progress=False, threads=False, timeout=20)
    if data.empty:
        raise ValueError(f"No intraday data for {symbol}")
    close = data["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = pd.to_numeric(close, errors="coerce").dropna()
    if close.empty:
        raise ValueError(f"No valid close for {symbol}")
    return float(close.iloc[-1])


def rate() -> float:
    try:
        return max(0.0, last_price("^IRX") / 100.0)
    except Exception:
        return 0.04


def choose_expiry(ticker: yf.Ticker, now: datetime) -> tuple[str, int]:
    candidates = []
    for exp in ticker.options:
        try:
            d = datetime.strptime(exp, "%Y-%m-%d").date()
        except ValueError:
            continue
        dte = (d - now.date()).days
        if MIN_DTE <= dte <= MAX_DTE:
            candidates.append((abs(dte - 30), dte, exp))
    if not candidates:
        raise ValueError("No SPX expiry between 23 and 37 DTE")
    _, dte, exp = min(candidates)
    return exp, dte


def select_25_delta(df: pd.DataFrame, spot: float, t: float, r: float, is_call: bool) -> dict:
    rows = []
    for _, row in df.iterrows():
        strike = row.get("strike")
        iv = row.get("impliedVolatility")
        bid = row.get("bid")
        ask = row.get("ask")
        if not (finite(strike) and finite(iv) and 0.01 < float(iv) < 5.0):
            continue
        if finite(bid) and finite(ask) and float(bid) <= 0 and float(ask) <= 0:
            continue
        delta = option_delta(spot, float(strike), t, float(iv), r, is_call)
        if delta is None:
            continue
        target = TARGET_DELTA if is_call else -TARGET_DELTA
        rows.append((abs(delta - target), row, delta))
    if not rows:
        raise ValueError("No valid option near 25-delta")
    _, row, delta = min(rows, key=lambda x: x[0])
    return {
        "strike": float(row["strike"]),
        "iv": float(row["impliedVolatility"]),
        "delta": float(delta),
        "bid": float(row["bid"]) if finite(row.get("bid")) else None,
        "ask": float(row["ask"]) if finite(row.get("ask")) else None,
    }


def official_skew_close() -> dict:
    hist = yf.download("^SKEW", period="2y", interval="1d", auto_adjust=False, progress=False, threads=False, timeout=20)
    if hist.empty:
        raise ValueError("No official SKEW history")
    close = hist["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = pd.to_numeric(close, errors="coerce").dropna()
    if close.empty:
        raise ValueError("No official SKEW closes")
    current = float(close.iloc[-1])
    pct = 100.0 * float((close <= current).sum()) / float(len(close))
    return {"value": current, "percentile_2y": pct, "sessions": int(len(close))}


def prior_live_proxy() -> float | None:
    if not HISTORY.exists():
        return None
    with HISTORY.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in reversed(rows):
        if finite(row.get("put_call_iv_spread_vol_points")):
            return float(row["put_call_iv_spread_vol_points"])
    return None


def append_history(row: dict) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    exists = HISTORY.exists()
    with HISTORY.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def main() -> None:
    now = datetime.now(timezone.utc).astimezone(ET)
    if not market_is_open(now):
        print(json.dumps({"status": "SKIPPED_OUTSIDE_REGULAR_SESSION", "timestamp_et": now.isoformat()}))
        return
    if not CURRENT.exists():
        raise SystemExit(f"Missing {CURRENT}")

    spx = yf.Ticker("^SPX")
    spot = last_price("^SPX")
    expiry, dte = choose_expiry(spx, now)
    chain = spx.option_chain(expiry)
    t = max(dte, 1) / 365.0
    r = rate()
    call25 = select_25_delta(chain.calls, spot, t, r, True)
    put25 = select_25_delta(chain.puts, spot, t, r, False)
    spread = (put25["iv"] - call25["iv"]) * 100.0
    ratio = put25["iv"] / call25["iv"] if call25["iv"] > 0 else None
    prior = prior_live_proxy()
    direction = "UNAVAILABLE"
    if finite(prior):
        delta = spread - float(prior)
        direction = "WIDENING" if delta > 0.10 else "NARROWING" if delta < -0.10 else "FLAT"

    official = official_skew_close()
    result = {
        "name": "S&P 500 Tail-Risk Pricing",
        "official_symbol": "SKEW",
        "provisional_intraday": True,
        "live_metric": "25-delta SPX put IV minus 25-delta SPX call IV",
        "live_proxy_vol_points": spread,
        "live_proxy_ratio": ratio,
        "direction_vs_prior_snapshot": direction,
        "spot": spot,
        "expiry": expiry,
        "dte": dte,
        "risk_free_rate": r,
        "put_25_delta": put25,
        "call_25_delta": call25,
        "official_skew_latest_close": official["value"],
        "official_skew_percentile_2y": official["percentile_2y"],
        "official_skew_history_sessions": official["sessions"],
        "source": "Yahoo Finance SPX option chain for live proxy; official SKEW daily close/history",
        "timestamp_et": now.isoformat(),
    }

    payload = json.loads(CURRENT.read_text(encoding="utf-8"))
    values = payload.setdefault("values", {})
    values["SKEW_LIVE_PROXY"] = spread
    values["SKEW_LIVE_PROXY_RATIO"] = ratio
    values["SKEW_DIRECTION"] = direction
    values["SKEW_OFFICIAL_CLOSE"] = official["value"]
    values["SKEW_OFFICIAL_PERCENTILE_2Y"] = official["percentile_2y"]
    payload["skew_live"] = result
    CURRENT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    append_history({
        "timestamp_et": now.isoformat(),
        "expiry": expiry,
        "dte": dte,
        "spot": spot,
        "put_call_iv_spread_vol_points": spread,
        "put_call_iv_ratio": ratio,
        "official_skew_close": official["value"],
        "official_skew_percentile_2y": official["percentile_2y"],
    })
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
