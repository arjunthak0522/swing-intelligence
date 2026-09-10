#!/usr/bin/env python3
"""Prospective CPCE research feed for RE-ENTRY.

Captures Cboe equity put/call ratio context from the StockCharts $CPCE quote feed and
stores it separately from REENTRY_UNIFIED_v1. This script does not alter the live engine,
thresholds, or dashboard decision.
"""
from __future__ import annotations

import csv
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/reentry/cpce_research_current.json"
LEDGER = ROOT / "data/reentry/cpce_research_history.csv"


def finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except Exception:
        return False


def allowed(now: datetime) -> bool:
    now = now.astimezone(ET)
    if now.weekday() >= 5:
        return False
    minute = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= minute <= 16 * 60 + 45


def fetch_cpce() -> dict:
    url = f"https://stockcharts.com/quotebrain/quotes?s={quote('$CPCE')}&f=json&randomNumber={int(time.time()*1000)}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 RE-ENTRY-CPCE-research/1.0"})
    with urlopen(req, timeout=20) as resp:  # nosec - fixed StockCharts endpoint
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload:
        raise ValueError("StockCharts returned no $CPCE quote")
    row = payload[0]
    return {
        "value": float(row["close"]) if finite(row.get("close")) else None,
        "prior_close": float(row["closeYesterday"]) if finite(row.get("closeYesterday")) else None,
        "vendor_timestamp": (row.get("time") or {}).get("time"),
        "realtime": row.get("realtime"),
        "cached": row.get("cached"),
    }


def read_rows() -> list[dict]:
    if not LEDGER.exists():
        return []
    with LEDGER.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def same_day(rows: list[dict], market_date: str) -> list[dict]:
    result = [r for r in rows if r.get("market_date") == market_date and finite(r.get("CPCE"))]
    result.sort(key=lambda r: str(r.get("timestamp_et") or ""))
    return result


def append(row: dict) -> None:
    rows = read_rows()
    fields = list(rows[0].keys()) if rows else []
    for key in row:
        if key not in fields:
            fields.append(key)
    with LEDGER.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        writer.writerow(row)


def main() -> None:
    now = datetime.now(timezone.utc).astimezone(ET)
    if not allowed(now):
        print(json.dumps({"status": "OUTSIDE_REFRESH_WINDOW", "research_only": True, "timestamp_et": now.isoformat()}))
        return

    market_date = now.date().isoformat()
    quote_row = fetch_cpce()
    rows = same_day(read_rows(), market_date)
    previous_snapshot = float(rows[-1]["CPCE"]) if rows else None
    value = quote_row["value"]

    change_vs_prior_snapshot = value - previous_snapshot if finite(value) and finite(previous_snapshot) else None
    change_vs_prior_close = value - quote_row["prior_close"] if finite(value) and finite(quote_row["prior_close"]) else None
    recent = [float(r["CPCE"]) for r in rows[-4:] if finite(r.get("CPCE"))]
    recent_with_current = recent + ([float(value)] if finite(value) else [])
    recent_mean = sum(recent_with_current) / len(recent_with_current) if recent_with_current else None

    direction = "UNAVAILABLE"
    if finite(change_vs_prior_snapshot):
        direction = "RISING" if change_vs_prior_snapshot > 0.005 else "FALLING" if change_vs_prior_snapshot < -0.005 else "FLAT"

    result = {
        "classification": "RESEARCH_ONLY_PROSPECTIVE",
        "engine_impact": "NONE",
        "market_date": market_date,
        "timestamp_et": now.isoformat(),
        "symbol": "$CPCE",
        "value": value,
        "prior_close": quote_row["prior_close"],
        "previous_same_session_snapshot": previous_snapshot,
        "change_vs_prior_snapshot": change_vs_prior_snapshot,
        "change_vs_prior_close": change_vs_prior_close,
        "direction_vs_prior_snapshot": direction,
        "recent_snapshot_mean": recent_mean,
        "vendor_timestamp": quote_row["vendor_timestamp"],
        "vendor_realtime": quote_row["realtime"],
        "vendor_cached": quote_row["cached"],
        "source": "StockCharts $CPCE quote feed",
        "research_hypothesis": "Test CPCE level, spike magnitude, persistence, and especially elevated-then-falling behavior as incremental evidence after the existing unified families are known.",
        "production_threshold": None,
        "promotion_status": "NOT_IN_ENGINE",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    append({
        "market_date": market_date,
        "timestamp_et": now.isoformat(),
        "CPCE": value,
        "prior_close": quote_row["prior_close"],
        "previous_same_session_snapshot": previous_snapshot,
        "change_vs_prior_snapshot": change_vs_prior_snapshot,
        "change_vs_prior_close": change_vs_prior_close,
        "direction_vs_prior_snapshot": direction,
        "recent_snapshot_mean": recent_mean,
        "vendor_timestamp": quote_row["vendor_timestamp"],
        "vendor_realtime": quote_row["realtime"],
        "vendor_cached": quote_row["cached"],
    })
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
