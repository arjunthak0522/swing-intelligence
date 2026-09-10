# RE-ENTRY post-freeze cutover checklist

This checklist is the only approved path from the current Vercel freeze to a production cutover.

## Freeze state

- Production remains untouched.
- Research branch: `intraday-signal-research`.
- Primary decision engine: `REENTRY_UNIFIED_v1`.
- Official user-facing states: `WAIT`, `WATCH`, `GO_EARLY`.
- Do not reintroduce the retired completed-close model, analog vote, CAUTIOUS YES/YES/STRONG YES terminology, separate intraday trading decision, position sizing, sell logic, or random technical indicators.

## Must be true before any deployment

1. GitHub Freeze QA is green for both Python regression tests and the local Next.js build.
2. Scheduled unified prospective capture has produced fresh rows in `data/reentry/unified_snapshot_ledger.csv`.
3. The latest `data/reentry/exhaustion_intraday_current.json` contains:
   - `snapshot_version`
   - `unified_engine`
   - `market_prices`
   - `data_quality`
   - `sources`
   - `prospective_history`
4. `unified_engine.engine_version` is exactly `REENTRY_UNIFIED_v1` unless an explicitly researched and approved version change has occurred.
5. `unified_engine.decision` is one of `WAIT`, `WATCH`, `GO_EARLY`.
6. A degraded data-quality state must suppress actionable presentation rather than substituting a legacy decision.
7. SKEW fallback must use only the last valid same-session proxy and must never compare a new session against the prior session's live proxy.
8. Market prices for SPY, QQQ and VIX are display context only and must not alter the unified decision.
9. Prospective research reports must remain labeled research-only and must not feed the production decision.
10. CPCE must remain research-only until an incremental-value study is completed and explicitly approved.

## Production dashboard acceptance test

The first screen must answer one question: should cash remain sidelined or begin going back into SPY/QQQ?

Required visible hierarchy:

1. One large decision: WAIT, WATCH or GO EARLY.
2. One phase label: LIVE - PROVISIONAL, CLOSE SETTLING or MARKET CLOSED - FINAL.
3. One plain-English explanation of why the decision exists.
4. Oversold gate status.
5. Fast reversal family count out of 4.
6. Context family count out of 4.
7. All eight decision families underneath with raw values and active/inactive state.
8. Current SPY, QQQ and VIX move shown as context only.
9. Data reliability status and explicit degraded-data warning when applicable.
10. Prospective validation shown below the operational decision and clearly separated from the engine.

The production page must not render:

- RE-ENTER
- NO RE-ENTRY SETUP
- CAUTIOUS YES
- YES / STRONG YES
- analog decision
- market-damage vote
- sector/factor vote
- subsector vote
- a second intraday decision engine

## Pre-deploy verification sequence

1. Run the unified engine manually during the valid refresh window.
2. Confirm a new canonical ledger row is written with all eight family flags, decision, quality status and SPY/QQQ prices.
3. Confirm the whipsaw, persistence-shadow and forward-outcome research suite runs without modifying the unified snapshot decision.
4. Confirm the CPCE workflow writes only its separate research files.
5. Run Freeze QA again.
6. Review the research-branch page using a local/CI build only. Do not use Vercel as a debugging loop.
7. Compare the rendered page against the latest canonical JSON and verify every displayed decision-family state matches the source object.
8. Only after the above passes, create the production deployment candidate.

## Deployment rule

Do not deploy automatically when the freeze ends. Deployment requires an explicit user instruction to deploy.

When deployment is approved:

1. Freeze the exact research-branch commit SHA that passed QA.
2. Merge or promote only the validated files required for the unified production experience.
3. Do not merge unrelated research experiments simply because they live on the same branch.
4. Run the same regression and web-build checks on the deployment candidate.
5. Deploy once.
6. Perform a rendered production smoke test against the canonical JSON.
7. If a defect is found, diagnose locally/CI first and issue one corrected deployment. Do not enter a Vercel trial-and-error loop.

## Research promotion rule

No persistence, hysteresis, session-extreme, magnitude, CPCE, NASI-bootstrap, or other research variant may be promoted because it looks cleaner or produces fewer state flips.

Promotion requires evidence that the candidate improves the actual product objective relative to `REENTRY_UNIFIED_v1`: earlier useful re-entry with acceptable false-start risk. At minimum compare SPY and QQQ forward returns, positive rate, maximum adverse excursion, maximum favorable excursion, entry delay and missed rebound upside.

## Definition of done

RE-ENTRY is operationally complete when the user can open one production page during market hours, see a fresh single-engine decision no more than the intended refresh interval old, understand which of the eight families caused it, see whether the data are reliable, and after the close see the same engine settle into a final state without another model taking over.
