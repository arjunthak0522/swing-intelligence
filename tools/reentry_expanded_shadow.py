#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "data/reentry/exhaustion_intraday_current.json"
HISTORY = ROOT / "data/reentry/expanded_shadow_history.csv"


def finite(x) -> bool:
    try:
        return x is not None and math.isfinite(float(x))
    except Exception:
        return False


def market_is_open(now: datetime) -> bool:
    now = now.astimezone(ET)
    if now.weekday() >= 5:
        return False
    minute = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= minute < 16 * 60


def load_prior(market_date: str) -> dict | None:
    if not HISTORY.exists():
        return None
    with HISTORY.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("market_date") == market_date]
    return rows[-1] if rows else None


def num(row: dict | None, key: str) -> float | None:
    if not row:
        return None
    value = row.get(key)
    return float(value) if finite(value) else None


def append(row: dict) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    exists = HISTORY.exists()
    with HISTORY.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def main() -> None:
    now = datetime.now(timezone.utc).astimezone(ET)
    if not market_is_open(now):
        print(json.dumps({"status": "SKIPPED_OUTSIDE_REGULAR_SESSION", "timestamp_et": now.isoformat()}))
        return
    if not CURRENT.exists():
        raise SystemExit(f"Missing {CURRENT}")

    payload = json.loads(CURRENT.read_text(encoding="utf-8"))
    values = payload.get("values", {})
    market_date = values.get("market_date") or now.date().isoformat()
    prior = load_prior(market_date)

    fast_count = int(payload.get("turn_family_count") or 0)
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

    # Context turns are deliberately directional. Oversold/stressed levels establish setup;
    # they do not count as reversal evidence by themselves.
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

    # Less-strict candidate rule:
    # A) retain existing 2+ fast-family path, OR
    # B) allow 1 fast-family turn plus at least 1 independent context turn.
    if not oversold_gate:
        state, action = "INACTIVE", "WAIT"
    elif fast_count >= 2:
        state, action = "EARLY_GO", "GO_EARLY_INTRADAY"
    elif fast_count >= 1 and context_count >= 1:
        state, action = "EARLY_GO", "GO_EARLY_CONTEXT_SUPPORTED"
    elif fast_count >= 1 or context_count >= 2:
        state, action = "WATCH", "WATCH_EARLY_TURN"
    else:
        state, action = "WAIT", "WAIT_FOR_WASHOUT"

    result = {
        "research_only": True,
        "rule_version": "EXPANDED_EARLY_GO_v1",
        "official_completed_close_signal_modified": False,
        "oversold_gate": oversold_gate,
        "fast_family_count": fast_count,
        "context_support_count": context_count,
        "context_support": context,
        "state": state,
        "candidate_action": action,
        "logic": "GO if oversold and either 2+ fast families turn, or 1 fast family plus 1 independent context turn from MMFD/NASI/VVIX/SKEW.",
        "timestamp_et": now.isoformat(),
    }

    payload["expanded_shadow"] = result
    CURRENT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    append({
        "market_date": market_date,
        "timestamp_et": now.isoformat(),
        "state": state,
        "candidate_action": action,
        "oversold_gate": int(oversold_gate),
        "fast_family_count": fast_count,
        "context_support_count": context_count,
        "MMFD_IMPROVING": int(mmfd_turn),
        "NASI_TURNING_UP": int(nasi_turn),
        "VVIX_EASING": int(vvix_relief),
        "SKEW_NARROWING": int(skew_relief),
        "MMFD": mmfd,
        "NASI_RSI": nasi,
        "VVIX": vvix,
        "SKEW_LIVE_PROXY": skew,
    })
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
