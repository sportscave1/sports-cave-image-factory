-- Private server-only mailbox recovery, independent of campaign delivery.
CREATE TABLE IF NOT EXISTS public.support_email_drafts (
    mailbox text NOT NULL,
    actor text NOT NULL,
    draft_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    payload jsonb NOT NULL CHECK (octet_length(payload::text) <= 31457280),
    revision bigint NOT NULL DEFAULT 1,
    state text NOT NULL DEFAULT 'active' CHECK (state IN ('active','discarded')),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(mailbox,actor,draft_id)
);
CREATE INDEX IF NOT EXISTS support_email_drafts_recent ON public.support_email_drafts(mailbox,actor,updated_at DESC) WHERE state='active';
CREATE TABLE IF NOT EXISTS public.support_email_outbox (
    mailbox text NOT NULL,
    operation_id uuid NOT NULL,
    actor text NOT NULL DEFAULT '',
    message_id text NOT NULL,
    fingerprint text NOT NULL,
    payload jsonb NOT NULL CHECK (octet_length(payload::text) <= 31457280),
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','in_progress','accepted','rejected','unknown')),
    sent_folder text NOT NULL DEFAULT '',
    sent_policy text NOT NULL DEFAULT 'append',
    copy_status text NOT NULL DEFAULT 'pending' CHECK (copy_status IN ('pending','attempting','present','appended','unknown','failed')),
    attempts integer NOT NULL DEFAULT 0,
    reconcile_attempts integer NOT NULL DEFAULT 0,
    error_category text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    due_at timestamptz NOT NULL DEFAULT now(),
    accepted_at timestamptz,
    PRIMARY KEY(mailbox,operation_id),
    UNIQUE(mailbox,message_id)
);
CREATE INDEX IF NOT EXISTS support_email_outbox_due ON public.support_email_outbox(mailbox,due_at,created_at) WHERE status IN ('queued','in_progress','unknown','accepted');
ALTER TABLE public.support_email_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.support_email_outbox ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.support_email_drafts,public.support_email_outbox FROM PUBLIC,anon,authenticated;
