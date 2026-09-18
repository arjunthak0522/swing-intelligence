#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd
import yfinance as yf

NASDAQ_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
BATCH_SIZE = 150
MAX_BATCH_WORKERS = 8
MIN_NASDAQ_VALID = 500
MIN_ZBT_SESSIONS = 10
MIN_VELOCITY_HISTORY = 20


def finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except Exception:
        return False


def as_float(value):
    return float(value) if finite(value) else None


def ticker_close(frame: pd.DataFrame, ticker: str) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    if isinstance(frame.columns, pd.MultiIndex):
        for getter in (lambda: frame["Close"][ticker], lambda: frame[ticker]["Close"]):
            try:
                return pd.to_numeric(getter(), errors="coerce").dropna()
            except Exception:
                pass
        return pd.Series(dtype=float)
    if "Close" in frame.columns:
        return pd.to_numeric(frame["Close"], errors="coerce").dropna()
    return pd.Series(dtype=float)


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def daily_last(rows: list[dict], key: str) -> dict[str, float]:
    by_day: dict[str, float] = {}
    for row in rows:
        day = row.get("market_date")
        value = as_float(row.get(key))
        if day and value is not None:
            by_day[day] = value
    return by_day


def breadth_ratio_series(rows: list[dict], current_values: dict, market_date: str | None) -> pd.Series:
    by_day: dict[str, float] = {}
    for row in rows:
        day = row.get("market_date")
        adv = as_float(row.get("NAADV"))
        dec = as_float(row.get("NADEC"))
        if not day or adv is None or dec is None or adv + dec <= 0:
            continue
        by_day[day] = adv / (adv + dec)
    adv = as_float(current_values.get("NAADV"))
    dec = as_float(current_values.get("NADEC"))
    if market_date and adv is not None and dec is not None and adv + dec > 0:
        by_day[market_date] = adv / (adv + dec)
    if not by_day:
        return pd.Series(dtype=float)
    series = pd.Series(by_day, dtype=float)
    series.index = pd.to_datetime(series.index)
    return series.sort_index()


def zweig_breadth_thrust(rows: list[dict], values: dict, market_date: str | None, stamp: str | None) -> dict:
    raw = breadth_ratio_series(rows, values, market_date)
    if raw.empty:
        raise ValueError("Nasdaq advance/decline history is unavailable")
    ema10 = raw.ewm(span=10, adjust=False).mean()
    current = float(ema10.iloc[-1])
    sessions = len(ema10)
    enough = sessions >= MIN_ZBT_SESSIONS
    recent = ema10.tail(10)
    recent_low = float(recent.min()) if not recent.empty else None
    triggered = bool(enough and recent_low is not None and recent_low <= 0.40 and current >= 0.615)
    if not enough:
        state = "BUILDING_HISTORY"
    elif triggered:
        state = "THRUST_TRIGGERED"
    elif current >= 0.615:
        state = "STRONG_PARTICIPATION"
    elif current >= 0.55:
        state = "BUILDING"
    elif current <= 0.40:
        state = "WASHED_OUT"
    else:
        state = "NEUTRAL"
    return {
        "name": "Rapid breadth participation surge",
        "state": state,
        "current_10d_ema": current,
        "current_raw_advance_share": float(raw.iloc[-1]),
        "recent_10_session_low_ema": recent_low,
        "session_count": sessions,
        "minimum_sessions": MIN_ZBT_SESSIONS,
        "triggered": triggered,
        "direction": "RISING" if len(ema10) >= 2 and ema10.iloc[-1] > ema10.iloc[-2] else "FALLING" if len(ema10) >= 2 and ema10.iloc[-1] < ema10.iloc[-2] else "FLAT",
        "benchmark": "Classic breadth-thrust watch: the 10-day average of advancing-stock share moves from 40% or less to 61.5% or more within 10 trading sessions.",
        "meaning": "Looks for a rapid shift from broad selling to broad participation. It can turn before price-based trend confirmation.",
        "role": "LEADING_CONTEXT_ONLY",
        "decision_input": False,
        "freshness_type": "INTRADAY_SNAPSHOT_PLUS_CAPTURED_HISTORY",
        "last_updated": stamp,
        "status": "READY" if enough else "BUILDING_HISTORY",
        "source": "RE-ENTRY captured Nasdaq advancing/declining issues",
    }


def empirical_percentile(sample: list[float], current: float | None) -> float | None:
    if current is None or not sample:
        return None
    vals = [float(v) for v in sample if finite(v)]
    if not vals:
        return None
    less = sum(v < current for v in vals)
    equal = sum(v == current for v in vals)
    return 100.0 * (less + 0.5 * equal) / len(vals)


