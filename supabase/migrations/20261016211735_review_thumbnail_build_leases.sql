-- Disposable review work only. No preparation, approval or order queue changes.
CREATE TABLE public.auto_edition_review_preview_builds (
 identity text PRIMARY KEY CHECK(identity ~ '^[a-f0-9]{64}$'),
 token uuid NOT NULL,
 lease_until timestamptz NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.auto_edition_review_preview_builds ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.auto_edition_review_preview_builds FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.auto_edition_review_preview_builds TO service_role;
