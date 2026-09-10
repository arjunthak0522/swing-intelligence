#!/usr/bin/env python3
"""Research-only persistence variants for REENTRY_UNIFIED_v1.

This script never changes the live decision. It replays actually captured point-in-time
snapshots and measures what simple confirmation requirements would have done to GO EARLY
timing and state churn. Promotion is explicitly out of scope.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data/reentry/unified_snapshot_ledger.csv"
HISTORY = ROOT / "data/reentry/unified_engine_history.csv"
OUT_JSON = ROOT / "research/reentry_unified_persistence_shadow.json"
OUT_MD = ROOT / "research/reentry_unified_persistence_shadow.md"

STATE_ORDER = {"WAIT": 0, "WATCH": 1, "GO_EARLY": 2}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def state(row: dict) -> str:
    value = str(row.get("decision") or row.get("state") or "WAIT").upper()
    return value if value in STATE_ORDER else "WAIT"


def replay_confirmation(rows: list[dict], required: int) -> list[dict]:
    out = []
    streak = 0
    for row in rows:
        raw = state(row)
        if raw == "GO_EARLY":
            streak += 1
            shadow = "GO_EARLY" if streak >= required else "WATCH"
        else:
            streak = 0
            shadow = raw
        out.append({**row, "raw_state": raw, "shadow_state": shadow, "go_streak": streak})
    return out


def transitions(rows: list[dict], key: str) -> int:
    values = [str(r.get(key) or "WAIT") for r in rows]
    return sum(a != b for a, b in zip(values, values[1:]))


def go_episodes(rows: list[dict], key: str) -> list[dict]:
    episodes = []
    start = None
    last = None
    for row in rows:
        ts = parse_ts(str(row.get("timestamp_et") or ""))
        if ts is None:
            continue
        active = str(row.get(key) or "") == "GO_EARLY"
        if active and start is None:
            start = row
        if not active and start is not None:
            episodes.append({"start": start, "last": last or start, "ended_before": row})
            start = None
        if active:
            last = row
    if start is not None:
        episodes.append({"start": start, "last": last or start, "ended_before": None})
    return episodes


def first_go_delay(raw_rows: list[dict], shadow_rows: list[dict]) -> dict | None:
    raw_go = next((r for r in raw_rows if state(r) == "GO_EARLY"), None)
    shadow_go = next((r for r in shadow_rows if r.get("shadow_state") == "GO_EARLY"), None)
    if raw_go is None:
        return None
    raw_ts = parse_ts(str(raw_go.get("timestamp_et") or ""))
    shadow_ts = parse_ts(str((shadow_go or {}).get("timestamp_et") or ""))
    delay = None if raw_ts is None or shadow_ts is None else (shadow_ts - raw_ts).total_seconds() / 60.0

    def number(row: dict | None, key: str):
        try:
            return float((row or {}).get(key))
        except Exception:
            return None

    return {
        "raw_first_go": raw_go.get("timestamp_et"),
        "shadow_first_go": (shadow_go or {}).get("timestamp_et"),
        "delay_minutes": delay,
        "raw_SPY_price": number(raw_go, "SPY_price"),
        "shadow_SPY_price": number(shadow_go, "SPY_price"),
        "raw_QQQ_price": number(raw_go, "QQQ_price"),
        "shadow_QQQ_price": number(shadow_go, "QQQ_price"),
    }


def summarize_variant(by_day: dict[str, list[dict]], required: int) -> dict:
    detail = {}
    total_transitions = 0
    total_go_episodes = 0
    delays = []
    for day, rows in sorted(by_day.items()):
        ordered = sorted(rows, key=lambda r: str(r.get("timestamp_et") or ""))
        shadow = replay_confirmation(ordered, required)
        delay = first_go_delay(ordered, shadow)
        if delay and delay.get("delay_minutes") is not None:
            delays.append(float(delay["delay_minutes"]))
        t = transitions(shadow, "shadow_state")
        ge = len(go_episodes(shadow, "shadow_state"))
        total_transitions += t
        total_go_episodes += ge
        detail[day] = {
            "snapshots": len(ordered),
            "raw_state_counts": dict(Counter(state(r) for r in ordered)),
            "shadow_state_counts": dict(Counter(str(r.get("shadow_state")) for r in shadow)),
            "raw_transitions": transitions([{**r, "raw_state": state(r)} for r in ordered], "raw_state"),
            "shadow_transitions": t,
            "first_go_timing": delay,
        }
    return {
        "confirmation_snapshots_required": required,
        "market_days": len(detail),
        "state_transitions": total_transitions,
        "go_early_episodes": total_go_episodes,
        "mean_first_go_delay_minutes": sum(delays) / len(delays) if delays else None,
        "days_with_measurable_go_delay": len(delays),
        "daily": detail,
    }


def main() -> None:
    rows = read_csv(LEDGER)
    source = "unified_snapshot_ledger.csv"
    if not rows:
        rows = read_csv(HISTORY)
        source = "unified_engine_history.csv (price context unavailable)"

    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("market_date") and row.get("timestamp_et"):
            by_day[str(row["market_date"])].append(row)

    baseline_transitions = 0
    baseline_go_episodes = 0
    for day_rows in by_day.values():
        ordered = sorted(day_rows, key=lambda r: str(r.get("timestamp_et") or ""))
        baseline = [{**r, "raw_state": state(r)} for r in ordered]
        baseline_transitions += transitions(baseline, "raw_state")
        baseline_go_episodes += len(go_episodes(baseline, "raw_state"))

    payload = {
        "classification": "RESEARCH_ONLY_PROSPECTIVE",
        "engine_impact": "NONE",
        "source": source,
        "generated_at": datetime.now().astimezone().isoformat(),
        "captured_snapshots": len(rows),
        "market_days": len(by_day),
        "baseline": {
            "state_transitions": baseline_transitions,
            "go_early_episodes": baseline_go_episodes,
        },
        "variants": {
            "confirm_2_snapshots": summarize_variant(by_day, 2),
            "confirm_3_snapshots": summarize_variant(by_day, 3),
        },
        "promotion_status": "DO_NOT_PROMOTE_FROM_THIS_REPORT",
        "limitations": [
            "Confirmation is measured in captured snapshots, not fixed clock minutes.",
            "A variant that reduces flips can still be worse if it misses rebound upside.",
            "Forward-return and adverse-excursion comparisons are required before any engine change.",
            "This script does not modify REENTRY_UNIFIED_v1 or the dashboard decision.",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# RE-ENTRY persistence shadow",
        "",
        "**Research only - no production signal change.**",
        "",
        f"Captured snapshots: **{len(rows)}** across **{len(by_day)}** market day(s).",
        "",
        f"Baseline transitions: **{baseline_transitions}**",
        "",
    ]
    for name, result in payload["variants"].items():
        lines += [
            f"## {name}",
            f"- state transitions: **{result['state_transitions']}**",
            f"- GO EARLY episodes: **{result['go_early_episodes']}**",
            f"- mean first-GO delay: **{result['mean_first_go_delay_minutes']} minutes**",
            "",
        ]
    lines += [
        "## Decision boundary",
        "",
        "A lower transition count is not sufficient evidence to change the engine. The confirmation variants must also be tested against SPY/QQQ forward returns, adverse excursion, rebound capture, and missed-upside cost.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