def mcclellan_velocity(rows: list[dict], values: dict, market_date: str | None, stamp: str | None) -> dict:
    by_day = daily_last(rows, "NAMO")
    current = as_float(values.get("NAMO"))
    if market_date and current is not None:
        by_day[market_date] = current
    days = sorted(by_day)
    vals = [by_day[d] for d in days]
    if not vals:
        raise ValueError("NAMO history is unavailable")
    delta1 = vals[-1] - vals[-2] if len(vals) >= 2 else None
    delta3 = vals[-1] - vals[-4] if len(vals) >= 4 else None
    changes = [vals[i] - vals[i - 1] for i in range(1, len(vals))]
    pct = empirical_percentile(changes, delta1)
    reliable = len(changes) >= MIN_VELOCITY_HISTORY
    published_pct = pct if reliable else None
    if delta1 is None:
        state = "BUILDING_HISTORY"
        direction = "UNAVAILABLE"
    elif delta1 > 0:
        state = "TURNING_UP"
        direction = "RISING"
    elif delta1 < 0:
        state = "TURNING_DOWN"
        direction = "FALLING"
    else:
        state = "FLAT"
        direction = "FLAT"
    return {
        "name": "Nasdaq breadth momentum speed",
        "state": state,
        "current_namo": vals[-1],
        "change_1_session": delta1,
        "change_3_sessions": delta3,
        "velocity_percentile": published_pct,
        "sample_velocity_percentile": pct,
        "history_sessions": len(vals),
        "minimum_reliable_velocity_sessions": MIN_VELOCITY_HISTORY,
        "direction": direction,
        "benchmark": "A positive change means Nasdaq breadth momentum is improving. A reliable historical percentile is shown only after 20 captured changes.",
        "meaning": "Measures how quickly Nasdaq participation momentum is repairing instead of waiting for a slower cumulative breadth trend to confirm.",
        "role": "LEADING_CONTEXT_ONLY",
        "decision_input": False,
        "freshness_type": "INTRADAY_SNAPSHOT_PLUS_CAPTURED_HISTORY",
        "last_updated": stamp,
        "status": "RELIABLE" if reliable else "BUILDING_HISTORY",
        "source": "RE-ENTRY NAMO capture history",
    }


def load_nasdaq_symbols() -> list[str]:
    req = Request(NASDAQ_LISTED, headers={"User-Agent": "Mozilla/5.0 RE-ENTRY-leading-indicators/1.0"})
    with urlopen(req, timeout=30) as resp:  # nosec - fixed Nasdaq Trader endpoint
        raw = resp.read().decode("utf-8", errors="replace")
    symbols: list[str] = []
    for row in csv.DictReader(io.StringIO(raw), delimiter="|"):
        if not row or str(row.get("Symbol", "")).startswith("File Creation Time"):
            continue
        if str(row.get("Test Issue", "N")).strip().upper() == "Y" or str(row.get("ETF", "N")).strip().upper() == "Y":
            continue
        symbol = str(row.get("Symbol", "")).strip()
        name = str(row.get("Security Name", "")).upper()
        if not symbol or any(token in name for token in (" WARRANT", " WTS", " UNIT", " RIGHT", " PREFERRED")):
            continue
        if not re.fullmatch(r"[A-Z0-9.\-]+", symbol):
            continue
        symbols.append(symbol.replace(".", "-"))
    return sorted(set(symbols))


def short_breadth_batch(batch: list[str], cutoff: pd.Timestamp | None) -> tuple[dict, pd.Timestamp | None]:
    counts = {
        5: {"above": 0, "valid": 0, "prior_above": 0, "prior_valid": 0},
        10: {"above": 0, "valid": 0, "prior_above": 0, "prior_valid": 0},
    }
    latest_date = None
    try:
        frame = yf.download(batch, period="1mo", interval="1d", group_by="ticker", auto_adjust=True, progress=False, threads=False, timeout=25)
    except Exception:
        return counts, None
    for ticker in batch:
        closes = ticker_close(frame, ticker)
        if closes.empty:
            continue
        closes.index = pd.to_datetime(closes.index)
        if cutoff is not None:
            closes = closes.loc[closes.index.normalize() <= cutoff.normalize()]
        if closes.empty:
            continue
        latest_date = max(latest_date, closes.index[-1]) if latest_date is not None else closes.index[-1]
        for length in (5, 10):
            if len(closes) >= length:
                current = float(closes.iloc[-1])
                ma = float(closes.iloc[-length:].mean())
                if finite(current) and finite(ma) and ma > 0:
                    counts[length]["valid"] += 1
                    if current > ma:
                        counts[length]["above"] += 1
            if len(closes) >= length + 1:
                prior = float(closes.iloc[-2])
                prior_ma = float(closes.iloc[-(length + 1):-1].mean())
                if finite(prior) and finite(prior_ma) and prior_ma > 0:
                    counts[length]["prior_valid"] += 1
                    if prior > prior_ma:
                        counts[length]["prior_above"] += 1
    return counts, latest_date


