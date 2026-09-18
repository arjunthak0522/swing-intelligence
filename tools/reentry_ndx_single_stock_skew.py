#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from statistics import median
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

ET = ZoneInfo("America/New_York")
NASDAQ100_API = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
TARGET_DTE = 30
MIN_DTE = 21
MAX_DTE = 45
MIN_VALID_NAMES = 40
MIN_COVERAGE = 0.40
MIN_HISTORY_FOR_PERCENTILE = 20
CACHE_MINUTES = 55
MAX_WORKERS = 8


def finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except Exception:
        return False


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def option_delta(spot: float, strike: float, iv: float, dte: int, rate: float, put: bool) -> float | None:
    if not all(finite(v) for v in (spot, strike, iv, dte, rate)) or spot <= 0 or strike <= 0 or iv <= 0 or dte <= 0:
        return None
    t = dte / 365.0
    denom = iv * math.sqrt(t)
    if denom <= 0:
        return None
    d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * t) / denom
    call_delta = normal_cdf(d1)
    return call_delta - 1.0 if put else call_delta


def ndx_symbols() -> list[str]:
    req = Request(
        NASDAQ100_API,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nasdaq.com/market-activity/quotes/nasdaq-ndx-index",
        },
    )
    with urlopen(req, timeout=30) as resp:  # nosec - fixed Nasdaq endpoint
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    rows = (((payload.get("data") or {}).get("data") or {}).get("rows") or [])
    symbols = []
    for row in rows:
        symbol = str((row or {}).get("symbol") or "").strip().upper().replace(".", "-")
        if symbol and symbol not in {"NDX", "QQQ"}:
            symbols.append(symbol)
    symbols = sorted(set(symbols))
    if len(symbols) < 90:
        raise ValueError(f"Nasdaq-100 constituent feed unexpectedly small: {len(symbols)}")
    return symbols


def risk_free_rate() -> float:
    try:
        data = yf.download("^IRX", period="5d", interval="1d", auto_adjust=False, progress=False, threads=False, timeout=15)
        if isinstance(data.columns, pd.MultiIndex):
            series = data["Close"]["^IRX"] if "^IRX" in data["Close"] else data["Close"].iloc[:, 0]
        else:
            series = data["Close"]
        series = pd.to_numeric(series, errors="coerce").dropna()
        if not series.empty:
            return max(-0.01, min(0.20, float(series.iloc[-1]) / 100.0))
    except Exception:
        pass
    return 0.04


def latest_spot(ticker: yf.Ticker) -> float | None:
    try:
        info = ticker.fast_info
        for key in ("last_price", "previous_close"):
            value = info.get(key) if hasattr(info, "get") else getattr(info, key, None)
            if finite(value) and float(value) > 0:
                return float(value)
    except Exception:
        pass
    try:
        hist = ticker.history(period="5d", interval="1d", auto_adjust=False)
        close = pd.to_numeric(hist.get("Close"), errors="coerce").dropna()
        if not close.empty:
            return float(close.iloc[-1])
    except Exception:
        pass
    return None


def choose_expiry(expiries: tuple[str, ...] | list[str], now_date) -> tuple[str, int] | None:
    choices = []
    for raw in expiries:
        try:
            exp = datetime.strptime(str(raw), "%Y-%m-%d").date()
        except ValueError:
            continue
        dte = (exp - now_date).days
        if MIN_DTE <= dte <= MAX_DTE:
            choices.append((abs(dte - TARGET_DTE), dte, str(raw)))
    if not choices:
        return None
    _, dte, raw = min(choices)
    return raw, dte


