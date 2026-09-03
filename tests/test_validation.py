import pandas as pd
import numpy as np
import pytest
from swing_intelligence.validation import validate_market_history, build_manifest


def frame(n=1200):
    idx = pd.bdate_range("2018-01-01", periods=n)
    close = 100 * np.exp(np.cumsum(np.full(n, .0002)))
    return pd.DataFrame({"open":close*.999,"high":close*1.01,"low":close*.99,"close":close,"volume":1_000_000}, index=idx)


def test_market_history_accepts_sane_daily_data():
    out = validate_market_history(frame())
    assert out["rows"] == 1200
    assert out["weekend_rows"] == 0


def test_market_history_rejects_weekends():
    f=frame(); extra=f.iloc[[-1]].copy(); extra.index=[pd.Timestamp("2025-01-04")]
    with pytest.raises(ValueError, match="weekend"):
        validate_market_history(pd.concat([f,extra]).sort_index())


def test_manifest_hash_stable():
    f=frame(); a=build_manifest(f,"SPY","unit","2026-09-03T12:00:00Z"); b=build_manifest(f,"SPY","unit","2026-09-03T12:00:00Z")
    assert a.sha256 == b.sha256
