# Internal Correction Intelligence V2 — frozen research protocol

Status: research only. This document does not modify `reentry_v1.0` production logic.

## Question

When SPY has only shallow headline weakness, can cross-sectional sector and factor damage plus stabilization identify attractive SPY/QQQ re-entry environments that V1 misses?

Secondary question: inside V1 weakness episodes, does cross-sectional information improve timing or tail risk rather than merely add noise?

## Data families

### Existing V1 inputs
- SPY 20-session drawdown
- SPY 5-session return
- S&P 500 breadth above 50DMA and 200DMA
- 1D/3D breadth repair
- VIX 5D change
- VIX/VIX3M

### Sector proxies
- XLC Communication Services
- XLY Consumer Discretionary
- XLP Consumer Staples
- XLE Energy
- XLF Financials
- XLV Health Care
- XLI Industrials
- XLB Materials
- XLRE Real Estate
- XLK Technology
- XLU Utilities

### Factor proxies
- MTUM Momentum
- QUAL Quality
- VLUE Value
- IWF Growth
- IWD Value style
- USMV Low volatility
- SPYD High dividend
- IWM Size / small-cap proxy

These are liquid ETF proxies, not proprietary point-in-time factor-index histories. Research results must be labeled accordingly.

## Candidate cross-sectional features
For each sector/factor proxy:
- drawdown from 20D high
- drawdown from 60D high
- 1D, 5D, 20D return
- 20D and 60D relative return versus SPY

Aggregate features:
- count of sectors down at least 3% from 20D high
- count of sectors down at least 5%
- count of damaged sectors repairing (5D return > 0)
- sector 20D return dispersion
- count of factors down at least 3% from 20D high
- count of damaged factors repairing
- factor 20D return dispersion
- MTUM relative drawdown versus SPY
- IWF minus IWD 20D relative performance
- QUAL minus MTUM 20D relative performance
- RSP/SPY-style breadth proxy remains separate from true breadth

## Frozen primary definition before results

### Shallow headline surface
SPY drawdown from 20D high > -3%.

### Internal damage candidate
At least one of:
1. 4+ sectors are at least 3% below their 20D highs, or
2. 3+ factor proxies are at least 3% below their 20D highs, or
3. sector 20D return dispersion is in the trailing 80th percentile or higher AND at least 3 sectors are below their 20D highs by 2%+.

### Stabilization
At least one of:
1. 2+ damaged sectors have positive 5D returns, or
2. 2+ damaged factor proxies have positive 5D returns, or
3. sector median 1D return > 0 and factor median 1D return > 0.

### Primary internal-correction event
Shallow headline surface + internal damage + stabilization.

Signals are de-duplicated with a 10-session cooldown for primary event statistics.

## Outcomes
Entry: next session close after the signal date.
Round-trip modeled cost: 10 bps.
Horizons: 5, 7, 10, 15, 30, 60 trading days.
For SPY and QQQ report:
- n
- median/mean forward return
- positive rate
- p25/p10 final return
- close-to-close MAE and MFE
- median MAE
- p10 MAE
- worst MAE

## Comparisons
1. Internal-correction events vs all shallow-surface dates.
2. Internal-correction events that occur while V1 `weakness_present == false` vs other V1-missed shallow dates.
3. Within V1 weakness episodes, compare dates with internal stabilization vs dates without it.
4. Era split: 2016–2020 vs 2021–present.
5. Threshold robustness without optimization:
   - sector damage count 3 / 4 / 5
   - factor damage count 2 / 3 / 4
   - drawdown threshold 2% / 3% / 4%
   - cooldown 5 / 10 / 15 sessions

## Promotion rule
Do not alter V1 unless the cross-sectional layer:
- adds a meaningful number of independent V1-missed episodes,
- has positive forward medians and at least 55% positive outcomes in both eras for the primary short horizons,
- is not dependent on one narrow threshold choice,
- does not materially worsen MAE/tail behavior,
- and demonstrates incremental information beyond a simple shallow-SPY trigger.

No feature may be promoted simply because it looks intuitive or because one in-sample threshold performs well.
