import pandas as pd
import pytest

from swing_intelligence.data import normalize_ohlcv


def test_normalize_ohlcv():
    raw = pd.DataFrame({
        "Date": ["2025-01-02", "2025-01-03"],
        "Open": [100, 101], "High": [102, 103], "Low": [99, 100],
        "Close": [101, 102], "Volume": [1_000, 1_100],
    })
    out = normalize_ohlcv(raw)
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(out.index, pd.DatetimeIndex)


def test_rejects_bad_ohlc():
    raw = pd.DataFrame({
        "Date": ["2025-01-02"], "Open": [100], "High": [98], "Low": [99], "Close": [101], "Volume": [1000]
    })
    with pytest.raises(ValueError):
        normalize_ohlcv(raw)


def test_stooq_requires_key(monkeypatch):
    from swing_intelligence.data import fetch_stooq_daily, DataRequest
    monkeypatch.delenv("STOOQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="STOOQ_API_KEY"):
        fetch_stooq_daily(DataRequest("SPY"))


def test_twelve_data_chunk_ranges_cover_long_history_without_overlap():
    from swing_intelligence.data import _date_chunks
    chunks = _date_chunks("2000-01-01", "2026-09-03", years_per_chunk=14)
    assert chunks == [("2000-01-01", "2013-12-31"), ("2014-01-01", "2026-09-03")]
