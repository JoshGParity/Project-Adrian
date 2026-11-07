create table public.keepalive_pings (
  id bigint generated always as identity primary key,
  pinged_at timestamptz not null default now(),
  status_code integer,
  latency_ms integer not null
);
