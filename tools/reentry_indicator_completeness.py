#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd
import yfinance as yf

CBOE_SKEW_HISTORY = "https://cdn.cboe.com/api/global/us_indices/daily_prices/SKEW_History.csv"


def finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except Exception:
        return False


def market_date(payload: dict) -> str:
    values = payload.get("values") or {}
    return str((payload.get("unified_engine") or {}).get("market_date") or values.get("market_date") or "")


def market_phase(payload: dict) -> str:
    return str((payload.get("unified_engine") or {}).get("market_phase") or "").upper()


def date_prefix(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    return None


def infer_freshness_state(row: dict, target_date: str, phase: str) -> str:
    explicit = str(row.get("freshness_state") or "").strip().upper()
    if explicit in {"LIVE", "DELAYED", "TODAY_CLOSE", "PRIOR_CLOSE", "STALE", "UNAVAILABLE"}:
        return explicit
    if str(row.get("state") or "").upper() == "UNAVAILABLE" or str(row.get("status") or "").upper() == "UNAVAILABLE":
        return "UNAVAILABLE"

    freshness_type = str(row.get("freshness_type") or "").upper()
    observed_date = date_prefix(row.get("last_updated") or row.get("timestamp_et") or row.get("official_skew_date"))
    if not observed_date:
        return "UNAVAILABLE"

    if target_date and observed_date < target_date:
        if "DAILY" in freshness_type or "CLOSE" in freshness_type or "PRIOR" in freshness_type:
            return "PRIOR_CLOSE"
        return "STALE"
    if target_date and observed_date > target_date:
        return "STALE"

    if "INTRADAY" in freshness_type:
        return "DELAYED"
    if "CURRENT_DAILY_BAR" in freshness_type or "CURRENT_BAR" in freshness_type:
        return "DELAYED" if phase != "MARKET_CLOSED_FINAL" else "TODAY_CLOSE"
    if "DAILY_CLOSE" in freshness_type or freshness_type == "DAILY_CLOSE":
        return "TODAY_CLOSE" if phase == "MARKET_CLOSED_FINAL" else "DELAYED"
    return "DELAYED"


def normalize_row_freshness(row: dict, target_date: str, phase: str) -> None:
    if not isinstance(row, dict):
        return
    row["freshness_state"] = infer_freshness_state(row, target_date, phase)


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
            close = close.iloc[:, 0]
        return pd.to_numeric(close, errors="coerce").dropna()
    return pd.Series(dtype=float)


def skew_history() -> tuple[pd.Series, str]:
    try:
        frame = yf.download("^SKEW", period="2y", interval="1d", auto_adjust=False, progress=False, threads=False, timeout=20)
        series = extract_close(frame, "^SKEW")
        if not series.empty:
            series.index = pd.to_datetime(series.index)
            return series.sort_index(), "Yahoo Finance official SKEW daily history"
    except Exception:
        pass

    req = Request(CBOE_SKEW_HISTORY, headers={"User-Agent": "Mozilla/5.0 RE-ENTRY/1.0", "Accept": "text/csv,*/*"})
    with urlopen(req, timeout=20) as resp:  # nosec - fixed Cboe endpoint
        raw = resp.read().decode("utf-8", errors="replace")
    frame = pd.read_csv(io.StringIO(raw))
    cols = {str(c).upper().strip(): c for c in frame.columns}
    date_col = cols.get("DATE")
    close_col = cols.get("CLOSE") or cols.get("SKEW")
    if not date_col or not close_col:
        raise ValueError(f"Unexpected Cboe SKEW columns: {list(frame.columns)}")
    dates = pd.to_datetime(frame[date_col], errors="coerce")
    values = pd.to_numeric(frame[close_col], errors="coerce")
    series = pd.Series(values.values, index=dates).dropna()
    series = series[~series.index.isna()].sort_index()
    if series.empty:
        raise ValueError("Official SKEW history is empty")
    return series.tail(520), "Cboe official SKEW daily history"


def populate_official_skew(payload: dict) -> None:
    values = payload.setdefault("values", {})
    existing = payload.get("skew_live") if isinstance(payload.get("skew_live"), dict) else {}
    target_date = market_date(payload)
    phase = market_phase(payload)
    live_ok = finite(values.get("SKEW_LIVE_PROXY"))
    official_existing = finite(existing.get("official_skew_latest_close"))

    if official_existing:
        latest_date = str(existing.get("official_skew_date") or date_prefix(existing.get("last_updated")) or "")
        official_state = "TODAY_CLOSE" if target_date and latest_date == target_date and phase == "MARKET_CLOSED_FINAL" else "PRIOR_CLOSE" if target_date and latest_date and latest_date < target_date else "DELAYED"
        existing["official_freshness_state"] = official_state
        if live_ok:
            existing["freshness_type"] = existing.get("freshness_type") or "INTRADAY_PROXY_PLUS_DAILY_CLOSE"
            existing["freshness_state"] = "LIVE"
            existing["last_updated"] = existing.get("timestamp_et") or existing.get("last_updated")
        else:
            existing["freshness_type"] = "DAILY_CLOSE"
            existing["freshness_state"] = official_state
            existing["last_updated"] = latest_date or existing.get("last_updated")
        payload["skew_live"] = existing
        return

    series, source = skew_history()
    current = float(series.iloc[-1])
    prior = float(series.iloc[-2]) if len(series) >= 2 else None
    latest_date = pd.Timestamp(series.index[-1]).date().isoformat()
    direction = "UNAVAILABLE"
    if finite(prior):
        delta = current - float(prior)
        direction = "WIDENING" if delta > 0.10 else "NARROWING" if delta < -0.10 else "FLAT"
    sample = series.tail(504)
    percentile = 100.0 * float((sample <= current).sum()) / float(len(sample))
    official_state = "TODAY_CLOSE" if target_date and latest_date == target_date and phase == "MARKET_CLOSED_FINAL" else "PRIOR_CLOSE"

    values["SKEW_OFFICIAL_CLOSE"] = current
    values["SKEW_OFFICIAL_PERCENTILE_2Y"] = percentile
    result = dict(existing)
    result.update({
        "name": "Official Cboe SKEW",
        "official_symbol": "SKEW",
        "official_skew_latest_close": current,
        "official_skew_prior_close": prior,
        "official_skew_date": latest_date,
        "official_skew_direction": direction,
        "official_skew_percentile_2y": percentile,
        "official_skew_history_sessions": int(len(sample)),
        "source_mode": result.get("source_mode") or "OFFICIAL_DAILY_CLOSE_FALLBACK",
        "official_freshness_state": official_state,
        "freshness_type": result.get("freshness_type") or ("INTRADAY_PROXY_PLUS_DAILY_CLOSE" if live_ok else "DAILY_CLOSE"),
        "freshness_state": "LIVE" if live_ok else official_state,
        "last_updated": result.get("timestamp_et") if live_ok else latest_date,
        "source": result.get("source") or source,
        "provisional_intraday": live_ok,
    })
    payload["skew_live"] = result


def unavailable_card(name: str, cadence: str, role: str) -> dict:
    return {
        "name": name,
        "state": "UNAVAILABLE",
        "direction": "UNAVAILABLE",
        "role": role,
        "decision_input": False,
        "freshness_type": cadence,
        "freshness_state": "UNAVAILABLE",
        "last_updated": None,
        "status": "UNAVAILABLE",
        "meaning": "No current or recent valid observation was available. The indicator remains listed so missing data is explicit rather than silently omitted.",
    }


def ensure_indicator_blocks(payload: dict) -> None:
    target_date = market_date(payload)
    phase = market_phase(payload)
    leading_names = {
        "zweig_breadth_thrust": ("Zweig Breadth Thrust", "INTRADAY_OR_DELAYED"),
        "mcclellan_velocity": ("Nasdaq McClellan Oscillator velocity", "PRIOR_CLOSE_OR_CAPTURED_HISTORY"),
        "nasdaq_short_breadth": ("Short-term Nasdaq breadth", "CURRENT_DAILY_BAR_OR_PRIOR_CLOSE"),
        "credit_risk_turn": ("Credit-risk turn - HYG/LQD", "DAILY_CLOSE_OR_CURRENT_BAR"),
    }
    block = payload.get("leading_indicators")
    if not isinstance(block, dict):
        block = {
            "version": "REENTRY_LEADING_INDICATORS_v1",
            "decision_input": False,
            "changes_deploy_trigger": False,
            "changes_recovery_stage": False,
            "creates_new_score": False,
            "indicators": {},
            "errors": {"block": "Leading-indicator builder did not complete"},
        }
        payload["leading_indicators"] = block
    indicators = block.setdefault("indicators", {})
    for key, (name, cadence) in leading_names.items():
        indicators.setdefault(key, unavailable_card(name, cadence, "LEADING_CONTEXT_ONLY"))
        normalize_row_freshness(indicators[key], target_date, phase)

    secondary_names = {
        "vol_structure": ("VIX term-structure repair", "DAILY_CLOSE_OR_PRIOR_CLOSE"),
        "breadth_thrust": ("Breadth participation thrust", "INTRADAY_OR_DELAYED"),
        "risk_appetite": ("Risk-appetite broadening", "DAILY_CLOSE_OR_PRIOR_CLOSE"),
        "options_sentiment": ("Options sentiment", "LIVE_OR_DAILY_CLOSE_OR_PRIOR_CLOSE"),
    }
    secondary = payload.get("secondary_confirmation")
    if not isinstance(secondary, dict):
        secondary = {
            "version": "REENTRY_SECONDARY_CONFIRMATION_v1",
            "decision_input": False,
            "changes_deploy_trigger": False,
            "changes_recovery_stage": False,
            "families": {},
            "breadth_context": {},
            "errors": {"block": "Secondary-confirmation builder did not complete"},
        }
        payload["secondary_confirmation"] = secondary
    families = secondary.setdefault("families", {})
    for key, (name, cadence) in secondary_names.items():
        families.setdefault(key, unavailable_card(name, cadence, "SECONDARY_CONTEXT_ONLY"))
        normalize_row_freshness(families[key], target_date, phase)
    breadth_context = secondary.setdefault("breadth_context", {})
    breadth_context.setdefault("t2108", unavailable_card("NYSE Stocks Above 40-Day Moving Average", "DAILY_CLOSE_OR_PRIOR_CLOSE", "BREADTH_CONTEXT_ONLY"))
    normalize_row_freshness(breadth_context["t2108"], target_date, phase)

    if isinstance(payload.get("skew_live"), dict):
        normalize_row_freshness(payload["skew_live"], target_date, phase)

    engine = payload.get("unified_engine")
    if isinstance(engine, dict):
        engine["leading_indicators"] = block
        engine["secondary_confirmation"] = secondary


def repair_quality(payload: dict) -> None:
    quality = payload.get("data_quality")
    if not isinstance(quality, dict):
        return
    values = payload.get("values") or {}
    official_ok = finite(values.get("SKEW_OFFICIAL_CLOSE"))
    live_ok = finite(values.get("SKEW_LIVE_PROXY"))
    availability = quality.setdefault("context_source_availability", {})
    availability["SKEW_PROXY"] = live_ok
    availability["SKEW_OFFICIAL"] = official_ok

    issues = list(quality.get("issues") or [])
    warnings = list(quality.get("warnings") or [])
    if official_ok:
        issues = [item for item in issues if item != "Missing context source: SKEW_PROXY"]
        if not live_ok:
            skew = payload.get("skew_live") or {}
            note = f"Live SPX skew proxy unavailable; using official SKEW {skew.get('freshness_state') or 'PRIOR_CLOSE'} from {skew.get('official_skew_date') or skew.get('last_updated')}."
            if note not in warnings:
                warnings.append(note)
    quality["issues"] = issues
    quality["warnings"] = warnings
    quality["status"] = "DEGRADED" if issues else "PARTIAL" if warnings else "OK"
    quality["actionable"] = quality["status"] != "DEGRADED"
    engine = payload.get("unified_engine")
    if isinstance(engine, dict):
        engine["data_quality_status"] = quality["status"]
        engine["actionable"] = quality["actionable"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    args = parser.parse_args()
    path = Path(args.snapshot)
    payload = json.loads(path.read_text(encoding="utf-8"))

    skew_error = None
    try:
        populate_official_skew(payload)
    except Exception as exc:
        skew_error = f"{type(exc).__name__}: {exc}"

    ensure_indicator_blocks(payload)
    repair_quality(payload)
    payload["indicator_completeness"] = {
        "contract": "Every defined indicator is present on every published snapshot. Freshness may be LIVE, DELAYED, TODAY_CLOSE, PRIOR_CLOSE, STALE, or UNAVAILABLE.",
        "official_skew_fallback_error": skew_error,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["indicator_completeness"], indent=2))


if __name__ == "__main__":
    main()
