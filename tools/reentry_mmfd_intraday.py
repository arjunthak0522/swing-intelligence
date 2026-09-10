#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
import math
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "data/reentry/exhaustion_intraday_current.json"

NASDAQ_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
BATCH_SIZE = 180
MIN_VALID = 1200
MIN_COVERAGE = 0.55


def finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except Exception:
        return False


def market_is_open(now: datetime) -> bool:
    now_et = now.astimezone(ET) if now.tzinfo else now.replace(tzinfo=ET)
    if now_et.weekday() >= 5:
        return False
    minutes = now_et.hour * 60 + now_et.minute
    return 9 * 60 + 30 <= minutes < 16 * 60


def curl_text(url: str) -> str:
    result = subprocess.run(
        [
            "curl", "--location", "--compressed", "--silent", "--show-error", "--fail",
            "--max-time", "30",
            "--user-agent", "Mozilla/5.0 RE-ENTRY-mmfd-research/1.0",
            url,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=35,
    )
    if not result.stdout.strip():
        raise ValueError(f"Empty response from {url}")
    return result.stdout


def parse_pipe_file(text: str, symbol_field: str) -> list[str]:
    rows = []
    reader = csv.DictReader(io.StringIO(text), delimiter="|")
    for row in reader:
        if not row or str(row.get(symbol_field, "")).startswith("File Creation Time"):
            continue
        if str(row.get("Test Issue", "N")).strip().upper() == "Y":
            continue
        if str(row.get("ETF", "N")).strip().upper() == "Y":
            continue
        symbol = str(row.get(symbol_field, "")).strip()
        if not symbol:
            continue
        name = str(row.get("Security Name", "")).upper()
        if any(token in name for token in (" WARRANT", " WTS", " UNIT", " RIGHT", " PREFERRED")):
            continue
        if not re.fullmatch(r"[A-Z0-9.\-]+", symbol):
            continue
        rows.append(symbol.replace(".", "-"))
    return rows


def load_us_equity_universe() -> list[str]:
    nasdaq = parse_pipe_file(curl_text(NASDAQ_LISTED), "Symbol")
    other = parse_pipe_file(curl_text(OTHER_LISTED), "ACT Symbol")
    return sorted(set(nasdaq + other))


def extract_ticker_closes(frame: pd.DataFrame, ticker: str) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    if isinstance(frame.columns, pd.MultiIndex):
        if ticker in frame.columns.get_level_values(0):
            sub = frame[ticker]
            if "Close" in sub.columns:
                return pd.to_numeric(sub["Close"], errors="coerce").dropna()
        if ticker in frame.columns.get_level_values(-1):
            try:
                return pd.to_numeric(frame["Close"][ticker], errors="coerce").dropna()
            except Exception:
                pass
    if "Close" in frame.columns:
        return pd.to_numeric(frame["Close"], errors="coerce").dropna()
    return pd.Series(dtype=float)


def calculate_mmfd(universe: list[str], market_date: str) -> dict:
    above = 0
    valid = 0
    current_day_valid = 0
    failures = 0

    for start in range(0, len(universe), BATCH_SIZE):
        batch = universe[start:start + BATCH_SIZE]
        try:
            frame = yf.download(
                tickers=batch,
                period="10d",
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
                timeout=25,
            )
        except Exception:
            failures += len(batch)
            continue

        for ticker in batch:
            closes = extract_ticker_closes(frame, ticker)
            if len(closes) < 5:
                continue
            last_index = closes.index[-1]
            try:
                last_date = pd.Timestamp(last_index).date().isoformat()
            except Exception:
                last_date = ""
            if last_date != market_date:
                continue
            current_day_valid += 1
            last5 = closes.iloc[-5:]
            if len(last5) < 5 or last5.isna().any():
                continue
            current = float(last5.iloc[-1])
            ma5 = float(last5.mean())
            if not (finite(current) and finite(ma5) and ma5 > 0):
                continue
            valid += 1
            if current > ma5:
                above += 1

    coverage = valid / len(universe) if universe else 0.0
    if valid < MIN_VALID or coverage < MIN_COVERAGE:
        raise ValueError(
            f"Insufficient live universe coverage: valid={valid}, universe={len(universe)}, coverage={coverage:.3f}"
        )
    value = 100.0 * above / valid
    return {
        "formula_version": "MMFD_EQUIVALENT_ABOVE_LIVE_5DMA_v1",
        "provisional_intraday": True,
        "universe_source": "Nasdaq Trader nasdaqlisted + otherlisted",
        "universe_definition": "US listed non-ETF, non-test equities; obvious warrants/units/rights/preferreds excluded",
        "universe_size": len(universe),
        "current_day_bars": current_day_valid,
        "valid_5d_observations": valid,
        "above_5dma_count": above,
        "coverage_pct": coverage * 100.0,
        "mmfd_live": value,
        "reference_scale": {
            "extreme_oversold_below": 15.0,
            "oversold_below": 30.0,
            "neutral_center": 50.0,
            "strong_above": 70.0,
            "extreme_overbought_above": 85.0,
        },
        "failed_symbol_slots": failures,
    }


def fetch_vendor_mmfd() -> dict | None:
    url = f"https://stockcharts.com/quotebrain/quotes?s={quote('$MMFD')}&f=json&randomNumber={int(time.time()*1000)}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 RE-ENTRY-mmfd-validation/1.0"})
    with urlopen(req, timeout=20) as resp:  # nosec - fixed StockCharts endpoint
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload:
        return None
    row = payload[0]
    close = row.get("close")
    return {
        "value": float(close) if finite(close) else None,
        "as_of": (row.get("time") or {}).get("time"),
        "realtime": row.get("realtime"),
        "cached": row.get("cached"),
    }


