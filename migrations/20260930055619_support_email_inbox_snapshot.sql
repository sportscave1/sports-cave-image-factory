-- One bounded, server-only read model per mailbox credential scope. No bodies.
CREATE TABLE IF NOT EXISTS public.support_email_inbox_snapshot (
    mailbox_key text PRIMARY KEY,
    snapshot jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (octet_length(snapshot::text) <= 524288)
);
ALTER TABLE public.support_email_inbox_snapshot ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.support_email_inbox_snapshot FROM PUBLIC, anon, authenticated;