def nasdaq_short_breadth(market_date: str | None) -> dict:
    symbols = load_nasdaq_symbols()
    if len(symbols) < 1000:
        raise ValueError(f"Nasdaq universe unexpectedly small: {len(symbols)}")
    totals = {
        5: {"above": 0, "valid": 0, "prior_above": 0, "prior_valid": 0},
        10: {"above": 0, "valid": 0, "prior_above": 0, "prior_valid": 0},
    }
    cutoff = pd.Timestamp(market_date) if market_date else None
    latest_date = None
    batches = [symbols[start:start + BATCH_SIZE] for start in range(0, len(symbols), BATCH_SIZE)]
    with ThreadPoolExecutor(max_workers=MAX_BATCH_WORKERS, thread_name_prefix="nasdaq-short-breadth") as pool:
        futures = [pool.submit(short_breadth_batch, batch, cutoff) for batch in batches]
        for future in as_completed(futures):
            counts, batch_latest = future.result()
            if batch_latest is not None:
                latest_date = max(latest_date, batch_latest) if latest_date is not None else batch_latest
            for length in (5, 10):
                for key in ("above", "valid", "prior_above", "prior_valid"):
                    totals[length][key] += counts[length][key]
    for length in (5, 10):
        if totals[length]["valid"] < MIN_NASDAQ_VALID:
            raise ValueError(f"Insufficient Nasdaq {length}DMA breadth coverage: {totals[length]['valid']}/{len(symbols)}")
    out = {}
    for length in (5, 10):
        cur = 100.0 * totals[length]["above"] / totals[length]["valid"]
        prior = 100.0 * totals[length]["prior_above"] / totals[length]["prior_valid"] if totals[length]["prior_valid"] else None
        change = cur - prior if prior is not None else None
        out[f"above_{length}dma_pct"] = cur
        out[f"prior_above_{length}dma_pct"] = prior
        out[f"change_{length}dma_points"] = change
        out[f"valid_{length}dma"] = totals[length]["valid"]
    five = out["above_5dma_pct"]
    ten = out["above_10dma_pct"]
    if five >= 60 and ten >= 55:
        state = "BROAD_REPAIR"
    elif five >= 50 or ten >= 50:
        state = "BUILDING"
    elif five < 30 and ten < 30:
        state = "WASHED_OUT"
    else:
        state = "MIXED"
    five_change = out.get("change_5dma_points")
    ten_change = out.get("change_10dma_points")
    direction_score = sum(1 if finite(v) and float(v) > 1 else -1 if finite(v) and float(v) < -1 else 0 for v in (five_change, ten_change))
    direction = "RISING" if direction_score > 0 else "FALLING" if direction_score < 0 else "FLAT"
    return {
        "name": "Short-term Nasdaq participation",
        "state": state,
        "direction": direction,
        **out,
        "universe_size": len(symbols),
        "coverage_5dma_pct": 100.0 * totals[5]["valid"] / len(symbols),
        "coverage_10dma_pct": 100.0 * totals[10]["valid"] / len(symbols),
        "batch_workers": MAX_BATCH_WORKERS,
        "benchmark": "The 5-day average reacts fastest; the 10-day average is steadier. Rising percentages after a washout mean more Nasdaq stocks are participating in the recovery.",
        "meaning": "Shows how many Nasdaq stocks are reclaiming very short-term trends, which can expose an early internal turn before the Nasdaq-100 index looks fully recovered.",
        "role": "LEADING_CONTEXT_ONLY",
        "decision_input": False,
        "freshness_type": "CURRENT_DAILY_BAR",
        "last_updated": pd.Timestamp(latest_date).date().isoformat() if latest_date is not None else market_date,
        "status": "READY",
        "source": "RE-ENTRY calculated from Nasdaq-listed non-ETF equities and 5/10-day adjusted closes",
    }