def classify(value: float) -> str:
    if value < 15:
        return "EXTREME_OVERSOLD"
    if value < 30:
        return "OVERSOLD"
    if value <= 70:
        return "NORMAL"
    if value <= 85:
        return "STRONG"
    return "EXTREME_OVERBOUGHT"


def calculate_vvix(now: datetime) -> dict:
    intraday = yf.download(
        tickers="^VVIX",
        period="1d",
        interval="5m",
        auto_adjust=False,
        progress=False,
        threads=False,
        timeout=20,
    )
    intraday_close = extract_ticker_closes(intraday, "^VVIX")
    if intraday_close.empty:
        raise ValueError("No current VVIX intraday quote")
    current = float(intraday_close.iloc[-1])

    history = yf.download(
        tickers="^VVIX",
        period="2y",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
        timeout=20,
    )
    daily = extract_ticker_closes(history, "^VVIX")
    if daily.empty:
        raise ValueError("No VVIX daily history")
    dated = daily.copy()
    dated.index = pd.to_datetime(dated.index)
    completed = dated[dated.index.date < now.date()]
    if len(completed) < 100:
        raise ValueError(f"Insufficient VVIX history: {len(completed)} completed sessions")
    prior_close = float(completed.iloc[-1])
    percentile = 100.0 * float((completed <= current).sum()) / float(len(completed))
    delta = current - prior_close
    direction = "RISING" if delta > 0.25 else "FALLING" if delta < -0.25 else "FLAT"
    if percentile >= 95:
        state = "EXTREME_STRESS"
    elif percentile >= 80:
        state = "HIGH_STRESS"
    elif percentile >= 60:
        state = "ELEVATED"
    elif percentile >= 20:
        state = "NORMAL"
    else:
        state = "CALM"
    return {
        "symbol": "^VVIX",
        "name": "Volatility of VIX",
        "value": current,
        "prior_close": prior_close,
        "change_points_vs_prior_close": delta,
        "direction_vs_prior_close": direction,
        "historical_percentile_2y": percentile,
        "completed_history_sessions": int(len(completed)),
        "state": state,
        "provisional_intraday": True,
        "source": "Yahoo Finance intraday VVIX quote and daily history",
        "timestamp_et": now.isoformat(),
    }


def main() -> None:
    now = datetime.now(timezone.utc).astimezone(ET)
    if not market_is_open(now):
        print(json.dumps({"status": "SKIPPED_OUTSIDE_REGULAR_SESSION", "timestamp_et": now.isoformat()}))
        return
    if not CURRENT.exists():
        raise SystemExit(f"Missing {CURRENT}")

    market_date = now.date().isoformat()
    universe = load_us_equity_universe()
    result = calculate_mmfd(universe, market_date)
    value = float(result["mmfd_live"])
    result["state"] = classify(value)
    result["timestamp_et"] = now.isoformat()

    try:
        vendor = fetch_vendor_mmfd()
    except Exception as exc:
        vendor = {"error": f"{type(exc).__name__}: {exc}"}
    result["vendor_crosscheck"] = vendor
    if isinstance(vendor, dict) and finite(vendor.get("value")):
        result["difference_vs_vendor_points"] = value - float(vendor["value"])

    payload = json.loads(CURRENT.read_text(encoding="utf-8"))
    payload.setdefault("values", {})["MMFD"] = value
    payload["values"]["MMFD_STATE"] = result["state"]
    payload["mmfd_live"] = result

    try:
        vvix = calculate_vvix(now)
        payload["values"]["VVIX"] = vvix["value"]
        payload["values"]["VVIX_STATE"] = vvix["state"]
        payload["values"]["VVIX_PERCENTILE_2Y"] = vvix["historical_percentile_2y"]
        payload["values"]["VVIX_DIRECTION"] = vvix["direction_vs_prior_close"]
        payload["vvix_live"] = vvix
    except Exception as exc:
        payload["vvix_live"] = {"error": f"{type(exc).__name__}: {exc}", "timestamp_et": now.isoformat()}

    CURRENT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mmfd_live": result, "vvix_live": payload.get("vvix_live")}, indent=2))


if __name__ == "__main__":
    main()
