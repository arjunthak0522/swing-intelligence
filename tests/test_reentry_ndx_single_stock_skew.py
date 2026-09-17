import importlib.util
from datetime import date
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/reentry_ndx_single_stock_skew.py"
spec = importlib.util.spec_from_file_location("reentry_ndx_single_stock_skew", MODULE_PATH)
skew = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(skew)


def test_option_delta_at_the_money_is_sensible():
    call = skew.option_delta(100.0, 100.0, 0.20, 30, 0.04, False)
    put = skew.option_delta(100.0, 100.0, 0.20, 30, 0.04, True)
    assert call is not None and 0.45 < call < 0.60
    assert put is not None and -0.55 < put < -0.40
    assert abs((call - 1.0) - put) < 1e-12


def test_choose_expiry_prefers_nearest_one_month_contract():
    expiries = ["2026-10-02", "2026-10-16", "2026-10-30"]
    selected = skew.choose_expiry(expiries, date(2026, 9, 17))
    assert selected is not None
    expiry, dte = selected
    assert expiry == "2026-10-16"
    assert dte == 29


def test_proxy_withholds_extreme_labels_until_history_is_mature():
    state, pct, sample_pct = skew.build_state([0.10, 0.11, 0.12], 0.01)
    assert state == "BUILDING_HISTORY"
    assert pct is None
    assert sample_pct is not None


def test_proxy_is_context_only():
    row = {
        "market_date": "2026-09-17",
        "timestamp_et": "2026-09-17T11:00:00-04:00",
        "raw_average": 0.05,
        "three_day_average": 0.06,
        "universe_size": 101,
        "valid_count": 75,
        "coverage_pct": 74.26,
        "median_dte": 29,
    }
    card = skew.card_from_row(row, [row])
    assert card["decision_input"] is False
    assert card["changes_deploy_trigger"] is False
    assert card["changes_recovery_stage"] is False
    assert card["replication_status"] == "FREE_DATA_PROXY_NOT_GOLDMAN_EXACT"
