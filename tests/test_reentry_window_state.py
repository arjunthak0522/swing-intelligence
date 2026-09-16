import csv
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/reentry_unified_engine.py"
spec = importlib.util.spec_from_file_location("reentry_unified_engine", MODULE_PATH)
engine = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(engine)


def write_history(path, rows):
    fields = ["market_date", "timestamp_et", "decision", "deployment_signal"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def test_fresh_deploy_opens_window(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "HISTORY", tmp_path / "history.csv")
    state = engine.reentry_window_state("2026-09-16", "DEPLOY")
    assert state["reentry_window_active"] is True
    assert state["reentry_window_trigger_date"] == "2026-09-16"
    assert state["reentry_window_age_sessions"] == 0
    assert state["reentry_window_is_decision_input"] is False


def test_prior_deploy_keeps_window_active_without_new_trigger(tmp_path, monkeypatch):
    history = tmp_path / "history.csv"
    write_history(history, [
        {"market_date":"2026-09-14","timestamp_et":"2026-09-14T15:00:00-04:00","decision":"GO_EARLY","deployment_signal":"DEPLOY"},
        {"market_date":"2026-09-15","timestamp_et":"2026-09-15T15:00:00-04:00","decision":"WATCH","deployment_signal":"WATCH"},
    ])
    monkeypatch.setattr(engine, "HISTORY", history)
    state = engine.reentry_window_state("2026-09-16", "WATCH")
    assert state["reentry_window_active"] is True
    assert state["reentry_window_trigger_date"] == "2026-09-14"
    assert state["reentry_window_age_sessions"] == 2
    assert state["reentry_window_research_status"] == "SUPPORTED_WITHIN_RESEARCH_HORIZON"


def test_window_does_not_invent_expiry_beyond_researched_horizon(tmp_path, monkeypatch):
    history = tmp_path / "history.csv"
    rows = []
    for i in range(32):
        rows.append({"market_date":f"2026-08-{i+1:02d}","timestamp_et":"x","decision":"WAIT","deployment_signal":"HOLD_CASH"})
    rows[0]["decision"] = "GO_EARLY"
    rows[0]["deployment_signal"] = "DEPLOY"
    write_history(history, rows)
    monkeypatch.setattr(engine, "HISTORY", history)
    state = engine.reentry_window_state("2026-09-16", "WATCH")
    assert state["reentry_window_active"] is True
    assert state["reentry_window_research_status"] == "BEYOND_RESEARCHED_HORIZON"
