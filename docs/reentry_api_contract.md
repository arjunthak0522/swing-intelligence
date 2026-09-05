# RE-ENTRY canonical API contract

The UI must treat the canonical engine snapshot as authoritative. It must never recompute strategy logic client-side.

The only decision-producing engine is `tools/reentry_engine.py` on the active research branch until an explicit production promotion is approved. Historical `reentry_v1.0` artifacts remain frozen reference evidence and are not an alternate live engine.

## Canonical decision outputs

The UI consumes these engine-owned fields directly:

- `signal`: `RE-ENTER`, `WAIT`, or `NO RE-ENTRY SETUP`
- `signal_interpretation`
- `setup_source`
- `market_damage`
- `internal_reset`
- `selling_pressure`
- `analog_decision`
- `factor_leadership_state`
- `subsector_decision_evidence`
- `market_commentary`
- `data_freshness`

Subsector evidence is part of the canonical snapshot but may not independently promote `WAIT` to `RE-ENTER`. The rejected subsector-only promotion remains research-reproducible only and must never be implemented client-side.

## Public read API

Supabase Edge Function: `reentry-read`

Supported resources:

- `?resource=latest` -> latest full canonical engine snapshot
- `?resource=snapshot&date=YYYY-MM-DD` -> full snapshot for one date
- `?resource=history&limit=N` -> compact daily signal history
- `?resource=analogs&date=YYYY-MM-DD` -> 40 ranked historical analogs
- `?resource=realized&date=YYYY-MM-DD` -> matured realized SPY/QQQ outcomes

The UI must show `DATA INCOMPLETE` and suppress the current decision whenever `data_freshness.same_day_complete` is not true.

## Secure ingest API

Supabase Edge Function: `reentry-ingest`

Production ingest remains disabled for the research branch. When production promotion is explicitly approved, only GitHub Actions OIDC tokens from the approved production branch and audience `reentry-supabase` may write canonical snapshots.

Request body:

```json
{
  "snapshot": { "...": "canonical unified RE-ENTRY snapshot" },
  "realized": { "...": "matured realized outcomes for the same as_of date" }
}
```

Snapshot rows are immutable. A repeated identical payload is idempotent. A different payload for an already-recorded `as_of` date must return HTTP 409 instead of rewriting history.

Realized outcome cells are also immutable once inserted. Missing horizons may be added later as 5/7/10/15/30/60 trading-day outcomes mature.

## Persistence tables

- `reentry_daily_snapshots`
- `reentry_analogs`
- `reentry_realized_outcomes`

RLS remains enabled with no public table policies. Reads and writes go through the Edge Functions, not direct browser table access.
