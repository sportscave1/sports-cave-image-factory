-- Additive rollout: older companions continue claiming only slot 1.
ALTER TABLE public.morning_design_jobs
 ADD COLUMN IF NOT EXISTS slot smallint NOT NULL DEFAULT 1 CHECK(slot IN (1,2));
CREATE UNIQUE INDEX IF NOT EXISTS morning_design_active_slot
 ON public.morning_design_jobs(slot) WHERE stage BETWEEN 1 AND 3;
DROP INDEX IF EXISTS public.morning_design_one_active;
