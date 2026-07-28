CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS activity_report_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purpose TEXT NOT NULL,
    report_date DATE NOT NULL,
    covered_start_at TIMESTAMPTZ NOT NULL,
    covered_end_at TIMESTAMPTZ NOT NULL,
    report_timezone TEXT NOT NULL DEFAULT 'Australia/Sydney',
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    provider TEXT NOT NULL DEFAULT 'resend',
    provider_message_id TEXT,
    idempotency_key TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    locked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    sanitized_error TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_test BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (idempotency_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_report_one_production_per_day
    ON activity_report_deliveries (purpose, report_date)
    WHERE is_test IS FALSE;

CREATE INDEX IF NOT EXISTS idx_activity_report_deliveries_date
    ON activity_report_deliveries (report_date DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_activity_report_deliveries_status
    ON activity_report_deliveries (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS activity_report_archives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    delivery_id UUID NOT NULL UNIQUE
        REFERENCES activity_report_deliveries(id),
    purpose TEXT NOT NULL,
    report_date DATE NOT NULL,
    covered_start_at TIMESTAMPTZ NOT NULL,
    covered_end_at TIMESTAMPTZ NOT NULL,
    report_timezone TEXT NOT NULL DEFAULT 'Australia/Sydney',
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    provider TEXT NOT NULL DEFAULT 'resend',
    provider_message_id TEXT,
    staff_summaries JSONB NOT NULL DEFAULT '[]'::jsonb,
    daily_execution_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    report_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    attention_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    html_snapshot TEXT NOT NULL,
    text_snapshot TEXT NOT NULL,
    csv_filename TEXT NOT NULL,
    csv_content TEXT NOT NULL,
    is_test BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_activity_report_archives_date
    ON activity_report_archives (report_date DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_activity_report_archives_status
    ON activity_report_archives (status, updated_at DESC);

ALTER TABLE activity_report_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_report_archives ENABLE ROW LEVEL SECURITY;
