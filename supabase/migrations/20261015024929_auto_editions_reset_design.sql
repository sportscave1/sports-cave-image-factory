-- Local reset proposal. Explicit release approval required before production.
-- Active checkpoints/mappings/approvals/allocations are not rewritten here.
ALTER TABLE public.auto_edition_onboarding ADD COLUMN replacement jsonb
 CHECK(replacement IS NULL OR (jsonb_typeof(replacement)='object'
 AND replacement->>'stage' IN ('Discovering','Queued','Preparing','Failed','Complete')));
CREATE INDEX auto_edition_reset_pending ON public.auto_edition_onboarding((replacement->>'stage'))
 WHERE replacement IS NOT NULL AND replacement->>'stage' IN ('Discovering','Queued','Preparing');
