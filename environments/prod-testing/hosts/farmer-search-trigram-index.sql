-- PERMANENT search index on the farmer register (2026-11-18, runbook step K.4, user request: "don't delete it later").
-- Speeds up the staff portal's name / Farmer ID search: search_text ILIKE '%term%' (and its count(*)).
-- Name as requested; the load-test scripts only ever drop ix_loadtest_* indexes, so they never touch this one.
-- Idempotent; CONCURRENTLY = no lock on reads or writes while it builds. Run on the PRIMARY as postgres:
--   ssh -F ssh_config pg-primary-01 'sudo -u postgres psql -d farmer_registry -v ON_ERROR_STOP=1' < hosts/stepk/farmer-search-trigram-index.sql
-- The permanent fix belongs in the registry's own migrations; until then re-run this after any database rebuild.
create extension if not exists pg_trgm;
create index concurrently if not exists idx_g2p_register_farmers_search_text_trigram
  on public.g2p_register_farmers using gin (search_text gin_trgm_ops);
-- a failed CONCURRENTLY build leaves an INVALID index behind; stop loudly so it can be dropped and rebuilt
do $$ begin
  if exists (select 1 from pg_index i join pg_class c on c.oid = i.indexrelid
             where c.relname = 'idx_g2p_register_farmers_search_text_trigram' and not i.indisvalid) then
    raise exception 'idx_g2p_register_farmers_search_text_trigram is INVALID: drop index concurrently and re-run';
  end if; end $$;
comment on index public.idx_g2p_register_farmers_search_text_trigram is
  'PERMANENT (openg2p-test step K.4, 2026-11-18): trigram index for search_text ILIKE search. Do not drop.';
analyze public.g2p_register_farmers;
