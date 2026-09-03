import pandas as pd
import pytest

from swing_intelligence.runner import _reject_stale_history


def test_rejects_stale_or_truncated_vendor_history():
    idx = pd.bdate_range("2020-01-01", "2020-12-31")
    df = pd.DataFrame({"close": 100.0}, index=idx)
    with pytest.raises(ValueError, match="stale or truncated"):
        _reject_stale_history(df, "SPY", max_calendar_days=10)
