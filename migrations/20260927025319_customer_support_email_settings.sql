-- Optional OS signature/settings metadata only. Never stores mail, drafts or attachments.
BEGIN;
CREATE TABLE IF NOT EXISTS public.customer_support_email_settings (
    mailbox TEXT PRIMARY KEY CHECK (mailbox=lower(mailbox)),
    sender_name TEXT NOT NULL DEFAULT 'Sports Cave' CHECK (length(sender_name) <= 120),
    signatures JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(signatures)='object'),
    folder_mapping JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(folder_mapping)='object'),
    sent_policy TEXT NOT NULL DEFAULT 'verify' CHECK (sent_policy IN ('verify','server','append')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.customer_support_email_preferences (
    mailbox TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES public.os_users(id) ON DELETE CASCADE,
    signature_key TEXT NOT NULL DEFAULT 'company' CHECK (signature_key IN ('company','nathan','reina','none')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (mailbox,user_id)
);
ALTER TABLE public.customer_support_email_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_support_email_preferences ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.customer_support_email_settings FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.customer_support_email_preferences FROM PUBLIC, anon, authenticated;
-- Same trusted server Postgres connection and OS authorization model as Email V1.
COMMIT;
