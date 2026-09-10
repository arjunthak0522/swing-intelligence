#!/usr/bin/env python3
"""Research-only NASI+ bootstrap stability diagnostic.

Compares the existing current-year bootstrap against a longer multi-year bootstrap using
the exact same NASI+ formula. This does not modify the live NASI+ value or unified engine.

Important: this diagnostic fails closed when older-year source history is incomplete. It
must never label a current-year-only comparison as a valid multi-year validation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from reentry_exhaustion_intraday import calculate_nasi_plus, fetch_nasdaq_daily_breadth, finite

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "data/reentry/exhaustion_intraday_current.json"
OUT_JSON = ROOT / "research/reentry_nasi_bootstrap_diagnostic.json"
OUT_MD = ROOT / "research/reentry_nasi_bootstrap_diagnostic.md"
LOOKBACK_YEARS = 4
MIN_REQUIRED_YEARS = 3


def main() -> None:
    if not CURRENT.exists():
        raise SystemExit(f"Missing {CURRENT}")
    payload = json.loads(CURRENT.read_text(encoding="utf-8"))
    values = payload.get("values") or {}
    market_date = str(values.get("market_date") or "")
    live_adv = values.get("NAADV")
    live_dec = values.get("NADEC")
    if not market_date or not finite(live_adv) or not finite(live_dec):
        raise SystemExit("Current snapshot lacks market_date or Nasdaq advances/declines")

    year = int(market_date[:4])
    current_year_history = fetch_nasdaq_daily_breadth(year)
    long_history = []
    errors = []
    loaded_years = []
    requested_years = list(range(year - LOOKBACK_YEARS + 1, year + 1))
    for y in requested_years:
        try:
            rows = fetch_nasdaq_daily_breadth(y)
            long_history.extend(rows)
            loaded_years.append(y)
        except Exception as exc:
            errors.append(f"{y}: {type(exc).__name__}: {exc}")
    long_history = sorted({r["market_date"]: r for r in long_history}.values(), key=lambda r: r["market_date"])

    current = calculate_nasi_plus(current_year_history, float(live_adv), float(live_dec), market_date)
    source_complete = len(loaded_years) >= MIN_REQUIRED_YEARS and year in loaded_years
    materially_longer = len(long_history) >= max(len(current_year_history) * 2, 250)
    valid_multi_year_test = source_complete and materially_longer

    longer = None
    comparison = {
        "rsi_difference_multi_year_minus_current_year": None,
        "direction_match": None,
        "oversold_classification_match": None,
        "existing_observations": current.get("completed_daily_observations"),
        "multi_year_observations": None,
    }

    if valid_multi_year_test:
        longer = calculate_nasi_plus(long_history, float(live_adv), float(live_dec), market_date)
        current_rsi = current.get("nasi_rsi")
        long_rsi = longer.get("nasi_rsi")
        comparison = {
            "rsi_difference_multi_year_minus_current_year": float(long_rsi) - float(current_rsi) if finite(current_rsi) and finite(long_rsi) else None,
            "direction_match": current.get("direction_vs_prior_close") == longer.get("direction_vs_prior_close"),
            "oversold_classification_match": bool(current.get("oversold_below_30")) == bool(longer.get("oversold_below_30")),
            "existing_observations": current.get("completed_daily_observations"),
            "multi_year_observations": longer.get("completed_daily_observations"),
        }

    diagnostic = {
        "classification": "RESEARCH_ONLY_DIAGNOSTIC",
        "engine_impact": "NONE",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_date": market_date,
        "formula_version": current.get("formula_version"),
        "requested_years": requested_years,
        "loaded_years": loaded_years,
        "source_complete": source_complete,
        "materially_longer_history": materially_longer,
        "valid_multi_year_test": valid_multi_year_test,
        "existing_current_year": current,
        "multi_year": longer,
        "comparison": comparison,
        "source_errors": errors,
        "promotion_status": "NO_CHANGE_TO_LIVE_NASI_PLUS",
        "diagnostic_status": "VALID" if valid_multi_year_test else "INCOMPLETE_SOURCE_HISTORY",
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(diagnostic, indent=2), encoding="utf-8")

    current_rsi = current.get("nasi_rsi")
    long_rsi = longer.get("nasi_rsi") if longer else None
    lines = [
        "# NASI+ bootstrap stability diagnostic",
        "",
        "**Research only - the live NASI+ calculation is unchanged.**",
        "",
        f"Diagnostic status: **{diagnostic['diagnostic_status']}**",
        f"Market date: **{market_date}**",
        f"Requested years: **{', '.join(map(str, requested_years))}**",
        f"Successfully loaded years: **{', '.join(map(str, loaded_years)) if loaded_years else 'none'}**",
        f"Existing bootstrap observations: **{current.get('completed_daily_observations')}**",
        f"Valid multi-year comparison: **{valid_multi_year_test}**",
    ]
    if valid_multi_year_test:
        lines += [
            f"Multi-year bootstrap observations: **{longer.get('completed_daily_observations')}**",
            f"Existing NASI+ RSI: **{current_rsi}**",
            f"Multi-year NASI+ RSI: **{long_rsi}**",
            f"RSI difference: **{comparison['rsi_difference_multi_year_minus_current_year']}**",
            f"Direction match: **{comparison['direction_match']}**",
            f"Oversold classification match: **{comparison['oversold_classification_match']}**",
        ]
    else:
        lines += [
            "",
            "**No multi-year stability conclusion is permitted from this run.** Older source history is incomplete or not materially longer than the current-year bootstrap.",
        ]
    lines += [
        "",
        "Do not change the live bootstrap unless a genuinely longer, source-complete diagnostic shows a material and decision-relevant instability.",
    ]
    if errors:
        lines += ["", "## Source errors", ""] + [f"- {x}" for x in errors]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(diagnostic, indent=2))


if __name__ == "__main__":
    main()
