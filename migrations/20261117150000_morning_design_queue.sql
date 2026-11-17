CREATE TABLE IF NOT EXISTS public.morning_design_control (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 enabled boolean NOT NULL DEFAULT false,
 activated_at timestamptz,
 start_date date NOT NULL DEFAULT (now() AT TIME ZONE 'Australia/Sydney')::date
);
INSERT INTO public.morning_design_control(singleton) VALUES(true) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS public.morning_design_jobs (
 id uuid PRIMARY KEY,
 edition_date date NOT NULL,
 section text NOT NULL,
 title text NOT NULL,
 prompt text NOT NULL,
 stage smallint NOT NULL DEFAULT 0 CHECK(stage BETWEEN 0 AND 5),
 chat_url text NOT NULL DEFAULT '',
 message text NOT NULL DEFAULT '',
 file_id text NOT NULL DEFAULT '',
 file_rev text NOT NULL DEFAULT '',
 file_path text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS morning_design_waiting ON public.morning_design_jobs(edition_date,created_at,id) WHERE stage=0;
CREATE UNIQUE INDEX IF NOT EXISTS morning_design_one_active ON public.morning_design_jobs((true)) WHERE stage BETWEEN 1 AND 3;
CREATE INDEX IF NOT EXISTS morning_design_active ON public.morning_design_jobs(stage) WHERE stage BETWEEN 1 AND 3;
ALTER TABLE public.morning_design_control ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.morning_design_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.morning_design_control, public.morning_design_jobs FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS(SELECT FROM pg_roles WHERE rolname='anon') THEN
  REVOKE ALL ON public.morning_design_control, public.morning_design_jobs FROM anon;
 END IF;
 IF EXISTS(SELECT FROM pg_roles WHERE rolname='authenticated') THEN
  REVOKE ALL ON public.morning_design_control, public.morning_design_jobs FROM authenticated;
 END IF;
END $$;
