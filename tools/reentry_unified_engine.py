#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "data/reentry/exhaustion_intraday_current.json"
HISTORY = ROOT / "data/reentry/unified_engine_history.csv"
FINAL_BUFFER_MINUTE = 16 * 60 + 15
ACTIVE_END_MINUTE = 16 * 60 + 45
FAST_FAMILY_MEMORY_MINUTES = 30
FAST_FAMILY_KEYS = (
    "FAST_BREADTH_TURN",
    "MOMENTUM_TURN",
    "NET_VOLUME_TURN",
    "DOWN_UP_RATIO_RELIEF",
)


def finite(x) -> bool:
    try:
        return x is not None and math.isfinite(float(x))
    except Exception:
        return False


def truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def allowed_window(now: datetime) -> bool:
    now = now.astimezone(ET)
    if now.weekday() >= 5:
        return False
    minute = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= minute <= ACTIVE_END_MINUTE


def market_phase(now: datetime) -> str:
    now = now.astimezone(ET)
    minute = now.hour * 60 + now.minute
    if minute < 16 * 60:
        return "LIVE_PROVISIONAL"
    if minute < FINAL_BUFFER_MINUTE:
        return "CLOSE_SETTLING"
    return "MARKET_CLOSED_FINAL"


def load_day_rows(market_date: str) -> list[dict]:
    if not HISTORY.exists():
        return []
    with HISTORY.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("market_date") == market_date]
    rows.sort(key=lambda r: r.get("timestamp_et") or "")
    return rows


def load_prior(market_date: str) -> dict | None:
    rows = load_day_rows(market_date)
    return rows[-1] if rows else None


def first_latched_go(market_date: str) -> dict | None:
    for row in load_day_rows(market_date):
        if (row.get("decision") or row.get("state")) == "GO_EARLY":
            return row
    return None


def recent_rows(market_date: str, now: datetime, minutes: int) -> list[dict]:
    cutoff = now.astimezone(ET) - timedelta(minutes=minutes)
    out = []
    for row in load_day_rows(market_date):
        raw = row.get("timestamp_et")
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(raw).astimezone(ET)
        except (TypeError, ValueError):
            continue
        if cutoff <= ts <= now.astimezone(ET):
            out.append(row)
    return out


def num(row: dict | None, key: str) -> float | None:
    if not row:
        return None
    value = row.get(key)
    return float(value) if finite(value) else None


def append(row: dict) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    if not HISTORY.exists():
        with HISTORY.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
        return
    with HISTORY.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = reader.fieldnames or []
    new_fields = list(fields)
    for key in row:
        if key not in new_fields:
            new_fields.append(key)
    with HISTORY.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=new_fields)
        writer.writeheader()
        writer.writerows(rows)
        writer.writerow(row)


def current_fast_families(payload: dict) -> dict[str, bool]:
    source = payload.get("families") or {}
    return {
        "FAST_BREADTH_TURN": bool(source.get("fast_breadth_turn")),
        "MOMENTUM_TURN": bool(source.get("momentum_turn")),
        "NET_VOLUME_TURN": bool(source.get("net_volume_turn")),
        "DOWN_UP_RATIO_RELIEF": bool(source.get("down_up_ratio_relief")),
    }


def active_fast_families(payload: dict, history: list[dict]) -> tuple[dict[str, bool], dict[str, str | None]]:
    active = current_fast_families(payload)
    last_seen: dict[str, str | None] = {key: None for key in FAST_FAMILY_KEYS}
    current_ts = (payload.get("values") or {}).get("timestamp_et")
    for key, on in active.items():
        if on:
            last_seen[key] = current_ts
    for row in history:
        timestamp = row.get("timestamp_et")
        for key in FAST_FAMILY_KEYS:
            if truthy(row.get(key)):
                active[key] = True
                last_seen[key] = timestamp
    return active, last_seen


