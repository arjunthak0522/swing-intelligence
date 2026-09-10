from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import yfinance as yf

HISTORY = Path("data/reentry/exhaustion_history.csv")
OUT = Path("data/reentry/exhaustion_outcomes.csv")
HORIZONS = (5, 10, 30, 60)
ROUND_TRIP_COST = 0.001


def load_prices(start: str) -> pd.DataFrame:
    raw = yf.download(["SPY", "QQQ"], start=start, auto_adjust=False, progress=False, group_by="column")
    if raw.empty:
        raise RuntimeError("no SPY/QQQ prices returned")
    close = raw["Close"].copy()
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    return close.sort_index()


def main() -> None:
    if not HISTORY.exists():
        raise SystemExit("exhaustion history not present")
    hist = pd.read_csv(HISTORY)
    if hist.empty:
        print("no exhaustion history rows yet")
        return
    hist["market_date"] = pd.to_datetime(hist["market_date"]).dt.normalize()
    prices = load_prices((hist["market_date"].min() - pd.Timedelta(days=7)).date().isoformat())

    rows: list[dict] = []
    for rec in hist.to_dict("records"):
        signal_dt = pd.Timestamp(rec["market_date"]).normalize()
        if signal_dt not in prices.index:
            continue
        signal_i = int(prices.index.get_loc(signal_dt))
        entry_i = signal_i + 1
        if entry_i >= len(prices):
            continue
        entry_dt = prices.index[entry_i]
        row = {
            "market_date": signal_dt.date().isoformat(),
            "state": rec.get("state", ""),
            "signal_date": signal_dt.date().isoformat(),
            "entry_price_date": entry_dt.date().isoformat(),
            "MMFD": rec.get("MMFD", ""),
            "MMTW": rec.get("MMTW", ""),
            "NYMO": rec.get("NYMO", ""),
            "NAMO": rec.get("NAMO", ""),
            "NYUD": rec.get("NYUD", ""),
            "NAUD": rec.get("NAUD", ""),
        }
        for symbol in ("SPY", "QQQ"):
            entry = prices[symbol].iloc[entry_i]
            for h in HORIZONS:
                exit_i = entry_i + h
                key = f"{symbol}_{h}D"
                if exit_i < len(prices) and pd.notna(entry) and pd.notna(prices[symbol].iloc[exit_i]):
                    row[key] = float(prices[symbol].iloc[exit_i] / entry - 1.0 - ROUND_TRIP_COST)
                else:
                    row[key] = ""
        rows.append(row)

    fields = [
        "market_date", "state", "signal_date", "entry_price_date", "MMFD", "MMTW", "NYMO", "NAMO", "NYUD", "NAUD",
        *[f"{s}_{h}D" for s in ("SPY", "QQQ") for h in HORIZONS],
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} prospective exhaustion rows using t+1 close execution")


if __name__ == "__main__":
    main()
