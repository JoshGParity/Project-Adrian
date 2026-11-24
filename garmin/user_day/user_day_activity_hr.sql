-- Heart rate for each minute of each activity. Applied Nov 24, 2026.
create table public.user_day_activity_hr (
  activity_id bigint not null,
  minute integer not null,
  heart_rate integer,
  pulled_at timestamptz not null default now(),
  primary key (activity_id, minute)
);