def valid_chain(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty or "strike" not in frame or "impliedVolatility" not in frame:
        return pd.DataFrame()
    out = frame.copy()
    out["strike"] = pd.to_numeric(out["strike"], errors="coerce")
    out["impliedVolatility"] = pd.to_numeric(out["impliedVolatility"], errors="coerce")
    quote_ok = pd.Series(True, index=out.index)
    if "bid" in out and "ask" in out:
        bid = pd.to_numeric(out["bid"], errors="coerce").fillna(0)
        ask = pd.to_numeric(out["ask"], errors="coerce").fillna(0)
        quote_ok = (bid > 0) & (ask > 0) & (ask >= bid)
    elif "lastPrice" in out:
        quote_ok = pd.to_numeric(out["lastPrice"], errors="coerce").fillna(0) > 0
    out = out[
        out["strike"].gt(0)
        & out["impliedVolatility"].between(0.03, 5.0)
        & quote_ok
    ]
    return out


def nearest_delta_iv(frame: pd.DataFrame, spot: float, dte: int, rate: float, target: float, put: bool) -> tuple[float, float] | None:
    frame = valid_chain(frame)
    if frame.empty:
        return None
    best = None
    for row in frame.itertuples(index=False):
        strike = float(getattr(row, "strike"))
        iv = float(getattr(row, "impliedVolatility"))
        delta = option_delta(spot, strike, iv, dte, rate, put)
        if delta is None:
            continue
        gap = abs(delta - target)
        if best is None or gap < best[0]:
            best = (gap, iv, delta)
    if best is None:
        return None
    max_gap = 0.12 if abs(target) == 0.25 else 0.15
    if best[0] > max_gap:
        return None
    return float(best[1]), float(best[2])


def symbol_skew(symbol: str, rate: float, now_date) -> dict:
    ticker = yf.Ticker(symbol)
    spot = latest_spot(ticker)
    if not finite(spot) or float(spot) <= 0:
        raise ValueError("spot unavailable")
    expiry_choice = choose_expiry(ticker.options, now_date)
    if expiry_choice is None:
        raise ValueError("no listed expiry in 21-45 DTE window")
    expiry, dte = expiry_choice
    chain = ticker.option_chain(expiry)
    put25 = nearest_delta_iv(chain.puts, float(spot), dte, rate, -0.25, True)
    call25 = nearest_delta_iv(chain.calls, float(spot), dte, rate, 0.25, False)
    call50 = nearest_delta_iv(chain.calls, float(spot), dte, rate, 0.50, False)
    if not put25 or not call25 or not call50 or call50[0] <= 0:
        raise ValueError("required 25d/50d IV points unavailable")
    normalized = (put25[0] - call25[0]) / call50[0]
    if not finite(normalized) or abs(float(normalized)) > 2.0:
        raise ValueError("normalized skew failed sanity check")
    return {
        "symbol": symbol,
        "normalized_skew": float(normalized),
        "put25_iv": put25[0],
        "call25_iv": call25[0],
        "call50_iv": call50[0],
        "put25_delta": put25[1],
        "call25_delta": call25[1],
        "call50_delta": call50[1],
        "spot": float(spot),
        "expiry": expiry,
        "dte": int(dte),
    }


def read_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=ET)
    except ValueError:
        return None


def cached_today(rows: list[dict], market_date: str, now: datetime) -> dict | None:
    for row in reversed(rows):
        if row.get("market_date") != market_date:
            continue
        stamp = parse_time(row.get("timestamp_et"))
        if stamp is None:
            continue
        age = (now - stamp.astimezone(ET)).total_seconds() / 60.0
        value = row.get("raw_average")
        if age >= 0 and age < CACHE_MINUTES and finite(value):
            return row
    return None


def empirical_percentile(values: list[float], current: float) -> float | None:
    clean = [float(v) for v in values if finite(v)]
    if not clean:
        return None
    less = sum(v < current for v in clean)
    equal = sum(v == current for v in clean)
    return 100.0 * (less + 0.5 * equal) / len(clean)


def build_state(history_values: list[float], current: float) -> tuple[str, float | None, float | None]:
    sample_pct = empirical_percentile(history_values, current)
    reliable = len(history_values) >= MIN_HISTORY_FOR_PERCENTILE
    pct = sample_pct if reliable else None
    if not reliable:
        return "BUILDING_HISTORY", pct, sample_pct
    if pct is not None and pct <= 10:
        return "VERY_FLAT", pct, sample_pct
    if pct is not None and pct <= 25:
        return "FLAT", pct, sample_pct
    if pct is not None and pct >= 90:
        return "VERY_ELEVATED", pct, sample_pct
    if pct is not None and pct >= 75:
        return "ELEVATED", pct, sample_pct
    return "NORMAL", pct, sample_pct


