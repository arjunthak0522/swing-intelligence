from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from urllib.parse import quote
from urllib.request import Request, urlopen

SYMBOLS = {
    "$SPXA20R": "S&P 500 % above 20DMA",
    "$SPXA50R": "S&P 500 % above 50DMA",
    "$SPXA200R": "S&P 500 % above 200DMA",
    "$BPSPX": "S&P 500 Bullish Percent Index",
    "$NYMO": "NYSE McClellan Oscillator",
    "$NAMO": "Nasdaq McClellan Oscillator",
    "$NYUD": "NYSE advance-decline volume",
    "$NAUD": "Nasdaq advance-decline volume",
    "$NYUPV": "NYSE advancing volume",
    "$NYDNV": "NYSE declining volume",
    "$NAUPV": "Nasdaq advancing volume",
    "$NADNV": "Nasdaq declining volume",
    "$MMFD": "Percent of stocks above 5-day average",
    "$MMTW": "Percent of stocks above 20-day average",
}

EODDATA_FALLBACK = {
    "$MMFD": "https://eoddata.com/stockquote/INDEX/MMFD.htm",
    "$MMTW": "https://eoddata.com/stockquote/INDEX/MMTW.htm",
}


def fetch_quote(symbol: str) -> dict | None:
    url = f"https://stockcharts.com/quotebrain/quotes?s={quote(symbol)}&f=json&randomNumber={int(time.time()*1000)}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=20) as resp:  # nosec - fixed StockCharts endpoint
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload:
        return None
    row = payload[0]
    return {
        "symbol": symbol,
        "name": row.get("name") or SYMBOLS[symbol],
        "close": row.get("close"),
        "close_yesterday": row.get("closeYesterday"),
        "as_of": (row.get("time") or {}).get("time"),
        "zone": (row.get("time") or {}).get("zone"),
        "realtime": row.get("realtime"),
        "cached": row.get("cached"),
        "source": "StockCharts delayed quotebrain feed",
    }


def fetch_eoddata_fallback(symbol: str) -> dict | None:
    url = EODDATA_FALLBACK[symbol]
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=20) as resp:  # nosec - fixed EODData endpoint
        raw = resp.read().decode("utf-8", errors="replace")
    text = unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"\s+", " ", text)
    row = re.search(
        r"RECENT END OF DAY PRICES\s+Date\s+Open\s+High\s+Low\s+Close\s+Volume\s+"
        r"(\d{2}\s+[A-Za-z]{3}\s+\d{2})\s+"
        r"([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)\s+"
        r"([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)\s+\d+",
        text,
        re.IGNORECASE,
    )
    if not row:
        return None
    first_date = row.group(1)
    first_close = float(row.group(5))
    after = text[row.end():]
    second = re.search(
        r"(\d{2}\s+[A-Za-z]{3}\s+\d{2})\s+"
        r"([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)\s+"
        r"([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)\s+\d+",
        after,
        re.IGNORECASE,
    )
    prev_close = float(second.group(5)) if second else None
    return {
        "symbol": symbol,
        "name": SYMBOLS[symbol],
        "close": first_close,
        "close_yesterday": prev_close,
        "as_of": first_date,
        "zone": "America/New_York",
        "realtime": False,
        "cached": None,
        "source": "EODData free recent EOD page fallback",
        "source_url": url,
    }


def finite(x):
    try:
        return x is not None and float(x) == float(x)
    except Exception:
        return False


def improved(q: dict | None) -> bool | None:
    if not q or not finite(q.get("close")) or not finite(q.get("close_yesterday")):
        return None
    return float(q["close"]) > float(q["close_yesterday"])


