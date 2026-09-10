#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data/reentry/unified_snapshot_ledger.csv"
HISTORY = ROOT / "data/reentry/unified_engine_history.csv"
INTRADAY = ROOT / "data/reentry/exhaustion_intraday_history.csv"
OUT_JSON = ROOT / "research/reentry_unified_whipsaw_analysis.json"
OUT_MD = ROOT / "research/reentry_unified_whipsaw_analysis.md"

STATE_ORDER = {"WAIT": 0, "WATCH": 1, "GO_EARLY": 2}
FAMILY_KEYS = [
    "FAST_BREADTH_TURN",
    "MOMENTUM_TURN",
    "NET_VOLUME_TURN",
    "DOWN_UP_RATIO_RELIEF",
    "MMFD_IMPROVING",
    "NASI_TURNING_UP",
    "VVIX_EASING",
    "SKEW_NARROWING",
]


def finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except Exception:
        return False


def truth(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def normalize_state(row: dict) -> str:
    raw = str(row.get("state") or row.get("decision") or "").upper().strip()
    if raw in STATE_ORDER:
        return raw
    if raw in {"WASHOUT", "GO_EARLY_INTRADAY"}:
        return "GO_EARLY"
    if raw in {"WASHOUT_WATCH", "WATCH_EARLY_TURN"}:
        return "WATCH"
    return "WAIT"


def episodeize(rows: list[dict]) -> list[dict]:
    episodes = []
    current = None
    for row in rows:
        ts = parse_ts(str(row.get("timestamp_et") or ""))
        if ts is None:
            continue
        state = normalize_state(row)
        if current is None or current["state"] != state:
            if current is not None:
                current["end"] = ts
                current["duration_minutes"] = max(0.0, (current["end"] - current["start"]).total_seconds() / 60.0)
                episodes.append(current)
            current = {"state": state, "start": ts, "end": ts, "rows": 1}
        else:
            current["end"] = ts
            current["rows"] += 1
    if current is not None:
        current["duration_minutes"] = max(0.0, (current["end"] - current["start"]).total_seconds() / 60.0)
        episodes.append(current)
    return episodes


def family_changes(a: dict, b: dict) -> list[str]:
    changed = []
    for key in FAMILY_KEYS:
        if key not in a or key not in b or a.get(key) in (None, "") or b.get(key) in (None, ""):
            continue
        if truth(a.get(key)) != truth(b.get(key)):
            changed.append(key)
    return changed


def family_flip_analysis(rows: list[dict]) -> dict:
    result = {}
    ordered = sorted(rows, key=lambda r: str(r.get("timestamp_et") or ""))
    for key in FAMILY_KEYS:
        vals = []
        for row in ordered:
            raw = row.get(key)
            if raw in (None, ""):
                continue
            vals.append(truth(raw))
        flips = sum(a != b for a, b in zip(vals, vals[1:]))
        result[key] = {"observations": len(vals), "true_count": sum(vals), "flip_count": flips}
    return result


def summarize_day(rows: list[dict]) -> dict:
    rows = sorted(rows, key=lambda r: parse_ts(str(r.get("timestamp_et") or "")) or datetime.min)
    states = [normalize_state(r) for r in rows]
    transition_types = []
    transition_drivers = Counter()
    intervals = []
    for left, right in zip(rows, rows[1:]):
        a = normalize_state(left)
        b = normalize_state(right)
        lts = parse_ts(str(left.get("timestamp_et") or ""))
        rts = parse_ts(str(right.get("timestamp_et") or ""))
        if lts and rts:
            intervals.append((rts - lts).total_seconds() / 60.0)
        if a != b:
            transition_types.append(f"{a}->{b}")
            for key in family_changes(left, right):
                transition_drivers[key] += 1

    eps = episodeize(rows)
    go_eps = [e for e in eps if e["state"] == "GO_EARLY"]
    watch_eps = [e for e in eps if e["state"] == "WATCH"]
    wait_eps = [e for e in eps if e["state"] == "WAIT"]
    return {
        "snapshots": len(rows),
        "state_counts": dict(Counter(states)),
        "transition_count": len(transition_types),
        "transition_types": dict(Counter(transition_types)),
        "transition_family_changes": dict(transition_drivers),
        "max_state": max(states, key=lambda s: STATE_ORDER.get(s, 0)) if states else None,
        "final_state": states[-1] if states else None,
        "go_early_episodes": len(go_eps),
        "watch_episodes": len(watch_eps),
        "wait_episodes": len(wait_eps),
        "go_early_durations_minutes": [round(e["duration_minutes"], 2) for e in go_eps],
        "watch_durations_minutes": [round(e["duration_minutes"], 2) for e in watch_eps],
        "ephemeral_go_under_10m": sum(e["duration_minutes"] < 10 for e in go_eps),
        "ephemeral_watch_under_10m": sum(e["duration_minutes"] < 10 for e in watch_eps),
        "median_snapshot_spacing_minutes": statistics.median(intervals) if intervals else None,
        "family_flip_analysis": family_flip_analysis(rows),
    }


def precursor_flip_analysis(rows: list[dict]) -> dict:
    ordered = sorted(rows, key=lambda r: str(r.get("timestamp_et") or ""))
    fields = ["SPXA20R", "NYUD", "NAUD", "nyse_down_up_ratio", "nasdaq_down_up_ratio", "NASI_RSI", "VVIX"]
    result = {}
    for key in fields:
        values = [float(r[key]) for r in ordered if finite(r.get(key))]
        direction_flips = 0
        prior_direction = 0
        for a, b in zip(values, values[1:]):
            direction = 1 if b > a else -1 if b < a else 0
            if direction and prior_direction and direction != prior_direction:
                direction_flips += 1
            if direction:
                prior_direction = direction
        result[key] = {"observations": len(values), "direction_flip_count": direction_flips}
    return result


def main() -> None:
    unified = read_csv(LEDGER)
    source = "unified_snapshot_ledger.csv"
    if not unified:
        unified = read_csv(HISTORY)
        source = "unified_engine_history.csv"
    intraday = read_csv(INTRADAY)

    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in unified:
        day = str(row.get("market_date") or "")
        if day:
            by_day[day].append(row)

    daily = {day: summarize_day(rows) for day, rows in sorted(by_day.items())}
    all_transitions = sum(v["transition_count"] for v in daily.values())
    all_go = sum(v["go_early_episodes"] for v in daily.values())
    all_watch = sum(v["watch_episodes"] for v in daily.values())
    ephemeral_go = sum(v["ephemeral_go_under_10m"] for v in daily.values())
    ephemeral_watch = sum(v["ephemeral_watch_under_10m"] for v in daily.values())
    aggregate_driver_changes = Counter()
    for d in daily.values():
        aggregate_driver_changes.update(d.get("transition_family_changes") or {})

    intraday_by_day: dict[str, list[dict]] = defaultdict(list)
    for row in intraday:
        day = str(row.get("market_date") or "")
        if day:
            intraday_by_day[day].append(row)

    payload = {
        "classification": "RESEARCH_ONLY_PROSPECTIVE",
        "engine_impact": "NONE",
        "generated_at": datetime.now().astimezone().isoformat(),
        "source": source,
        "purpose": "Measure state instability and persistence using only actually captured REENTRY_UNIFIED_v1 snapshots. No historical states are invented.",
        "unified_history_rows": len(unified),
        "market_days": len(daily),
        "aggregate": {
            "state_transition_count": all_transitions,
            "go_early_episode_count": all_go,
            "watch_episode_count": all_watch,
            "go_early_under_10m_count": ephemeral_go,
            "watch_under_10m_count": ephemeral_watch,
            "family_changes_at_state_transitions": dict(aggregate_driver_changes),
        },
        "daily": daily,
        "precursor_metric_direction_flip_analysis": {
            day: precursor_flip_analysis(rows) for day, rows in sorted(intraday_by_day.items())
        },
        "limitations": [
            "This is prospective captured-history analysis, not a historical reconstruction.",
            "Durations reflect snapshot spacing, so irregular workflow cadence can understate or overstate persistence.",
            "A family change at the same snapshot as a state transition is attribution evidence, not proof of causation.",
            "No persistence or hysteresis rule is promoted by this report.",
        ],
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# RE-ENTRY unified whipsaw analysis",
        "",
        "**Research only. No engine logic changed.**",
        "",
        f"Captured unified snapshots: **{len(unified)}** across **{len(daily)}** market day(s).",
        "",
        "## Aggregate",
        "",
        f"- State transitions: **{all_transitions}**",
        f"- GO EARLY episodes: **{all_go}**",
        f"- GO EARLY episodes lasting under 10 minutes: **{ephemeral_go}**",
        f"- WATCH episodes: **{all_watch}**",
        f"- WATCH episodes lasting under 10 minutes: **{ephemeral_watch}**",
        "",
        "## Family changes observed at state transitions",
        "",
    ]
    if aggregate_driver_changes:
        for key, count in aggregate_driver_changes.most_common():
            lines.append(f"- {key}: **{count}**")
    else:
        lines.append("- No attributable unified-family transitions captured yet.")
    lines += ["", "## Daily detail", ""]
    for day, d in daily.items():
        lines += [
            f"### {day}",
            f"- snapshots: {d['snapshots']}",
            f"- median snapshot spacing: {d['median_snapshot_spacing_minutes']} minutes",
            f"- transitions: {d['transition_count']}",
            f"- final state: {d['final_state']}",
            f"- maximum state reached: {d['max_state']}",
            f"- GO EARLY durations, minutes: {d['go_early_durations_minutes']}",
            f"- WATCH durations, minutes: {d['watch_durations_minutes']}",
            "",
        ]
    lines += [
        "## Interpretation boundary",
        "",
        "This report only measures instability in states that were actually captured. It does not recommend a confirmation window, minimum duration, or hysteresis rule. Those variants must be compared against forward returns and opportunity cost before any engine change.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