def upsert_history(path: Path, row: dict) -> list[dict]:
    rows = read_history(path)
    replaced = False
    for i, existing in enumerate(rows):
        if existing.get("market_date") == row.get("market_date"):
            rows[i] = row
            replaced = True
            break
    if not replaced:
        rows.append(row)
    rows.sort(key=lambda r: (r.get("market_date") or "", r.get("timestamp_et") or ""))
    fields = []
    for r in rows:
        for key in r:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def card_from_row(row: dict, rows: list[dict], cached: bool = False) -> dict:
    current = float(row["raw_average"])
    historical = [float(r["raw_average"]) for r in rows if r.get("market_date") < row["market_date"] and finite(r.get("raw_average"))]
    state, pct, sample_pct = build_state(historical, current)
    prior = historical[-1] if historical else None
    direction = "RISING" if prior is not None and current > prior else "FALLING" if prior is not None and current < prior else "FLAT" if prior is not None else "UNAVAILABLE"
    return {
        "name": "Nasdaq-100 single-stock downside protection premium",
        "state": state,
        "direction": direction,
        "raw_average": current,
        "three_day_average": float(row["three_day_average"]) if finite(row.get("three_day_average")) else current,
        "history_percentile": pct,
        "sample_history_percentile": sample_pct,
        "history_sessions": len(historical) + 1,
        "minimum_reliable_history_sessions": MIN_HISTORY_FOR_PERCENTILE,
        "universe_size": int(float(row["universe_size"])),
        "valid_count": int(float(row["valid_count"])),
        "coverage_pct": float(row["coverage_pct"]),
        "median_dte": float(row["median_dte"]),
        "target_dte": TARGET_DTE,
        "formula": "equal-weight mean across valid NDX securities of (25-delta put IV - 25-delta call IV) / 50-delta call IV; display uses 3-session average",
        "benchmark": "Lower values mean investors are paying less extra premium for downside protection versus comparable upside options across Nasdaq-100 stocks. Percentile labels are withheld until at least 20 captured sessions; no proprietary threshold is assumed.",
        "meaning": "Measures how much extra option premium investors are paying for downside protection across individual Nasdaq-100 stocks. A very flat reading can indicate unusually little single-stock hedging demand even when broad index crash protection remains expensive.",
        "role": "LEADING_CONTEXT_ONLY",
        "decision_input": False,
        "creates_new_score": False,
        "changes_deploy_trigger": False,
        "changes_recovery_stage": False,
        "freshness_type": "FREE_OPTION_CHAIN_SNAPSHOT_WITH_3_SESSION_AVERAGE",
        "freshness_state": "CACHED_INTRADAY" if cached else "INTRADAY_DELAYED",
        "last_updated": row.get("timestamp_et"),
        "status": "READY" if state != "BUILDING_HISTORY" else "BUILDING_HISTORY",
        "source": "Nasdaq current Nasdaq-100 constituent feed + Yahoo Finance constituent option chains",
        "replication_status": "FREE_DATA_PROXY_NOT_GOLDMAN_EXACT",
        "validation_status": "LIVE_CONTEXT_ONLY_NO_FREE_HISTORICAL_OPTION_SURFACE",
        "validation_note": "Free sources do not provide a reliable historical constituent option-surface archive, so this cannot be backtested as an exact Goldman-series replica. It remains context only.",
    }


