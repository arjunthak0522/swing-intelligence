# Swing Intelligence

Standalone institutional-grade, retail-friendly SPY/QQQ swing research engine.

Research principles:
- no arbitrary composite scoring
- benchmark-relative historical edge
- strict no-lookahead execution
- validation and untouched holdout gates
- walk-forward evidence
- parameter stability
- bootstrap confidence intervals and multiple-testing control
- SPY / QQQ / CASH selection only when evidence qualifies

The GitHub Actions workflow uses the repository secret `TWELVE_DATA_API_KEY` to fetch provenance-checked market history and run the real signal tournament.
