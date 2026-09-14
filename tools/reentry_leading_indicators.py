#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import subprocess
from pathlib import Path

import pandas as pd
import yfinance as yf

NASDAQ_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
UNICORN_BASE = "https://unicorn.us.com/advdec"
BATCH_SIZE = 180
MIN_NASDAQ_VALID = 900
MAX_DAILY_SOURCE_AGE_DAYS = 7


def finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except Exception:
        return False


def curl_text(url: str, insecure: bool = False) -> str:
    cmd = ["curl", "--location", "--compressed", "--silent", "--show-error", "--fail", "--max-time", "35", "--user-agent", "Mozilla/5.0 RE-ENTRY-leading-indicators/1.0"]
    if insecure:
        cmd.append("--insecure")
    cmd.append(url)
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=40)
    if not result.stdout.strip():
        raise ValueError(f"Empty response from {url}")
    return result.stdout


def ticker_close(frame: pd.DataFrame, ticker: str) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    if isinstance(frame.columns, pd.MultiIndex):
        if ticker in frame.columns.get_level_values(0):
            sub = frame[ticker]
            if "Close" in sub.columns:
                return pd.to_numeric(sub["Close"], errors="coerce").dropna()
        try:
            return pd.to_numeric(frame["Close"][ticker], errors="coerce").dropna()
        except Exception:
            return pd.Series(dtype=float)
    if "Close" in frame.columns:
        return pd.to_numeric(frame["Close"], errors="coerce").dropna()
    return pd.Series(dtype=float)


def load_nasdaq_symbols() -> list[str]:
    text = curl_text(NASDAQ_LISTED)
    out = []
    for row in csv.DictReader(io.StringIO(text), delimiter="|"):
        if not row or str(row.get("Symbol", "")).startswith("File Creation Time"):
            continue
        if str(row.get("Test Issue", "N")).upper() == "Y" or str(row.get("ETF", "N")).upper() == "Y":
            continue
        symbol = str(row.get("Symbol", "")).strip()
        name = str(row.get("Security Name", "")).upper()
        if not symbol or any(token in name for token in (" WARRANT", " WTS", " UNIT", " RIGHT", " PREFERRED")):
            continue
        if re.fullmatch(r"[A-Z0-9.\-]+", symbol):
            out.append(symbol.replace(".", "-"))
    return sorted(set(out))


def nasdaq_short_breadth() -> dict:
    symbols = load_nasdaq_symbols()
    above5 = above10 = prior5 = prior10 = valid = prior_valid = 0
    latest = None
    for start in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[start:start + BATCH_SIZE]
        try:
            frame = yf.download(batch, period="1mo", interval="1d", group_by="ticker", auto_adjust=True, progress=False, threads=True, timeout=25)
        except Exception:
            continue
        for ticker in batch:
            closes = ticker_close(frame, ticker)
            if len(closes) < 10:
                continue
            closes.index = pd.to_datetime(closes.index)
            latest = max(latest, closes.index[-1]) if latest is not None else closes.index[-1]
            cur = float(closes.iloc[-1])
            ma5 = float(closes.iloc[-5:].mean())
            ma10 = float(closes.iloc[-10:].mean())
            if not all(finite(x) for x in (cur, ma5, ma10)):
                continue
            valid += 1
            above5 += int(cur > ma5)
            above10 += int(cur > ma10)
            if len(closes) >= 11:
                p = float(closes.iloc[-2])
                p5 = float(closes.iloc[-6:-1].mean())
                p10 = float(closes.iloc[-11:-1].mean())
                if all(finite(x) for x in (p, p5, p10)):
                    prior_valid += 1
                    prior5 += int(p > p5)
                    prior10 += int(p > p10)
    if valid < MIN_NASDAQ_VALID:
        raise ValueError(f"Insufficient Nasdaq breadth coverage: {valid}/{len(symbols)}")
    p5 = 100.0 * above5 / valid
    p10 = 100.0 * above10 / valid
    prev5 = 100.0 * prior5 / prior_valid if prior_valid else None
    prev10 = 100.0 * prior10 / prior_valid if prior_valid else None
    d5 = p5 - prev5 if prev5 is not None else None
    d10 = p10 - prev10 if prev10 is not None else None
    if d5 is not None and d10 is not None and d5 > 0 and d10 > 0:
        state = "BROADENING_FAST"
        direction = "RISING"
    elif d5 is not None and d10 is not None and d5 < 0 and d10 < 0:
        state = "WEAKENING"
        direction = "FALLING"
    else:
        state = "MIXED"
        direction = "MIXED"
    return {
        "name": "Nasdaq short-term breadth",
        "state": state,
        "direction": direction,
        "pct_above_5dma": p5,
        "pct_above_10dma": p10,
        "prior_pct_above_5dma": prev5,
        "prior_pct_above_10dma": prev10,
        "change_5dma_points": d5,
        "change_10dma_points": d10,
        "universe_size": len(symbols),
        "valid_count": valid,
        "coverage_pct": 100.0 * valid / len(symbols) if symbols else 0.0,
        "decision_input": False,
        "role": "LEADING_CONTEXT",
        "benchmark": "Watch the direction and speed of the 5-day and 10-day participation measures. Rising together means the Nasdaq rebound is broadening quickly.",
        "why_it_matters": "Very short-term breadth can turn before slower 20-day or 40-day participation measures and can reveal whether a QQQ rebound is spreading beyond a few mega-cap names.",
        "freshness_type": "DAILY_CLOSE",
        "last_updated": pd.Timestamp(latest).date().isoformat() if latest is not None else None,
        "source": "RE-ENTRY calculation from current Nasdaq-listed non-ETF equities and adjusted daily closes",
        "validation_status": "RESEARCH_ONLY",
    }


