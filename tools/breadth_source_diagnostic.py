from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
from urllib.request import urlopen

import pandas as pd

URL = "https://tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv"


def main() -> None:
    with urlopen(URL, timeout=30) as resp:  # nosec - fixed public GitHub Pages URL
        text = resp.read().decode("utf-8")
    df = pd.read_csv(StringIO(text))
    if df.empty:
        raise RuntimeError("Breadth CSV is empty")
    date_col = "Date" if "Date" in df.columns else df.columns[0]
    dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
    numeric = {}
    for c in df.columns:
        if c == date_col:
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        if s.notna().any():
            numeric[c] = {
                "non_null": int(s.notna().sum()),
                "min": float(s.min()),
                "max": float(s.max()),
            }
    result = {
        "source": URL,
        "rows": int(len(df)),
        "columns": list(df.columns),
        "first_date": str(dates.min().date()) if len(dates) else None,
        "last_date": str(dates.max().date()) if len(dates) else None,
        "numeric_columns": numeric,
        "has_50dma_breadth": "Breadth_50_Index_Raw" in df.columns,
        "has_200dma_breadth": "Breadth_Index_Raw" in df.columns,
    }
    out = Path("artifacts/breadth_source_diagnostic")
    out.mkdir(parents=True, exist_ok=True)
    (out / "diagnostic.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
