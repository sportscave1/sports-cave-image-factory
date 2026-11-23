-- Bound overlap admission/heartbeat reads to live sessions, not upload history.
CREATE INDEX IF NOT EXISTS companion_package_uploads_live_lease
    ON public.companion_package_uploads
    (owner_id,(context->>'product_gid'),(context->>'lease_token'))
    WHERE state IN ('Receiving','Queued');
