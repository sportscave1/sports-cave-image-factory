-- Canonical server-only review storage. Anonymous clients use bounded public projections.
CREATE TABLE IF NOT EXISTS sc_reviews (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 source text NOT NULL CHECK(source IN ('csv','judgeme','sports_cave')),
 source_review_id text, source_store_id text NOT NULL DEFAULT '',
 product_id text, product_title text NOT NULL DEFAULT '', product_handle text NOT NULL DEFAULT '',
 product_image text NOT NULL DEFAULT '', product_url text NOT NULL DEFAULT '',
 customer_id text, order_id text,
 reviewer_name text NOT NULL, reviewer_email_hash text,
 rating smallint NOT NULL CHECK(rating BETWEEN 1 AND 5),
 title text NOT NULL DEFAULT '', body text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT now(), imported_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','PUBLISHED','ARCHIVED','SPAM')),
 verified_purchase boolean NOT NULL DEFAULT false, source_verified boolean NOT NULL DEFAULT false,
 merchant_reply text NOT NULL DEFAULT '', merchant_reply_at timestamptz, reply_actor text,
 moderated_at timestamptz, mapping_resolved_at timestamptz,
 source_metadata jsonb NOT NULL DEFAULT '{}', dedupe_key text UNIQUE NOT NULL,
 search_document tsvector GENERATED ALWAYS AS (to_tsvector('simple', reviewer_name||' '||product_title||' '||title||' '||body)) STORED,
 CHECK(length(title)<=200 AND length(body)<=5000 AND length(merchant_reply)<=3000),
 CHECK(NOT verified_purchase OR (order_id IS NOT NULL AND customer_id IS NOT NULL AND product_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS sc_reviews_source ON sc_reviews(source,source_store_id,source_review_id) WHERE source_review_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS sc_reviews_page ON sc_reviews(status,created_at DESC,id);
CREATE INDEX IF NOT EXISTS sc_reviews_product_page ON sc_reviews(product_id,status,created_at DESC,id);
CREATE INDEX IF NOT EXISTS sc_reviews_search ON sc_reviews USING gin(search_document);
CREATE TABLE IF NOT EXISTS sc_review_totals (
 scope text PRIMARY KEY, total bigint NOT NULL DEFAULT 0, rating_total bigint NOT NULL DEFAULT 0,
 fives bigint NOT NULL DEFAULT 0, attention bigint NOT NULL DEFAULT 0,
 published bigint NOT NULL DEFAULT 0, published_rating bigint NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sc_review_days (day date PRIMARY KEY, total bigint NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sc_review_settings (key text PRIMARY KEY,value jsonb NOT NULL,updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS sc_review_imports (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source text NOT NULL, label text NOT NULL,
 status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','RUNNING','COMPLETED','FAILED')),
 payload jsonb NOT NULL DEFAULT '[]', cursor integer NOT NULL DEFAULT 0,
 total integer NOT NULL DEFAULT 0, imported integer NOT NULL DEFAULT 0, duplicates integer NOT NULL DEFAULT 0,
 unresolved integer NOT NULL DEFAULT 0, invalid integer NOT NULL DEFAULT 0,
 provider_page integer NOT NULL DEFAULT 1, attempts integer NOT NULL DEFAULT 0,
 lease_until timestamptz, error_code text, actor text,
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sc_review_import_due ON sc_review_imports(status,lease_until,created_at);
CREATE TABLE IF NOT EXISTS sc_review_tokens (
 token_hash text PRIMARY KEY, order_id text NOT NULL, customer_id text NOT NULL, product_id text NOT NULL,
 expires_at timestamptz NOT NULL, review_id uuid REFERENCES sc_reviews(id),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(order_id,customer_id,product_id)
);
CREATE TABLE IF NOT EXISTS sc_review_audit (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,review_id uuid REFERENCES sc_reviews(id),
 actor text NOT NULL,action text NOT NULL,created_at timestamptz NOT NULL DEFAULT now()
);
-- Update global/product totals and UTC date buckets in the same review transaction.
CREATE OR REPLACE FUNCTION sc_review_aggregate() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE r sc_reviews; delta integer; target text; live integer; pub integer; att integer;
BEGIN
 FOR delta IN -1..1 BY 2 LOOP
  IF delta=-1 THEN
   IF TG_OP='INSERT' THEN CONTINUE; END IF; r:=OLD;
  ELSE r:=NEW;
  END IF;
  live:=CASE WHEN r.status IN ('PENDING','PUBLISHED') THEN 1 ELSE 0 END;
  pub:=CASE WHEN r.status='PUBLISHED' AND r.product_id IS NOT NULL THEN 1 ELSE 0 END;
  att:=CASE WHEN live=1 AND (r.status='PENDING' OR r.product_id IS NULL OR (r.rating<=2 AND r.merchant_reply='')) THEN 1 ELSE 0 END;
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
CREATE TRIGGER sc_review_aggregate_change AFTER INSERT OR UPDATE ON sc_reviews FOR EACH ROW EXECUTE FUNCTION sc_review_aggregate();
REVOKE ALL ON FUNCTION sc_review_aggregate() FROM PUBLIC,anon,authenticated;
ALTER TABLE sc_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE sc_review_totals ENABLE ROW LEVEL SECURITY;
ALTER TABLE sc_review_days ENABLE ROW LEVEL SECURITY;
ALTER TABLE sc_review_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE sc_review_imports ENABLE ROW LEVEL SECURITY;
ALTER TABLE sc_review_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE sc_review_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON sc_reviews,sc_review_totals,sc_review_days,sc_review_settings,sc_review_imports,sc_review_tokens,sc_review_audit FROM PUBLIC,anon,authenticated;