def classify_cash_context(values: dict, oversold_gate: bool, deploy: bool) -> dict:
    sp20 = values.get("SPXA20R")
    mmfd = values.get("MMFD")
    nasi = values.get("NASI_RSI")

    extension_signals = {
        "SPXA20R_STRONG": finite(sp20) and float(sp20) >= 70.0,
        "MMFD_STRONG": finite(mmfd) and float(mmfd) >= 70.0,
        "NASI_OVERBOUGHT": finite(nasi) and float(nasi) >= 70.0,
    }
    weak_signals = {
        "SPXA20R_WEAK": finite(sp20) and 30.0 <= float(sp20) < 50.0,
        "MMFD_WEAK": finite(mmfd) and 30.0 <= float(mmfd) < 50.0,
        "NASI_WEAK": finite(nasi) and 30.0 <= float(nasi) < 50.0,
    }
    extension_count = sum(extension_signals.values())
    weak_count = sum(weak_signals.values())

    if deploy:
        market_condition = "RECOVERING_FROM_OVERSOLD"
        market_condition_reason = "A qualifying reversal has already fired after an oversold reset; current internals are being monitored as the recovery develops."
    elif oversold_gate:
        market_condition = "OVERSOLD"
        market_condition_reason = "At least one canonical oversold gate is active, so spare-cash deployment is getting closer but still requires reversal confirmation."
    elif extension_count >= 2:
        market_condition = "EXTENDED"
        market_condition_reason = "At least two independent breadth measures are in strong or overbought territory; this is not an attractive tactical entry for spare cash."
    elif weak_count >= 2:
        market_condition = "PULLBACK"
        market_condition_reason = "Multiple breadth measures are below their neutral zones, but the market has not reached the canonical oversold gate."
    else:
        market_condition = "BALANCED"
        market_condition_reason = "Breadth is neither meaningfully oversold nor broadly extended; there is no tactical cash-deployment edge."

    return {
        "market_condition": market_condition,
        "market_condition_reason": market_condition_reason,
        "extension_signal_count": extension_count,
        "extension_signals": extension_signals,
        "weak_signal_count": weak_count,
        "weak_signals": weak_signals,
        "regime_is_decision_input": False,
    }


def evaluate(payload: dict, prior: dict | None, recent: list[dict], latched_go: dict | None) -> dict:
    values = payload.get("values", {})
    current_fast = current_fast_families(payload)
    fast_families, fast_last_seen = active_fast_families(payload, recent)
    fast_count = sum(fast_families.values())
    sp20 = values.get("SPXA20R")
    mmfd = values.get("MMFD")
    nasi = values.get("NASI_RSI")
    vvix = values.get("VVIX")
    skew = values.get("SKEW_LIVE_PROXY")

    oversold_gate = (
        (finite(sp20) and float(sp20) < 30.0)
        or (finite(mmfd) and float(mmfd) < 30.0)
        or str(payload.get("daily_context_state", "")).upper() in {"OVERSOLD", "WASHOUT", "CONFIRMED"}
    )

    prior_mmfd = num(prior, "MMFD")
    prior_nasi = num(prior, "NASI_RSI")
    prior_vvix = num(prior, "VVIX")
    prior_skew = num(prior, "SKEW_LIVE_PROXY")

    mmfd_turn = finite(mmfd) and finite(prior_mmfd) and float(mmfd) > float(prior_mmfd)
    nasi_turn = str(values.get("NASI_DIRECTION", "")).upper() == "RISING" or (
        finite(nasi) and finite(prior_nasi) and float(nasi) > float(prior_nasi)
    )
    vvix_relief = str(values.get("VVIX_DIRECTION", "")).upper() == "FALLING" or (
        finite(vvix) and finite(prior_vvix) and float(vvix) < float(prior_vvix)
    )
    skew_relief = str(values.get("SKEW_DIRECTION", "")).upper() == "NARROWING" or (
        finite(skew) and finite(prior_skew) and float(skew) < float(prior_skew)
    )

    context = {
        "MMFD_IMPROVING": bool(mmfd_turn),
        "NASI_TURNING_UP": bool(nasi_turn),
        "VVIX_EASING": bool(vvix_relief),
        "SKEW_NARROWING": bool(skew_relief),
    }
    context_count = sum(context.values())

    go_latched = latched_go is not None
    go_triggered_at = latched_go.get("timestamp_et") if latched_go else None

    if go_latched:
        state, action = "GO_EARLY", "GO_EARLY"
        reason = "GO EARLY already fired earlier this market session and remains latched through the close. Current evidence continues to update but cannot revoke the same-day decision."
    elif not oversold_gate:
        state, action = "WAIT", "WAIT"
        reason = "Oversold setup gate is not active."
    elif fast_count >= 2:
        state, action = "GO_EARLY", "GO_EARLY"
        reason = "Oversold setup is active and at least two independent fast reversal families have turned within the recent confirmation window."
    elif fast_count >= 1 and context_count >= 1:
        state, action = "GO_EARLY", "GO_EARLY"
        reason = "Oversold setup is active with at least one recent fast reversal family and at least one independent context turn."
    elif fast_count >= 1 or context_count >= 2:
        state, action = "WATCH", "WATCH"
        reason = "Oversold setup is active and reversal evidence is developing, but the GO EARLY threshold is not met."
    else:
        state, action = "WAIT", "WAIT"
        reason = "Oversold setup is active, but reversal evidence has not reached WATCH or GO EARLY."

    deploy = action == "GO_EARLY"
    if deploy:
        deployment_signal = "DEPLOY"
        deployment_reason = "A qualifying reversal has fired after an oversold reset. Begin deploying spare cash; today\'s signal remains latched through the session."
    elif oversold_gate:
        deployment_signal = "WATCH"
        deployment_reason = "The market is oversold enough to be interesting, but reversal confirmation has not yet reached the deployment threshold."
    else:
        deployment_signal = "HOLD_CASH"
        deployment_reason = "There is no qualifying oversold re-entry setup. Keep spare cash available rather than forcing an entry."

    cash_context = classify_cash_context(values, oversold_gate, deploy)

    return {
        "engine_version": "REENTRY_UNIFIED_v1",
        "primary_engine": True,
        "deployment_signal": deployment_signal,
        "deployment_reason": deployment_reason,
        **cash_context,
        "oversold_gate": oversold_gate,
        "fast_family_count": fast_count,
        "fast_families": fast_families,
        "fast_families_current_snapshot": current_fast,
        "fast_family_memory_minutes": FAST_FAMILY_MEMORY_MINUTES,
        "fast_family_last_seen_et": fast_last_seen,
        "context_support_count": context_count,
        "context_support": context,
        "go_latched_for_session": go_latched,
        "go_triggered_at_et": go_triggered_at,
        "state": state,
        "decision": action,
        "decision_reason": reason,
        "logic": "Cash action is HOLD CASH when no oversold setup is active, WATCH when the canonical oversold gate is active but no GO has fired, and DEPLOY once GO EARLY qualifies. GO EARLY requires either 2+ fast reversal families within the last 30 minutes, or 1 recent fast family plus 1 current context turn. Once GO EARLY fires, DEPLOY remains latched through that market session and resets on the next market date. Market-condition labels are descriptive context and do not modify the trigger.",
    }


