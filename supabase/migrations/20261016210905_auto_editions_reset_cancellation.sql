-- Durable prerequisite only. Existing Reset replacement contract is unchanged.
ALTER TABLE public.auto_edition_onboarding ADD COLUMN IF NOT EXISTS reset_cancellation jsonb;
