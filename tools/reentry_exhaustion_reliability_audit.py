from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

HISTORY = Path("data/reentry/exhaustion_history.csv")
DAILY_OUTCOMES = Path("data/reentry/exhaustion_outcomes.csv")
EVENTS = Path("data/reentry/washout_events.csv")
EVENT_OUTCOMES = Path("data/reentry/washout_event_outcomes.csv")
REPORT = Path("artifacts/selling_exhaustion_reliability/reliability_report.json")
STATUS = Path("data/reentry/exhaustion_reliability.json")

CORE_FIELDS = ("MMFD", "MMTW", "SPXA20R", "SPXA50R", "BPSPX", "NYMO", "NAMO", "NYUD", "NAUD", "NYUPV", "NYDNV", "NAUPV", "NADNV")
MIN_PROSPECTIVE_ROWS = 60
MIN_WASHOUT_EVENTS = 20
MIN_MATURED_EVENT_10D = 20
MIN_MATURED_EVENT_30D = 12
MAX_MISSING_RATE = 0.05


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def present(value: str | None) -> bool:
    return value not in (None, "", "nan", "NaN", "None")


def number(value: str | None) -> float | None:
    try:
        return float(value) if present(value) else None
    except Exception:
        return None


def metric(rows: list[dict[str, str]], field: str) -> dict:
    vals = sorted(v for v in (number(r.get(field)) for r in rows) if v is not None)
    if not vals:
        return {"n": 0, "mean": None, "median": None, "positive_rate": None, "p10": None}
    n = len(vals)
    mid = n // 2
    median = vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2
    p10_i = max(0, int(round((n - 1) * 0.10)))
    return {"n": n, "mean": sum(vals) / n, "median": median, "positive_rate": sum(v > 0 for v in vals) / n, "p10": vals[p10_i]}


def main() -> None:
    history = read_csv(HISTORY)
    daily_outcomes = read_csv(DAILY_OUTCOMES)
    events = read_csv(EVENTS)
    event_outcomes = read_csv(EVENT_OUTCOMES)

    total_cells = max(1, len(history) * len(CORE_FIELDS))
    missing_cells = sum(1 for row in history for field in CORE_FIELDS if not present(row.get(field)))
    missing_rate = missing_cells / total_cells

    matured_event_10 = [r for r in event_outcomes if present(r.get("SPY_10D")) and present(r.get("QQQ_10D"))]
    matured_event_30 = [r for r in event_outcomes if present(r.get("SPY_30D")) and present(r.get("QQQ_30D"))]

    gates = {
        "source_completeness": {"pass": missing_rate <= MAX_MISSING_RATE, "value": missing_rate, "requirement": f"missing core-field rate <= {MAX_MISSING_RATE:.0%}"},
        "prospective_daily_sample": {"pass": len(history) >= MIN_PROSPECTIVE_ROWS, "value": len(history), "requirement": f">= {MIN_PROSPECTIVE_ROWS} completed daily snapshots"},
        "first_washout_event_sample": {"pass": len(events) >= MIN_WASHOUT_EVENTS, "value": len(events), "requirement": f">= {MIN_WASHOUT_EVENTS} independent first-WASHOUT GO events"},
        "matured_event_10d_sample": {"pass": len(matured_event_10) >= MIN_MATURED_EVENT_10D, "value": len(matured_event_10), "requirement": f">= {MIN_MATURED_EVENT_10D} first-WASHOUT events with both SPY/QQQ 10D outcomes"},
        "matured_event_30d_sample": {"pass": len(matured_event_30) >= MIN_MATURED_EVENT_30D, "value": len(matured_event_30), "requirement": f">= {MIN_MATURED_EVENT_30D} first-WASHOUT events with both SPY/QQQ 30D outcomes"},
    }

    event_metrics = {s: {f"{h}D": metric(event_outcomes, f"{s}_{h}D") for h in (5, 10, 30, 60)} for s in ("SPY", "QQQ")}
    sample_ready = all(g["pass"] for g in gates.values())

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "official_signal_modified": False,
        "framework": "SELLING EXHAUSTION",
        "semantics": {
            "OVERSOLD": "internals stretched but still deteriorating - no GO",
            "WASHOUT": "first internal turn after oversold - early GO candidate",
            "CONFIRMED": "later corroboration, not required for the early GO",
        },
        "execution_convention": "completed-close signal at t; hypothetical entry at next completed close t+1; 10 bps round-trip cost",
        "architecture": {
            "oversold_family": ["MMFD", "MMTW", "SPXA20R", "SPXA50R", "BPSPX", "NYMO", "NAMO"],
            "selling_pressure_family": ["NYUD", "NAUD", "NYUPV/NYDNV", "NAUPV/NADNV"],
            "turn_family": ["fast breadth recovery", "McClellan recovery", "net-volume recovery"],
            "anti_double_counting": "Correlated indicators are grouped into families before state classification.",
        },
        "data": {
            "daily_history_rows": len(history),
            "daily_outcome_rows": len(daily_outcomes),
            "first_washout_events": len(events),
            "first_washout_event_outcomes": len(event_outcomes),
            "core_missing_rate": missing_rate,
            "matured_event_10d_rows": len(matured_event_10),
            "matured_event_30d_rows": len(matured_event_30),
        },
        "gates": gates,
        "sample_ready_for_promotion_review": sample_ready,
        "paired_superiority_gate": {
            "pass": False,
            "status": "NOT_YET_EVALUABLE",
            "requirement": "First-WASHOUT GO must lead the frozen RE-ENTRY signal often enough to matter while preserving or improving 10D/30D positive rates and p10 downside tails in paired episodes.",
        },
        "promotion_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
        "first_washout_forward_metrics": event_metrics,
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2)
    REPORT.write_text(payload, encoding="utf-8")
    STATUS.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
