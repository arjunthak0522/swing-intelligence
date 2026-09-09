# Intraday survivor robustness check

Window: **2024-09-09 through 2026-09-09**, **85 reconstructed RE-ENTRY starts**.

Hourly-bar **opens** are used at each timestamp so the test does not use information from later inside the hour.

## Robust survivors

- **None.** The initial 60-day findings did not survive the broader hourly robustness screen.

## Snapshot detail

### sectors_broad
- 10:30: 5D present n=40 mean +0.69% vs absent n=44 +0.66%; 10D present n=40 +1.21% vs absent n=44 +0.95%
- 11:30: 5D present n=41 mean +0.52% vs absent n=43 +0.83%; 10D present n=41 +0.99% vs absent n=43 +1.15%
- 13:30: 5D present n=43 mean +0.18% vs absent n=42 +1.14%; 10D present n=43 +0.68% vs absent n=42 +1.38%
- 14:30: 5D present n=45 mean +0.19% vs absent n=40 +1.18%; 10D present n=45 +0.78% vs absent n=40 +1.30%

### subsectors_broad
- 10:30: 5D present n=45 mean +0.51% vs absent n=39 +0.87%; 10D present n=45 +0.68% vs absent n=39 +1.53%
- 11:30: 5D present n=45 mean +0.56% vs absent n=39 +0.81%; 10D present n=45 +1.02% vs absent n=39 +1.14%
- 13:30: 5D present n=41 mean +0.32% vs absent n=44 +0.97%; 10D present n=41 +0.57% vs absent n=44 +1.46%
- 14:30: 5D present n=43 mean +0.22% vs absent n=42 +1.11%; 10D present n=43 +0.49% vs absent n=42 +1.58%

### vol_easing
- 10:30: 5D present n=40 mean +0.79% vs absent n=44 +0.58%; 10D present n=40 +1.28% vs absent n=44 +0.88%
- 11:30: 5D present n=44 mean +0.76% vs absent n=40 +0.59%; 10D present n=44 +1.10% vs absent n=40 +1.05%
- 13:30: 5D present n=42 mean +0.48% vs absent n=43 +0.83%; 10D present n=42 +0.97% vs absent n=43 +1.09%
- 14:30: 5D present n=43 mean +0.37% vs absent n=42 +0.96%; 10D present n=43 +1.01% vs absent n=42 +1.05%

## Important limitation

This is a robustness screen on reconstructed episode dates and mutable vendor history. It is not sufficient by itself to promote an intraday feature into the frozen official RE-ENTRY engine.
