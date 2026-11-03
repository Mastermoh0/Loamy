-- Phase 1 of the timezone work: one IANA timezone name per user.
-- Run once in the Supabase SQL editor. Existing users keep behaving as Lagos time.
alter table public.users
  add column if not exists timezone text not null default 'Africa/Lagos';
