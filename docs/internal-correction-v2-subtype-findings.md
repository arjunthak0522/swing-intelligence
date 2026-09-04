# Internal Correction V2 - subtype decomposition findings

Status: RESEARCH ONLY. Do not merge to main or change `reentry_v1.0` production behavior.

Data caveat: Sector and factor histories use liquid ETF proxies and are not proprietary point-in-time factor-index constituent histories. QQQ-specific research additionally uses free ETF proxies including XLK, SMH, MTUM, IWF, RSP, and RSPT where history is available. RSPT has shorter history.

## Executive conclusion

V2 is not one homogeneous timing signal. The research supports using cross-sectional internal damage primarily as a SUPPORTING re-entry context layer, especially for hidden / rolling corrections and 15-60 trading-day backdrop. V1 should remain the CORE broad-market short-term timing layer.

The strongest evidence is not a generic factor reset. It is the combination of broad cross-sectional damage and/or high dispersion followed by stabilization.

## Strongest findings

### 1. Sector + factor damage together - strongest confirmation subtype
- 48 events, but only 2 were V1-missed. This is primarily confirmation of already-visible weakness rather than discovery of hidden setups.
- SPY median forward returns: +1.16% 5D, +1.72% 7D, +2.26% 10D, +1.96% 15D, +3.89% 30D, +5.47% 60D.
- QQQ median forward returns: +1.28% 5D, +1.73% 7D, +2.29% 10D, +2.17% 15D, +4.26% 30D, +6.32% 60D.
- Matched-control median advantage is positive at every horizon for both SPY and QQQ. SPY 30D advantage is about +1.50 percentage points and its bootstrap interval is positive in this run.
- Classification: SUPPORTING confirmation layer. Do not make it a separate trigger.

### 2. High-dispersion / rotation reset - strongest hidden-reset discovery subtype
- 44 events, 28 missed by V1.
- SPY median: +0.77% 10D, +1.75% 15D, +3.37% 30D, +5.29% 60D.
- QQQ median: +1.13% 10D, +2.10% 15D, +3.24% 30D, +5.87% 60D.
- Matched-control median advantages are positive across all tested horizons in this run, including SPY +2.51 pp and QQQ +1.71 pp at 30D.
- The V1-missed subset retained constructive 30D outcomes: SPY median about +2.55%, QQQ about +3.37%.
- Classification: strongest SUPPORTING candidate for rolling/internal correction detection.

### 3. Sector-only correction - useful but less clean at 60D
- 49 events, 15 missed by V1.
- SPY 30D median +4.36%, QQQ +3.68%.
- 30D matched advantages are positive for both assets, but 60D matched advantages turn slightly negative.
- Classification: SUPPORTING for 10-30D context, not a standalone long-horizon signal.

### 4. Momentum vs Quality rotation - useful medium-horizon context
- 43 events, 30 missed by V1.
- Short-term edge is modest, but 15-60D matched advantage improves, especially for QQQ.
- QQQ matched median advantage: about +1.58 pp at 15D, +1.54 pp at 30D, +4.57 pp at 60D.
- Classification: SUPPORTING context for factor reset / rotation, especially QQQ backdrop, not exact-day timing.

### 5. Concentration correction - useful hidden-reset context
- 57 events, 29 missed by V1.
- Positive matched-control median advantage across tested horizons for both SPY and QQQ.
- Raw 30D medians: SPY +1.99%, QQQ +2.26%.
- QQQ 60D matched advantage is strong in this run, about +4.10 pp.
- Classification: SUPPORTING, but keep wording conservative because the proxy definition is imperfect.

## Promising but not ready

### Factor-only correction
- Exceptional raw results, but only 11 events with just 2 events in 2016-2020 and 3 V1-missed events.
- Too sparse to promote despite very strong numbers.
- Classification: EXPERIMENTAL.

### Momentum unwind
- 66 events, 34 missed by V1.
- Raw medium-term outcomes are constructive, but matched 5-10D advantage is slightly negative and 30D matched edge is modest.
- Classification: SUPPORTING only as a medium-term context input inside a broader reset, not as an independent trigger.

