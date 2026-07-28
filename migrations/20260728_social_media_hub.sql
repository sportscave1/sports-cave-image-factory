CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS social_daily_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES os_users(id),
    plan_date DATE NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Australia/Sydney',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'completed')),
    focus_areas TEXT[] NOT NULL DEFAULT '{}',
    content_plan TEXT NOT NULL DEFAULT ''
        CHECK (char_length(content_plan) <= 3000),
    planned_platforms TEXT[] NOT NULL DEFAULT '{}',
    planned_post_count INTEGER
        CHECK (planned_post_count IS NULL OR planned_post_count >= 0),
    improvement_test TEXT NOT NULL DEFAULT ''
        CHECK (char_length(improvement_test) <= 1500),
    what_worked TEXT NOT NULL DEFAULT ''
        CHECK (char_length(what_worked) <= 2000),
    what_learned TEXT NOT NULL DEFAULT ''
        CHECK (char_length(what_learned) <= 2000),
    improve_next TEXT NOT NULL DEFAULT ''
        CHECK (char_length(improve_next) <= 2000),
    blockers TEXT NOT NULL DEFAULT ''
        CHECK (char_length(blockers) <= 2000),
    execution_score NUMERIC(4,1) NOT NULL DEFAULT 0
        CHECK (execution_score >= 0 AND execution_score <= 10),
    created_by UUID NOT NULL REFERENCES os_users(id),
    updated_by UUID NOT NULL REFERENCES os_users(id),
    completed_at TIMESTAMPTZ,
    reopened_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, plan_date)
);

CREATE TABLE IF NOT EXISTS social_daily_priorities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID NOT NULL REFERENCES social_daily_plans(id),
    priority_index INTEGER NOT NULL
        CHECK (priority_index >= 1 AND priority_index <= 3),
    task TEXT NOT NULL
        CHECK (char_length(task) >= 1 AND char_length(task) <= 240),
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (plan_id, priority_index)
);

CREATE TABLE IF NOT EXISTS social_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES os_users(id),
    content_name TEXT NOT NULL
        CHECK (char_length(content_name) >= 1 AND char_length(content_name) <= 240),
    campaign TEXT NOT NULL DEFAULT ''
        CHECK (char_length(campaign) <= 240),
    content_format TEXT NOT NULL
        CHECK (content_format IN (
            'Reel', 'Static post', 'Carousel', 'Story',
            'Short', 'Pin', 'Video', 'Other'
        )),
    market TEXT NOT NULL DEFAULT 'Global'
        CHECK (market IN (
            'Australia', 'USA', 'UK', 'Canada', 'New Zealand', 'Global'
        )),
    created_date DATE NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
        CHECK (char_length(notes) <= 2000),
    created_by UUID NOT NULL REFERENCES os_users(id),
    updated_by UUID NOT NULL REFERENCES os_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS social_post_platforms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES social_posts(id),
    platform TEXT NOT NULL
        CHECK (platform IN (
            'Instagram', 'Facebook', 'Pinterest', 'TikTok', 'YouTube'
        )),
    status TEXT NOT NULL DEFAULT 'Planned'
        CHECK (status IN ('Planned', 'Created', 'Scheduled', 'Live')),
    scheduled_published_at TIMESTAMPTZ,
    public_url TEXT NOT NULL DEFAULT ''
        CHECK (
            char_length(public_url) <= 1000
            AND (public_url = '' OR public_url ~* '^https://')
        ),
    reach_views BIGINT CHECK (reach_views IS NULL OR reach_views >= 0),
    engagements BIGINT CHECK (engagements IS NULL OR engagements >= 0),
    link_clicks BIGINT CHECK (link_clicks IS NULL OR link_clicks >= 0),
    saves_shares BIGINT CHECK (saves_shares IS NULL OR saves_shares >= 0),
    result_note TEXT NOT NULL DEFAULT ''
        CHECK (char_length(result_note) <= 1200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (post_id, platform)
);

CREATE TABLE IF NOT EXISTS social_weekly_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES os_users(id),
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Australia/Sydney',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'submitted')),
    performed_best TEXT NOT NULL DEFAULT ''
        CHECK (char_length(performed_best) <= 2000),
    learned TEXT NOT NULL DEFAULT ''
        CHECK (char_length(learned) <= 2000),
    test_next TEXT NOT NULL DEFAULT ''
        CHECK (char_length(test_next) <= 2000),
    average_execution_score NUMERIC(4,1),
    mips_completed INTEGER NOT NULL DEFAULT 0,
    completed_workdays INTEGER NOT NULL DEFAULT 0,
    created_by UUID NOT NULL REFERENCES os_users(id),
    updated_by UUID NOT NULL REFERENCES os_users(id),
    submitted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, week_start)
);

CREATE TABLE IF NOT EXISTS social_weekly_platform_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID NOT NULL REFERENCES social_weekly_reports(id),
    platform TEXT NOT NULL
        CHECK (platform IN (
            'Instagram', 'Facebook', 'Pinterest', 'TikTok', 'YouTube'
        )),
    audience_total BIGINT CHECK (audience_total IS NULL OR audience_total >= 0),
    reach_views BIGINT CHECK (reach_views IS NULL OR reach_views >= 0),
    engagements BIGINT CHECK (engagements IS NULL OR engagements >= 0),
    outbound_clicks BIGINT CHECK (outbound_clicks IS NULL OR outbound_clicks >= 0),
    posts_published INTEGER CHECK (posts_published IS NULL OR posts_published >= 0),
    best_post_url TEXT NOT NULL DEFAULT ''
        CHECK (
            char_length(best_post_url) <= 1000
            AND (best_post_url = '' OR best_post_url ~* '^https://')
        ),
    best_post_result TEXT NOT NULL DEFAULT ''
        CHECK (char_length(best_post_result) <= 600),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (report_id, platform)
);

CREATE TABLE IF NOT EXISTS social_action_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_key TEXT NOT NULL UNIQUE,
    actor_user_id UUID NOT NULL REFERENCES os_users(id),
    action_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_social_daily_plans_user_date
    ON social_daily_plans(user_id, plan_date DESC);

CREATE INDEX IF NOT EXISTS idx_social_daily_plans_date_status
    ON social_daily_plans(plan_date DESC, status);

CREATE INDEX IF NOT EXISTS idx_social_posts_user_date
    ON social_posts(user_id, created_date DESC);

CREATE INDEX IF NOT EXISTS idx_social_posts_format_date
    ON social_posts(content_format, created_date DESC);

CREATE INDEX IF NOT EXISTS idx_social_post_platform_status
    ON social_post_platforms(platform, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_social_weekly_reports_user_week
    ON social_weekly_reports(user_id, week_start DESC);

CREATE INDEX IF NOT EXISTS idx_social_weekly_reports_status_week
    ON social_weekly_reports(status, week_start DESC);

CREATE INDEX IF NOT EXISTS idx_social_weekly_metrics_platform
    ON social_weekly_platform_metrics(platform, updated_at DESC);

ALTER TABLE social_daily_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_daily_priorities ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_post_platforms ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_weekly_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_weekly_platform_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_action_requests ENABLE ROW LEVEL SECURITY;
