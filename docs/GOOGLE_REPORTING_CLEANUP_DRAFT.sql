-- DRAFT ONLY. Prepared for project ceyzbfpuwuuxaiqwiltz, workspace sports-cave.
-- No schema drops, CASCADE, TRUNCATE, credentials or automatic execution.
-- Before any deletion: verify deployed direct readers against Google; stop old
-- worker revisions; verify a scoped export checksum and isolated restore;
-- review dependency inventory and row counts; obtain owner approval for this
-- exact list. Separate project and all audit/business records are excluded.
-- Keep the original historical exports: APIs cannot reproduce every past report.
-- To review: execute ONLY this read-only transaction in the verified project.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';
SELECT 'analytics_ga4_report_snapshots' AS table_name, COUNT(*) AS candidate_rows FROM public.analytics_ga4_report_snapshots WHERE workspace_key='sports-cave';
SELECT 'seo_gsc_property_totals_v2' AS table_name, COUNT(*) AS candidate_rows FROM public.seo_gsc_property_totals_v2 WHERE workspace_key='sports-cave' AND source_date >= DATE '2025-06-12';
SELECT 'seo_gsc_query_daily_v2' AS table_name, COUNT(*) AS candidate_rows FROM public.seo_gsc_query_daily_v2 WHERE workspace_key='sports-cave' AND source_date >= DATE '2025-06-12';
SELECT 'seo_gsc_query_page_daily_v2' AS table_name, COUNT(*) AS candidate_rows FROM public.seo_gsc_query_page_daily_v2 WHERE workspace_key='sports-cave' AND source_date >= DATE '2025-06-12';
SELECT 'seo_gsc_page_daily_v2' AS table_name, COUNT(*) AS candidate_rows FROM public.seo_gsc_page_daily_v2 WHERE workspace_key='sports-cave' AND source_date >= DATE '2025-06-12';
SELECT 'seo_gsc_search_appearance_daily_v2' AS table_name, COUNT(*) AS candidate_rows FROM public.seo_gsc_search_appearance_daily_v2 WHERE workspace_key='sports-cave' AND source_date >= DATE '2025-06-12';
SELECT 'seo_reporting_daily_metrics' AS table_name, COUNT(*) AS candidate_rows FROM public.seo_reporting_daily_metrics WHERE workspace_key='sports-cave';
SELECT 'seo_reporting_query_daily' AS table_name, COUNT(*) AS candidate_rows FROM public.seo_reporting_query_daily WHERE workspace_key='sports-cave';
SELECT 'seo_reporting_landing_page_daily' AS table_name, COUNT(*) AS candidate_rows FROM public.seo_reporting_landing_page_daily WHERE workspace_key='sports-cave';
SELECT 'seo_reporting_page_daily' AS table_name, COUNT(*) AS candidate_rows FROM public.seo_reporting_page_daily WHERE workspace_key='sports-cave';
ROLLBACK;

-- The following deletion plan is intentionally INERT (commented out).
-- Each table must have an approved expected row count and cutoff at execution.
-- BEGIN;
-- SET LOCAL lock_timeout = '2s';
-- SET LOCAL statement_timeout = '30s';
-- DELETE FROM public.analytics_ga4_report_snapshots WHERE workspace_key='sports-cave';
-- DELETE FROM public.seo_gsc_property_totals_v2 WHERE workspace_key='sports-cave' AND source_date >= DATE '2025-06-12';
-- DELETE FROM public.seo_gsc_query_daily_v2 WHERE workspace_key='sports-cave' AND source_date >= DATE '2025-06-12';
-- DELETE FROM public.seo_gsc_query_page_daily_v2 WHERE workspace_key='sports-cave' AND source_date >= DATE '2025-06-12';
-- DELETE FROM public.seo_gsc_page_daily_v2 WHERE workspace_key='sports-cave' AND source_date >= DATE '2025-06-12';
-- DELETE FROM public.seo_gsc_search_appearance_daily_v2 WHERE workspace_key='sports-cave' AND source_date >= DATE '2025-06-12';
-- DELETE FROM public.seo_reporting_daily_metrics WHERE workspace_key='sports-cave';
-- DELETE FROM public.seo_reporting_query_daily WHERE workspace_key='sports-cave';
-- DELETE FROM public.seo_reporting_landing_page_daily WHERE workspace_key='sports-cave';
-- DELETE FROM public.seo_reporting_page_daily WHERE workspace_key='sports-cave';
-- ROLLBACK; -- Never change to COMMIT before separate exact-list approval.