### Growth vs Value rotation
- 61 events, 36 missed by V1.
- 5-10D results are weak / mixed and matched controls are mostly negative until around 30D.
- Classification: EXPERIMENTAL as an independent subtype. It can still describe factor state in the synthesis output.

### QQQ-specific internal correction prototype
- 69 events, 35 missed by V1.
- Raw outcomes are constructive, but the current matched-control definition does not show incremental 30D advantage. QQQ 30D matched advantage is negative in this run.
- Classification: EXPERIMENTAL. The QQQ layer needs a better Nasdaq-specific control set and likely separate calibration rather than simply combining generic broad-market variables.

### Leadership reset
- 29 events, only 7 missed by V1.
- Raw outcomes look acceptable, but matched 30D and 60D advantages are negative for both SPY and QQQ.
- Classification: EXPERIMENTAL. Do not promote.

## Threshold robustness

The broad internal-reset family was tested across 81 nearby combinations of:
- sector count 3 / 4 / 5
- factor count 2 / 3 / 4
- drawdown threshold 2% / 3% / 4%
- cooldown 5 / 10 / 15 sessions

All 81 combinations retained positive 30D median outcomes for both SPY and QQQ.

Across those 81 variants:
- SPY 30D median ranged roughly +2.57% to +6.02%, median about +3.66%.
- QQQ 30D median ranged roughly +2.62% to +6.62%, median about +3.97%.
- SPY 30D positive rate ranged about 67.7% to 90.9%.
- QQQ 30D positive rate ranged about 66.0% to 77.3%.

This is strong evidence that the broad V2 family is not dependent on one magical threshold.

## What the research says about horizons

### 5-15 trading days
V1 remains the cleaner CORE timing layer. The V2 subtypes are inconsistent enough at short horizons that they should not independently override V1.

The exception is sector + factor confirmation, which shows good short-horizon behavior, but it usually overlaps V1 rather than finding hidden setups.

### 15-60 trading days
V2 adds the most value here. High dispersion, cross-sectional sector damage, momentum-quality rotation, and concentration/broadening patterns are useful for identifying when meaningful risk has already been wrung out below the headline index surface.

## Recommended hierarchy

### CORE
- Existing V1 broad-market weakness / stabilization logic.
- Existing historical analog framework where already validated.

### SUPPORTING
- High-dispersion / rotation internal reset.
- Sector + factor confirmation.
- Sector correction with stabilization.
- Momentum vs Quality rotation as medium-horizon context.
- Concentration / broadening correction as medium-horizon context.
- Generic V2 internal-correction family for 15-60D backdrop.

### EXPERIMENTAL
- Factor-only correction due to sample size.
- Growth vs Value rotation as an independent trigger.
- Leadership reset.
- Current QQQ-specific prototype until matched controls are redesigned.
- Any individual subtype threshold promoted in isolation.

## Exact next implementation step

Build a research-only V1 + V2 synthesis state machine without changing production decisions.

The synthesis should expose two separate axes:

1. Short-term timing - driven primarily by V1.
2. Medium-term internal-reset backdrop - driven by V2 SUPPORTING evidence.

Recommended research-state logic:

- Broad weakness + V1 stabilization + meaningful internal reset -> stronger RE-ENTER confirmation.
- Shallow/no broad weakness + high-dispersion or sector internal reset + stabilization -> ROLLING CORRECTION / DEVELOPING RE-ENTRY candidate.
- Broad weakness + internal deterioration -> WAIT.
- No broad weakness + no meaningful internal reset -> NO RE-ENTRY SETUP.
- Factor-only or leadership-only reset without sector confirmation -> DEVELOPING SETUP only, never a hard trigger.

Do not create a black-box score. Keep the evidence fields explicit.

The next backtest must compare:
- frozen V1 decisions
- V1 + V2 confirmation
- V1-missed hidden resets captured by V2
- full synthesis decisions

Success requires preserving V1 broad-correction behavior while adding hidden rolling-correction opportunities without materially increasing false positives or firing constantly.
