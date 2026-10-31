-- 006_layer2_layer3_memory.sql
-- Schema for Layer 2 (durable user facts + per-user vendor memory) and
-- Layer 3 (full-history transaction search with original currency / channel).
-- Run once in the Supabase SQL Editor. Safe to re-run (idempotent).
--
-- IMPORTANT: there is no separate `user_facts` table. user_memory.py stores each
-- fact as a row in public.vector_embeddings with collection = 'user_facts', so the
-- vector table from 004 is the table. This script makes sure that table, its
-- vector extension and the match_documents() search function exist, then adds the
-- indexes and columns the new code relies on.

-- 1. pgvector + vector table (same definition as 004; no-op if 004 already ran) --
create extension if not exists vector;

create table if not exists public.vector_embeddings (
    id          bigint generated always as identity primary key,
    collection  text        not null,
    doc_id      text        not null,
    user_id     text,
    content     text        not null default '',
    metadata    jsonb       not null default '{}'::jsonb,
    embedding   vector(768),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    constraint vector_embeddings_collection_doc_id_key unique (collection, doc_id)
);

create index if not exists vector_embeddings_collection_user_idx
    on public.vector_embeddings (collection, user_id);

create index if not exists vector_embeddings_metadata_gin_idx
    on public.vector_embeddings using gin (metadata jsonb_path_ops);

create index if not exists vector_embeddings_embedding_hnsw_idx
    on public.vector_embeddings using hnsw (embedding vector_cosine_ops);

alter table public.vector_embeddings enable row level security;

-- 2. Semantic search used by user_memory.facts_for_prompt (needs user_id + collection filters) --
create or replace function public.match_documents(
    query_embedding vector(768),
    match_threshold float default 0.0,
    match_count     int   default 5,
    p_user_id       text  default null,
    p_collection    text  default null
)
returns table (
    doc_id      text,
    collection  text,
    user_id     text,
    content     text,
    metadata    jsonb,
    similarity  float
)
language sql
stable
as $$
    select
        v.doc_id,
        v.collection,
        v.user_id,
        v.content,
        v.metadata,
        1 - (v.embedding <=> query_embedding) as similarity
    from public.vector_embeddings v
    where v.embedding is not null
      and (p_user_id is null or v.user_id = p_user_id)
      and (p_collection is null or v.collection = p_collection)
      and 1 - (v.embedding <=> query_embedding) >= match_threshold
    order by v.embedding <=> query_embedding
    limit greatest(match_count, 1);
$$;

revoke all on function public.match_documents(vector, float, int, text, text) from public, anon, authenticated;
grant execute on function public.match_documents(vector, float, int, text, text) to service_role;

-- 3. Layer 2: fast "all facts for this user, newest first" reads and the 200-fact cap count --
create index if not exists vector_embeddings_user_facts_idx
    on public.vector_embeddings (user_id, created_at desc)
    where collection = 'user_facts';

-- 4. Layer 2: per-user vendor memory. email_parser now filters vendor rules by user_id.
--    Rows written before that change carry the owner only inside metadata, so copy it
--    into the real column. Rows with no owner anywhere stay NULL and are ignored
--    (they were shared across accounts, which is exactly what we no longer want).
update public.vector_embeddings
set user_id = metadata->>'user_id'
where user_id is null
  and metadata ? 'user_id'
  and coalesce(metadata->>'user_id', '') <> '';

create index if not exists vector_embeddings_vendor_memory_idx
    on public.vector_embeddings (user_id, (metadata->>'vendor_key'))
    where collection = 'vendor_memory';

-- 5. Layer 3: transaction search / details read original currency and amount.
--    No-ops if these columns already exist. `metadata` (channel, fx_rate, user_words,
--    logged_at) is jsonb and already created by earlier migrations.
alter table public.transactions add column if not exists original_amount   numeric;
alter table public.transactions add column if not exists original_currency text;
alter table public.transactions add column if not exists metadata          jsonb not null default '{}'::jsonb;

create index if not exists transactions_metadata_channel_idx
    on public.transactions ((metadata->>'channel'));

-- 6. Verify. Expect: vector_ext = 1, fn = 1, and the three columns listed.
select
    (select count(*) from pg_extension where extname = 'vector')                       as vector_ext,
    (select count(*) from pg_proc where proname = 'match_documents')                   as fn,
    (select count(*) from public.vector_embeddings where collection = 'user_facts')    as facts_stored,
    (select string_agg(column_name, ', ' order by column_name)
       from information_schema.columns
      where table_schema = 'public' and table_name = 'transactions'
        and column_name in ('original_amount', 'original_currency', 'metadata'))        as transaction_cols;
