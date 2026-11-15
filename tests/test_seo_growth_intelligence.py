import inspect
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import google_seo_import
import google_seo_phase4
import run_migrations
import seo_growth_intelligence as growth


ROOT = Path(__file__).resolve().parents[1]


class GrowthSnapshotTests(unittest.TestCase):
    def test_sanitise_removes_credentials_and_customer_fields_without_removing_keywords(self):
        payload = {
            "target_keyword": "nba wall art",
            "access_token": "secret-token",
            "customer_email": "buyer@example.test",
            "nested": {"refresh_token": "hidden", "recommended_action": "Improve page"},
        }
        clean = growth.sanitize_for_chatgpt(payload)
        self.assertEqual(clean["target_keyword"], "nba wall art")
        self.assertNotIn("access_token", clean)
        self.assertNotIn("customer_email", clean)
        self.assertNotIn("refresh_token", clean["nested"])
        self.assertEqual(clean["nested"]["recommended_action"], "Improve page")

    def test_prompt_and_snapshot_use_supplied_evidence_only(self):
        reporting = {
            "ready": True,
            "health": {"common_reporting_date": "2026-08-12", "data_status": "ready"},
            "filters": {
                "start_date": "2026-07-16",
                "end_date": "2026-08-12",
                "previous_start_date": "2026-06-18",
                "previous_end_date": "2026-07-15",
            },
            "current": {"organic_clicks": 10, "organic_impressions": 100},
            "previous": {"organic_clicks": 5, "organic_impressions": 50},
            "top_queries": [{"query": "cricket wall art", "clicks": 4, "impressions": 40}],
        }
        bundle = growth.build_analysis_bundle(
            reporting,
            {"keywords": [{"keyword": "cricket wall art", "customer_email": "nope@example.test"}]},
            analysis_mode="Prepare for ChatGPT",
            filters=reporting["filters"],
        )
        self.assertIn("Use only the supplied Sports Cave evidence", bundle["prompt"])
        self.assertIn("cricket wall art", bundle["snapshot_json"])
        self.assertNotIn("nope@example.test", bundle["snapshot_json"])
        self.assertEqual(bundle["data_through"], "2026-08-12")

    def test_structured_report_validation_requires_schema_and_recommendations(self):
        payload = {
            "report_id": "report-1",
            "report_type": "Weekly",
            "date_range": "2026-07-16 to 2026-08-12",
            "comparison_range": "2026-06-18 to 2026-07-15",
            "market": "AU",
            "device": "All devices",
            "data_through": "2026-08-12",
            "executive_summary": "Clicks improved.",
            "important_changes": [],
            "trending_searches": [],
            "ranking_gains": [],
            "ranking_losses": [],
            "quick_wins": [],
            "landing_page_findings": [],
            "revenue_supported_findings": [],
            "risks": [],
            "recommendations": [
                {
                    "recommendation_id": "rec-1",
                    "target_keyword": "nba wall art",
                    "keyword_cluster": "nba art",
                    "target_market": "AU",
                    "current_page": "/collections/nba",
                    "recommended_page": "/collections/nba",
                    "current_position": 8.0,
                    "previous_position": 10.0,
                    "impressions": 100,
                    "clicks": 4,
                    "revenue_or_conversion_evidence": "No confirmed revenue in supplied data.",
                    "recommended_action": "Improve collection copy.",
                    "priority": "High",
                    "reason": "Near page one.",
                    "confidence": 0.8,
                    "measurement_date": "2026-08-12",
                    "requires_approval": True,
                    "proposed_owner": "Nathan",
                }
            ],
            "weekly_plan": [],
            "longer_term_strategy": [],
            "measurement_requirements": [],
            "data_limitations": [],
        }
        clean = growth.validate_structured_report(payload)
        self.assertEqual(clean["recommendations"][0]["recommendation_id"], "rec-1")
        with self.assertRaises(growth.SEOGrowthError):
            growth.validate_structured_report({"report_id": "missing-required-fields"})

    def test_openai_unconfigured_fallback_does_not_call_network(self):
        requester = Mock(side_effect=AssertionError("network should not be called"))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "SPORTS_CAVE_OPENAI_API_KEY": ""}, clear=False):
            result = growth.generate_openai_report({"prompt": "x", "snapshot": {}}, request_post=requester)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "openai_not_configured")
        requester.assert_not_called()


