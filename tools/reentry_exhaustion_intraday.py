#!/usr/bin/env python3
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
DAILY = ROOT / "data/reentry/exhaustion_history.csv"
HISTORY = ROOT / "data/reentry/exhaustion_intraday_history.csv"
CURRENT = ROOT / "data/reentry/exhaustion_intraday_current.json"

SYMBOLS = ["$SPXA20R", "$NYMO", "$NAMO", "$NYUD", "$NAUD", "$NYUPV", "$NYDNV", "$NAUPV", "$NADNV"]


def finite(x):
    try:
        return x is not None and math.isfinite(float(x))
    except Exception:
        return False


def fetch_quote(symbol: str) -> dict | None:
    url = f"https://stockcharts.com/quotebrain/quotes?s={quote(symbol)}&f=json&randomNumber={int(time.time()*1000)}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 RE-ENTRY-intraday-research/1.0"})
    with urlopen(req, timeout=20) as resp:  # nosec - fixed StockCharts endpoint
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload:
        return None
    row = payload[0]
    return {
        "close": row.get("close"),
        "close_yesterday": row.get("closeYesterday"),
        "as_of": (row.get("time") or {}).get("time"),
        "realtime": row.get("realtime"),
        "cached": row.get("cached"),
    }


def load_daily() -> list[dict]:
    if not DAILY.exists():
        return []
    with DAILY.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_intraday() -> list[dict]:
    if not HISTORY.exists():
        return []
    with HISTORY.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def latest_daily(rows: list[dict]) -> dict | None:
    rows = [r for r in rows if r.get("market_date")]
    return max(rows, key=lambda r: r["market_date"]) if rows else None


def market_is_open(now: datetime) -> bool:
    now_et = now.astimezone(ET) if now.tzinfo else now.replace(tzinfo=ET)
    if now_et.weekday() >= 5:
        return False
    minutes = now_et.hour * 60 + now_et.minute
    return 9 * 60 + 30 <= minutes < 16 * 60


def latest_same_day(rows: list[dict], market_date: str) -> dict | None:
    valid = []
    for row in rows:
        if row.get("market_date") != market_date:
            continue
        raw_timestamp = row.get("timestamp_et")
        if not raw_timestamp:
            continue
        try:
            timestamp = datetime.fromisoformat(raw_timestamp).astimezone(ET)
        except (TypeError, ValueError):
            continue
        if timestamp.date().isoformat() != market_date or not market_is_open(timestamp):
            continue
        valid.append((timestamp, row))
    return max(valid, key=lambda item: item[0])[1] if valid else None


def f(row: dict | None, key: str):
    if not row:
        return None
    x = row.get(key)
    return float(x) if finite(x) else None


