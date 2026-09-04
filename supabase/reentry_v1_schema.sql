-- RE-ENTRY V1 persistence blueprint.
-- Dedicated standalone database only. Do not apply to REVEAL.

create table if not exists public.reentry_daily_snapshots (
    as_of date primary key,
    engine_version text not null,
    schema_version text not null,
    signal text not null check (signal in ('RE-ENTER', 'WAIT', 'NO RE-ENTRY SETUP')),
    analog_decision text not null check (analog_decision in ('NO', 'CAUTIOUS YES', 'YES', 'STRONG YES')),
    market_state text not null,
    weakness_present boolean not null,
    payload_hash text not null,
    payload jsonb not null,
    created_at timestamptz not null default now()
);

create unique index if not exists reentry_daily_snapshots_payload_hash_idx
    on public.reentry_daily_snapshots (payload_hash);
create index if not exists reentry_daily_snapshots_created_at_idx
    on public.reentry_daily_snapshots (created_at desc);

create table if not exists public.reentry_analogs (
    signal_date date not null references public.reentry_daily_snapshots(as_of) on delete cascade,
    rank integer not null check (rank between 1 and 40),
    analog_date date not null,
    distance double precision not null check (distance >= 0),
    engine_version text not null,
    primary key (signal_date, rank)
);
create index if not exists reentry_analogs_analog_date_idx
    on public.reentry_analogs (analog_date);

create table if not exists public.reentry_realized_outcomes (
    signal_date date not null references public.reentry_daily_snapshots(as_of) on delete cascade,
    engine_version text not null,
    symbol text not null check (symbol in ('SPY', 'QQQ')),
    horizon integer not null check (horizon in (5, 7, 10, 15, 30, 60)),
    entry_date date not null,
    exit_date date not null check (exit_date >= entry_date),
    entry_close double precision not null check (entry_close > 0),
    exit_close double precision not null check (exit_close > 0),
    realized_return double precision not null,
    max_drawdown double precision not null check (max_drawdown <= 0),
    max_favorable_excursion double precision not null check (max_favorable_excursion >= 0),
    round_trip_cost double precision not null check (round_trip_cost >= 0),
    created_at timestamptz not null default now(),
    primary key (signal_date, symbol, horizon)
);
create index if not exists reentry_realized_outcomes_exit_date_idx
    on public.reentry_realized_outcomes (exit_date desc);

alter table public.reentry_daily_snapshots enable row level security;
alter table public.reentry_realized_outcomes enable row level security;
alter table public.reentry_analogs enable row level security;

-- Intentionally no public table policies. The public-facing app reads through the
-- reentry-read Edge Function. Scheduled writes go through reentry-ingest and are
-- authenticated with GitHub Actions OIDC, so no long-lived Supabase write secret is
-- stored in GitHub or Vercel.