def calculate(market_date: str, stamp: str, history_path: Path) -> dict:
    now = datetime.now(ET)
    rows = read_history(history_path)
    cached = cached_today(rows, market_date, now)
    if cached is not None:
        return card_from_row(cached, rows, cached=True)

    symbols = ndx_symbols()
    rate = risk_free_rate()
    results = []
    errors = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="ndx-skew") as pool:
        futures = {pool.submit(symbol_skew, symbol, rate, now.date()): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                errors[symbol] = f"{type(exc).__name__}: {exc}"

    valid = len(results)
    coverage = valid / len(symbols) if symbols else 0.0
    if valid < MIN_VALID_NAMES or coverage < MIN_COVERAGE:
        raise ValueError(f"Insufficient NDX single-stock option coverage: {valid}/{len(symbols)} ({coverage:.1%})")
    values = [r["normalized_skew"] for r in results]
    dtes = [r["dte"] for r in results]
    raw_average = sum(values) / len(values)

    prior_rows = [r for r in rows if r.get("market_date") != market_date and finite(r.get("raw_average"))]
    prior_values = [float(r["raw_average"]) for r in prior_rows[-2:]]
    three_day_values = prior_values + [raw_average]
    three_day_average = sum(three_day_values) / len(three_day_values)
    row = {
        "market_date": market_date,
        "timestamp_et": stamp,
        "raw_average": raw_average,
        "three_day_average": three_day_average,
        "universe_size": len(symbols),
        "valid_count": valid,
        "coverage_pct": 100.0 * coverage,
        "median_dte": median(dtes),
        "risk_free_rate": rate,
        "error_count": len(errors),
    }
    updated_rows = upsert_history(history_path, row)
    card = card_from_row(row, updated_rows, cached=False)
    card["sample_symbols"] = sorted(r["symbol"] for r in results)[:12]
    card["error_count"] = len(errors)
    return card


def unavailable(error: Exception) -> dict:
    return {
        "name": "Nasdaq-100 single-stock downside protection premium",
        "state": "UNAVAILABLE",
        "direction": "UNAVAILABLE",
        "role": "LEADING_CONTEXT_ONLY",
        "decision_input": False,
        "creates_new_score": False,
        "changes_deploy_trigger": False,
        "changes_recovery_stage": False,
        "freshness_type": "FREE_OPTION_CHAIN_SNAPSHOT",
        "freshness_state": "UNAVAILABLE",
        "last_updated": None,
        "status": "UNAVAILABLE",
        "meaning": "Measures the downside-protection premium versus comparable upside options across Nasdaq-100 stocks when sufficient free option-chain coverage is available.",
        "source": "Nasdaq current Nasdaq-100 constituent feed + Yahoo Finance constituent option chains",
        "replication_status": "FREE_DATA_PROXY_NOT_GOLDMAN_EXACT",
        "validation_status": "LIVE_CONTEXT_ONLY_NO_FREE_HISTORICAL_OPTION_SURFACE",
        "error": f"{type(error).__name__}: {error}",
    }


def patch_snapshot(snapshot_path: Path, history_path: Path) -> dict:
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    unified = payload.get("unified_engine") or {}
    values = payload.get("values") or {}
    market_date = str(unified.get("market_date") or values.get("market_date") or "")
    stamp = str(unified.get("timestamp_et") or values.get("timestamp_et") or datetime.now(ET).isoformat())
    if not market_date:
        raise ValueError("Snapshot does not contain market_date")
    try:
        card = calculate(market_date, stamp, history_path)
        error = None
    except Exception as exc:
        card = unavailable(exc)
        error = card["error"]

    block = payload.get("leading_indicators")
    if not isinstance(block, dict):
        block = {
            "version": "REENTRY_LEADING_INDICATORS_v1",
            "timestamp_et": stamp,
            "market_date": market_date,
            "decision_input": False,
            "changes_deploy_trigger": False,
            "changes_recovery_stage": False,
            "creates_new_score": False,
            "purpose": "Context-only indicators; none can create, block, delay, or revoke DEPLOY.",
            "indicators": {},
            "errors": {},
        }
    block.setdefault("indicators", {})["ndx_single_stock_skew"] = card
    errors = block.setdefault("errors", {})
    if error:
        errors["ndx_single_stock_skew"] = error
    else:
        errors.pop("ndx_single_stock_skew", None)
    payload["leading_indicators"] = block
    if isinstance(unified, dict):
        unified["leading_indicators"] = block
        payload["unified_engine"] = unified
    snapshot_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return card


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--history", required=True)
    args = parser.parse_args()
    card = patch_snapshot(Path(args.snapshot), Path(args.history))
    print(json.dumps(card, indent=2))


if __name__ == "__main__":
    main()
