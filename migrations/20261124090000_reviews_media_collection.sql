-- Additive review ownership and collection; no customer messages or discounts sent.
ALTER TABLE sc_reviews ADD COLUMN IF NOT EXISTS review_type text NOT NULL DEFAULT 'PRODUCT' CHECK(review_type IN ('PRODUCT','STORE'));
ALTER TABLE sc_reviews ADD COLUMN IF NOT EXISTS source_fingerprint text;
CREATE UNIQUE INDEX IF NOT EXISTS sc_review_source_fingerprint ON sc_reviews(source_fingerprint) WHERE source_fingerprint IS NOT NULL;
CREATE TABLE IF NOT EXISTS sc_review_identities (
 source text NOT NULL, source_store_id text NOT NULL, external_id text NOT NULL,
 review_id uuid NOT NULL REFERENCES sc_reviews(id),
 PRIMARY KEY(source,source_store_id,external_id)
);
ALTER TABLE sc_review_identities ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON sc_review_identities FROM PUBLIC,anon,authenticated;
ALTER TABLE sc_review_imports ADD COLUMN IF NOT EXISTS skipped integer NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS sc_review_media (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), review_id uuid NOT NULL REFERENCES sc_reviews(id),
 kind text NOT NULL CHECK(kind IN ('image','video')), source_url text NOT NULL DEFAULT '',
 object_key text NOT NULL DEFAULT '', sha256 text, size_bytes bigint, mime_type text,
 status text NOT NULL DEFAULT 'QUEUED' CHECK(status IN ('QUEUED','COPIED','FAILED')),
 approved boolean NOT NULL DEFAULT false, consent boolean NOT NULL DEFAULT false,
 attempts integer NOT NULL DEFAULT 0, lease_until timestamptz, error_code text,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(review_id,source_url),
 CHECK(status<>'COPIED' OR (object_key<>'' AND sha256 IS NOT NULL AND size_bytes>0))
);
CREATE INDEX IF NOT EXISTS sc_review_media_due ON sc_review_media(status,lease_until,created_at) WHERE attempts<3;
CREATE INDEX IF NOT EXISTS sc_review_media_review ON sc_review_media(review_id);
CREATE TABLE IF NOT EXISTS sc_review_rewards (
 review_id uuid PRIMARY KEY REFERENCES sc_reviews(id), customer_id text NOT NULL, order_id text NOT NULL,
 media_kind text NOT NULL CHECK(media_kind IN ('image','video')),
 percent integer NOT NULL CHECK(percent BETWEEN 1 AND 50),
 status text NOT NULL DEFAULT 'ELIGIBLE' CHECK(status IN ('ELIGIBLE','ISSUING','ISSUED','SENDING','SENT','CANCELLED','HELD')),
 code text, discount_id text, issued_at timestamptz, provider_id text, error_code text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE sc_review_media ENABLE ROW LEVEL SECURITY;
ALTER TABLE sc_review_rewards ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON sc_review_media,sc_review_rewards FROM PUBLIC,anon,authenticated;

CREATE OR REPLACE FUNCTION sc_review_aggregate() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE r sc_reviews; delta integer; target text; live integer; pub integer; att integer;
BEGIN
 FOR delta IN -1..1 BY 2 LOOP
  IF delta=-1 THEN
   IF TG_OP='INSERT' THEN CONTINUE; END IF; r:=OLD;
  ELSE r:=NEW;
  END IF;
  live:=CASE WHEN r.status IN ('PENDING','PUBLISHED') THEN 1 ELSE 0 END;
  pub:=CASE WHEN r.status='PUBLISHED' AND (r.product_id IS NOT NULL OR r.review_type='STORE') THEN 1 ELSE 0 END;
  att:=CASE WHEN live=1 AND (r.status='PENDING' OR (r.product_id IS NULL AND r.review_type='PRODUCT') OR (r.rating<=2 AND r.merchant_reply='')) THEN 1 ELSE 0 END;
  FOREACH target IN ARRAY ARRAY['all',COALESCE(r.product_id,'unmapped')] LOOP
   INSERT INTO sc_review_totals(scope,total,rating_total,fives,attention,published,published_rating)
   VALUES(target,delta*live,delta*live*r.rating,delta*live*CASE WHEN r.rating=5 THEN 1 ELSE 0 END,delta*att,delta*pub,delta*pub*r.rating)
   ON CONFLICT(scope) DO UPDATE SET total=sc_review_totals.total+excluded.total,rating_total=sc_review_totals.rating_total+excluded.rating_total,
    fives=sc_review_totals.fives+excluded.fives,attention=sc_review_totals.attention+excluded.attention,
    published=sc_review_totals.published+excluded.published,published_rating=sc_review_totals.published_rating+excluded.published_rating;
  END LOOP;
  INSERT INTO sc_review_days(day,total) VALUES((r.created_at AT TIME ZONE 'UTC')::date,delta*live*CASE WHEN r.source_metadata->>'date_known' IS DISTINCT FROM 'false' THEN 1 ELSE 0 END)
  ON CONFLICT(day) DO UPDATE SET total=sc_review_days.total+excluded.total;
 END LOOP;
 RETURN NEW;
END $$;

-- Reclassify only legacy rows without any product hints.
UPDATE sc_reviews SET review_type='STORE' WHERE product_id IS NULL AND COALESCE(source_metadata->'product_hints','{}'::jsonb) IN ('{}'::jsonb,'{"product_id":"","product_handle":"","product_url":"","product_sku":"","product_title":""}'::jsonb);
