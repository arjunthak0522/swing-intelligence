#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
USER_AGENT = "Mozilla/5.0 RE-ENTRY-options-sentiment/1.0"
DAILY_URL = "https://www.cboe.com/markets/us/options/market-statistics/daily"
LIVE_URL = "https://www.cboe.com/us/options/market_statistics/market/"
MAX_EOD_LOOKBACK_DAYS = 7


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
    with urlopen(req, timeout=25) as resp:  # nosec - fixed Cboe endpoints
        raw = resp.read().decode("utf-8", errors="replace")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def classify(eq: float | None) -> str:
    if eq is None:
        return "UNAVAILABLE"
    if eq >= 0.90:
        return "HIGH_FEAR"
    if eq >= 0.70:
        return "FEAR"
    if eq >= 0.50:
        return "NORMAL"
    return "COMPLACENT"


def daily_ratios(market_date: str) -> dict | None:
    text = fetch_text(f"{DAILY_URL}?{urlencode({'dt': market_date})}")

    def extract(label: str) -> float | None:
        match = re.search(re.escape(label) + r"\s*([0-9]+(?:\.[0-9]+)?)", text, re.I)
        return float(match.group(1)) if match else None

    eq = extract("EQUITY PUT/CALL RATIO")
    idx = extract("INDEX PUT/CALL RATIO")
    total = extract("TOTAL PUT/CALL RATIO")
    if eq is None and idx is None and total is None:
        return None
    return {
        "equity_put_call": eq,
        "index_put_call": idx,
        "total_put_call": total,
        "freshness_type": "DAILY_CLOSE",
        "last_updated": market_date,
        "source": "Cboe U.S. Options Daily Market Statistics",
    }


def latest_completed_daily(target_date: str) -> dict | None:
    """Return target-date EOD when published, otherwise the newest prior completed EOD."""
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    for offset in range(MAX_EOD_LOOKBACK_DAYS + 1):
        candidate = target - timedelta(days=offset)
        if candidate.weekday() >= 5:
            continue
        try:
            ratios = daily_ratios(candidate.isoformat())
        except Exception:
            ratios = None
        if ratios is None:
            continue
        ratios["freshness_state"] = "TODAY_CLOSE" if candidate == target else "PRIOR_CLOSE"
        ratios["requested_market_date"] = target_date
        return ratios
    return None


def _live_section_ratio(text: str, heading: str, next_heading: str | None) -> tuple[float | None, str | None]:
    marker = re.compile(
        rf"{re.escape(heading)}\s+TIME\s+CALLS\s+PUTS\s+TOTAL\s+P/C\s+RATIO",
        re.I,
    )
    match = marker.search(text)
    if not match:
        return None, None
    end = len(text)
    if next_heading:
        next_match = re.search(re.escape(next_heading), text[match.end():], re.I)
        if next_match:
            end = match.end() + next_match.start()
    section = text[match.end():end]
    rows = re.findall(
        r"(\d{1,2}:\d{2}\s*[AP]M)\s+(\d+)\s+(\d+)\s+(\d+)\s+([0-9]+(?:\.[0-9]+)?)",
        section,
        re.I,
    )
    if not rows:
        return None, None
    latest = rows[-1]
    return float(latest[4]), re.sub(r"\s+", " ", latest[0].upper()).strip()


def live_ratios(market_date: str) -> dict | None:
    text = fetch_text(LIVE_URL)
    date_match = re.search(
        r"Cboe Exchange Market Statistics for [A-Za-z]+,\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        text,
        re.I,
    )
    if not date_match:
        return None
    live_date = datetime.strptime(date_match.group(1), "%B %d, %Y").date().isoformat()
    if live_date != market_date:
        return None

    total, total_time = _live_section_ratio(text, "Total", "Index Options")
    idx, idx_time = _live_section_ratio(text, "Index Options", "Equity Options")
    eq, eq_time = _live_section_ratio(text, "Equity Options", None)
    if eq is None and idx is None and total is None:
        return None

    latest_time = eq_time or idx_time or total_time
    return {
        "equity_put_call": eq,
        "index_put_call": idx,
        "total_put_call": total,
        "freshness_type": "INTRADAY_DELAYED",
        "freshness_state": "LIVE",
        "last_updated": f"{market_date} {latest_time} CT" if latest_time else market_date,
        "requested_market_date": market_date,
        "source": "Cboe U.S. Options Current Market Statistics",
    }


def build_signal(market_date: str) -> dict:
    today = datetime.now(ET).date().isoformat()
    ratios = None

    # During the current session prefer a genuine live observation. If Cboe has
    # not exposed one yet, use the latest completed official EOD observation.
    if market_date == today:
        try:
            ratios = live_ratios(market_date)
        except Exception:
            ratios = None

    if ratios is None:
        ratios = latest_completed_daily(market_date)
    if ratios is None:
        raise ValueError("Cboe did not expose a live or recent completed-session put/call observation")

    eq = ratios.get("equity_put_call")
    return {
        "name": "Options sentiment",
        "state": classify(eq),
        "supportive": False,
        "equity_put_call": eq,
        "index_put_call": ratios.get("index_put_call"),
        "total_put_call": ratios.get("total_put_call"),
        "benchmark": "Equity P/C <0.50 complacent · 0.50-0.70 normal · 0.70-0.90 fear · >=0.90 high fear (working display scale until percentiles mature)",
        "retail_explanation": "This looks at how heavily traders are using puts versus calls. High put activity often means fear is elevated.",
        "signal_behavior": "CONTRARIAN",
        "behavior_explanation": "Unusually high fear can improve a re-entry setup, but fear alone is not a buy signal. Confirmation comes when fear retreats while breadth improves.",
        "freshness_type": ratios["freshness_type"],
        "freshness_state": ratios.get("freshness_state"),
        "last_updated": ratios["last_updated"],
        "requested_market_date": ratios.get("requested_market_date"),
        "source": ratios["source"],
        "validation_status": "VALIDATED_SENTIMENT_OVERLAY",
        "validation_note": "Across 94 historical DEPLOY episodes using Cboe archive plus daily statistics, equity fear (P/C >=0.70) appeared at 49 starts and was generally supportive over 30-90D, but missed the SPY 10D median gate. Fear-reversing occurred at only 14 starts, below the promotion sample threshold. Cboe also documents 2022 early-exercise distortion in raw equity P/C. Keep as a contrarian sentiment overlay, never a DEPLOY gate.",
    }


def patch_snapshot(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    market_date = str((payload.get("unified_engine") or {}).get("market_date") or payload.get("values", {}).get("market_date") or "")
    if not market_date:
        raise ValueError("Snapshot does not contain a market_date")
    signal = build_signal(market_date)

    secondary = payload.get("secondary_confirmation")
    if not isinstance(secondary, dict):
        raise ValueError("Snapshot does not contain secondary_confirmation")
    families = secondary.setdefault("families", {})
    families["options_sentiment"] = signal
    errors = secondary.get("errors")
    if isinstance(errors, dict):
        errors.pop("options_sentiment", None)
        if not errors:
            secondary.pop("errors", None)

    nested = (payload.get("unified_engine") or {}).get("secondary_confirmation")
    if isinstance(nested, dict):
        nested.setdefault("families", {})["options_sentiment"] = signal
        nested_errors = nested.get("errors")
        if isinstance(nested_errors, dict):
            nested_errors.pop("options_sentiment", None)
            if not nested_errors:
                nested.pop("errors", None)

    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return signal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    args = parser.parse_args()
    signal = patch_snapshot(Path(args.snapshot))
    print(json.dumps(signal, indent=2))


if __name__ == "__main__":
    main()
