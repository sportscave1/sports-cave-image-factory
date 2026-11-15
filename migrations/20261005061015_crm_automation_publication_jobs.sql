BEGIN;
CREATE TABLE IF NOT EXISTS public.crm_automation_publish_jobs (
 id uuid PRIMARY KEY,
 automation_id uuid NOT NULL REFERENCES public.crm_automations(id),
 revision integer NOT NULL CHECK (revision>0),
 publication_version integer NOT NULL CHECK (publication_version>0),
 snapshot jsonb NOT NULL,
 requested_by text NOT NULL,
 state text NOT NULL DEFAULT 'QUEUED' CHECK (state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')),
 requested_at timestamptz NOT NULL DEFAULT now(),
 available_at timestamptz NOT NULL DEFAULT now(),
 started_at timestamptz,
 completed_at timestamptz,
 attempts integer NOT NULL DEFAULT 0,
 owner text,
 lease_until timestamptz,
 error text
);
CREATE UNIQUE INDEX IF NOT EXISTS crm_automation_publish_active
 ON public.crm_automation_publish_jobs(automation_id) WHERE state IN ('QUEUED','RUNNING');
CREATE INDEX IF NOT EXISTS crm_automation_publish_due
 ON public.crm_automation_publish_jobs(state,available_at,requested_at) WHERE state IN ('QUEUED','RUNNING');
CREATE INDEX IF NOT EXISTS crm_automation_publish_revision
 ON public.crm_automation_publish_jobs(automation_id,revision,requested_at DESC);
ALTER TABLE public.crm_automation_publish_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.crm_automation_publish_jobs FROM PUBLIC,anon,authenticated;
COMMIT;
