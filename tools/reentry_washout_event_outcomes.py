from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import yfinance as yf

EVENTS = Path("data/reentry/washout_events.csv")
OUT = Path("data/reentry/washout_event_outcomes.csv")
HORIZONS = (5, 10, 30, 60)


def load_events() -> list[dict[str, str]]:
    if not EVENTS.exists():
        return []
    with EVENTS.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_prices(start: str) -> pd.DataFrame:
    raw = yf.download(["SPY", "QQQ"], start=start, auto_adjust=False, progress=False, group_by="column")
    if raw.empty:
        raise RuntimeError("no SPY/QQQ prices returned")
    close = raw["Close"].copy()
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    return close.sort_index()


def main() -> None:
    events = load_events()
    fields = [
        "oversold_date", "washout_date", "sessions_from_oversold",
        *[f"{s}_{h}D" for s in ("SPY", "QQQ") for h in HORIZONS],
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not events:
        with OUT.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=fields).writeheader()
        print("no washout events yet")
        return

    start = min(e["washout_date"] for e in events)
    prices = load_prices(start)
    rows: list[dict[str, object]] = []
    for e in events:
        dt = pd.Timestamp(e["washout_date"]).normalize()
        elig = prices.index[prices.index >= dt]
        if not len(elig):
            continue
        entry_dt = elig[0]
        i = int(prices.index.get_loc(entry_dt))
        row: dict[str, object] = {
            "oversold_date": e.get("oversold_date", ""),
            "washout_date": e.get("washout_date", ""),
            "sessions_from_oversold": e.get("sessions_from_oversold", ""),
        }
        for symbol in ("SPY", "QQQ"):
            entry = prices[symbol].iloc[i]
            for h in HORIZONS:
                key = f"{symbol}_{h}D"
                if i + h < len(prices) and pd.notna(entry) and pd.notna(prices[symbol].iloc[i + h]):
                    row[key] = float(prices[symbol].iloc[i + h] / entry - 1.0)
                else:
                    row[key] = ""
        rows.append(row)

    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} washout event outcome rows")


if __name__ == "__main__":
    main()
