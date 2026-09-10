from __future__ import annotations

import csv
from pathlib import Path

HISTORY = Path("data/reentry/exhaustion_history.csv")
EVENTS = Path("data/reentry/washout_events.csv")

FIELDS = [
    "oversold_date",
    "washout_date",
    "sessions_from_oversold",
    "washout_state",
    "MMFD",
    "MMTW",
    "SPXA20R",
    "BPSPX",
    "NYMO",
    "NAMO",
    "NYUD",
    "NAUD",
    "nyse_down_up_ratio",
    "nasdaq_down_up_ratio",
]


def load(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    rows = load(HISTORY)
    if not rows:
        print("no exhaustion history")
        return

    rows = sorted(rows, key=lambda r: r.get("market_date", ""))
    events: list[dict[str, str]] = []
    active_oversold: dict[str, str] | None = None
    active_index: int | None = None

    for i, row in enumerate(rows):
        state = row.get("state", "")
        if state == "OVERSOLD":
            if active_oversold is None:
                active_oversold = row
                active_index = i
            continue

        if state == "WASHOUT" and active_oversold is not None and active_index is not None:
            events.append({
                "oversold_date": active_oversold.get("market_date", ""),
                "washout_date": row.get("market_date", ""),
                "sessions_from_oversold": str(i - active_index),
                "washout_state": state,
                "MMFD": row.get("MMFD", ""),
                "MMTW": row.get("MMTW", ""),
                "SPXA20R": row.get("SPXA20R", ""),
                "BPSPX": row.get("BPSPX", ""),
                "NYMO": row.get("NYMO", ""),
                "NAMO": row.get("NAMO", ""),
                "NYUD": row.get("NYUD", ""),
                "NAUD": row.get("NAUD", ""),
                "nyse_down_up_ratio": row.get("nyse_down_up_ratio", ""),
                "nasdaq_down_up_ratio": row.get("nasdaq_down_up_ratio", ""),
            })
            active_oversold = None
            active_index = None
            continue

        # A completed reset without a washout ends the candidate sequence.
        if state == "NONE":
            active_oversold = None
            active_index = None

    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(events)

    print(f"tracked {len(events)} first-washout go events")


if __name__ == "__main__":
    main()