def main() -> None:
    now = datetime.now(timezone.utc).astimezone(ET)
    if not allowed_window(now):
        print(json.dumps({"status": "OUTSIDE_REFRESH_WINDOW", "timestamp_et": now.isoformat()}))
        return
    if not CURRENT.exists():
        raise SystemExit(f"Missing {CURRENT}")

    payload = json.loads(CURRENT.read_text(encoding="utf-8"))
    values = payload.get("values", {})
    market_date = values.get("market_date") or now.date().isoformat()
    prior = load_prior(market_date)
    recent = recent_rows(market_date, now, FAST_FAMILY_MEMORY_MINUTES)
    latched_go = first_latched_go(market_date)
    result = evaluate(payload, prior, recent, latched_go)
    result["market_phase"] = market_phase(now)
    result["timestamp_et"] = now.isoformat()
    result["market_date"] = market_date
    if result["decision"] == "GO_EARLY" and not result["go_triggered_at_et"]:
        result["go_triggered_at_et"] = now.isoformat()

    payload["unified_engine"] = result
    payload.pop("expanded_shadow", None)
    CURRENT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    append({
        "market_date": market_date,
        "timestamp_et": now.isoformat(),
        "market_phase": result["market_phase"],
        "state": result["state"],
        "decision": result["decision"],
        "deployment_signal": result["deployment_signal"],
        "market_condition": result["market_condition"],
        "extension_signal_count": result["extension_signal_count"],
        "weak_signal_count": result["weak_signal_count"],
        "go_latched_for_session": int(result["go_latched_for_session"]),
        "go_triggered_at_et": result["go_triggered_at_et"],
        "oversold_gate": int(result["oversold_gate"]),
        "fast_family_count": result["fast_family_count"],
        "FAST_BREADTH_TURN": int(result["fast_families"]["FAST_BREADTH_TURN"]),
        "MOMENTUM_TURN": int(result["fast_families"]["MOMENTUM_TURN"]),
        "NET_VOLUME_TURN": int(result["fast_families"]["NET_VOLUME_TURN"]),
        "DOWN_UP_RATIO_RELIEF": int(result["fast_families"]["DOWN_UP_RATIO_RELIEF"]),
        "FAST_BREADTH_TURN_CURRENT": int(result["fast_families_current_snapshot"]["FAST_BREADTH_TURN"]),
        "MOMENTUM_TURN_CURRENT": int(result["fast_families_current_snapshot"]["MOMENTUM_TURN"]),
        "NET_VOLUME_TURN_CURRENT": int(result["fast_families_current_snapshot"]["NET_VOLUME_TURN"]),
        "DOWN_UP_RATIO_RELIEF_CURRENT": int(result["fast_families_current_snapshot"]["DOWN_UP_RATIO_RELIEF"]),
        "fast_family_memory_minutes": result["fast_family_memory_minutes"],
        "context_support_count": result["context_support_count"],
        "MMFD_IMPROVING": int(result["context_support"]["MMFD_IMPROVING"]),
        "NASI_TURNING_UP": int(result["context_support"]["NASI_TURNING_UP"]),
        "VVIX_EASING": int(result["context_support"]["VVIX_EASING"]),
        "SKEW_NARROWING": int(result["context_support"]["SKEW_NARROWING"]),
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
    })
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
