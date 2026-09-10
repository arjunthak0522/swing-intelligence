from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import yfinance as yf

EVENTS = Path("data/reentry/washout_events.csv")
OUT = Path("data/reentry/washout_event_outcomes.csv")
HORIZONS = (5, 10, 30, 60)
ROUND_TRIP_COST = 0.001


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
        "oversold_date", "washout_date", "signal_date", "entry_price_date", "sessions_from_oversold",
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
        signal_dt = pd.Timestamp(e["washout_date"]).normalize()
        if signal_dt not in prices.index:
            continue
        signal_i = int(prices.index.get_loc(signal_dt))
        entry_i = signal_i + 1
        if entry_i >= len(prices):
            continue
        entry_dt = prices.index[entry_i]
        row: dict[str, object] = {
            "oversold_date": e.get("oversold_date", ""),
            "washout_date": e.get("washout_date", ""),
            "signal_date": signal_dt.date().isoformat(),
            "entry_price_date": entry_dt.date().isoformat(),
            "sessions_from_oversold": e.get("sessions_from_oversold", ""),
        }
        for symbol in ("SPY", "QQQ"):
            entry = prices[symbol].iloc[entry_i]
            for h in HORIZONS:
                key = f"{symbol}_{h}D"
                exit_i = entry_i + h
                if exit_i < len(prices) and pd.notna(entry) and pd.notna(prices[symbol].iloc[exit_i]):
                    row[key] = float(prices[symbol].iloc[exit_i] / entry - 1.0 - ROUND_TRIP_COST)
                else:
                    row[key] = ""
        rows.append(row)

    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} washout event outcome rows using t+1 close execution")


if __name__ == "__main__":
    main()
