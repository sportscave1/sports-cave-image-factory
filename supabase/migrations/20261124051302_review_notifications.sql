-- Existing reviews intentionally start seen: only new INSERTs create arrivals.
ALTER TABLE public.sc_reviews ADD COLUMN IF NOT EXISTS notification_received_at timestamptz;
CREATE INDEX IF NOT EXISTS sc_reviews_received_page ON public.sc_reviews
 (notification_received_at DESC NULLS LAST,created_at DESC,id DESC);
CREATE TABLE IF NOT EXISTS public.sc_review_seen (
 actor_id text NOT NULL,
 review_id uuid NOT NULL REFERENCES public.sc_reviews(id) ON DELETE CASCADE,
 seen_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(actor_id,review_id)
);
ALTER TABLE public.sc_review_seen ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sc_review_seen FROM PUBLIC,anon,authenticated;
CREATE OR REPLACE FUNCTION public.sc_review_arrival_stamp() RETURNS trigger
 LANGUAGE plpgsql SET search_path='' AS $$
 BEGIN NEW.notification_received_at=clock_timestamp(); RETURN NEW; END;
$$;
REVOKE ALL ON FUNCTION public.sc_review_arrival_stamp() FROM PUBLIC,anon,authenticated;
DROP TRIGGER IF EXISTS sc_review_new_arrival ON public.sc_reviews;
CREATE TRIGGER sc_review_new_arrival BEFORE INSERT ON public.sc_reviews
 FOR EACH ROW EXECUTE FUNCTION public.sc_review_arrival_stamp();
