from __future__ import annotations

import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SYMBOLS = {
    "$MMFD": "Percent of stocks above 5-day average",
    "$MMTW": "Percent of stocks above 20-day average",
    "$BPSPX": "S&P 500 Bullish Percent Index",
    "$NYMO": "NYSE McClellan Oscillator",
    "$NAMO": "Nasdaq McClellan Oscillator",
    "$SPXA20R": "S&P 500 percent above 20-day moving average",
    "$SPXA50R": "S&P 500 percent above 50-day moving average",
    "$SPXA200R": "S&P 500 percent above 200-day moving average",
    "$NYUPV": "NYSE advancing volume",
    "$NYDNV": "NYSE declining volume",
    "$NAUPV": "Nasdaq advancing volume",
    "$NADNV": "Nasdaq declining volume",
}

BASE = "https://stockcharts.com/quotebrain/quotes"


def fetch(symbol: str) -> dict:
    url = BASE + "?" + urlencode({"s": symbol, "f": "json", "randomNumber": int(time.time() * 1000)})
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=20) as response:  # nosec - fixed HTTPS source
        payload = json.loads(response.read().decode("utf-8"))
    return {"url": url, "payload": payload}


def main() -> None:
    results = {}
    for symbol, meaning in SYMBOLS.items():
        try:
            data = fetch(symbol)
            results[symbol] = {"meaning": meaning, "ok": True, **data}
        except Exception as exc:
            results[symbol] = {"meaning": meaning, "ok": False, "error": repr(exc)}
    print(json.dumps({"source": "StockCharts quotebrain delayed quote endpoint", "results": results}, indent=2, default=str))


if __name__ == "__main__":
    main()
