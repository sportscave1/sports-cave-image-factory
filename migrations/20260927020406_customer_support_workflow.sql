-- Optional Sports Cave workflow ONLY. Apply manually after review; never run at app startup.
-- Customer messages, headers, subjects, bodies and attachment data have no columns here.
BEGIN;
CREATE TABLE IF NOT EXISTS public.customer_support_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mailbox TEXT NOT NULL CHECK (mailbox = lower(mailbox)),
    thread_key TEXT NOT NULL CHECK (thread_key ~ '^[0-9a-f]{64}$'),
    assigned_user_id UUID REFERENCES public.os_users(id) ON DELETE SET NULL,
    support_status TEXT NOT NULL DEFAULT 'Needs Reply'
        CHECK (support_status IN ('Needs Reply','Waiting on Customer','Waiting on Sports Cave','Resolved')),
    matched_order_id TEXT REFERENCES public.shopify_orders(shopify_order_id) ON DELETE SET NULL,
    matched_order_number TEXT,
    match_method TEXT,
    internal_notes TEXT NOT NULL DEFAULT '' CHECK (length(internal_notes) <= 8000),
    needs_approval BOOLEAN NOT NULL DEFAULT FALSE,
    last_handled_by UUID REFERENCES public.os_users(id) ON DELETE SET NULL,
    last_handled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (mailbox, thread_key)
);
ALTER TABLE public.customer_support_threads ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.customer_support_threads FROM PUBLIC, anon, authenticated;
-- This app uses its existing trusted server-side Postgres connection + OS page permissions.
-- There is intentionally no public Data API policy or browser-facing grant.
COMMENT ON TABLE public.customer_support_threads IS
    'Sports Cave support workflow metadata only. VentraIP IMAP remains the email source of truth.';
COMMIT;
