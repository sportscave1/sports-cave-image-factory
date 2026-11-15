CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS human_work_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    staff_display_name TEXT NOT NULL,
    staff_role TEXT,
    origin TEXT NOT NULL DEFAULT 'human',
    area TEXT NOT NULL,
    action_type TEXT NOT NULL,
    description TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    source_route TEXT,
    outcome TEXT NOT NULL DEFAULT 'completed',
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actual_seconds INTEGER,
    correlation_key TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    audit_log_id BIGINT REFERENCES audit_logs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (origin = 'human')
);

ALTER TABLE human_work_events ADD COLUMN IF NOT EXISTS staff_role TEXT;
ALTER TABLE human_work_events ADD COLUMN IF NOT EXISTS source_route TEXT;
ALTER TABLE human_work_events ADD COLUMN IF NOT EXISTS actual_seconds INTEGER;
ALTER TABLE human_work_events ADD COLUMN IF NOT EXISTS audit_log_id BIGINT;
ALTER TABLE human_work_events ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;
ALTER TABLE human_work_events ADD COLUMN IF NOT EXISTS origin TEXT DEFAULT 'human';
UPDATE human_work_events SET origin='human' WHERE COALESCE(origin, '') = '';

CREATE UNIQUE INDEX IF NOT EXISTS idx_human_work_events_correlation_key
    ON human_work_events(correlation_key);
