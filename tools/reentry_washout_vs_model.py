from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_confidence import feature_frame
from reentry_walkforward_validation import generate_decisions

EVENTS = Path("data/reentry/washout_events.csv")
OUT = Path("data/reentry/washout_vs_model.csv")
REPORT = Path("artifacts/selling_exhaustion_reliability/washout_vs_model.json")
QUALIFYING = {"CAUTIOUS YES", "YES", "STRONG YES"}
MAX_LOOKAHEAD_SESSIONS = 20


def load_events() -> list[dict[str, str]]:
    if not EVENTS.exists():
        return []
    with EVENTS.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    events = load_events()
    fields = [
        "oversold_date", "washout_date", "model_date", "sessions_washout_leads_model",
        "model_decision", "status",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    if not events:
        with OUT.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=fields).writeheader()
        report = {
            "research_only": True,
            "paired_events": 0,
            "status": "AWAITING_FIRST_WASHOUT_EVENT",
            "note": "First actionable WASHOUT must follow an OVERSOLD state. No event exists yet in prospective history.",
        }
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return

    frame = feature_frame(require_same_day=False)
    decisions = generate_decisions(frame)
    trading_index = frame.index

    rows: list[dict[str, object]] = []
    leads: list[int] = []
    for e in events:
        washout = pd.Timestamp(e["washout_date"]).normalize()
        if washout not in trading_index:
            continue
        start_i = int(trading_index.get_loc(washout))
        end_i = min(len(trading_index) - 1, start_i + MAX_LOOKAHEAD_SESSIONS)
        window_dates = trading_index[start_i:end_i + 1]
        elig = decisions.reindex(window_dates)
        elig = elig[elig["decision"].isin(QUALIFYING)]
        if elig.empty:
            rows.append({
                "oversold_date": e.get("oversold_date", ""),
                "washout_date": e.get("washout_date", ""),
                "model_date": "",
                "sessions_washout_leads_model": "",
                "model_decision": "",
                "status": "NO_MODEL_REENTRY_WITHIN_20_SESSIONS",
            })
            continue
        model_date = pd.Timestamp(elig.index[0])
        lead = int(trading_index.get_loc(model_date) - trading_index.get_loc(washout))
        leads.append(lead)
        rows.append({
            "oversold_date": e.get("oversold_date", ""),
            "washout_date": e.get("washout_date", ""),
            "model_date": model_date.date().isoformat(),
            "sessions_washout_leads_model": lead,
            "model_decision": str(elig.iloc[0]["decision"]),
            "status": "PAIRED",
        })

    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    arr = np.asarray(leads, dtype=float)
    report = {
        "research_only": True,
        "paired_events": int(len(leads)),
        "all_events": int(len(events)),
        "median_sessions_washout_leads_model": float(np.median(arr)) if len(arr) else None,
        "share_washout_before_model": float((arr > 0).mean()) if len(arr) else None,
        "share_washout_same_or_before_model": float((arr >= 0).mean()) if len(arr) else None,
        "status": "EVALUABLE" if len(leads) >= 20 else "INSUFFICIENT_PROSPECTIVE_SAMPLE",
        "important_note": "This is a paired prospective timing audit against the existing walk-forward decision implementation. It does not alter the frozen official RE-ENTRY engine.",
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
