-- RE-ENTRY V1 persistence blueprint.
-- This file is intentionally NOT applied to the existing REVEAL Supabase project.
-- Use it when a dedicated standalone RE-ENTRY project is provisioned.

create table if not exists public.reentry_daily_snapshots (
    as_of date primary key,
    engine_version text not null,
    schema_version text not null,
    signal text not null check (signal in ('RE-ENTER', 'WAIT', 'NO RE-ENTRY SETUP')),
    analog_decision text not null check (analog_decision in ('NO', 'CAUTIOUS YES', 'YES', 'STRONG YES')),
    market_state text not null,
    weakness_present boolean not null,
    payload jsonb not null,
    created_at timestamptz not null default now()
);

create index if not exists reentry_daily_snapshots_created_at_idx
    on public.reentry_daily_snapshots (created_at desc);

create table if not exists public.reentry_realized_outcomes (
    signal_date date not null references public.reentry_daily_snapshots(as_of) on delete cascade,
    engine_version text not null,
    symbol text not null check (symbol in ('SPY', 'QQQ')),
    horizon integer not null check (horizon in (5, 7, 10, 15, 30, 60)),
    entry_date date not null,
    exit_date date not null,
    entry_close double precision not null,
    exit_close double precision not null,
    realized_return double precision not null,
    max_drawdown double precision not null,
    max_favorable_excursion double precision not null,
    round_trip_cost double precision not null,
    created_at timestamptz not null default now(),
    primary key (signal_date, symbol, horizon)
);

create table if not exists public.reentry_analogs (
    signal_date date not null references public.reentry_daily_snapshots(as_of) on delete cascade,
    rank integer not null check (rank between 1 and 40),
    analog_date date not null,
    distance double precision not null,
    engine_version text not null,
    primary key (signal_date, rank)
);

alter table public.reentry_daily_snapshots enable row level security;
alter table public.reentry_realized_outcomes enable row level security;
alter table public.reentry_analogs enable row level security;

-- No public policies are created here. The standalone app should expose reads through
-- its server layer, and scheduled engine writes should use server-side credentials only.
