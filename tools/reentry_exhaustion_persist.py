from __future__ import annotations

import csv
import json
from pathlib import Path

SNAPSHOT = Path("reentry-exhaustion-live-snapshot.json")
OUT = Path("data/reentry/exhaustion_history.csv")

SYMBOL_COLUMNS = [
    "$MMFD", "$MMTW", "$SPXA20R", "$SPXA50R", "$SPXA200R", "$BPSPX",
    "$NYMO", "$NAMO", "$NYUD", "$NAUD", "$NYUPV", "$NYDNV", "$NAUPV", "$NADNV",
]

BASE_COLUMNS = [
    "market_date", "generated_at_utc", "state", "washout_family_count",
    "turn_family_count", "selling_pressure_count", "nyse_down_up_ratio",
    "nasdaq_down_up_ratio",
]

FIELDNAMES = BASE_COLUMNS + [s.replace("$", "") for s in SYMBOL_COLUMNS]


def market_date(payload: dict) -> str:
    dates: list[str] = []
    for q in payload.get("quotes", {}).values():
        if not q or not q.get("as_of"):
            continue
        raw = str(q["as_of"])
        if len(raw) >= 10 and raw[4] == "-":
            dates.append(raw[:10])
    if dates:
        return max(dates)
    # EODData fallbacks can use dd Mon yy. Keep generated date only if no ISO quote exists.
    return str(payload.get("generated_at_utc", ""))[:10]


def value(payload: dict, symbol: str):
    q = payload.get("quotes", {}).get(symbol)
    return "" if not q or q.get("close") is None else q.get("close")


def build_row(payload: dict) -> dict:
    row = {
        "market_date": market_date(payload),
        "generated_at_utc": payload.get("generated_at_utc", ""),
        "state": payload.get("framework", {}).get("state", ""),
        "washout_family_count": payload.get("washout", {}).get("family_count", ""),
        "turn_family_count": payload.get("turn", {}).get("family_count", ""),
        "selling_pressure_count": payload.get("selling_pressure", {}).get("count", ""),
        "nyse_down_up_ratio": payload.get("selling_pressure", {}).get("nyse_down_up_volume_ratio", ""),
        "nasdaq_down_up_ratio": payload.get("selling_pressure", {}).get("nasdaq_down_up_volume_ratio", ""),
    }
    for symbol in SYMBOL_COLUMNS:
        row[symbol.replace("$", "")] = value(payload, symbol)
    return row


def load_existing() -> list[dict]:
    if not OUT.exists():
        return []
    with OUT.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    if not SNAPSHOT.exists():
        raise SystemExit(f"missing snapshot: {SNAPSHOT}")
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    row = build_row(payload)
    if not row["market_date"]:
        raise SystemExit("could not determine market_date")

    rows = load_existing()
    by_date = {r.get("market_date", ""): r for r in rows if r.get("market_date")}
    by_date[row["market_date"]] = {k: str(row.get(k, "")) for k in FIELDNAMES}
    ordered = [by_date[d] for d in sorted(by_date)]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(ordered)

    print(json.dumps({"persisted": row["market_date"], "rows": len(ordered), "path": str(OUT)}))


if __name__ == "__main__":
    main()
