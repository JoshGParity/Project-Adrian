-- Each activity's heart-rate zone floors, from its file. Applied Nov 24, 2026.
alter table public.user_day_activity
  add column zone1_floor_bpm integer,
  add column zone2_floor_bpm integer,
  add column zone3_floor_bpm integer,
  add column zone4_floor_bpm integer,
  add column zone5_floor_bpm integer;
