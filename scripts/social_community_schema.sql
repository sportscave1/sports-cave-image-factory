-- Explicit provisioning only: this file is not part of startup migrations.
-- Apply to an isolated development database first; production needs release approval.
BEGIN;
CREATE TABLE IF NOT EXISTS public.social_collaborators (
    username text PRIMARY KEY,
    followers integer NOT NULL CHECK (followers >= 0),
    engagement numeric,
    fit boolean NOT NULL DEFAULT false,
    score integer NOT NULL CHECK (score BETWEEN 0 AND 100),
    reason text NOT NULL DEFAULT '',
    draft text NOT NULL CHECK (length(draft) BETWEEN 1 AND 1000),
    state text NOT NULL DEFAULT 'discovered' CHECK (state IN
        ('discovered','shortlisted','sending','sent','unknown','agreed','declined')),
    message_id text NOT NULL DEFAULT '',
    sent_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS social_collaborators_score ON public.social_collaborators(score DESC,username);
CREATE TABLE IF NOT EXISTS public.social_community_settings (
    id integer PRIMARY KEY CHECK (id=1),
    automation_enabled boolean NOT NULL DEFAULT false
);
ALTER TABLE public.social_collaborators ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.social_community_settings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.social_collaborators, public.social_community_settings FROM PUBLIC, anon, authenticated;
-- The existing OS server database role accesses these through supabase_backend.
-- No browser REST access or permissive RLS policies.
COMMIT;
