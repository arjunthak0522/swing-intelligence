#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
import math
import subprocess
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

SYMBOLS = [
    "$SPXA20R", "$NYMO", "$NAMO", "$NYUD", "$NAUD",
    "$NYUPV", "$NYDNV", "$NAUPV", "$NADNV",
    "$NAADV", "$NADEC", "$VVIX",
]
NASI_RSI_LENGTH = 14
NASI_EMA_FAST = 4
NASI_EMA_SLOW = 10


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
    return 9 * 60 + 30 <= minutes <= 16 * 60 + 45


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


def normalize_header(value: str) -> str:
    return "".join(ch.lower() for ch in (value or "") if ch.isalnum())


def parse_date(value: str) -> str | None:
    value = (value or "").strip()
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def fetch_nasdaq_daily_breadth(year: int) -> list[dict]:
    url = f"https://www.nasdaqtrader.com/dynamic/dailyfiles/daily{year}.txt"
    result = subprocess.run(
        [
            "curl", "--location", "--compressed", "--silent", "--show-error", "--fail",
            "--max-time", "30",
            "--user-agent", "Mozilla/5.0 RE-ENTRY-nasi-research/1.0",
            url,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=35,
    )
    text = result.stdout.lstrip("\ufeff")
    if not text.strip():
        raise ValueError(f"Nasdaq Trader daily{year}.txt returned an empty body")

    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    normalized = {name: normalize_header(name) for name in fields}

    def find_field(kind: str) -> str:
        exact = {"date": "date", "adv": "advances", "dec": "declines"}[kind]
        for name, norm in normalized.items():
            if norm == exact:
                return name
        for name, norm in normalized.items():
            if kind == "date" and norm.endswith("tradedate"):
                return name
            if kind == "adv" and "advance" in norm and "decline" not in norm:
                return name
            if kind == "dec" and "decline" in norm:
                return name
        raise ValueError(f"Could not resolve Nasdaq {kind} column for {year} from fields: {fields}")

    date_field = find_field("date")
    adv_field = find_field("adv")
    dec_field = find_field("dec")
    rows = []
    for row in reader:
        market_date = parse_date(row.get(date_field, ""))
        if not market_date:
            continue
        try:
            advances = float(str(row.get(adv_field, "")).replace(",", ""))
            declines = float(str(row.get(dec_field, "")).replace(",", ""))
        except ValueError:
            continue
        if advances < 0 or declines < 0 or advances + declines <= 0:
            continue
        rows.append({"market_date": market_date, "advances": advances, "declines": declines})
    if not rows:
        raise ValueError(f"Nasdaq Trader daily{year}.txt parsed zero breadth rows")
    return rows


def ema_step(value: float, previous: float | None, length: int) -> float:
    if previous is None:
        return value
    alpha = 2.0 / (length + 1.0)
    return previous + alpha * (value - previous)


def rsi_wilder(values: list[float], length: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= length:
        return out
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains[:length]) / length
    avg_loss = sum(losses[:length]) / length

    def to_rsi(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0 if gain > 0 else 50.0
        rs = gain / loss
        return 100.0 - 100.0 / (1.0 + rs)

    out[length] = to_rsi(avg_gain, avg_loss)
    for i in range(length + 1, len(values)):
        gain = gains[i - 1]
        loss = losses[i - 1]
        avg_gain = ((avg_gain * (length - 1)) + gain) / length
        avg_loss = ((avg_loss * (length - 1)) + loss) / length
        out[i] = to_rsi(avg_gain, avg_loss)
    return out


def calculate_nasi_plus(completed: list[dict], live_adv: float, live_dec: float, market_date: str) -> dict:
    series = [r for r in completed if r["market_date"] < market_date]
    series.append({"market_date": market_date, "advances": live_adv, "declines": live_dec})
    series.sort(key=lambda r: r["market_date"])

    ema19 = None
    ema39 = None
    summation = 0.0
    summation_values: list[float] = []
    calculations = []
    for item in series:
        total = item["advances"] + item["declines"]
        rana = 1000.0 * (item["advances"] - item["declines"]) / total
        ema19 = ema_step(rana, ema19, 19)
        ema39 = ema_step(rana, ema39, 39)
        oscillator = ema19 - ema39
        summation += oscillator
        summation_values.append(summation)
        calculations.append({
            "market_date": item["market_date"],
            "ratio_adjusted_net_advances": rana,
            "mcclellan_oscillator": oscillator,
            "summation_index": summation,
        })

    rsi_values = rsi_wilder(summation_values, NASI_RSI_LENGTH)
    ema4 = None
    ema10 = None
    for i, rsi in enumerate(rsi_values):
        if rsi is None:
            continue
        ema4 = ema_step(rsi, ema4, NASI_EMA_FAST)
        ema10 = ema_step(rsi, ema10, NASI_EMA_SLOW)
        calculations[i]["nasi_rsi"] = rsi
        calculations[i]["nasi_ema4"] = ema4
        calculations[i]["nasi_ema10"] = ema10

    latest = calculations[-1]
    prior_rsi = next((c.get("nasi_rsi") for c in reversed(calculations[:-1]) if c.get("nasi_rsi") is not None), None)
    current_rsi = latest.get("nasi_rsi")
    direction = "UNAVAILABLE"
    if finite(current_rsi) and finite(prior_rsi):
        delta = float(current_rsi) - float(prior_rsi)
        direction = "RISING" if delta > 0.05 else "FALLING" if delta < -0.05 else "FLAT"
    return {
        "formula_version": "NASI_PLUS_RSI14_RANA_19_39_EMA4_EMA10_v1",
        "provisional_intraday": True,
        "bootstrap_start_date": series[0]["market_date"] if series else None,
        "bootstrap_end_date": series[-2]["market_date"] if len(series) > 1 else None,
        "completed_daily_observations": len(series) - 1,
        "live_advances": live_adv,
        "live_declines": live_dec,
        "ratio_adjusted_net_advances": latest["ratio_adjusted_net_advances"],
        "mcclellan_oscillator": latest["mcclellan_oscillator"],
        "summation_index": latest["summation_index"],
        "nasi_rsi": current_rsi,
        "nasi_ema4": latest.get("nasi_ema4"),
        "nasi_ema10": latest.get("nasi_ema10"),
        "prior_completed_rsi": prior_rsi,
        "direction_vs_prior_close": direction,
        "oversold_below_30": finite(current_rsi) and float(current_rsi) < 30,
        "extreme_oversold_below_10": finite(current_rsi) and float(current_rsi) < 10,
        "historical_source": "Nasdaq Trader daily market file for verified current-year history",
        "intraday_source": "StockCharts Nasdaq advancing/declining issues",
    }


def append_history(row: dict) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    if not HISTORY.exists():
        with HISTORY.open("w", newline="", encoding="utf-8") as fobj:
            writer = csv.DictWriter(fobj, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
        return

    with HISTORY.open(newline="", encoding="utf-8") as fobj:
        reader = csv.DictReader(fobj)
        old_rows = list(reader)
        old_fields = reader.fieldnames or []
    fieldnames = list(old_fields)
    for key in row:
        if key not in fieldnames:
            fieldnames.append(key)
    if fieldnames != old_fields:
        with HISTORY.open("w", newline="", encoding="utf-8") as fobj:
            writer = csv.DictWriter(fobj, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(old_rows)
            writer.writerow(row)
    else:
        with HISTORY.open("a", newline="", encoding="utf-8") as fobj:
            csv.DictWriter(fobj, fieldnames=fieldnames).writerow(row)


def quote_provenance(quotes: dict) -> dict:
    out = {}
    for symbol, row in quotes.items():
        out[symbol] = {
            "vendor_timestamp": row.get("as_of") if isinstance(row, dict) else None,
            "realtime": row.get("realtime") if isinstance(row, dict) else None,
            "cached": row.get("cached") if isinstance(row, dict) else None,
            "available": bool(isinstance(row, dict) and finite(row.get("close"))),
        }
    return out


def main() -> None:
    now = datetime.now(timezone.utc).astimezone(ET)
    if not market_is_open(now):
        print(json.dumps({
            "research_only": True,
            "status": "SKIPPED_OUTSIDE_REFRESH_WINDOW",
            "timestamp_et": now.isoformat(),
            "note": "No RE-ENTRY evidence persisted outside the 09:30-16:45 ET refresh/finalization window.",
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
    naadv, nadec = qv("$NAADV"), qv("$NADEC")
    vvix = qv("$VVIX")
    vvix_prior_close = None
    vvix_quote = quotes.get("$VVIX")
    if vvix_quote and finite(vvix_quote.get("close_yesterday")):
        vvix_prior_close = float(vvix_quote["close_yesterday"])
    vvix_direction = "UNAVAILABLE"
    if finite(vvix) and finite(vvix_prior_close):
        vvix_delta = float(vvix) - float(vvix_prior_close)
        vvix_direction = "RISING" if vvix_delta > 0.25 else "FALLING" if vvix_delta < -0.25 else "FLAT"
    ny_ratio = nydnv / nyupv if finite(nydnv) and finite(nyupv) and nyupv > 0 else None
    na_ratio = nadnv / naupv if finite(nadnv) and finite(naupv) and naupv > 0 else None

    nasi = None
    if finite(naadv) and finite(nadec):
        try:
            history = fetch_nasdaq_daily_breadth(now.year)
            nasi = calculate_nasi_plus(history, float(naadv), float(nadec), market_date)
        except Exception as exc:
            errors["NASI_CALC"] = f"{type(exc).__name__}: {exc}"
    else:
        errors["NASI_CALC"] = "Live Nasdaq advances/declines unavailable"

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
        "NAADV": naadv,
        "NADEC": nadec,
        "NASI_RSI": nasi.get("nasi_rsi") if nasi else None,
        "NASI_EMA4": nasi.get("nasi_ema4") if nasi else None,
        "NASI_EMA10": nasi.get("nasi_ema10") if nasi else None,
        "NASI_DIRECTION": nasi.get("direction_vs_prior_close") if nasi else None,
        "VVIX": vvix,
        "VVIX_PRIOR_CLOSE": vvix_prior_close,
        "VVIX_DIRECTION": vvix_direction,
    }
    append_history(row)

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
        "nasi_plus": nasi,
        "stockcharts_quote_provenance": quote_provenance(quotes),
        "source_note": "Intraday breadth and VVIX from StockCharts delayed quote feed; per-symbol vendor timestamp/realtime/cached metadata is preserved in stockcharts_quote_provenance. NASI+ is calculated internally from raw Nasdaq breadth with verified Nasdaq Trader current-year daily history. Shadow research only; state can change before the close.",
        "errors": errors,
    }
    CURRENT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
