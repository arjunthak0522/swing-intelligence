# RE-ENTRY frozen engine contract

Status: **research frozen - ready for product integration, not production deployment**

Canonical implementation: `tools/reentry_engine.py`

The product answers one question: **Does it make sense to put cash back into the market right now?**

The engine emits exactly one of:

- `RE-ENTER`
- `WAIT`
- `NO RE-ENTRY SETUP`

The UI and any downstream service must consume the canonical snapshot. No client or integration may recreate, reinterpret, score, average, or override the strategy rules.

## 1. Headline market inputs

- SPY drawdown from 20-day high
- SPY 5-day return
- % of S&P 500 constituents above 50DMA
- % of S&P 500 constituents above 200DMA
- 1-day breadth change
- 3-day breadth change
- VIX 5-day change
- VIX / VIX3M ratio

Validated broad weakness context is present when one or more of these conditions is true:

- SPY is at least 1% below its 20-day high
- 50% or fewer S&P 500 stocks are above their 50DMA
- VIX is up at least 10% over five trading days
- VIX / VIX3M is at or above 1.0

There is no maximum drawdown exclusion. Large corrections remain eligible.

## 2. Sector layer - all 11 headline sectors

- XLC - Communication Services
- XLY - Consumer Discretionary
- XLP - Consumer Staples
- XLE - Energy
- XLF - Financials
- XLV - Health Care
- XLI - Industrials
- XLB - Materials
- XLRE - Real Estate
- XLK - Technology
- XLU - Utilities

For every sector the engine evaluates, where available:

- 20-day drawdown
- 60-day drawdown
- 20-day relative strength vs SPY
- 60-day relative strength vs SPY
- damage breadth at 2%, 3%, and 5% thresholds
- repair breadth
- cross-sectional dispersion
- relative-strength dispersion
- median daily repair behavior

## 3. Subsector and industry proxy layer

Subsector histories use liquid ETF proxies. They are diagnostic market-structure proxies, not proprietary point-in-time industry constituent histories.

### Communication Services
- FDN - Internet
- IYZ - Telecom
- PBS - Media

### Consumer Discretionary
- XRT - Retail
- ITB - Homebuilders
- PEJ - Leisure & Entertainment

### Consumer Staples
- PBJ - Food & Beverage
- RHS - Equal-Weight Consumer Staples

### Energy
- XOP - Oil & Gas Exploration / Production
- OIH - Oil Services
- CRAK - Refiners

### Financials
- KRE - Regional Banks
- KBE - Banks
- IAI - Broker-Dealers
- KIE - Insurance

### Health Care
- XBI - Biotech
- IBB - Large-Cap Biotech
- IHI - Medical Devices
- IHF - Healthcare Providers

### Industrials
- ITA - Aerospace & Defense
- XTN - Transportation
- PAVE - Infrastructure

### Materials
- XME - Metals & Mining
- COPX - Copper Miners
- SLX - Steel

### Real Estate
- REZ - Residential & Specialized REITs
- SRVR - Data Centers & Digital Infrastructure
- NETL - Net Lease REITs

### Technology
- SMH - Semiconductors
- IGV - Software
- HACK - Cybersecurity

### Utilities
- RNRG - Renewable Power Producers
- RYU - Equal-Weight Utilities

For subsectors the engine evaluates:

- 1-day return
- 5-day return
- 20-day drawdown
- 60-day drawdown
- 20-day relative strength vs SPY
- 60-day relative strength vs SPY
- 20-day relative strength vs parent sector
- 60-day relative strength vs parent sector
- damaged-share measures by parent sector
- repair-share measures by parent sector
- aggregate subsector damage and repair
- hidden damage beneath mild headline sector ETFs

Subsector evidence is decision evidence and explanatory context. It **cannot independently convert WAIT to RE-ENTER** and **cannot veto an otherwise validated broad-market RE-ENTER**. The direct subsector promotion candidate was historically tested and rejected.

## 4. Factor and rotation layer

Factor proxies:

- MTUM - Momentum
- QUAL - Quality
- VLUE - Value
- IWF - Growth
- IWD - Value style comparison
- USMV - Minimum Volatility
- SPYD - High Dividend
- IWM - Small Cap / Small vs Large

Factor measurements include:

- 20-day drawdown
- 60-day drawdown
- 20-day relative strength vs SPY
- 60-day relative strength vs SPY
- factor damage breadth
- factor repair breadth
- factor dispersion
- median daily factor behavior

Rotation / leadership evidence includes:

- Momentum relative to SPY
- Quality minus Momentum
- Growth minus Value
- Small vs Large

The engine can identify states including momentum reset, growth reset, quality leadership, and small-vs-large reset.

## 5. Historical analog layer

- 40 nearest **prior-only** historical market states
- no future information is used in the daily decision
- decision labels: `NO`, `CAUTIOUS YES`, `YES`, `STRONG YES`
- SPY and QQQ forward evidence at 5, 7, 10, 15, 30, and 60 trading days
- return, positive-rate, and adverse-excursion evidence
- historical validation assumes next-session execution and 10 bps round-trip friction

## 6. Canonical decision logic

### Broad weakness path

When validated broad weakness exists:

- `CAUTIOUS YES`, `YES`, or `STRONG YES` analog -> `RE-ENTER`
- `NO` analog -> `WAIT`

### Internal-only path

When headline SPY weakness is shallow, internal sector/factor damage can still create a setup.

A meaningful stabilized internal reset plus `YES` or `STRONG YES` analog support can produce `RE-ENTER` even when the headline market has not crossed the broad weakness thresholds.

A developing internal reset produces `WAIT` rather than being ignored.

### Early-entry extension

The engine intentionally prefers being slightly early rather than waiting for perfect confirmation.

A developing, meaningful, or broad internal reset may produce `RE-ENTER` when:

- aggregate selling pressure is `STABILIZING` or `REPAIRING`, and
- the historical analog decision is favorable

This is the validated early-entry extension. Subsector repair alone is not sufficient.

## 7. Persistence

`REENTRY_WINDOW_SESSIONS = 0`

A RE-ENTER signal is not mechanically carried forward. The engine reevaluates the entire state after every completed market session.

## 8. Freshness and fail-closed behavior

The current decision is valid only when all required market, breadth, sector, factor, and required subsector data resolve to the latest completed U.S. equity session.

If `data_freshness.same_day_complete` is false, the product must suppress the current decision and display `DATA INCOMPLETE`.

The engine must not treat an unfinished same-day daily bar as a completed close.

## 9. Output contract

The canonical snapshot exposes at minimum:

- signal
- signal interpretation
- setup source
- market damage
- internal reset
- selling pressure
- factor leadership state
- analog decision and interpretation
- weakness reasons
- current inputs
- sector/factor signal snapshot
- subsector intelligence
- subsector decision evidence
- market commentary
- 40 historical analogs
- 5/7/10/15/30/60D SPY and QQQ evidence
- data freshness

## 10. Frozen research decisions

The following are intentionally **not** part of the engine:

- no fitted black-box composite score
- no RSI / MACD / stochastic trigger
- no arbitrary position sizing
- no automatic buy/sell execution
- no forced short-horizon exit rule
- no subsector-only WAIT -> RE-ENTER override
- no multi-session RE-ENTER persistence window

Changes to any signal, threshold, proxy universe, decision mapping, or persistence behavior require new historical validation before promotion.