def main() -> None:
    quotes = {}
    errors = {}
    for symbol in SYMBOLS:
        try:
            q = fetch_quote(symbol)
            if q is None and symbol in EODDATA_FALLBACK:
                q = fetch_eoddata_fallback(symbol)
            quotes[symbol] = q
            if q is None:
                errors[symbol] = "EMPTY_PAYLOAD_ALL_FREE_SOURCES"
        except Exception as exc:
            if symbol in EODDATA_FALLBACK:
                try:
                    q = fetch_eoddata_fallback(symbol)
                    quotes[symbol] = q
                    if q is None:
                        errors[symbol] = f"FALLBACK_EMPTY_AFTER_{type(exc).__name__}"
                    continue
                except Exception as fallback_exc:
                    errors[symbol] = f"StockCharts {type(exc).__name__}; EODData {type(fallback_exc).__name__}: {fallback_exc}"
            else:
                errors[symbol] = f"{type(exc).__name__}: {exc}"
            quotes[symbol] = None

    def val(symbol):
        q = quotes.get(symbol)
        return float(q["close"]) if q and finite(q.get("close")) else None

    mmfd, mmtw = val("$MMFD"), val("$MMTW")
    sp20, sp50, bpi = val("$SPXA20R"), val("$SPXA50R"), val("$BPSPX")
    nymo, namo = val("$NYMO"), val("$NAMO")
    nyud, naud = val("$NYUD"), val("$NAUD")
    nyupv, nydnv = val("$NYUPV"), val("$NYDNV")
    naupv, nadnv = val("$NAUPV"), val("$NADNV")

    ny_ratio = (nydnv / nyupv) if finite(nydnv) and finite(nyupv) and nyupv > 0 else None
    na_ratio = (nadnv / naupv) if finite(nadnv) and finite(naupv) and naupv > 0 else None

    oversold_tests = {
        "mmfd_below_20": mmfd is not None and mmfd <= 20,
        "mmtw_below_30": mmtw is not None and mmtw <= 30,
        "sp500_20dma_below_30": sp20 is not None and sp20 <= 30,
        "sp500_50dma_below_40": sp50 is not None and sp50 <= 40,
        "bpspx_below_40": bpi is not None and bpi <= 40,
        "nymo_below_minus_100": nymo is not None and nymo <= -100,
        "namo_below_minus_100": namo is not None and namo <= -100,
    }
    fast_breadth = any(oversold_tests[k] for k in ("mmfd_below_20", "mmtw_below_30", "sp500_20dma_below_30"))
    intermediate_breadth = oversold_tests["sp500_50dma_below_40"]
    structural_breadth = oversold_tests["bpspx_below_40"]
    momentum_extreme = oversold_tests["nymo_below_minus_100"] or oversold_tests["namo_below_minus_100"]
    oversold_family_count = sum((fast_breadth, intermediate_breadth, structural_breadth, momentum_extreme))

    pressure_tests = {
        "nyse_net_volume_negative": nyud is not None and nyud < 0,
        "nasdaq_net_volume_negative": naud is not None and naud < 0,
        "nyse_down_up_ratio_gt_1_5": ny_ratio is not None and ny_ratio > 1.5,
        "nasdaq_down_up_ratio_gt_1_5": na_ratio is not None and na_ratio > 1.5,
    }
    pressure_count = sum(bool(v) for v in pressure_tests.values())

    turn_tests = {
        "mmfd_improving": improved(quotes.get("$MMFD")),
        "mmtw_improving": improved(quotes.get("$MMTW")),
        "sp500_20dma_improving": improved(quotes.get("$SPXA20R")),
        "bpspx_improving": improved(quotes.get("$BPSPX")),
        "nymo_improving": improved(quotes.get("$NYMO")),
        "namo_improving": improved(quotes.get("$NAMO")),
        "nyud_improving": improved(quotes.get("$NYUD")),
        "naud_improving": improved(quotes.get("$NAUD")),
    }
    fast_turn = any(turn_tests[k] is True for k in ("mmfd_improving", "mmtw_improving", "sp500_20dma_improving"))
    structural_turn = turn_tests["bpspx_improving"] is True
    momentum_turn = (turn_tests["nymo_improving"] is True) or (turn_tests["namo_improving"] is True)
    volume_turn = (turn_tests["nyud_improving"] is True) or (turn_tests["naud_improving"] is True)
    turn_family_count = sum((fast_turn, structural_turn, momentum_turn, volume_turn))

    # Snapshot semantics are deliberately event-first. A first observable turn after
    # an oversold condition is WASHOUT regardless of how many families turn at once.
    # CONFIRMED is a temporal state and is assigned only by the persistence layer on
    # a later market date when corroboration persists or broadens.
    immediate_turn = fast_turn or momentum_turn or volume_turn
    if oversold_family_count == 0:
        state = "NONE"
        candidate_action = "WAIT"
    elif not immediate_turn:
        state = "OVERSOLD"
        candidate_action = "WAIT_FOR_WASHOUT"
    else:
        state = "WASHOUT"
        candidate_action = "GO_EARLY"

    payload = {
        "research_only": True,
        "official_signal_authoritative": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "framework": {
            "name": "SELLING EXHAUSTION",
            "state": state,
            "candidate_action": candidate_action,
            "sequence": ["OVERSOLD", "WASHOUT", "CONFIRMED"],
            "note": "Research classification only. The first observable turn after an oversold condition is always WASHOUT and is intentionally treated as the early-entry candidate. CONFIRMED can only occur on a later market date if corroboration persists or broadens.",
        },
        "oversold": {
            "family_count": oversold_family_count,
            "family_tests": {
                "fast_breadth": fast_breadth,
                "intermediate_breadth": intermediate_breadth,
                "structural_breadth": structural_breadth,
                "momentum_extreme": momentum_extreme,
            },
            "raw_tests": oversold_tests,
        },
        "selling_pressure": {
            "count": pressure_count,
            "tests": pressure_tests,
            "nyse_down_up_volume_ratio": ny_ratio,
            "nasdaq_down_up_volume_ratio": na_ratio,
        },
        "turn": {
            "immediate_turn": immediate_turn,
            "family_count": turn_family_count,
            "family_tests": {
                "fast_breadth_turn": fast_turn,
                "structural_turn": structural_turn,
                "momentum_turn": momentum_turn,
                "volume_turn": volume_turn,
            },
            "raw_tests": turn_tests,
        },
        "quotes": quotes,
        "missing_or_unavailable": errors,
        "sources": [
            "StockCharts delayed quotebrain feed",
            "EODData free recent EOD page fallback for MMFD/MMTW when StockCharts payload is empty",
        ],
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
