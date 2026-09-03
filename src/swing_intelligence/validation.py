from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SourceManifest:
    symbol: str
    source: str
    retrieved_at: str
    first_date: str
    last_date: str
    rows: int
    sha256: str


def dataframe_sha256(df: pd.DataFrame) -> str:
    out = df.copy()
    out.index.name = out.index.name or "date"
    payload = out.to_csv(index=True, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_manifest(df: pd.DataFrame, symbol: str, source: str, retrieved_at: str) -> SourceManifest:
    if df.empty:
        raise ValueError("Cannot build manifest for empty dataframe")
    return SourceManifest(
        symbol=symbol.upper(), source=source, retrieved_at=retrieved_at,
        first_date=str(pd.Timestamp(df.index.min()).date()),
        last_date=str(pd.Timestamp(df.index.max()).date()),
        rows=len(df), sha256=dataframe_sha256(df),
    )


def validate_market_history(df: pd.DataFrame, *, min_rows: int = 1000, max_abs_daily_return: float = 0.30) -> dict:
    """Research-grade sanity checks that reject obviously bad/synthetic daily data."""
    if len(df) < min_rows:
        raise ValueError(f"Insufficient history: {len(df)} rows < {min_rows}")
    idx = pd.DatetimeIndex(df.index)
    if idx.has_duplicates or not idx.is_monotonic_increasing:
        raise ValueError("History index must be unique and increasing")
    weekend_rows = int((idx.dayofweek >= 5).sum())
    if weekend_rows:
        raise ValueError(f"History contains {weekend_rows} weekend rows")
    close = pd.to_numeric(df["close"], errors="coerce")
    r = close.pct_change().dropna()
    if r.empty:
        raise ValueError("No valid returns")
    max_abs = float(r.abs().max())
    if max_abs > max_abs_daily_return:
        raise ValueError(f"Implausible daily close move {max_abs:.1%}; investigate source/corporate-action handling")
    zero_volume_share = float((pd.to_numeric(df["volume"], errors="coerce").fillna(0) <= 0).mean())
    return {
        "rows": len(df),
        "first_date": str(idx.min().date()),
        "last_date": str(idx.max().date()),
        "weekend_rows": weekend_rows,
        "max_abs_daily_return": max_abs,
        "zero_volume_share": zero_volume_share,
    }


def write_manifest(manifest: SourceManifest, path: str | Path) -> None:
    import json
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.__dict__, indent=2) + "\n", encoding="utf-8")