def read_unicorn_series(filename: str) -> pd.Series:
    text = curl_text(f"{UNICORN_BASE}/{filename}", insecure=True)
    df = pd.read_csv(io.StringIO(text), header=None, names=["date", "value"], skipinitialspace=True)
    dates = pd.to_datetime(df["date"].astype(str).str.strip(), format="%Y%m%d", errors="coerce")
    vals = pd.to_numeric(df["value"], errors="coerce")
    s = pd.Series(vals.values, index=dates).dropna()
    s = s[~s.index.isna()].sort_index()
    if s.empty:
        raise ValueError(f"No valid breadth rows parsed for {filename}")
    return s


def zweig_breadth_thrust(market_date: str | None) -> dict:
    adv = read_unicorn_series("NYSE_advn.csv")
    dec = read_unicorn_series("NYSE_decln.csv")
    aligned = pd.concat([adv.rename("adv"), dec.rename("dec")], axis=1).dropna()
    if len(aligned) < 30:
        raise ValueError("Insufficient NYSE breadth history for Zweig Breadth Thrust")
    last_date = aligned.index[-1].date()
    target_date = pd.Timestamp(market_date).date() if market_date else pd.Timestamp.utcnow().date()
    age_days = (target_date - last_date).days
    common = {
        "name": "Zweig Breadth Thrust",
        "decision_input": False,
        "role": "LEADING_CONTEXT",
        "benchmark": "Classic setup watches for the 10-day breadth ratio to move from below 0.40 to above 0.615 within 10 sessions.",
        "why_it_matters": "A rapid shift from washed-out breadth to broad participation can identify a powerful internal reversal before slower trend measures fully recover.",
        "freshness_type": "DAILY_CLOSE",
        "last_updated": last_date.isoformat(),
        "source": "NYSE advancing/declining issues archive from Unicorn Research; RE-ENTRY computes the 10-day exponential breadth ratio",
        "source_age_days": age_days,
    }
    if age_days > MAX_DAILY_SOURCE_AGE_DAYS:
        return {
            **common,
            "state": "UNAVAILABLE_STALE_SOURCE",
            "direction": "UNAVAILABLE",
            "source_stale": True,
            "validation_status": "STALE_SOURCE_RESEARCH_ONLY",
            "freshness_note": f"Archive is {age_days} calendar days behind the snapshot date. No current Zweig reading is published.",
        }
    breadth = aligned["adv"] / (aligned["adv"] + aligned["dec"])
    ratio10 = breadth.ewm(span=10, adjust=False).mean()
    current = float(ratio10.iloc[-1])
    prior = float(ratio10.iloc[-2])
    recent10 = ratio10.iloc[-10:]
    min10 = float(recent10.min())
    thrust = bool(min10 < 0.40 and current > 0.615)
    setup = bool(min10 < 0.40 and current <= 0.615)
    if thrust:
        state = "THRUST_TRIGGERED"
    elif setup and current > prior:
        state = "THRUST_BUILDING"
    elif current > prior:
        state = "IMPROVING"
    else:
        state = "NOT_ACTIVE"
    return {
        **common,
        "state": state,
        "direction": "RISING" if current > prior else "FALLING" if current < prior else "FLAT",
        "breadth_ratio_10ema": current,
        "prior_breadth_ratio_10ema": prior,
        "recent_10_session_min": min10,
        "classic_thrust_triggered": thrust,
        "classic_setup_active": setup,
        "source_stale": False,
        "validation_status": "RESEARCH_ONLY",
    }


def prior_daily_value(history_path: Path, key: str, market_date: str | None) -> float | None:
    if not history_path.exists():
        return None
    rows = list(csv.DictReader(history_path.open(newline="", encoding="utf-8")))
    by_day = {}
    for row in rows:
        day = row.get("market_date")
        if not day or (market_date and day >= market_date):
            continue
        value = row.get(key)
        if finite(value):
            by_day[day] = float(value)
    return by_day[sorted(by_day)[-1]] if by_day else None