def credit_risk_turn() -> dict:
    data = {}
    for ticker in ("HYG", "LQD"):
        data[ticker] = ticker_close(yf.download(ticker, period="2mo", interval="1d", auto_adjust=True, progress=False, threads=False, timeout=20), ticker)
    common = data["HYG"].index.intersection(data["LQD"].index)
    if len(common) < 7:
        raise ValueError("Insufficient HYG/LQD history")
    ratio = (data["HYG"].reindex(common) / data["LQD"].reindex(common)).dropna()
    if len(ratio) < 7:
        raise ValueError("Insufficient aligned HYG/LQD history")
    current = float(ratio.iloc[-1])
    prior = float(ratio.iloc[-2])
    one = current / prior - 1.0 if prior else None
    five_base = float(ratio.iloc[-6])
    five = current / five_base - 1.0 if five_base else None
    if finite(one) and finite(five) and one > 0 and five > 0:
        state = "IMPROVING"
    elif finite(one) and one > 0 and (not finite(five) or five <= 0):
        state = "EARLY_TURN"
    elif finite(one) and finite(five) and one < 0 and five < 0:
        state = "DETERIORATING"
    else:
        state = "MIXED"
    direction = "RISING" if finite(one) and one > 0 else "FALLING" if finite(one) and one < 0 else "FLAT"
    return {
        "name": "Credit risk improvement",
        "state": state,
        "direction": direction,
        "hyg_lqd_ratio": current,
        "change_1d": one,
        "change_5d": five,
        "benchmark": "When high-yield bonds begin outperforming investment-grade bonds, investors are showing more willingness to take credit risk. A one-day improvement before the five-day trend turns can be an early clue.",
        "meaning": "Credit markets can begin calming before stocks fully recover. This provides an early cross-asset clue without being counted twice in the RE-ENTRY decision.",
        "role": "LEADING_CONTEXT_ONLY",
        "decision_input": False,
        "freshness_type": "DAILY_CLOSE_OR_CURRENT_BAR",
        "last_updated": pd.Timestamp(ratio.index[-1]).date().isoformat(),
        "status": "READY",
        "source": "Yahoo Finance adjusted closes: HYG/LQD",
        "double_counted_in_secondary_score": False,
    }


def unavailable(name: str, error: Exception) -> dict:
    return {
        "name": name,
        "state": "UNAVAILABLE",
        "direction": "UNAVAILABLE",
        "role": "LEADING_CONTEXT_ONLY",
        "decision_input": False,
        "freshness_type": "UNAVAILABLE",
        "last_updated": None,
        "status": "UNAVAILABLE",
        "error": f"{type(error).__name__}: {error}",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--breadth-history", required=True)
    args = parser.parse_args()
    snapshot_path = Path(args.snapshot)
    history_path = Path(args.breadth_history)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    values = payload.get("values") or {}
    unified = payload.get("unified_engine") or {}
    market_date = unified.get("market_date") or values.get("market_date")
    stamp = unified.get("timestamp_et") or values.get("timestamp_et")
    history = read_rows(history_path)

    indicators = {}
    builders = {
        "zweig_breadth_thrust": lambda: zweig_breadth_thrust(history, values, str(market_date) if market_date else None, stamp),
        "mcclellan_velocity": lambda: mcclellan_velocity(history, values, str(market_date) if market_date else None, stamp),
        "nasdaq_short_breadth": lambda: nasdaq_short_breadth(str(market_date) if market_date else None),
        "credit_risk_turn": credit_risk_turn,
    }
    names = {
        "zweig_breadth_thrust": "Zweig Breadth Thrust",
        "mcclellan_velocity": "Nasdaq McClellan Oscillator velocity",
        "nasdaq_short_breadth": "Short-term Nasdaq breadth",
        "credit_risk_turn": "Credit-risk turn",
    }
    errors = {}
    for key, builder in builders.items():
        try:
            indicators[key] = builder()
        except Exception as exc:
            errors[key] = f"{type(exc).__name__}: {exc}"
            indicators[key] = unavailable(names[key], exc)

    block = {
        "version": "REENTRY_LEADING_INDICATORS_v1",
        "timestamp_et": stamp,
        "market_date": market_date,
        "decision_input": False,
        "changes_deploy_trigger": False,
        "changes_recovery_stage": False,
        "creates_new_score": False,
        "purpose": "Detect early internal repair before the recovery becomes obvious. These indicators provide context only and cannot create, block, delay, or revoke DEPLOY.",
        "indicators": indicators,
        "errors": errors,
    }
    payload["leading_indicators"] = block
    if unified:
        unified["leading_indicators"] = block
        payload["unified_engine"] = unified
    snapshot_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(block, indent=2))


if __name__ == "__main__":
    main()
