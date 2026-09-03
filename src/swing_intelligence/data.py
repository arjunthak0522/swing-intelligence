from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from io import StringIO
import json
import os
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError

import pandas as pd


REQUIRED_OHLCV = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class DataRequest:
    symbol: str
    start: str = "2000-01-01"
    end: str | None = None


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize vendor OHLCV into the engine's canonical daily schema."""
    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="raise")
        out = out.set_index("date")
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, errors="raise")
    missing = [c for c in REQUIRED_OHLCV if c not in out.columns]
    if missing:
        raise ValueError(f"Missing OHLCV columns: {missing}")
    out = out.loc[:, REQUIRED_OHLCV].apply(pd.to_numeric, errors="coerce")
    out = out.dropna(subset=["open", "high", "low", "close"])
    out = out[~out.index.duplicated(keep="last")].sort_index()
    if not out.index.is_monotonic_increasing:
        raise ValueError("Data index must be monotonic increasing")
    if (out[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    if (out["high"] < out[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("Invalid OHLC row: high below another price")
    if (out["low"] > out[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC row: low above another price")
    return out


def load_csv(path: str | Path) -> pd.DataFrame:
    return normalize_ohlcv(pd.read_csv(path))


def fetch_stooq_daily(request: DataRequest, api_key: str | None = None, timeout: int = 30) -> pd.DataFrame:
    """Historical fallback for ETFs. Stooq requires an API key as of 2026."""
    key = api_key or os.getenv("STOOQ_API_KEY")
    if not key:
        raise RuntimeError("STOOQ_API_KEY is not configured")
    sym = request.symbol.lower()
    if not sym.endswith(".us") and not sym.startswith("^"):
        sym = f"{sym}.us"
    params = {"s": sym, "i": "d", "d1": request.start.replace("-", "")}
    if request.end:
        params["d2"] = request.end.replace("-", "")
    params["apikey"] = key
    url = "https://stooq.com/q/d/l/?" + urlencode(params)
    with urlopen(url, timeout=timeout) as resp:  # nosec - fixed HTTPS research endpoint
        text = resp.read().decode("utf-8")
    if not text.strip() or text.lstrip().startswith("No data"):
        raise RuntimeError(f"No Stooq data returned for {request.symbol}")
    return normalize_ohlcv(pd.read_csv(StringIO(text)))


def _date_chunks(start: str, end: str, years_per_chunk: int = 14) -> list[tuple[str, str]]:
    """Create non-overlapping calendar chunks small enough to stay below 5,000 daily bars."""
    cur = pd.Timestamp(start).normalize()
    stop = pd.Timestamp(end).normalize()
    if cur > stop:
        raise ValueError("start must be on or before end")
    chunks: list[tuple[str, str]] = []
    while cur <= stop:
        chunk_end = min(cur + pd.DateOffset(years=years_per_chunk) - pd.Timedelta(days=1), stop)
        chunks.append((str(cur.date()), str(chunk_end.date())))
        cur = chunk_end + pd.Timedelta(days=1)
    return chunks


def _fetch_twelve_data_slice(symbol: str, start: str, end: str, key: str, timeout: int, *, max_retries: int = 4) -> pd.DataFrame:
    params = {
        "symbol": symbol.upper(),
        "interval": "1day",
        "start_date": start,
        "end_date": end,
        "outputsize": 5000,
        "apikey": key,
        "format": "JSON",
        "order": "ASC",
    }
    url = "https://api.twelvedata.com/time_series?" + urlencode(params)
    payload = None
    for attempt in range(max_retries + 1):
        try:
            with urlopen(url, timeout=timeout) as resp:  # nosec - fixed HTTPS endpoint
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except HTTPError as exc:
            if exc.code != 429 or attempt >= max_retries:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = float(retry_after) if retry_after else min(60.0, 15.0 * (2 ** attempt))
            except (TypeError, ValueError):
                delay = min(60.0, 15.0 * (2 ** attempt))
            time.sleep(max(1.0, delay))
    if payload is None:
        raise RuntimeError(f"No Twelve Data response for {symbol}")
    if payload.get("status") == "error" or "values" not in payload:
        raise RuntimeError(f"Twelve Data error for {symbol}: {payload.get('message', 'missing values')}")
    df = pd.DataFrame(payload["values"]).rename(columns={"datetime": "date"})
    if "volume" not in df.columns:
        df["volume"] = 0
    return normalize_ohlcv(df)


def fetch_twelve_data_daily(
    request: DataRequest,
    api_key: str | None = None,
    timeout: int = 30,
    *,
    years_per_chunk: int = 14,
    min_interval_seconds: float = 8.0,
) -> pd.DataFrame:
    """Fetch complete daily history from Twelve Data without silent 5,000-bar truncation.

    Long histories are split into bounded calendar windows and then reassembled.
    Requests are paced so the free-tier rate limit is not used as a hidden failure mode.
    """
    key = api_key or os.getenv("TWELVE_DATA_API_KEY")
    if not key:
        raise RuntimeError("TWELVE_DATA_API_KEY is not configured")
    end = request.end or str(date.today())
    parts: list[pd.DataFrame] = []
    chunks = _date_chunks(request.start, end, years_per_chunk=years_per_chunk)
    for i, (start, chunk_end) in enumerate(chunks):
        if i:
            time.sleep(max(0.0, min_interval_seconds))
        part = _fetch_twelve_data_slice(request.symbol, start, chunk_end, key, timeout)
        parts.append(part)
    if not parts:
        raise RuntimeError(f"No Twelve Data history returned for {request.symbol}")
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return normalize_ohlcv(out)


def save_cache(df: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out.index.name = "date"
    out.to_csv(path)
