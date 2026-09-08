import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const SYMBOL_GROUPS = {
  broad: ["SPY", "QQQ"],
  sectors: ["XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLB", "XLRE", "XLK", "XLU"],
  factors: ["MTUM", "QUAL", "VLUE", "IWF", "IWD", "USMV", "SPYD", "IWM"],
  subsectors: [
    "FDN", "IYZ", "PBS", "XRT", "ITB", "PEJ", "PBJ", "RHS", "XOP", "OIH", "CRAK",
    "KRE", "KBE", "IAI", "KIE", "XBI", "IBB", "IHI", "IHF", "ITA", "XTN", "PAVE",
    "XME", "COPX", "SLX", "REZ", "SRVR", "NETL", "SMH", "IGV", "HACK", "RNRG", "RYU"
  ],
  volatility: ["^VIX", "^VIX3M"]
} as const;

const ALL = [...new Set(Object.values(SYMBOL_GROUPS).flat())];
const yahooSymbol = (s: string) => encodeURIComponent(s);

function freshRegularSessionBar(timestamp: number | null | undefined) {
  if (!timestamp) return false;
  const ageMs = Date.now() - timestamp * 1000;
  return ageMs >= -60_000 && ageMs <= 10 * 60_000;
}

async function fetchQuote(symbol: string) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${yahooSymbol(symbol)}?interval=5m&range=1d&includePrePost=false&events=div%2Csplits`;
  const res = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 RE-ENTRY/1.0",
      "Accept": "application/json"
    }
  });
  if (!res.ok) throw new Error(`${symbol}: Yahoo HTTP ${res.status}`);
  const body = await res.json();
  const result = body?.chart?.result?.[0];
  if (!result) throw new Error(`${symbol}: missing chart result`);
  const meta = result.meta ?? {};
  const timestamps: number[] = result.timestamp ?? [];
  const closes: Array<number | null> = result.indicators?.quote?.[0]?.close ?? [];
  let lastIndex = -1;
  for (let i = closes.length - 1; i >= 0; i--) {
    if (typeof closes[i] === "number" && Number.isFinite(closes[i])) { lastIndex = i; break; }
  }
  const price = lastIndex >= 0 ? closes[lastIndex] : meta.regularMarketPrice;
  const timestamp = lastIndex >= 0 ? timestamps[lastIndex] : meta.regularMarketTime;
  const previousClose = Number(meta.chartPreviousClose ?? meta.previousClose ?? meta.regularMarketPreviousClose);
  const changePct = Number.isFinite(price) && Number.isFinite(previousClose) && previousClose > 0
    ? price / previousClose - 1
    : null;
  const inferredRegular = freshRegularSessionBar(timestamp);
  const marketState = meta.marketState === "REGULAR" || inferredRegular ? "REGULAR" : (meta.marketState ?? null);
  return {
    symbol,
    price: Number.isFinite(price) ? price : null,
    previous_close: Number.isFinite(previousClose) ? previousClose : null,
    change_pct: changePct,
    timestamp: timestamp ? new Date(timestamp * 1000).toISOString() : null,
    exchange_timezone: meta.exchangeTimezoneName ?? null,
    market_state: marketState,
    market_state_source: meta.marketState === "REGULAR" ? "YAHOO" : (inferredRegular ? "FRESH_REGULAR_SESSION_BAR" : "YAHOO"),
    currency: meta.currency ?? null
  };
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "content-type",
      "Access-Control-Allow-Methods": "GET, OPTIONS"
    }});
  }
  if (req.method !== "GET") return new Response("Method Not Allowed", { status: 405 });

  const settled = await Promise.allSettled(ALL.map(fetchQuote));
  const quotes: Record<string, unknown> = {};
  const errors: string[] = [];
  settled.forEach((r, i) => {
    const symbol = ALL[i];
    if (r.status === "fulfilled") quotes[symbol] = r.value;
    else errors.push(String(r.reason?.message ?? r.reason ?? symbol));
  });

  const pct = (symbols: readonly string[]) => symbols
    .map(s => (quotes[s] as any)?.change_pct)
    .filter((x: unknown) => typeof x === "number" && Number.isFinite(x as number)) as number[];
  const sectorMoves = pct(SYMBOL_GROUPS.sectors);
  const subsectorMoves = pct(SYMBOL_GROUPS.subsectors);
  const factorMoves = pct(SYMBOL_GROUPS.factors);
  const positiveShare = (xs: number[]) => xs.length ? xs.filter(x => x > 0).length / xs.length : null;

  const payload = {
    generated_at: new Date().toISOString(),
    cadence: "5-minute market bars on request",
    status: errors.length === 0 ? "LIVE" : (Object.keys(quotes).length >= 40 ? "PARTIAL" : "DEGRADED"),
    official_signal_authoritative: false,
    interpretation: "Intraday data is provisional context only. The official RE-ENTRY decision is based on completed-close data.",
    groups: SYMBOL_GROUPS,
    summary: {
      sectors_positive_share: positiveShare(sectorMoves),
      subsectors_positive_share: positiveShare(subsectorMoves),
      factors_positive_share: positiveShare(factorMoves),
      tracked_quotes: Object.keys(quotes).length,
      expected_quotes: ALL.length
    },
    quotes,
    errors
  };

  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "public, s-maxage=60, stale-while-revalidate=120",
      "Access-Control-Allow-Origin": "*"
    }
  });
});
