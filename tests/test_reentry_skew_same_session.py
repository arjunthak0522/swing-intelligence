from __future__ import annotations

import csv
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import reentry_skew_intraday as skew


def write_history(path: Path):
    rows = [
        {
            "market_date": "2026-09-09",
            "timestamp_et": "2026-09-09T15:45:00-04:00",
            "put_call_iv_spread_vol_points": "5.0",
            "put_call_iv_ratio": "1.30",
            "source_mode": "LIVE_SPX_OPTIONS",
        },
        {
            "market_date": "2026-09-10",
            "timestamp_et": "2026-09-10T10:00:00-04:00",
            "put_call_iv_spread_vol_points": "3.4",
            "put_call_iv_ratio": "1.20",
            "source_mode": "LIVE_SPX_OPTIONS",
        },
        {
            "market_date": "2026-09-10",
            "timestamp_et": "2026-09-10T10:15:00-04:00",
            "put_call_iv_spread_vol_points": "3.0",
            "put_call_iv_ratio": "1.18",
            "source_mode": "LIVE_SPX_OPTIONS",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_prior_live_row_never_crosses_market_date(tmp_path, monkeypatch):
    history = tmp_path / "skew.csv"
    write_history(history)
    monkeypatch.setattr(skew, "HISTORY", history)

    prior = skew.prior_live_row("2026-09-10")
    assert prior is not None
    assert prior["timestamp_et"] == "2026-09-10T10:15:00-04:00"
    assert prior["put_call_iv_spread_vol_points"] == "3.0"


def test_direction_is_calculated_only_within_same_session(tmp_path, monkeypatch):
    history = tmp_path / "skew.csv"
    write_history(history)
    monkeypatch.setattr(skew, "HISTORY", history)

    assert skew.last_live_direction("2026-09-10") == "NARROWING"
    assert skew.last_live_direction("2026-09-09") == "UNAVAILABLE"


def test_legacy_rows_can_infer_market_date_from_timestamp(tmp_path, monkeypatch):
    history = tmp_path / "skew.csv"
    rows = [
        {
            "timestamp_et": "2026-09-10T09:45:00-04:00",
            "put_call_iv_spread_vol_points": "2.9",
            "put_call_iv_ratio": "1.1",
            "source_mode": "LIVE_SPX_OPTIONS",
        }
    ]
    with history.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(skew, "HISTORY", history)

    prior = skew.prior_live_row("2026-09-10")
    assert prior is not None
    assert prior["put_call_iv_spread_vol_points"] == "2.9"