def main() -> None:
    now = datetime.now(timezone.utc).astimezone(ET)
    if not market_is_open(now):
        print(json.dumps({
            "research_only": True,
            "status": "SKIPPED_OUTSIDE_REGULAR_SESSION",
            "timestamp_et": now.isoformat(),
            "note": "No intraday evidence persisted outside 09:30-16:00 ET regular session.",
        }))
        return

    market_date = now.date().isoformat()
    daily_rows = load_daily()
    daily = latest_daily(daily_rows)
    intraday_rows = load_intraday()
    prior = latest_same_day(intraday_rows, market_date)

    quotes = {}
    errors = {}
    for s in SYMBOLS:
        try:
            quotes[s] = fetch_quote(s)
        except Exception as exc:
            quotes[s] = None
            errors[s] = f"{type(exc).__name__}: {exc}"

    def qv(s):
        q = quotes.get(s)
        return float(q["close"]) if q and finite(q.get("close")) else None

    sp20, nymo, namo = qv("$SPXA20R"), qv("$NYMO"), qv("$NAMO")
    nyud, naud = qv("$NYUD"), qv("$NAUD")
    nyupv, nydnv, naupv, nadnv = qv("$NYUPV"), qv("$NYDNV"), qv("$NAUPV"), qv("$NADNV")
    ny_ratio = nydnv / nyupv if finite(nydnv) and finite(nyupv) and nyupv > 0 else None
    na_ratio = nadnv / naupv if finite(nadnv) and finite(naupv) and naupv > 0 else None

    prior_sp20 = f(prior, "SPXA20R")
    prior_nymo, prior_namo = f(prior, "NYMO"), f(prior, "NAMO")
    prior_nyud, prior_naud = f(prior, "NYUD"), f(prior, "NAUD")
    prior_nyr, prior_nar = f(prior, "nyse_down_up_ratio"), f(prior, "nasdaq_down_up_ratio")

    if prior is None:
        def yesterday(s):
            q = quotes.get(s)
            return float(q["close_yesterday"]) if q and finite(q.get("close_yesterday")) else None
        prior_sp20 = yesterday("$SPXA20R")
        prior_nymo, prior_namo = yesterday("$NYMO"), yesterday("$NAMO")
        prior_nyud, prior_naud = yesterday("$NYUD"), yesterday("$NAUD")

    fast_breadth_turn = finite(sp20) and finite(prior_sp20) and sp20 > prior_sp20
    momentum_turn = (
        (finite(nymo) and finite(prior_nymo) and nymo > prior_nymo)
        or (finite(namo) and finite(prior_namo) and namo > prior_namo)
    )
    volume_turn = (
        (finite(nyud) and finite(prior_nyud) and nyud > prior_nyud)
        or (finite(naud) and finite(prior_naud) and naud > prior_naud)
    )
    ratio_relief = (
        (finite(ny_ratio) and finite(prior_nyr) and ny_ratio < prior_nyr * 0.85)
        or (finite(na_ratio) and finite(prior_nar) and na_ratio < prior_nar * 0.85)
    )

    family_count = sum(bool(x) for x in (fast_breadth_turn, momentum_turn, volume_turn, ratio_relief))
    daily_state = (daily or {}).get("state", "")
    oversold_context = daily_state in {"OVERSOLD", "WASHOUT", "CONFIRMED"} or (finite(sp20) and sp20 <= 30)

    if not oversold_context:
        state, action = "INACTIVE", "WAIT"
    elif family_count == 0:
        state, action = "OVERSOLD", "WAIT_FOR_WASHOUT"
    elif family_count == 1:
        state, action = "WASHOUT_WATCH", "WATCH_EARLY_TURN"
    else:
        state, action = "WASHOUT", "GO_EARLY_INTRADAY"

    row = {
        "market_date": market_date,
        "timestamp_et": now.isoformat(),
        "state": state,
        "candidate_action": action,
        "turn_family_count": family_count,
        "daily_context_state": daily_state,
        "SPXA20R": sp20,
        "NYMO": nymo,
        "NAMO": namo,
        "NYUD": nyud,
        "NAUD": naud,
        "nyse_down_up_ratio": ny_ratio,
        "nasdaq_down_up_ratio": na_ratio,
    }

    fieldnames = list(row)
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    exists = HISTORY.exists()
    with HISTORY.open("a", newline="", encoding="utf-8") as fobj:
        writer = csv.DictWriter(fobj, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)

    payload = {
        "research_only": True,
        "official_completed_close_signal_modified": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "candidate_action": action,
        "semantics": {
            "OVERSOLD": "selling remains stretched with no intraday turn",
            "WASHOUT_WATCH": "one independent family has turned",
            "WASHOUT": "at least two independent fast families have turned - early intraday GO candidate",
            "CONFIRMED": "reserved for later completed-session corroboration; never assigned by this intraday script",
        },
        "daily_context_state": daily_state,
        "turn_family_count": family_count,
        "families": {
            "fast_breadth_turn": bool(fast_breadth_turn),
            "momentum_turn": bool(momentum_turn),
            "net_volume_turn": bool(volume_turn),
            "down_up_ratio_relief": bool(ratio_relief),
        },
        "values": row,
        "source_note": "StockCharts delayed intraday quote feed. Shadow research only; state can change before the close.",
        "errors": errors,
    }
    CURRENT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
