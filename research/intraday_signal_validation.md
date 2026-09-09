# RE-ENTRY intraday signal validation - research only

Generated: 2026-09-09T16:03:20.032271+00:00

**No frozen RE-ENTRY signal logic is changed by this research.**

Recent 5-minute sample: **2026-06-15 through 2026-09-09**, covering **10 reconstructed RE-ENTRY starts**.

## Candidate features tested

Index confirmation, sector breadth, subsector breadth, factor breadth, VIX direction, VIX/VIX3M term structure, 30-minute broad-index momentum, and breadth change since 10:30 ET.

## Features that survived the initial directional screen

- **sectors_broad** - favorable subset had higher mean 5D and 10D broad-market forward return at 2 snapshot times with minimum sample checks.
- **subsectors_broad** - favorable subset had higher mean 5D and 10D broad-market forward return at 2 snapshot times with minimum sample checks.
- **vol_easing** - favorable subset had higher mean 5D and 10D broad-market forward return at 3 snapshot times with minimum sample checks.

## Snapshot diagnostics

### 10:30 ET - n=10
- Score 6+ 5D: n=3, mean -0.32%; below 6: n=7, mean +0.52%
- Score 6+ 10D: n=3, mean -2.07%; below 6: n=7, mean +1.46%

### 12:00 ET - n=10
- Score 6+ 5D: n=5, mean -0.16%; below 6: n=5, mean +0.69%
- Score 6+ 10D: n=5, mean +0.68%; below 6: n=5, mean +0.12%

### 13:30 ET - n=10
- Score 6+ 5D: n=5, mean +0.94%; below 6: n=5, mean -0.41%
- Score 6+ 10D: n=5, mean +1.43%; below 6: n=5, mean -0.63%

### 15:00 ET - n=10
- Score 6+ 5D: n=3, mean -0.14%; below 6: n=7, mean +0.44%
- Score 6+ 10D: n=3, mean -1.04%; below 6: n=7, mean +1.01%

## Decision rule for this research pass

A feature is only called an initial survivor if the feature-present subset has a higher mean broad-market 5D **and** 10D return than the feature-absent subset at at least two snapshot times, with at least four observations in each side of the comparison.

## Limitations

- Recent 5-minute vendor history is a small sample and is not point-in-time archived by this project.
- Episode dates come from the reconstructed ledger, not the archived independent-event validator.
- Candidate thresholds are predeclared research heuristics, not validated trading rules.
- Results are descriptive only; no intraday feature is promoted into the official completed-close RE-ENTRY engine by this script.