CREATE INDEX IF NOT EXISTS idx_human_work_events_occurred_at
    ON human_work_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_human_work_events_user_occurred
    ON human_work_events(user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_human_work_events_area_action_occurred
    ON human_work_events(area, action_type, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_human_work_events_outcome_occurred
    ON human_work_events(outcome, occurred_at DESC);

WITH source_rows AS (
    SELECT
        log.*,
        COALESCE(log.new_value->'metadata', '{}'::jsonb) AS metadata,
        COALESCE(log.new_value->>'message', log.reason, initcap(replace(log.event_type, '_', ' '))) AS message,
        COALESCE(log.new_value->>'page', log.source, 'Sports Cave') AS page
    FROM audit_logs log
    WHERE COALESCE(log.new_value->'metadata'->>'actor_id', '') <> ''
      AND log.event_type = ANY(ARRAY[
          'mockup_generated', 'mockup_made', 'mockup_uploaded', 'mockup_deleted',
          'mockup_zip_saved', 'mockups_saved_dropbox', 'mockup_pack_exported',
          'mockup_zip_exported', 'prompt_pack_exported',
          'new_product_prompt_generated', 'existing_product_update_prompt_generated',
          'product_uploaded', 'product_created', 'product_updated',
          'product_media_updated', 'product_media_uploaded', 'product_assigned_collection',
          'product_published', 'product_edition_updated', 'edition_product_updated',
          'edition_product_manual_update', 'edition_product_archived',
          'collection_created', 'collection_updated', 'shopify_new_products_pulled',
          'shopify_catalogue_refreshed', 'shopify_product_reconciliation_completed',
          'shopify_metafield_pushed', 'manual_next_number_lowered',
          'task_added', 'dashboard_task_added', 'task_imported', 'task_completed',
          'dashboard_task_completed', 'design_task_completed',
          'task_design_style_updated', 'task_design_details_updated', 'task_deleted',
          'design_prompt_saved',
          'ad_prompt_generated', 'ad_images_saved', 'ad_plan_saved',
          'ad_creative_saved', 'ad_creative_approved', 'ad_copy_saved',
          'ad_published', 'ad_completed',
          'blog_created', 'blog_updated', 'keyword_updated', 'keyword_mapping_updated',
          'link_plan_created', 'link_plan_updated', 'outreach_created', 'outreach_updated',
          'gsc_csv_imported', 'seo_article_saved', 'seo_optimisation_saved',
          'seo_recommendation_saved', 'seo_recommendation_converted_to_task',
          'seo_task_saved', 'seo_task_status_updated', 'seo_growth_pipeline_queued',
          'google_seo_import_queued',
          'seo_phase4_queued', 'google_seo_properties_selected', 'google_seo_synced',
          'social_day_completed', 'social_day_reopened', 'social_plan_created',
          'social_plan_saved', 'social_plan_updated', 'social_record_corrected',
          'social_post_logged', 'social_post_marked_live', 'social_post_saved',
          'social_post_updated', 'social_weekly_checkin_created',
          'social_weekly_checkin_updated', 'social_weekly_checkin_submitted',
          'social_weekly_priority_saved', 'social_content_job_saved',
          'social_media_output_saved', 'reel_prompt_saved', 'reel_video_uploaded',
          'reel_saved',
          'order_fulfilled', 'order_fulfilled_certificate_generated',
          'prodigi_status_updated', 'certificate_generated', 'certificate_uploaded',
          'certificate_generation_failed', 'certificate_upload_failed',
          'daily_planner_task_completed', 'daily_planner_task_did_not_finish',
          'daily_planner_task_skipped',
          'files_folder_created', 'files_uploaded', 'files_item_renamed',
          'files_items_copied', 'files_items_moved', 'files_moved_to_recycle_bin',
          'account_created', 'account_updated', 'permissions_changed',
          'reporting_permission_changed', 'account_permanently_removed'
      ])
      AND lower(COALESCE(log.new_value->'metadata'->>'actor_type', '')) NOT IN ('system', 'webhook', 'background', 'automatic')
), canonical AS (
    SELECT
        metadata->>'actor_id' AS user_id,
        COALESCE(NULLIF(metadata->>'actor_display', ''), NULLIF(actor, ''), metadata->>'actor_id') AS staff_display_name,
        COALESCE(metadata->>'actor_role', '') AS staff_role,
        CASE
            WHEN event_type LIKE 'mockup%' OR event_type='prompt_pack_exported' THEN 'Mockups'
            WHEN event_type IN ('new_product_prompt_generated', 'existing_product_update_prompt_generated') THEN 'Product Uploads'
            WHEN event_type LIKE 'product%' OR event_type LIKE 'edition_product%' OR event_type LIKE 'collection%' OR event_type LIKE 'shopify%' OR event_type='manual_next_number_lowered' THEN 'Products'
            WHEN event_type LIKE 'task%' OR event_type LIKE 'dashboard_task%' OR event_type LIKE 'design%' THEN 'Design Studio'
            WHEN event_type LIKE 'ad%' THEN 'Ads'
            WHEN event_type LIKE 'seo%' OR event_type LIKE 'google_seo%' OR event_type IN ('blog_created', 'blog_updated', 'keyword_updated', 'keyword_mapping_updated', 'link_plan_created', 'link_plan_updated', 'outreach_created', 'outreach_updated', 'gsc_csv_imported') THEN 'SEO'
            WHEN event_type LIKE 'social%' OR event_type LIKE 'reel%' THEN 'Social Media'
            WHEN event_type LIKE 'daily_planner%' THEN 'Daily Planner'
            WHEN event_type LIKE 'files%' THEN 'Files'
            WHEN event_type LIKE 'account%' OR event_type LIKE 'permissions%' OR event_type LIKE 'reporting_permission%' THEN 'Accounts & Access'
            ELSE 'Orders'
        END AS area,
        CASE event_type
            WHEN 'new_product_prompt_generated' THEN 'product_upload_completed'
            WHEN 'existing_product_update_prompt_generated' THEN 'existing_product_updated'
            WHEN 'mockup_generated' THEN 'mockup_created'
            WHEN 'mockup_made' THEN 'mockup_created'
            WHEN 'mockup_uploaded' THEN 'mockup_saved'
            WHEN 'mockup_zip_saved' THEN 'mockup_pack_saved'
            WHEN 'mockups_saved_dropbox' THEN 'mockups_saved'
            WHEN 'product_uploaded' THEN 'product_upload_completed'
            WHEN 'edition_product_updated' THEN 'product_edition_updated'
            WHEN 'edition_product_manual_update' THEN 'product_edition_updated'
            WHEN 'task_added' THEN 'design_task_created'
            WHEN 'dashboard_task_added' THEN 'design_task_created'
            WHEN 'task_imported' THEN 'design_tasks_imported'
            WHEN 'task_completed' THEN 'design_task_completed'
            WHEN 'dashboard_task_completed' THEN 'design_task_completed'
            WHEN 'task_design_style_updated' THEN 'design_task_updated'
            WHEN 'task_design_details_updated' THEN 'design_task_updated'
            WHEN 'task_deleted' THEN 'design_task_deleted'
            WHEN 'ad_prompt_generated' THEN 'ad_copy_saved'
            WHEN 'ad_images_saved' THEN 'ad_creative_saved'
            WHEN 'blog_created' THEN 'seo_article_saved'
            WHEN 'blog_updated' THEN 'seo_article_saved'
            WHEN 'keyword_updated' THEN 'seo_keyword_mapping_updated'
            WHEN 'keyword_mapping_updated' THEN 'seo_keyword_mapping_updated'
            WHEN 'link_plan_created' THEN 'seo_recommendation_saved'
            WHEN 'link_plan_updated' THEN 'seo_recommendation_saved'
            WHEN 'outreach_created' THEN 'seo_recommendation_saved'
            WHEN 'outreach_updated' THEN 'seo_recommendation_saved'
            WHEN 'gsc_csv_imported' THEN 'seo_manual_import_completed'
            WHEN 'seo_recommendation_converted_to_task' THEN 'seo_task_created'
            WHEN 'seo_task_status_updated' THEN 'seo_task_completed'
            WHEN 'google_seo_synced' THEN 'google_seo_synced'
            WHEN 'social_plan_created' THEN 'social_plan_saved'
            WHEN 'social_plan_updated' THEN 'social_plan_saved'
            WHEN 'social_post_logged' THEN 'social_content_saved'
            WHEN 'social_post_saved' THEN 'social_content_saved'
            WHEN 'social_post_updated' THEN 'social_content_saved'
            WHEN 'social_post_marked_live' THEN 'social_content_published'
            WHEN 'social_weekly_checkin_created' THEN 'social_weekly_review_saved'
            WHEN 'social_weekly_checkin_updated' THEN 'social_weekly_review_saved'
            WHEN 'social_weekly_checkin_submitted' THEN 'social_weekly_review_completed'
            WHEN 'social_content_job_saved' THEN 'social_content_saved'
            WHEN 'social_media_output_saved' THEN 'social_creative_saved'
            ELSE event_type
        END AS action_type,
        message AS description,
        COALESCE(entity_type, '') AS entity_type,
        COALESCE(entity_id, '') AS entity_id,
        page AS source_route,
        CASE
            WHEN event_type LIKE '%_failed' OR lower(COALESCE(metadata->>'status', metadata->>'result', '')) IN ('denied', 'error', 'failed', 'failure', 'rejected') THEN 'failed'
            WHEN event_type='daily_planner_task_skipped' THEN 'skipped'
            WHEN event_type='daily_planner_task_did_not_finish' THEN 'did_not_finish'
            ELSE 'completed'
        END AS outcome,
        created_at AS occurred_at,
        CASE
            WHEN COALESCE(metadata->>'actual_elapsed_seconds', metadata->>'actual_seconds', metadata->>'focused_seconds', metadata->>'duration_seconds', '') ~ '^[0-9]+$'
            THEN COALESCE(metadata->>'actual_elapsed_seconds', metadata->>'actual_seconds', metadata->>'focused_seconds', metadata->>'duration_seconds')::integer
            ELSE NULL
        END AS actual_seconds,
        COALESCE(NULLIF(metadata->>'event_key', ''), 'audit-log:' || id::text) AS correlation_key,
        (
            metadata
            - 'password' - 'password_hash' - 'token' - 'access_token'
            - 'refresh_token' - 'secret' - 'api_key' - 'authorization'
        ) || jsonb_build_object('source_action_type', event_type, 'source_event_type', event_type) AS metadata,
        id AS audit_log_id
    FROM source_rows
)
INSERT INTO human_work_events(
    user_id, staff_display_name, staff_role, origin, area, action_type,
    description, entity_type, entity_id, source_route, outcome, occurred_at,
    actual_seconds, correlation_key, metadata, audit_log_id
)
SELECT
    user_id, staff_display_name, staff_role, 'human', area, action_type,
    description, entity_type, entity_id, source_route, outcome, occurred_at,
    actual_seconds, correlation_key, metadata, audit_log_id
FROM canonical
WHERE user_id <> ''
ON CONFLICT (correlation_key) DO NOTHING;
