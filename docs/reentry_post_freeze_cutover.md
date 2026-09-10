# RE-ENTRY post-freeze cutover checklist

This checklist is the only approved path from `intraday-signal-research` to production after the Vercel freeze is lifted.

## 1. Freeze-exit prerequisites

Do not start a Vercel preview until all are true:

- `REENTRY_UNIFIED_v1` remains the only operational engine.
- GitHub Actions freeze QA is green.
- Unified prospective capture workflow is enabled and writing point-in-time evidence.
- Unified research suite is green.
- NASI bootstrap diagnostic is not falsely reporting incomplete history as valid multi-year validation.
- No production threshold has been added for CPCE.
- Main production branch has not been modified during the freeze.

## 2. Pre-preview branch review

Confirm the research branch page:

- imports `unifiedReentry`, not the legacy decision loader
- exposes only `WAIT`, `WATCH`, and `GO EARLY`
- shows `LIVE - PROVISIONAL`, `CLOSE SETTLING`, or `MARKET CLOSED - FINAL`
- shows all four fast families and all four context families
- shows `DATA DEGRADED` when data quality is degraded
- does not substitute a retired decision when the unified snapshot is missing
- labels SPY/QQQ/VIX price data as context only
- keeps CPCE and persistence variants in research only

## 3. First Vercel preview

Create one preview from the fully QA'd research branch. Do not use iterative Vercel deploys as the debugging loop.

Validate the rendered page against the exact canonical JSON from the same timestamp:

- decision matches
- market phase matches
- oversold gate matches
- fast family count matches
- context support count matches
- each individual family state matches
- raw values match
- MMFD coverage matches
- data-quality status matches
- source/freshness wording is accurate

Any mismatch blocks production.

## 4. Closed-market rendered QA

Verify:

- final state is labeled `MARKET CLOSED - FINAL`
- page does not imply quotes are live when they are not
- SKEW uses the last valid same-session live proxy when appropriate
- official Cboe SKEW is not mislabeled as the live skew proxy
- no stale prior-session proxy is presented as current-session evidence

## 5. Open-market rendered QA

On a regular session, validate at multiple snapshots:

- update cadence is consistent with the scheduled capture cadence
- page timestamp changes with the canonical snapshot
- family flips appear exactly when the engine history records them
- the UI does not recompute or smooth the signal independently
- `LIVE - PROVISIONAL` remains visibly distinct from final close status

## 6. Production candidate

Only after both closed-market and open-market preview QA pass:

- identify one exact research-branch commit as the production candidate
- rerun freeze QA against that commit
- do not add unrelated UI or strategy changes
- merge/cut over once

## 7. Production smoke test

Immediately verify:

- production loads the same canonical decision as the candidate
- no legacy decision panels remain
- no old historical evidence is represented as unified-engine validation
- mobile and desktop render the same decision and family counts
- degraded-data behavior works

## 8. Rollback rule

If production differs from the canonical snapshot or a critical data-quality gate fails unexpectedly, roll back the frontend deployment. Do not alter `REENTRY_UNIFIED_v1` thresholds as an emergency UI fix.

## 9. Strategy-change rule

Persistence, hysteresis, magnitude filters, turn-from-session-extreme logic, or CPCE can only enter a future engine version after prospective evidence supports the change. Preserve v1 history and label the promoted engine with a new version.
