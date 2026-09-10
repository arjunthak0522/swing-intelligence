from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "web/app/page.tsx"
UNIFIED = ROOT / "web/lib/unifiedReentry.ts"


def test_active_page_uses_only_unified_loader():
    text = PAGE.read_text(encoding="utf-8")
    assert 'from "../lib/unifiedReentry"' in text
    assert 'from "../lib/reentry"' not in text
    assert "getLatestSnapshot" not in text
    assert "getIntradaySnapshot" not in text
    assert "getLatestEpisode" not in text


def test_active_page_does_not_render_retired_decision_language():
    text = PAGE.read_text(encoding="utf-8")
    banned = [
        "CAUTIOUS YES",
        "STRONG YES",
        "NO RE-ENTRY SETUP",
        "OFFICIAL DECISION",
        "analog_decision",
        "completed-close decision remains authoritative",
    ]
    for token in banned:
        assert token not in text


def test_unified_loader_accepts_only_unified_engine_snapshot():
    text = UNIFIED.read_text(encoding="utf-8")
    assert '"WAIT" | "WATCH" | "GO_EARLY"' in text
    assert "snapshot?.unified_engine?.engine_version" in text
    assert "DEFAULT_UNIFIED_URL" in text


def test_page_fails_closed_when_unified_snapshot_missing():
    text = PAGE.read_text(encoding="utf-8")
    assert "RE-ENTRY unavailable" in text
    assert "No legacy decision is substituted" in text
