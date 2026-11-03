-- Phase 2 of the timezone work: an absolute (UTC) moment for each transaction.
-- Run once in the Supabase SQL editor. Safe to re-run.
--
-- occurred_at : when the spend happened, stored as an absolute instant.
-- time_known  : true only when the real time of day was read (e.g. from a bank
--               alert body). False means occurred_at is an estimate (logging
--               time, or noon on the stated day) and must not be trusted for
--               minute-level matching.
alter table public.transactions
  add column if not exists occurred_at timestamptz,
  add column if not exists time_known boolean not null default false;

-- Existing rows only have a date. Interpret them as noon Lagos time (UTC+1,
-- no daylight saving), flagged as an estimate.
update public.transactions
set occurred_at = ((occurred_on::timestamp + interval '12 hours') at time zone 'Africa/Lagos')
where occurred_at is null
  and occurred_on is not null;

create index if not exists transactions_user_occurred_at_idx
  on public.transactions (user_id, occurred_at desc);
