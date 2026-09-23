#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

EMA_LENGTH = 10
MIN_ZBT_SESSIONS = 10
SYMBOLS = {
    "tick": "$TICK",
    "new_highs": "$NYHGH",
    "new_lows": "$NYLOW",
    "advances": "$NYADV",
    "declines": "$NYDEC",
}


def finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except Exception:
        return False


def as_float(value):
    return float(value) if finite(value) else None


def fetch_quote(symbol: str) -> dict:
    url = f"https://stockcharts.com/quotebrain/quotes?s={quote(symbol)}&f=json&randomNumber={int(time.time()*1000)}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 RE-ENTRY-nyse-context/1.0"})
    with urlopen(req, timeout=20) as resp:  # nosec - fixed StockCharts endpoint
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload:
        raise ValueError(f"No StockCharts quote returned for {symbol}")
    row = payload[0]
    return {
        "value": as_float(row.get("close")),
        "prior_close": as_float(row.get("closeYesterday")),
        "session_high": as_float(row.get("high")),
        "session_low": as_float(row.get("low")),
        "vendor_timestamp": (row.get("time") or {}).get("time"),
        "realtime": bool(row.get("realtime")),
        "cached": bool(row.get("cached")),
    }


def tick_state(value: float | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value >= 800:
        return "STRONG BUYING"
    if value >= 300:
        return "BUYING"
    if value <= -800:
        return "STRONG SELLING"
    if value <= -300:
        return "SELLING"
    return "NEUTRAL"


def high_low_state(highs: float | None, lows: float | None) -> str:
    if highs is None or lows is None:
        return "UNAVAILABLE"
    if highs > lows:
        return "MORE NEW HIGHS"
    if lows > highs:
        return "MORE NEW LOWS"
    return "BALANCED"


def read_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def upsert_daily_history(path: Path, row: dict) -> None:
    rows = read_history(path)
    by_day = {item.get("market_date"): item for item in rows if item.get("market_date")}
    existing = dict(by_day.get(row["market_date"], {}))
    for key, value in row.items():
        if value is not None and value != "":
            existing[key] = value
    existing["market_date"] = row["market_date"]
    by_day[row["market_date"]] = existing
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "market_date", "nyse_advances", "nyse_declines", "advance_share",
        "nyse_tick", "tick_session_high", "tick_session_low",
        "new_highs", "new_lows", "source_timestamp",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for day in sorted(by_day):
            writer.writerow({key: by_day[day].get(key, "") for key in fields})


def classic_nyse_zweig(rows: list[dict]) -> dict:
    series: list[tuple[str, float]] = []
    for row in rows:
        day = row.get("market_date")
        share = as_float(row.get("advance_share"))
        if day and share is not None:
            series.append((day, share))
    series.sort(key=lambda item: item[0])
    if not series:
        return {
            "name": "Classic NYSE breadth thrust",
            "state": "UNAVAILABLE",
            "triggered": False,
            "current_10d_ema": None,
            "recent_10_session_low_ema": None,
            "session_count": 0,
            "minimum_sessions": MIN_ZBT_SESSIONS,
            "direction": "UNAVAILABLE",
            "role": "LEADING_CONTEXT_ONLY",
            "decision_input": False,
            "status": "UNAVAILABLE",
        }

    alpha = 2.0 / (EMA_LENGTH + 1.0)
    ema_values: list[float] = []
    previous = None
    for _, value in series:
        previous = value if previous is None else previous + alpha * (value - previous)
        ema_values.append(previous)

    current = ema_values[-1]
    recent = ema_values[-10:]
    recent_low = min(recent)
    sessions = len(ema_values)
    enough = sessions >= MIN_ZBT_SESSIONS
    triggered = bool(enough and recent_low <= 0.40 and current >= 0.615)

    if not enough:
        state = "BUILDING HISTORY"
    elif triggered:
        state = "THRUST TRIGGERED"
    elif current >= 0.615:
        state = "STRONG PARTICIPATION"
    elif current >= 0.55:
        state = "BUILDING"
    elif current <= 0.40:
        state = "WASHED OUT"
    else:
        state = "NEUTRAL"

    direction = "UNAVAILABLE"
    if len(ema_values) >= 2:
        direction = "RISING" if ema_values[-1] > ema_values[-2] else "FALLING" if ema_values[-1] < ema_values[-2] else "FLAT"

    return {
        "name": "Classic NYSE breadth thrust",
        "state": state,
        "triggered": triggered,
        "current_10d_ema": current,
        "recent_10_session_low_ema": recent_low,
        "session_count": sessions,
        "minimum_sessions": MIN_ZBT_SESSIONS,
        "direction": direction,
        "benchmark": "Classic Zweig condition: the 10-day EMA of NYSE advancing-stock share rises from 40% or less to 61.5% or more within 10 trading sessions.",
        "meaning": "Tracks whether NYSE participation has shifted rapidly from broad selling to broad buying using the classic Zweig breadth-thrust formula.",
        "role": "LEADING_CONTEXT_ONLY",
        "decision_input": False,
        "changes_deploy_trigger": False,
        "changes_recovery_stage": False,
        "freshness_type": "CAPTURED_DAILY_HISTORY_PLUS_CURRENT_INTRADAY",
        "status": "READY" if enough else "BUILDING_HISTORY",
        "source": "StockCharts NYSE advancing and declining issues ($NYADV / $NYDEC)",
    }


def unavailable(name: str, reference: str, error: Exception) -> dict:
    return {
        "name": name,
        "reference": reference,
        "state": "UNAVAILABLE",
        "direction": "UNAVAILABLE",
        "role": "LEADING_CONTEXT_ONLY",
        "decision_input": False,
        "freshness_type": "UNAVAILABLE",
        "freshness_state": "UNAVAILABLE",
        "status": "UNAVAILABLE",
        "last_updated": None,
        "error": f"{type(error).__name__}: {error}",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--history", required=True)
    args = parser.parse_args()

    snapshot_path = Path(args.snapshot)
    history_path = Path(args.history)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    engine = payload.get("unified_engine") or {}
    values = payload.get("values") or {}
    market_date = str(engine.get("market_date") or values.get("market_date") or "")
    stamp = engine.get("timestamp_et") or values.get("timestamp_et")

    quotes: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for key, symbol in SYMBOLS.items():
        try:
            quotes[key] = fetch_quote(symbol)
        except Exception as exc:
            errors[key] = f"{type(exc).__name__}: {exc}"

    tick_quote = quotes.get("tick") or {}
    highs_quote = quotes.get("new_highs") or {}
    lows_quote = quotes.get("new_lows") or {}
    adv_quote = quotes.get("advances") or {}
    dec_quote = quotes.get("declines") or {}

    tick_value = tick_quote.get("value")
    highs = highs_quote.get("value")
    lows = lows_quote.get("value")
    advances = adv_quote.get("value")
    declines = dec_quote.get("value")

    if market_date:
        share = (
            float(advances) / (float(advances) + float(declines))
            if finite(advances) and finite(declines) and advances + declines > 0
            else None
        )
        upsert_daily_history(history_path, {
            "market_date": market_date,
            "nyse_advances": advances,
            "nyse_declines": declines,
            "advance_share": share,
            "nyse_tick": tick_value,
            "tick_session_high": tick_quote.get("session_high"),
            "tick_session_low": tick_quote.get("session_low"),
            "new_highs": highs,
            "new_lows": lows,
            "source_timestamp": (
                tick_quote.get("vendor_timestamp")
                or adv_quote.get("vendor_timestamp")
                or highs_quote.get("vendor_timestamp")
                or stamp
            ),
        })

    history_rows = read_history(history_path)
    current_history = next((row for row in reversed(history_rows) if row.get("market_date") == market_date), {})
    zbt = classic_nyse_zweig(history_rows)
    zbt["current_raw_advance_share"] = (
        float(advances) / (float(advances) + float(declines))
        if finite(advances) and finite(declines) and advances + declines > 0
        else None
    )
    zbt["last_updated"] = adv_quote.get("vendor_timestamp") or stamp
    zbt["freshness_state"] = "DELAYED" if zbt.get("current_raw_advance_share") is not None else "UNAVAILABLE"

    cached_tick = as_float(current_history.get("nyse_tick"))
    cached_tick_high = as_float(current_history.get("tick_session_high"))
    cached_tick_low = as_float(current_history.get("tick_session_low"))
    effective_tick = tick_value if tick_value is not None else cached_tick
    if effective_tick is None:
        tick = unavailable("NYSE buying vs selling ticks", "$TICK", ValueError(errors.get("tick", "No valid same-session observation")))
    else:
        using_cache = tick_value is None
        tick = {
            "name": "NYSE buying vs selling ticks",
            "reference": "$TICK",
            "value": effective_tick,
            "session_high": tick_quote.get("session_high") if tick_quote.get("session_high") is not None else cached_tick_high,
            "session_low": tick_quote.get("session_low") if tick_quote.get("session_low") is not None else cached_tick_low,
            "state": tick_state(effective_tick),
            "direction": "POSITIVE" if effective_tick > 0 else "NEGATIVE" if effective_tick < 0 else "FLAT",
            "meaning": "Shows whether more NYSE stocks are trading on upticks or downticks at this moment. Large positive readings show broad immediate buying pressure; large negative readings show broad immediate selling pressure.",
            "role": "LEADING_CONTEXT_ONLY",
            "decision_input": False,
            "changes_deploy_trigger": False,
            "changes_recovery_stage": False,
            "freshness_type": "INTRADAY",
            "freshness_state": "CACHED_INTRADAY" if using_cache else "LIVE" if tick_quote.get("realtime") else "DELAYED",
            "last_updated": tick_quote.get("vendor_timestamp") or current_history.get("source_timestamp") or stamp,
            "status": "READY",
            "source": "StockCharts NYSE TICK ($TICK)",
        }

    if highs is None or lows is None:
        high_low = unavailable("NYSE new highs vs new lows", "$NYHGH / $NYLOW", ValueError("No valid new-high/new-low observation"))
    else:
        total = float(highs) + float(lows)
        high_low = {
            "name": "NYSE new highs vs new lows",
            "reference": "$NYHGH / $NYLOW",
            "new_highs": highs,
            "new_lows": lows,
            "net_new_highs": float(highs) - float(lows),
            "new_low_share": float(lows) / total if total > 0 else None,
            "state": high_low_state(highs, lows),
            "direction": "POSITIVE" if highs > lows else "NEGATIVE" if lows > highs else "FLAT",
            "meaning": "Compares NYSE stocks making new 52-week highs with those making new 52-week lows. More new lows shows deterioration spreading; more new highs shows leadership broadening.",
            "role": "LEADING_CONTEXT_ONLY",
            "decision_input": False,
            "changes_deploy_trigger": False,
            "changes_recovery_stage": False,
            "freshness_type": "INTRADAY",
            "freshness_state": "LIVE" if highs_quote.get("realtime") or lows_quote.get("realtime") else "DELAYED",
            "last_updated": highs_quote.get("vendor_timestamp") or lows_quote.get("vendor_timestamp") or stamp,
            "status": "READY",
            "source": "StockCharts NYSE New 52-Week Highs/Lows ($NYHGH / $NYLOW)",
        }

    block = {
        "version": "REENTRY_NYSE_CONTEXT_v1",
        "market_date": market_date,
        "timestamp_et": stamp,
        "decision_input": False,
        "changes_deploy_trigger": False,
        "changes_recovery_stage": False,
        "creates_new_score": False,
        "purpose": "Add independent NYSE participation and stress context without changing the RE-ENTRY decision.",
        "indicators": {
            "nyse_tick": tick,
            "nyse_new_highs_lows": high_low,
            "classic_nyse_zweig_breadth_thrust": zbt,
        },
        "errors": errors,
    }

    payload["nyse_context"] = block
    if isinstance(payload.get("unified_engine"), dict):
        payload["unified_engine"]["nyse_context"] = block
    snapshot_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(block, indent=2))


if __name__ == "__main__":
    main()
