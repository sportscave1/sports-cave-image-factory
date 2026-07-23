CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS collector_frame_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_reference UUID NOT NULL DEFAULT gen_random_uuid(),
    customer_hash TEXT NOT NULL,
    shopify_customer_id TEXT NOT NULL,
    certificate_row_id BIGINT NOT NULL REFERENCES certificates(id),
    certificate_id TEXT,
    original_shopify_order_id TEXT NOT NULL,
    original_shopify_order_name TEXT,
    shopify_product_id TEXT NOT NULL,
    shopify_variant_id TEXT,
    artwork_title TEXT NOT NULL,
    edition_number INTEGER NOT NULL,
    edition_limit INTEGER NOT NULL,
    certificate_asset_reference JSONB NOT NULL DEFAULT '{}'::jsonb,
    frame_product_id TEXT NOT NULL,
    frame_variant_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    storefront_cart_id TEXT,
    checkout_url TEXT,
    framed_shopify_order_id TEXT,
    framed_shopify_order_name TEXT,
    ordered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (request_reference),
    UNIQUE (customer_hash, certificate_row_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_collector_frame_customer_certificate
    ON collector_frame_requests(customer_hash, certificate_row_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_collector_frame_status
    ON collector_frame_requests(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_collector_frame_shopify_order
    ON collector_frame_requests(framed_shopify_order_id)
    WHERE framed_shopify_order_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS collector_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_reference UUID NOT NULL DEFAULT gen_random_uuid(),
    customer_hash TEXT NOT NULL,
    shopify_customer_id TEXT NOT NULL,
    certificate_row_id BIGINT NOT NULL REFERENCES certificates(id),
    shopify_order_id TEXT NOT NULL,
    shopify_product_id TEXT NOT NULL,
    judge_me_product_id TEXT,
    rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_title TEXT,
    review_body TEXT NOT NULL,
    photo_bucket TEXT,
    photo_object_key TEXT,
    photo_mime_type TEXT,
    judge_me_review_id TEXT,
    judge_me_verification_status TEXT,
    status TEXT NOT NULL DEFAULT 'submitting',
    last_error TEXT,
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (submission_reference),
    UNIQUE (customer_hash, shopify_order_id, shopify_product_id)
);

CREATE INDEX IF NOT EXISTS idx_collector_reviews_customer_created
    ON collector_reviews(customer_hash, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_collector_reviews_status
    ON collector_reviews(status, updated_at DESC);

ALTER TABLE collector_frame_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE collector_reviews ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE collector_frame_requests IS
    'Server-only fulfilment links between an owned certificate and a framed-certificate Shopify line.';
COMMENT ON TABLE collector_reviews IS
    'Server-only Judge.me review submission state for delivered, customer-owned purchases.';
