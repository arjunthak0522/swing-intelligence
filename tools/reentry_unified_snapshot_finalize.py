#!/usr/bin/env python3
"""Finalize the single RE-ENTRY snapshot for dashboard consumption.

This file does not change signal thresholds or decision logic. It enriches the current
REENTRY_UNIFIED_v1 output with market-price context, source provenance, data-quality
status, and a point-in-time prospective ledger so the UI and research harness can use
one canonical object.
"""
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
HISTORY = ROOT / "data/reentry/unified_engine_history.csv"
LEDGER = ROOT / "data/reentry/unified_snapshot_ledger.csv"


def finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except Exception:
        return False


def iso_or_none(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def extract_close(frame: pd.DataFrame, ticker: str) -> pd.Series:
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
        close = frame["Close"]
        if isinstance(close, pd.DataFrame):
            if ticker in close.columns:
                close = close[ticker]
            else:
                close = close.iloc[:, 0]
        return pd.to_numeric(close, errors="coerce").dropna()
    return pd.Series(dtype=float)


def fetch_market_prices(now: datetime) -> tuple[dict, list[str]]:
    out: dict[str, dict] = {}
    errors: list[str] = []
    for ticker in ("SPY", "QQQ", "^VIX"):
        try:
            intra = yf.download(
                ticker,
                period="2d",
                interval="5m",
                auto_adjust=False,
                progress=False,
                threads=False,
                timeout=20,
            )
            closes = extract_close(intra, ticker)
            if closes.empty:
                raise ValueError("no intraday close")
            current = float(closes.iloc[-1])
            last_index = pd.Timestamp(closes.index[-1])
            if last_index.tzinfo is None:
                last_index = last_index.tz_localize("UTC")
            timestamp_et = last_index.tz_convert(ET).isoformat()

            daily = yf.download(
                ticker,
                period="10d",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
                timeout=20,
            )
            daily_closes = extract_close(daily, ticker)
            previous = None
            if not daily_closes.empty:
                dated = daily_closes.copy()
                dated.index = pd.to_datetime(dated.index)
                prior = dated[dated.index.date < now.date()]
                if not prior.empty:
                    previous = float(prior.iloc[-1])
            change = current / previous - 1.0 if finite(previous) and float(previous) != 0 else None
            out[ticker] = {
                "price": current,
                "previous_close": previous,
                "change_pct": change,
                "timestamp_et": timestamp_et,
                "source": "Yahoo Finance 5-minute quote context",
                "decision_input": False,
            }
        except Exception as exc:
            errors.append(f"{ticker}: {type(exc).__name__}: {exc}")
            out[ticker] = {
                "price": None,
                "previous_close": None,
                "change_pct": None,
                "timestamp_et": None,
                "source": "Yahoo Finance 5-minute quote context",
                "decision_input": False,
            }
    return out, errors


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_schema_evolving(path: Path, row: dict, dedupe_key: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    old_rows = read_csv(path)
    if dedupe_key and row.get(dedupe_key) is not None:
        if any(old.get(dedupe_key) == str(row.get(dedupe_key)) for old in old_rows):
            return
    fields = list(old_rows[0].keys()) if old_rows else []
    for key in row:
        if key not in fields:
            fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(old_rows)
        writer.writerow(row)


def history_rows() -> list[dict]:
    rows = read_csv(LEDGER) if LEDGER.exists() else read_csv(HISTORY)
    rows = [r for r in rows if r.get("timestamp_et") and (r.get("state") or r.get("decision"))]
    rows.sort(key=lambda r: r["timestamp_et"])
    return rows


def prospective_history_summary() -> dict:
    rows = history_rows()
    transitions = 0
    previous_by_day: dict[str, str] = {}
    for row in rows:
        day = row.get("market_date") or ""
        state = row.get("state") or row.get("decision") or ""
        prior = previous_by_day.get(day)
        if prior and state != prior:
            transitions += 1
        previous_by_day[day] = state
    return {
        "snapshot_count": len(rows),
        "market_days": len({r.get("market_date") for r in rows if r.get("market_date")}),
        "state_transitions": transitions,
        "go_early_snapshots": sum((r.get("state") or r.get("decision") or "") == "GO_EARLY" for r in rows),
        "watch_snapshots": sum((r.get("state") or r.get("decision") or "") == "WATCH" for r in rows),
    }


def build_quality(payload: dict) -> dict:
    values = payload.get("values", {})
    issues: list[str] = []
    warnings: list[str] = []

    fast_requirements = {
        "SPXA20R": finite(values.get("SPXA20R")),
        "breadth_momentum": finite(values.get("NYMO")) or finite(values.get("NAMO")),
        "ad_volume": finite(values.get("NYUD")) or finite(values.get("NAUD")),
        "down_up_ratio": finite(values.get("nyse_down_up_ratio")) or finite(values.get("nasdaq_down_up_ratio")),
    }
    context_requirements = {
        "MMFD": finite(values.get("MMFD")),
        "NASI_PLUS": finite(values.get("NASI_RSI")),
        "VVIX": finite(values.get("VVIX")),
        "SKEW_PROXY": finite(values.get("SKEW_LIVE_PROXY")),
    }

    for name, ok in fast_requirements.items():
        if not ok:
            issues.append(f"Missing fast-family source: {name}")
    for name, ok in context_requirements.items():
        if not ok:
            issues.append(f"Missing context source: {name}")

    mmfd = payload.get("mmfd_live") or {}
    coverage = mmfd.get("coverage_pct")
    if finite(coverage) and float(coverage) < 55.0:
        issues.append(f"MMFD coverage below hard floor: {float(coverage):.1f}%")
    elif finite(coverage) and float(coverage) < 80.0:
        warnings.append(f"MMFD coverage is usable but below 80%: {float(coverage):.1f}%")

    raw_errors = payload.get("errors") or {}
    if isinstance(raw_errors, dict) and raw_errors:
        warnings.extend(f"{key}: {value}" for key, value in raw_errors.items())

    for section in ("mmfd_live", "vvix_live", "skew_live"):
        row = payload.get(section)
        if isinstance(row, dict) and row.get("error"):
            issues.append(f"{section}: {row['error']}")

    engine = payload.get("unified_engine") or {}
    if not engine or not engine.get("engine_version"):
        issues.append("Unified decision missing")

    status = "DEGRADED" if issues else "PARTIAL" if warnings else "OK"
    return {
        "status": status,
        "actionable": status != "DEGRADED",
        "issues": issues,
        "warnings": warnings,
        "fast_source_availability": fast_requirements,
        "context_source_availability": context_requirements,
        "mmfd_coverage_pct": float(coverage) if finite(coverage) else None,
        "note": "Data-quality status does not alter REENTRY_UNIFIED_v1 signal thresholds or state logic.",
    }


def build_sources(payload: dict) -> dict:
    values = payload.get("values", {})
    nasi = payload.get("nasi_plus") or {}
    mmfd = payload.get("mmfd_live") or {}
    vvix = payload.get("vvix_live") or {}
    skew = payload.get("skew_live") or {}
    return {
        "fast_breadth": {
            "provider": "StockCharts quote feed",
            "timestamp": iso_or_none(values.get("timestamp_et")),
            "provisional": True,
        },
        "NASI_PLUS": {
            "provider": nasi.get("historical_source") or "Nasdaq Trader + StockCharts breadth",
            "timestamp": iso_or_none(values.get("timestamp_et")),
            "bootstrap_start_date": nasi.get("bootstrap_start_date"),
            "completed_daily_observations": nasi.get("completed_daily_observations"),
        },
        "MMFD": {
            "provider": mmfd.get("universe_source") or "Nasdaq Trader universe + Yahoo Finance prices",
            "timestamp": iso_or_none(mmfd.get("timestamp_et")),
            "coverage_pct": mmfd.get("coverage_pct"),
        },
        "VVIX": {
            "provider": vvix.get("source") or "Yahoo Finance",
            "timestamp": iso_or_none(vvix.get("timestamp_et")),
            "history_sessions": vvix.get("completed_history_sessions"),
        },
        "SKEW": {
            "provider": skew.get("source") or "Yahoo Finance SPX options + official SKEW history",
            "timestamp": iso_or_none(skew.get("timestamp_et")),
            "source_mode": skew.get("source_mode"),
            "official_date": skew.get("official_skew_date"),
        },
    }


def ledger_row(payload: dict) -> dict | None:
    engine = payload.get("unified_engine") or {}
    timestamp = engine.get("timestamp_et")
    if not timestamp:
        return None
    values = payload.get("values") or {}
    families = engine.get("fast_families") or {
        "FAST_BREADTH_TURN": bool((payload.get("families") or {}).get("fast_breadth_turn")),
        "MOMENTUM_TURN": bool((payload.get("families") or {}).get("momentum_turn")),
        "NET_VOLUME_TURN": bool((payload.get("families") or {}).get("net_volume_turn")),
        "DOWN_UP_RATIO_RELIEF": bool((payload.get("families") or {}).get("down_up_ratio_relief")),
    }
    context = engine.get("context_support") or {}
    quality = payload.get("data_quality") or {}
    prices = payload.get("market_prices") or {}

    def price(symbol: str, key: str):
        return (prices.get(symbol) or {}).get(key)

    return {
        "snapshot_id": timestamp,
        "market_date": engine.get("market_date") or values.get("market_date"),
        "timestamp_et": timestamp,
        "market_phase": engine.get("market_phase"),
        "state": engine.get("state"),
        "decision": engine.get("decision"),
        "actionable": int(bool(quality.get("actionable"))),
        "data_quality_status": quality.get("status"),
        "oversold_gate": int(bool(engine.get("oversold_gate"))),
        "fast_family_count": engine.get("fast_family_count"),
        "FAST_BREADTH_TURN": int(bool(families.get("FAST_BREADTH_TURN"))),
        "MOMENTUM_TURN": int(bool(families.get("MOMENTUM_TURN"))),
        "NET_VOLUME_TURN": int(bool(families.get("NET_VOLUME_TURN"))),
        "DOWN_UP_RATIO_RELIEF": int(bool(families.get("DOWN_UP_RATIO_RELIEF"))),
        "context_support_count": engine.get("context_support_count"),
        "MMFD_IMPROVING": int(bool(context.get("MMFD_IMPROVING"))),
        "NASI_TURNING_UP": int(bool(context.get("NASI_TURNING_UP"))),
        "VVIX_EASING": int(bool(context.get("VVIX_EASING"))),
        "SKEW_NARROWING": int(bool(context.get("SKEW_NARROWING"))),
        "SPXA20R": values.get("SPXA20R"),
        "NYMO": values.get("NYMO"),
        "NAMO": values.get("NAMO"),
        "NYUD": values.get("NYUD"),
        "NAUD": values.get("NAUD"),
        "nyse_down_up_ratio": values.get("nyse_down_up_ratio"),
        "nasdaq_down_up_ratio": values.get("nasdaq_down_up_ratio"),
        "MMFD": values.get("MMFD"),
        "NASI_RSI": values.get("NASI_RSI"),
        "VVIX": values.get("VVIX"),
        "SKEW_LIVE_PROXY": values.get("SKEW_LIVE_PROXY"),
        "SPY_price": price("SPY", "price"),
        "SPY_change_pct": price("SPY", "change_pct"),
        "SPY_price_timestamp_et": price("SPY", "timestamp_et"),
        "QQQ_price": price("QQQ", "price"),
        "QQQ_change_pct": price("QQQ", "change_pct"),
        "QQQ_price_timestamp_et": price("QQQ", "timestamp_et"),
        "VIX_price": price("^VIX", "price"),
        "VIX_change_pct": price("^VIX", "change_pct"),
        "MMFD_coverage_pct": quality.get("mmfd_coverage_pct"),
    }


def main() -> None:
    if not CURRENT.exists():
        raise SystemExit(f"Missing {CURRENT}")
    now = datetime.now(timezone.utc).astimezone(ET)
    payload = json.loads(CURRENT.read_text(encoding="utf-8"))

    market_prices, price_errors = fetch_market_prices(now)
    payload["snapshot_version"] = "REENTRY_UNIFIED_SNAPSHOT_v1"
    payload["snapshot_generated_at_et"] = now.isoformat()
    payload["market_prices"] = market_prices
    payload["market_price_errors"] = price_errors
    payload["sources"] = build_sources(payload)
    payload["data_quality"] = build_quality(payload)

    engine = payload.get("unified_engine")
    if isinstance(engine, dict):
        engine["data_quality_status"] = payload["data_quality"]["status"]
        engine["actionable"] = payload["data_quality"]["actionable"]

    row = ledger_row(payload)
    if row:
        append_schema_evolving(LEDGER, row, dedupe_key="snapshot_id")

    payload["prospective_history"] = prospective_history_summary()
    CURRENT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "snapshot_version": payload["snapshot_version"],
        "decision": (engine or {}).get("decision"),
        "market_phase": (engine or {}).get("market_phase"),
        "data_quality": payload["data_quality"],
        "prospective_history": payload["prospective_history"],
        "market_price_errors": price_errors,
        "ledger": str(LEDGER),
    }, indent=2))


if __name__ == "__main__":
    main()
