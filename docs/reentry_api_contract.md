# RE-ENTRY V1 API contract

The UI must treat the engine snapshot as authoritative. It must never recompute strategy logic client-side.

## Public read API

Supabase Edge Function: `reentry-read`

Supported resources:

- `?resource=latest` -> latest full canonical engine snapshot
- `?resource=snapshot&date=YYYY-MM-DD` -> full snapshot for one date
- `?resource=history&limit=N` -> compact daily signal history
- `?resource=analogs&date=YYYY-MM-DD` -> 40 ranked historical analogs
- `?resource=realized&date=YYYY-MM-DD` -> matured realized SPY/QQQ outcomes

The UI should show `DATA INCOMPLETE` and suppress the current decision whenever `data_freshness.same_day_complete` is not true.

## Secure ingest API

Supabase Edge Function: `reentry-ingest`

Only GitHub Actions OIDC tokens from `arjunthak0522/swing-intelligence`, branch `main`, audience `reentry-supabase` are accepted.

Request body:

```json
{
  "snapshot": { "...": "canonical reentry_v1.0 snapshot" },
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
