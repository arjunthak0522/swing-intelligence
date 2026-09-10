# RE-ENTRY freeze readiness status

Status date: 2026-09-10
Branch: `intraday-signal-research`
Production branch: `main` - untouched during Vercel freeze

## Operational architecture

- One operational engine: `REENTRY_UNIFIED_v1`
- Operational states: `WAIT`, `WATCH`, `GO EARLY`
- Same engine intraday and post-close
- Intraday phase: `LIVE_PROVISIONAL`
- Close-settling phase: `CLOSE_SETTLING`
- Final phase: `MARKET_CLOSED_FINAL`
- No legacy decision substitution is allowed
- No CPCE threshold is in the operational engine
- No persistence/hysteresis variant is in the operational engine

## Completed during freeze

- Unified engine truth-table regression tests
- SKEW same-session fallback/comparison repair and regression test
- Canonical unified snapshot finalizer
- Data-quality state: `OK | PARTIAL | DEGRADED`
- Fail-closed dashboard behavior for degraded/missing canonical data
- Per-symbol StockCharts provenance preservation for timestamp/realtime/cached status
- Exact fast-family and context-family audit trail in unified history
- Immutable prospective unified snapshot ledger
- SPY/QQQ/VIX display-only market context, explicitly not a decision input
- 15-minute prospective point-in-time capture workflow
- Daily exhaustion context capture reduced to only the feed needed by the unified engine
- Legacy scheduled washout/model-comparison/outcome/reliability chain removed from the daily operational schedule
- Prospective whipsaw analyzer
- 2-snapshot and 3-snapshot persistence shadow variants
- Forward outcome tracker for 1/3/5/10/15/30/60 sessions and adverse/favorable excursion
- CPCE research-only prospective feed
- NASI bootstrap diagnostic changed to fail closed when older-year source history is incomplete
- Research-branch dashboard converted to one-engine presentation
- Frontend architecture regression test preventing legacy decision-loader reintroduction
- Vercel-free local Next.js production build in GitHub Actions
- Updated unified snapshot API/consumer contract
- Controlled post-freeze cutover checklist

## Verified workflows

Verified successful during the freeze:

- RE-ENTRY Freeze QA
- RE-ENTRY Unified Research Suite
- RE-ENTRY NASI Bootstrap Diagnostic
- RE-ENTRY Daily Context Capture

A successful workflow run proves that the checked code path executed successfully. It does not substitute for future open-market rendered QA or prospective statistical evidence.

## Intentionally unresolved until more evidence exists

These are not engineering blockers and must not be filled with invented results:

1. Whether one-snapshot `GO EARLY` is too noisy in the unified engine.
2. Whether 2-snapshot or 3-snapshot confirmation improves the false-start/upside-missed tradeoff.
3. Whether turn-from-session-extreme is superior to immediate-previous-snapshot direction.
4. Whether a minimum movement magnitude adds value.
5. Whether CPCE adds independent predictive value after the existing eight families are known.
6. Mature SPY/QQQ forward outcomes after future unified `GO EARLY` events.
7. A legitimate multi-year point-in-time reconstruction of the exact unified intraday engine where raw historical internals are unavailable.

## Remaining Vercel-blocked work

Only after the freeze is explicitly lifted:

- create one preview from the fully QA'd research branch
- compare every rendered family/value/count/status against canonical JSON from the same timestamp
- perform closed-market rendered QA
- perform open-market rendered QA across multiple snapshots
- nominate one exact production candidate commit
- rerun QA on that commit
- deploy once
- perform production smoke test

Do not use Vercel as a debugging loop.

## Definition of usable

RE-ENTRY is usable when a user can open one screen and immediately see:

- exactly one `WAIT / WATCH / GO EARLY` decision
- whether it is provisional or final
- whether the data is trustworthy
- the four fast-family states
- the four context-family states
- current SPY/QQQ context
- the reason the current state was produced
- point-in-time prospective evidence clearly separated from retired-model historical research

## Promotion discipline

Any future change to thresholds, persistence, hysteresis, magnitude rules, session-extreme rules, or CPCE must be promoted only after evidence supports it. Preserve v1 history and create a new engine version for any strategy-policy change.
