-- Preserve every existing archive and identity. CRM intent is independent of social permission.
ALTER TABLE public.wall_previews
 ADD COLUMN IF NOT EXISTS client_preview_id UUID,
 ADD COLUMN IF NOT EXISTS session_id UUID,
 ADD COLUMN IF NOT EXISTS archive_sha256 TEXT,
 ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
 ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ,
 ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
 ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 ADD COLUMN IF NOT EXISTS email_requested_at TIMESTAMPTZ,
 ADD COLUMN IF NOT EXISTS email_sent_at TIMESTAMPTZ,
 ADD COLUMN IF NOT EXISTS attribution JSONB NOT NULL DEFAULT '{}'::jsonb,
 ADD COLUMN IF NOT EXISTS share_token TEXT,
 ADD COLUMN IF NOT EXISTS share_expires_at TIMESTAMPTZ,
 ADD COLUMN IF NOT EXISTS share_revoked_at TIMESTAMPTZ,
 ADD COLUMN IF NOT EXISTS purchased_at TIMESTAMPTZ,
 ADD COLUMN IF NOT EXISTS order_id TEXT,
 ADD COLUMN IF NOT EXISTS order_number TEXT;
-- Extend the existing enum, retaining legacy guest/blank identities.
ALTER TABLE public.wall_previews DROP CONSTRAINT IF EXISTS wall_previews_identity_source_check;
ALTER TABLE public.wall_previews ADD CONSTRAINT wall_previews_identity_source_check
 CHECK (identity_source IN ('', 'guest', 'logged_in', 'anonymous', 'email_capture'));
-- Keep the legacy index intact during rolling deployment. V2 uses an owner-scoped
-- fingerprint in image_sha256 and the actual composite digest in archive_sha256.
CREATE UNIQUE INDEX IF NOT EXISTS idx_wall_previews_client ON public.wall_previews(client_preview_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wall_previews_share ON public.wall_previews(share_token);
CREATE INDEX IF NOT EXISTS idx_wall_previews_confirmed ON public.wall_previews(confirmed_at DESC);
CREATE TABLE IF NOT EXISTS public.wall_preview_events (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 preview_id UUID NOT NULL REFERENCES public.wall_previews(id),
 event_key TEXT NOT NULL CHECK (char_length(event_key) <= 120),
 event_name TEXT NOT NULL CHECK (event_name IN ('WallPreviewStarted','WallPreviewConfirmed',
  'WallPreviewDownloaded','WallPreviewShared','WallPreviewEmailCaptured','WallPreviewAddedToCart','WallPreviewPurchased')),
 occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 session_id UUID,
 metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
 UNIQUE(preview_id,event_key)
);
CREATE INDEX IF NOT EXISTS idx_wall_preview_events_timeline ON public.wall_preview_events(preview_id,occurred_at);
CREATE INDEX IF NOT EXISTS idx_wall_preview_events_name ON public.wall_preview_events(event_name,occurred_at);
CREATE TABLE IF NOT EXISTS public.wall_preview_email_jobs (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 preview_id UUID NOT NULL REFERENCES public.wall_previews(id),
 kind TEXT NOT NULL CHECK (kind IN ('requested','4h','24h')),
 state TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','processing','sent','suppressed','failed','uncertain')),
 due_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 claimed_at TIMESTAMPTZ,
 attempts INTEGER NOT NULL DEFAULT 0,
 provider_id TEXT,
 reason TEXT NOT NULL DEFAULT '',
 finished_at TIMESTAMPTZ,
 UNIQUE(preview_id,kind)
);
CREATE INDEX IF NOT EXISTS idx_wall_preview_email_due ON public.wall_preview_email_jobs(state,due_at);
ALTER TABLE public.wall_previews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wall_preview_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wall_preview_email_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.wall_previews, public.wall_preview_events, public.wall_preview_email_jobs FROM PUBLIC,anon,authenticated;