def mcclellan_velocity(payload: dict, history_path: Path) -> dict:
    values = payload.get("values") or {}
    market_date = values.get("market_date")
    ny = float(values["NYMO"]) if finite(values.get("NYMO")) else None
    na = float(values["NAMO"]) if finite(values.get("NAMO")) else None
    pny = prior_daily_value(history_path, "NYMO", market_date)
    pna = prior_daily_value(history_path, "NAMO", market_date)
    dny = ny - pny if ny is not None and pny is not None else None
    dna = na - pna if na is not None and pna is not None else None
    improving = [x for x in (dny, dna) if x is not None and x > 0]
    worsening = [x for x in (dny, dna) if x is not None and x < 0]
    if len(improving) == 2:
        state = "ACCELERATING_UP"
        direction = "RISING"
    elif len(worsening) == 2:
        state = "ACCELERATING_DOWN"
        direction = "FALLING"
    else:
        state = "MIXED"
        direction = "MIXED"
    return {
        "name": "McClellan Oscillator thrust / velocity",
        "state": state,
        "direction": direction,
        "nymo": ny,
        "namo": na,
        "prior_nymo": pny,
        "prior_namo": pna,
        "nymo_change": dny,
        "namo_change": dna,
        "decision_input": False,
        "role": "LEADING_CONTEXT",
        "benchmark": "The important read is acceleration from deeply negative breadth toward less-negative or positive readings, especially when NYSE and Nasdaq improve together.",
        "why_it_matters": "The speed of the McClellan reversal can reveal selling exhaustion and breadth repair before the slower Summation Index confirms the move.",
        "freshness_type": "DAILY_CLOSE",
        "last_updated": market_date,
        "source": "RE-ENTRY canonical NYMO/NAMO readings compared with prior captured daily values",
        "validation_status": "RESEARCH_ONLY",
    }


def credit_turn() -> dict:
    frame = yf.download(["HYG", "LQD"], period="2mo", interval="1d", group_by="ticker", auto_adjust=True, progress=False, threads=True, timeout=25)
    hyg = ticker_close(frame, "HYG")
    lqd = ticker_close(frame, "LQD")
    common = hyg.index.intersection(lqd.index)
    ratio = (hyg.reindex(common) / lqd.reindex(common)).dropna()
    if len(ratio) < 7:
        raise ValueError("Insufficient HYG/LQD history")
    cur = float(ratio.iloc[-1])
    ch1 = cur / float(ratio.iloc[-2]) - 1.0
    ch5 = cur / float(ratio.iloc[-6]) - 1.0
    if ch1 > 0 and ch5 <= 0:
        state = "TURNING_UP"
        direction = "RISING"
    elif ch1 > 0 and ch5 > 0:
        state = "IMPROVING"
        direction = "RISING"
    elif ch1 < 0 and ch5 < 0:
        state = "DETERIORATING"
        direction = "FALLING"
    else:
        state = "MIXED"
        direction = "MIXED"
    return {
        "name": "Credit risk turn",
        "state": state,
        "direction": direction,
        "hyg_lqd_ratio": cur,
        "change_1d": ch1,
        "change_5d": ch5,
        "decision_input": False,
        "role": "LEADING_CONTEXT",
        "benchmark": "A rising HYG/LQD ratio means lower-quality credit is outperforming investment-grade bonds. A 1-day turn higher while the 5-day trend is still weak is an early repair signal.",
        "why_it_matters": "Credit can begin accepting risk again while equity headlines still look weak, making a turn in HYG/LQD useful early context for re-entry.",
        "freshness_type": "DAILY_CLOSE",
        "last_updated": pd.Timestamp(ratio.index[-1]).date().isoformat(),
        "source": "Yahoo Finance adjusted daily closes for HYG and LQD",
        "validation_status": "EXISTING_FAMILY_CONTEXT_ONLY",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--history", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    snapshot_path = Path(args.snapshot)
    output_path = Path(args.output) if args.output else snapshot_path
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    history_path = Path(args.history)
    market_date = (payload.get("values") or {}).get("market_date") or (payload.get("unified_engine") or {}).get("market_date")
    builders = {
        "zweig_breadth_thrust": lambda: zweig_breadth_thrust(market_date),
        "mcclellan_velocity": lambda: mcclellan_velocity(payload, history_path),
        "nasdaq_short_breadth": nasdaq_short_breadth,
        "credit_risk_turn": credit_turn,
    }
    indicators = {}
    errors = {}
    for key, builder in builders.items():
        try:
            indicators[key] = builder()
        except Exception as exc:
            errors[key] = f"{type(exc).__name__}: {exc}"
            indicators[key] = {
                "name": key.replace("_", " ").title(),
                "state": "UNAVAILABLE",
                "direction": "UNAVAILABLE",
                "decision_input": False,
                "role": "LEADING_CONTEXT",
                "freshness_type": "UNAVAILABLE",
                "last_updated": None,
                "validation_status": "RESEARCH_ONLY",
                "error": errors[key],
            }
    block = {
        "version": "REENTRY_LEADING_INDICATORS_v1",
        "decision_input": False,
        "changes_deploy_trigger": False,
        "changes_recovery_stage": False,
        "purpose": "Are market internals beginning to turn before the recovery becomes obvious?",
        "indicators": indicators,
        "errors": errors,
        "interpretation": "These are leading/context indicators only. They may corroborate an early turn but cannot create, block, delay, revoke, or double-count a REENTRY_UNIFIED_v1 DEPLOY signal.",
    }
    payload["leading_indicators"] = block
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(block, indent=2))


if __name__ == "__main__":
    main()
