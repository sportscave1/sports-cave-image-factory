-- Reuse marketing_permission for image reuse. No email consent is inferred from it.
ALTER TABLE public.wall_previews
 ADD COLUMN IF NOT EXISTS image_reuse_consent_at TIMESTAMPTZ,
 ADD COLUMN IF NOT EXISTS image_reuse_consent_source TEXT,
 ADD COLUMN IF NOT EXISTS submitted_marketing_opt_in BOOLEAN,
 ADD COLUMN IF NOT EXISTS marketing_consent_at TIMESTAMPTZ,
 ADD COLUMN IF NOT EXISTS marketing_consent_source TEXT;
CREATE TABLE IF NOT EXISTS public.wall_preview_customer_jobs (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 preview_id UUID NOT NULL UNIQUE REFERENCES public.wall_previews(id),
 state TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','processing','done','failed')),
 attempts INTEGER NOT NULL DEFAULT 0,
 due_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 claimed_at TIMESTAMPTZ,
 finished_at TIMESTAMPTZ,
 reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_wall_preview_customer_due ON public.wall_preview_customer_jobs(state,due_at);
ALTER TABLE public.wall_preview_customer_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.wall_preview_customer_jobs FROM PUBLIC,anon,authenticated;
