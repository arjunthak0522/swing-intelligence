import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/reentry_options_sentiment_live.py"
spec = importlib.util.spec_from_file_location("reentry_options_sentiment_live", MODULE_PATH)
options = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(options)


def fake_daily(day):
    return {
        "equity_put_call": 0.77,
        "index_put_call": 1.11,
        "total_put_call": 0.88,
        "freshness_type": "DAILY_CLOSE_T_PLUS_ONE",
        "freshness_state": "PRIOR_CLOSE",
        "last_updated": day,
        "observation_market_date": day,
        "source": "test",
    }


def test_final_daily_lookup_never_queries_target_session(monkeypatch):
    calls = []

    def stub(day):
        calls.append(day)
        return fake_daily(day)

    monkeypatch.setattr(options, "daily_ratios", stub)
    result = options.latest_completed_daily("2026-09-17")
    assert result is not None
    assert "2026-09-17" not in calls
    assert result["observation_market_date"] == "2026-09-16"
    assert result["available_for_market_date"] == "2026-09-17"
    assert result["freshness_state"] == "PRIOR_CLOSE"


def test_weekend_is_skipped_for_t_plus_one_lookup(monkeypatch):
    calls = []

    def stub(day):
        calls.append(day)
        return fake_daily(day)

    monkeypatch.setattr(options, "daily_ratios", stub)
    # Monday: prior usable finalized daily reading is Friday, not weekend or Monday.
    result = options.latest_completed_daily("2026-09-21")
    assert result is not None
    assert result["observation_market_date"] == "2026-09-18"
    assert calls == ["2026-09-18"]


def test_same_day_live_and_prior_official_are_kept_separate(monkeypatch):
    monkeypatch.setattr(options, "live_ratios", lambda market_date: {
        "equity_put_call": 0.75,
        "index_put_call": 1.31,
        "total_put_call": 0.96,
        "freshness_type": "INTRADAY_DELAYED",
        "freshness_state": "LIVE",
        "last_updated": f"{market_date} 09:00 AM CT",
        "observation_market_date": market_date,
        "requested_market_date": market_date,
        "source": "live-test",
    })
    monkeypatch.setattr(options, "latest_completed_daily", lambda market_date: {
        **fake_daily("2026-09-16"),
        "requested_market_date": market_date,
        "available_for_market_date": market_date,
    })
    class FixedDateTime(options.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 17, 11, 0, tzinfo=tz)
    monkeypatch.setattr(options, "datetime", FixedDateTime)

    signal = options.build_signal("2026-09-17")
    assert signal["reading_mode"] == "INTRADAY_CBOE"
    assert signal["equity_put_call"] == 0.75
    assert signal["official_daily_equity_put_call"] == 0.77
    assert signal["official_daily_observation_date"] == "2026-09-16"
    assert signal["official_daily_available_for_market_date"] == "2026-09-17"
    assert signal["final_daily_t_plus_one_enforced"] is True
