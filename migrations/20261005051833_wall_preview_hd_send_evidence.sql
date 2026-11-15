-- Additive consent evidence. Existing identity, image permission and consent
-- timestamps remain the authority. No historical rows are rewritten.
ALTER TABLE public.wall_previews
 ADD COLUMN IF NOT EXISTS marketing_consent_text TEXT,
 ADD COLUMN IF NOT EXISTS marketing_consent_version TEXT;
CREATE TABLE IF NOT EXISTS public.wall_preview_archive_jobs (
 preview_id UUID PRIMARY KEY REFERENCES public.wall_previews(id) ON DELETE CASCADE,
 version INTEGER NOT NULL,
 image BYTEA,
 state TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','done','failed')),
 attempts INTEGER NOT NULL DEFAULT 0,
 due_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 last_attempt_at TIMESTAMPTZ,
 finished_at TIMESTAMPTZ,
 reason TEXT NOT NULL DEFAULT '',
 CHECK (image IS NULL OR octet_length(image)<=12582912)
);
CREATE INDEX IF NOT EXISTS idx_wall_preview_archive_jobs_due
 ON public.wall_preview_archive_jobs(due_at) WHERE state='queued';
ALTER TABLE public.wall_preview_archive_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.wall_preview_archive_jobs FROM PUBLIC, anon, authenticated;
ALTER TABLE public.wall_previews ENABLE ROW LEVEL SECURITY;
