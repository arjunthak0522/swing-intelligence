from __future__ import annotations

import json
import time
from datetime import datetime, timezone
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
    }


def finite(x):
    try:
        return x is not None and float(x) == float(x)
    except Exception:
        return False


def improved(q: dict | None, higher_is_better: bool = True) -> bool | None:
    if not q or not finite(q.get("close")) or not finite(q.get("close_yesterday")):
        return None
    now, prev = float(q["close"]), float(q["close_yesterday"])
    return now > prev if higher_is_better else now < prev


def main() -> None:
    quotes = {}
    errors = {}
    for symbol in SYMBOLS:
        try:
            q = fetch_quote(symbol)
            quotes[symbol] = q
            if q is None:
                errors[symbol] = "EMPTY_PAYLOAD"
        except Exception as exc:
            quotes[symbol] = None
            errors[symbol] = f"{type(exc).__name__}: {exc}"

    def val(symbol):
        q = quotes.get(symbol)
        return float(q["close"]) if q and finite(q.get("close")) else None

    sp20, sp50, bpi = val("$SPXA20R"), val("$SPXA50R"), val("$BPSPX")
    nymo, namo = val("$NYMO"), val("$NAMO")
    nyud, naud = val("$NYUD"), val("$NAUD")
    nyupv, nydnv = val("$NYUPV"), val("$NYDNV")
    naupv, nadnv = val("$NAUPV"), val("$NADNV")

    ny_ratio = (nydnv / nyupv) if finite(nydnv) and finite(nyupv) and nyupv > 0 else None
    na_ratio = (nadnv / naupv) if finite(nadnv) and finite(naupv) and naupv > 0 else None

    washout_tests = {
        "sp500_20dma_below_30": sp20 is not None and sp20 <= 30,
        "sp500_50dma_below_40": sp50 is not None and sp50 <= 40,
        "bpspx_below_40": bpi is not None and bpi <= 40,
        "nymo_below_minus_100": nymo is not None and nymo <= -100,
        "namo_below_minus_100": namo is not None and namo <= -100,
    }
    washout_count = sum(bool(v) for v in washout_tests.values())

    pressure_tests = {
        "nyse_net_volume_negative": nyud is not None and nyud < 0,
        "nasdaq_net_volume_negative": naud is not None and naud < 0,
        "nyse_down_up_ratio_gt_1_5": ny_ratio is not None and ny_ratio > 1.5,
        "nasdaq_down_up_ratio_gt_1_5": na_ratio is not None and na_ratio > 1.5,
    }
    pressure_count = sum(bool(v) for v in pressure_tests.values())

    turn_tests = {
        "sp500_20dma_improving": improved(quotes.get("$SPXA20R")),
        "bpspx_improving": improved(quotes.get("$BPSPX")),
        "nymo_improving": improved(quotes.get("$NYMO")),
        "namo_improving": improved(quotes.get("$NAMO")),
        "nyud_improving": improved(quotes.get("$NYUD")),
        "naud_improving": improved(quotes.get("$NAUD")),
    }
    turn_count = sum(v is True for v in turn_tests.values())

    if washout_count == 0:
        state = "NONE"
    elif pressure_count >= 2 and turn_count == 0:
        state = "WASHOUT"
    elif turn_count >= 2:
        state = "DEVELOPING"
    else:
        state = "WASHOUT"

    if washout_count >= 2 and turn_count >= 3 and pressure_count <= 2:
        state = "CONFIRMED"

    payload = {
        "research_only": True,
        "official_signal_authoritative": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "framework": {
            "name": "SELLING EXHAUSTION",
            "state": state,
            "families": ["WASHOUT", "SELLING_PRESSURE", "TURN"],
            "note": "Research classification only. Correlated indicators are grouped into families rather than counted as independent official votes.",
        },
        "washout": {"count": washout_count, "tests": washout_tests},
        "selling_pressure": {
            "count": pressure_count,
            "tests": pressure_tests,
            "nyse_down_up_volume_ratio": ny_ratio,
            "nasdaq_down_up_volume_ratio": na_ratio,
        },
        "turn": {"count": turn_count, "tests": turn_tests},
        "quotes": quotes,
        "missing_or_unavailable": errors,
        "source": "StockCharts delayed quotebrain feed",
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