class GrowthPipelineTests(unittest.TestCase):
    def test_pipeline_stage_order_uses_one_run_log(self):
        class FakeStore:
            def __init__(self):
                self.started = []
                self.completed = []

            def queue_pipeline_run(self, **_kwargs):
                return {"id": "pipeline-1", "status": "queued"}

            def claim_pipeline_run(self, _worker_id):
                return {"id": "pipeline-1", "status": "running"}

            def start_stage(self, _run_id, stage_key, _order):
                self.started.append(stage_key)

            def complete_stage(self, _run_id, stage_key, **_kwargs):
                self.completed.append(stage_key)

            def fail_stage(self, *_args, **_kwargs):
                raise AssertionError("stage should not fail")

            def refresh_due_measurements(self):
                return {"processed": 0, "written": 0}

            def complete_pipeline(self, pipeline_run_id, **values):
                return {"id": pipeline_run_id, **values}

        class FakePhase4:
            def refresh_health(self):
                return {}

            def refresh_reporting_snapshots(self):
                return {"status": "completed", "common_reporting_date": "2026-08-12"}

            def map_saved_urls(self):
                return {"received": 1, "written": 1}

            def reconcile_revenue(self):
                return {"received": 1, "written": 1}

            def saved_health(self):
                return {"common_reporting_date": "2026-08-12"}

        class FakeWorker:
            def __init__(self, **_kwargs):
                pass

            def run_once(self, **_kwargs):
                return {"status": "completed", "received": 1, "written": 1}

        store = FakeStore()
        with patch.object(google_seo_import, "SEOImportWorker", FakeWorker), patch.object(
            google_seo_phase4, "SEOPhase4Worker", FakeWorker
        ), patch.object(
            google_seo_import, "queue_daily_runs", return_value=[]
        ), patch.object(
            google_seo_phase4, "queue_daily_pipeline", return_value=[]
        ):
            result = growth.run_daily_growth_pipeline(
                store=store,
                import_store=object(),
                phase4_store=FakePhase4(),
                connection_store=Mock(get_connection=Mock(return_value={"status": "Connected"})),
                requested_by="test",
                worker_id="worker",
                fresh_gsc_refresher=lambda: {"status": "preliminary", "processed": 1, "written": 1},
            )
        self.assertEqual(result["status"], "completed")
        self.assertNotIn("technical_audit", dict(growth.PIPELINE_STAGES))
        self.assertEqual(store.started, [stage[0] for stage in growth.PIPELINE_STAGES])
        self.assertEqual(store.completed, [stage[0] for stage in growth.PIPELINE_STAGES])

    def test_existing_google_daily_command_delegates_to_analytics_refresh(self):
        source = inspect.getsource(google_seo_import.run_complete_daily_pipeline)
        self.assertIn("seo_growth_intelligence.run_daily_analytics_refresh", source)
        self.assertIn("SEO_GOOGLE_IMPORT_DAILY_ONLY", source)


class GrowthMigrationTests(unittest.TestCase):
    def test_growth_migration_is_additive_safe_and_registered(self):
        sql = (ROOT / "migrations" / growth.GROWTH_MIGRATION).read_text(encoding="utf-8")
        self.assertTrue(run_migrations.safe_migration_sql(sql))
        self.assertIn("CREATE TABLE IF NOT EXISTS seo_growth_pipeline_runs", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS seo_growth_analysis_snapshots", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS seo_growth_measurements", sql)
        self.assertIn(growth.GROWTH_MIGRATION, google_seo_phase4.PHASE4_MIGRATIONS)


if __name__ == "__main__":
    unittest.main()
