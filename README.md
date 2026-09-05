# RE-ENTRY - Swing Intelligence

Standalone institutional-grade, retail-friendly SPY/QQQ market re-entry intelligence engine.

Primary question:

**Does it make sense to put cash back into the market right now?**

Canonical research engine: `tools/reentry_engine.py`

Frozen engine specification: `docs/reentry_frozen_engine_contract.md`

API / product integration contract: `docs/reentry_api_contract.md`

The engine combines headline market weakness, true breadth, volatility, all 11 major sectors, factor/rotation evidence, liquid subsector/industry proxies beneath every sector, and 40 prior-only historical analogs. It emits one authoritative state: `RE-ENTER`, `WAIT`, or `NO RE-ENTRY SETUP`.

Research principles:

- no arbitrary composite scoring
- no client-side strategy reconstruction
- no lookahead in daily decisions
- same-day completed-close freshness required
- benchmark-relative historical evidence
- incremental-value validation for new signals
- matched controls, era splits, robustness and timing tests
- parameter stability and bootstrap confidence checks
- SPY and QQQ forward evidence at 5/7/10/15/30/60 trading days
- slightly-early bias only where historically validated
- no automatic position sizing or trade execution

Important frozen decision: subsector intelligence is part of the canonical evidence stack, but subsector repair alone cannot independently promote `WAIT` to `RE-ENTER`.

Production remains frozen until explicit approval.
