from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRIMARY_FILES = [
    ROOT / "web/app/CategorizedIndicatorBoard.tsx",
    ROOT / "web/app/ReentryDecisionDetails.tsx",
    ROOT / "web/app/page.tsx",
    ROOT / "web/app/AggregateHistoricalEvidence.tsx",
]

PAYLOAD_FILES = [
    ROOT / "tools/reentry_leading_indicators.py",
    ROOT / "tools/reentry_secondary_confirmation.py",
    ROOT / "tools/reentry_ndx_single_stock_skew.py",
    ROOT / "tools/reentry_options_sentiment_live.py",
    ROOT / "tools/reentry_indicator_completeness.py",
]

# These are allowed in secondary technical/reference fields, source fields and internal
# variable names, but not as the primary retail label or plain-English explanation.
FORBIDDEN_RETAIL_TOKENS = (
    "SPXA20R", "MMFD", "NASI", "VVIX", "SKEW", "CPCE",
    "NYMO", "NAMO", "NYUD", "NAUD", "SPY", "QQQ",
    "RSP", "IWM", "HYG", "LQD", "VIX3M",
)

TOKEN_RE = re.compile(
    r"(?<![A-Z0-9])(" + "|".join(map(re.escape, FORBIDDEN_RETAIL_TOKENS)) + r")(?![A-Z0-9])"
)


def assert_plain(text: str, where: str) -> None:
    match = TOKEN_RE.search(text)
    assert not match, f"{where} contains technical shorthand {match.group(1)!r}: {text!r}"


def test_primary_indicator_labels_are_plain_english() -> None:
    board = (ROOT / "web/app/CategorizedIndicatorBoard.tsx").read_text(encoding="utf-8")
    details = (ROOT / "web/app/ReentryDecisionDetails.tsx").read_text(encoding="utf-8")

    row_names = re.findall(r'row\("([^"]+)"', board)
    metric_names = re.findall(r'MetricCard name="([^"]+)"', details)

    assert row_names, "No categorized indicator row labels found"
    assert metric_names, "No deep-diagnostic MetricCard labels found"

    for name in row_names:
        assert_plain(name, "categorized primary label")
    for name in metric_names:
        assert_plain(name, "deep-diagnostic primary label")


def test_context_turn_labels_do_not_lead_with_engine_codes() -> None:
    details = (ROOT / "web/app/ReentryDecisionDetails.tsx").read_text(encoding="utf-8")
    match = re.search(r"const contextRows=\[(.*?)\] as const;", details, flags=re.S)
    assert match, "contextRows not found"
    labels = re.findall(r'\["([^"]+)"', match.group(1))
    assert len(labels) == 4
    for label in labels:
        assert_plain(label, "context-turn label")


def test_live_board_meanings_are_plain_english() -> None:
    board = (ROOT / "web/app/CategorizedIndicatorBoard.tsx").read_text(encoding="utf-8")
    match = re.search(r"const meanings: Record<string, string> = \{(.*?)\n  \};\n\n  const oversoldCount", board, flags=re.S)
    assert match, "meanings block not found"
    block = match.group(1)

    # Scan only the right-hand side of each meaning entry. Keys and technical reference
    # fields are intentionally allowed to carry symbols for auditability.
    for lineno, line in enumerate(block.splitlines(), start=1):
        if ":" not in line:
            continue
        rhs = line.split(":", 1)[1]
        assert_plain(rhs, f"live-board meaning line {lineno}")


def test_deep_diagnostic_explanations_are_plain_english() -> None:
    details = (ROOT / "web/app/ReentryDecisionDetails.tsx").read_text(encoding="utf-8")

    user_copy = []
    user_copy += re.findall(r'behaviorExplanation="([^"]+)"', details)
    user_copy += re.findall(r'benchmark="([^"]+)"', details)
    user_copy += [x for pair in re.findall(r'return(?:"([^"]*)"|\`([^\`]*)\`)', details) for x in pair if x]

    for text in user_copy:
        assert_plain(text, "deep-diagnostic explanation")


def test_payload_names_and_explanations_are_plain_english() -> None:
    field_re = re.compile(
        r'["\'](?:name|meaning|retail_explanation|behavior_explanation)["\']\s*:\s*["\']([^"\']*)["\']'
    )
    for path in PAYLOAD_FILES:
        content = path.read_text(encoding="utf-8")
        for value in field_re.findall(content):
            assert_plain(value, f"{path.name} retail copy")


def test_market_and_history_surfaces_use_descriptive_asset_names_first() -> None:
    page = (ROOT / "web/app/page.tsx").read_text(encoding="utf-8")
    history = (ROOT / "web/app/AggregateHistoricalEvidence.tsx").read_text(encoding="utf-8")

    assert "<small>SPY " not in page
    assert "<small>QQQ " not in page
    assert "<span>SPY median</span>" not in history
    assert "<span>QQQ median</span>" not in history
    assert "S&P 500 ETF" in page
    assert "Nasdaq-100 ETF" in page


def test_internal_role_codes_are_not_exposed_as_explanatory_copy() -> None:
    board = (ROOT / "web/app/CategorizedIndicatorBoard.tsx").read_text(encoding="utf-8")
    assert '<span className="indicator-technical-role">{item.role}</span>' not in board
    # Stale payload wording must never override audited retail copy.\n    assert ".meaning ||" not in board, "payload-provided meanings must not override audited plain-English copy"\n    assert "ENGINE INPUT" in board
    assert "CONTEXT ONLY" in board
