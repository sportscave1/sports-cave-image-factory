import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

import os_accounts
import run_migrations
import seo_navigation
import seo_workspace as seo


ROOT = Path(__file__).resolve().parents[1]


def user(*, permissions=(), role="worker"):
    return {
        "id": "user-1",
        "email": "seo@example.test",
        "display_name": "SEO User",
        "role": role,
        "is_active": True,
        "page_permissions": list(permissions),
    }


class SEONavigationTests(unittest.TestCase):
    def test_registry_has_one_assignable_parent_and_all_growth_routes(self):
        parent = os_accounts.PAGE_BY_KEY[seo.SEO_PAGE_KEY]
        self.assertEqual(parent["route"], seo.SEO_OVERVIEW_ROUTE)
        self.assertEqual(parent["label"], "SEO")
        self.assertTrue(parent["worker_assignable"])
        self.assertEqual(len(seo.SEO_ROUTES), 8)
        self.assertEqual(
            seo.SEO_ROUTES[:4],
            (
                seo.SEO_OVERVIEW_ROUTE,
                seo.SEO_KEYWORDS_ROUTE,
                seo.SEO_REPORTS_ROUTE,
                seo.SEO_TASKS_ROUTE,
            ),
        )
        for route in seo.SEO_ROUTES:
            self.assertIn(route, os_accounts.PAGE_BY_ROUTE)
        for route in seo.SEO_ROUTES[1:]:
            page = os_accounts.PAGE_BY_ROUTE[route]
            self.assertFalse(page["worker_assignable"])
            self.assertEqual(page["parent_key"], seo.SEO_PAGE_KEY)
            self.assertTrue(page["navigation_child"])

    def test_parent_permission_grants_every_seo_route_and_nothing_unrelated(self):
        approved = user(permissions=[seo.SEO_PAGE_KEY])
        denied = user(permissions=["orders"])
        for route in seo.SEO_ROUTES:
            self.assertTrue(os_accounts.can_access_page(approved, route))
            self.assertFalse(os_accounts.can_access_page(denied, route))
        self.assertFalse(os_accounts.can_access_page(approved, "Orders"))

    def test_navigation_source_keeps_seo_children_and_disabled_email_without_headings(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('SIDEBAR_OPEN_GROUP_KEY = "sidebar-open-group"', source)
        self.assertIn('key=f"sidebar-disclosure::{group}"', source)
        self.assertIn('key="sidebar-nav::Email::soon"', source)
        self.assertIn('disabled=True', source)
        self.assertIn('help="Coming later"', source)
        self.assertNotIn("def _sidebar_section_label", source)
        self.assertNotIn("sc-sidebar-section-label", source)
        self.assertLess(
            source.index('_sidebar_route_button("Mockups"'),
            source.index('if seo_nav.SEO_OVERVIEW_ROUTE in allowed_routes:'),
        )
        self.assertLess(
            source.index('key="sidebar-nav::Email::soon"'),
            source.index('_sidebar_route_button("VA Training"'),
        )
        for label in seo.SEO_NAV_LABELS.values():
            self.assertIn(f'"{label}"', (ROOT / "seo_navigation.py").read_text(encoding="utf-8"))
        self.assertNotIn('"route": "Email"', source)

    def test_router_supports_deep_seo_routes(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("elif current_page in seo_nav.SEO_ROUTES:", source)
        self.assertIn("get_seo_page().render_page(", source)
        self.assertIn("current_page not in seo_nav.SEO_ROUTES", source)


class SEOStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = seo.LocalSEOStore(Path(self.temp_dir.name) / "seo.json")
        self.actor = user(permissions=[seo.SEO_PAGE_KEY])

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_empty_store_initialises_with_defaults_and_sanitised_legacy_citations(self):
        state = self.store.load()
        self.assertEqual(state["blog_records"], [])
        self.assertEqual(len(state["citations"]), 253)
        self.assertEqual(sum(row["status"] == "Live" for row in state["citations"]), 251)
        self.assertEqual(state["outreach_records"], [])
        self.assertEqual(state["keywords"], [])
        self.assertEqual(len(state["target_library"]), len(seo.INTERNAL_LINK_TARGETS))
        self.assertEqual(state["settings"]["integrations"]["gsc"]["status"], "Not connected")

    def test_create_edit_status_and_archive_persist(self):
        state = self.store.load()
        record = seo.upsert_record(
            state,
            "blog_records",
            {"article_title": "A sporting story", "status": "Brief"},
            actor=self.actor,
        )
        self.store.save(state, actor_id=self.actor["id"])
        reloaded = self.store.load()
        self.assertEqual(reloaded["blog_records"][0]["status"], "Brief")
        seo.upsert_record(
            reloaded,
            "blog_records",
            {**reloaded["blog_records"][0], "status": "Draft"},
            actor=self.actor,
            record_id=record["id"],
        )
        self.store.save(reloaded, actor_id=self.actor["id"])
        final = self.store.load()
        self.assertEqual(final["blog_records"][0]["status"], "Draft")
        seo.archive_record(final, "blog_records", record["id"], actor=self.actor)
        self.store.save(final, actor_id=self.actor["id"])
        self.assertEqual(seo.active_records(self.store.load(), "blog_records"), [])

    def test_old_partial_state_receives_schema_defaults_without_losing_records(self):
        partial = {
            "blog_records": [{"id": "blog-1", "article_title": "Existing"}],
            "settings": {"business_details": {"business_name": "Sports Cave"}},
        }
        self.store.path.parent.mkdir(parents=True, exist_ok=True)
        self.store.path.write_text(json.dumps(partial), encoding="utf-8")
        state = self.store.load()
        self.assertEqual(state["blog_records"][0]["id"], "blog-1")
        self.assertIn("keywords", state)
        self.assertEqual(state["settings"]["business_details"]["website"], seo.BUSINESS_DETAILS["website"])

    def test_seed_target_library_does_not_duplicate_after_reloads(self):
        state = self.store.load()
        self.store.save(state)
        first = self.store.load()
        self.store.save(first)
        second = self.store.load()
        ids = [row["id"] for row in second["target_library"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), len(seo.INTERNAL_LINK_TARGETS))

    def test_migration_is_non_destructive_and_uses_one_shared_state_table(self):
        sql = (ROOT / "migrations" / seo.SEO_MIGRATION).read_text(encoding="utf-8")
        data_sql = (ROOT / "migrations" / seo.SEO_DATA_MIGRATION).read_text(encoding="utf-8")
        self.assertTrue(run_migrations.safe_migration_sql(sql))
        self.assertTrue(run_migrations.safe_migration_sql(data_sql))
        self.assertIn("CREATE TABLE IF NOT EXISTS seo_workspace_state", sql)
        self.assertIn("payload JSONB", sql)
        self.assertIn("ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("ALTER COLUMN schema_version SET DEFAULT 2", data_sql)


class SEOValidationTests(unittest.TestCase):
    def test_live_citation_requires_public_profile_and_displayed_website(self):
        with self.assertRaisesRegex(seo.SEOValidationError, "Profile URL"):
            seo.validate_citation({"platform": "Example", "status": "Live"})
        valid = seo.validate_citation(
            {
                "platform": "Example",
                "status": "Live",
                "profile_url": "https://example.com/sports-cave",
                "publicly_accessible": True,
                "website_displayed": "Yes",
                "username_handle": "sports-cave",
            }
        )
        self.assertEqual(valid["status"], "Live")

    def test_outreach_rejection_live_validation_and_one_follow_up(self):
        base = {"site_creator": "Sports Site", "website": "https://example.com"}
        with self.assertRaisesRegex(seo.SEOValidationError, "short reason"):
            seo.validate_outreach({**base, "status": "Rejected"})
        with self.assertRaisesRegex(seo.SEOValidationError, "Only one follow-up"):
            seo.validate_outreach({**base, "status": "Research", "follow_up_count": 2})
        with self.assertRaisesRegex(seo.SEOValidationError, "live URL"):
            seo.validate_outreach({**base, "status": "Live"})
        valid = seo.validate_outreach(
            {
                **base,
                "status": "Live",
                "live_url": "https://example.com/article",
                "target_page": "https://www.sportscaveshop.com/collections/nba",
                "anchor_text": "Sports Cave",
                "relevant_placement": True,
                "verification_date": "2026-08-12",
                "follow_up_count": 1,
            }
        )
        self.assertEqual(valid["follow_up_count"], 1)

    def test_internal_link_product_is_explicitly_optional(self):
        row = seo.validate_link_plan(
            {
                "source_blog": "Story",
                "homepage_url": "https://www.sportscaveshop.com",
                "collection_url": "https://www.sportscaveshop.com/collections/cricket",
                "no_product_link": True,
                "product_url": "https://example.com/should-be-removed",
            }
        )
        self.assertEqual(row["product_url"], "")

    def test_blog_utilities_and_publish_pack(self):
        article = "# Title\n\nOpening words.\n\n## First section\nText here.\n\n## Second section\nMore text."
        self.assertEqual(seo.heading_count(article), 2)
        self.assertGreater(seo.word_count(article), 5)
        validation = seo.meta_validation("x" * 55, "y" * 150)
        self.assertTrue(validation["meta_title_valid"])
        self.assertTrue(validation["meta_description_valid"])
        pack = seo.build_publish_ready_pack(
            {
                "article_title": "Story",
                "article_draft": article,
                "meta_title": "x" * 55,
                "product_url": "",
                "review_checklist": ["Facts verified"],
            }
        )
        self.assertIn("SPORTS CAVE BLOG PUBLISH-READY PACK", pack)
        self.assertIn("Product link: Omitted", pack)
        self.assertIn("Facts verified", pack)


class GSCImportTests(unittest.TestCase):
    def _csv(self, headers, rows):
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        return output.getvalue().encode("utf-8-sig")

    def test_standard_case_insensitive_headers_and_extra_columns(self):
        preview = seo.parse_gsc_csv(
            self._csv(
                ["qUeRy", "CLICKS", "Impressions", "ctr", "POSITION", "Country"],
                [["cricket wall art", "4", "120", "3.3%", "8.2", "Australia"]],
            )
        )
        self.assertEqual(preview["importable_count"], 1)
        row = preview["rows"][0]
        self.assertEqual(row["raw_query"], "cricket wall art")
        self.assertEqual(row["clicks"], 4)
        self.assertEqual(row["extra_columns"], {"Country": "Australia"})
        self.assertEqual(row["buyer_intent"], "Strong")

    def test_missing_query_header_is_rejected(self):
        with self.assertRaisesRegex(seo.SEOValidationError, "Query column"):
            seo.parse_gsc_csv(self._csv(["Clicks", "Impressions"], [[1, 2]]))

    def test_invalid_numbers_duplicates_and_reviewed_existing_are_not_imported(self):
        preview = seo.parse_gsc_csv(
            self._csv(
                ["Query", "Clicks", "Impressions", "CTR", "Position"],
                [
                    ["sports wall art", "1", "10", "10%", "4"],
                    ["Sports Wall Art", "2", "20", "10%", "5"],
                    ["bad row", "not-a-number", "4", "1%", "6"],
                    ["reviewed term", "3", "30", "10%", "7"],
                ],
            ),
            existing_keywords=[{"keyword": "reviewed term", "mapping_status": "Approved"}],
        )
        self.assertEqual(preview["importable_count"], 1)
        self.assertEqual(preview["skipped_count"], 2)
        self.assertEqual(preview["invalid_count"], 1)

    def test_preview_commit_counts_and_csv_export_round_trip(self):
        state = seo.default_state()
        preview = seo.parse_gsc_csv(
            self._csv(
                ["Query", "Clicks", "Impressions", "CTR", "Position"],
                [["motor racing prints", "2", "40", "5%", "9"]],
            )
        )
        self.assertEqual(state["keywords"], [])
        result = seo.commit_gsc_import(state, preview, actor=user())
        self.assertEqual(result["imported"], 1)
        exported = seo.keyword_csv_bytes(state["keywords"]).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(exported)))
        self.assertEqual(rows[0]["Keyword"], "motor racing prints")
        self.assertEqual(rows[0]["Clicks"], "2")

    def test_keyword_to_blog_handoff_maps_without_publishing(self):
        state = seo.default_state()
        keyword = seo.upsert_record(
            state,
            "keywords",
            {"keyword": "nba wall art", "buyer_intent": "Strong", "page_type": "Blog"},
            actor=user(),
        )
        blog = seo.create_blog_brief_from_keyword(state, keyword, actor=user())
        self.assertEqual(blog["status"], "Brief")
        self.assertEqual(blog["primary_keyword"], "nba wall art")
        self.assertNotIn("published_at", blog)
        mapped = next(row for row in state["keywords"] if row["id"] == keyword["id"])
        self.assertEqual(mapped["mapping_status"], "Mapped")


class SEOOverviewAndUIContractTests(unittest.TestCase):
    def test_overview_metrics_are_derived_only_from_records(self):
        state = seo.default_state()
        state["blog_records"] = [{"id": "b1", "status": "Draft"}, {"id": "b2", "status": "Published"}]
        state["keywords"] = [{"id": "k1", "mapping_status": "Mapped"}]
        state["citations"] = [{"id": "c1", "status": "Live"}]
        state["outreach_records"] = [
            {"id": "o1", "status": "Sent"},
            {"id": "o2", "status": "Live"},
        ]
        metrics = seo.overview_metrics(state)
        self.assertEqual(metrics["Blog Posts in Progress"], 1)
        self.assertEqual(metrics["Keywords Mapped"], 1)
        self.assertEqual(metrics["Citations Live"], 1)
        self.assertEqual(metrics["Outreach Pending"], 1)
        self.assertEqual(metrics["Backlinks Live"], 1)

    def test_ui_contains_all_pages_honest_reporting_state_and_no_fake_integrations(self):
        source = (ROOT / "seo_page.py").read_text(encoding="utf-8")
        navigation_source = (ROOT / "seo_navigation.py").read_text(encoding="utf-8")
        for route in seo_navigation.SEO_NAV_LABELS.values():
            self.assertIn(route, navigation_source)
        self.assertNotIn('class="sc-seo-future-value">&mdash;', source)
        self.assertIn('"Main SEO metrics"', source)
        self.assertIn('"Organic Performance"', source)
        self.assertIn("SEO reporting will appear here when GSC, GA4 and Shopify share", source)
        self.assertIn(
            "Not connected",
            (ROOT / "google_seo.py").read_text(encoding="utf-8"),
        )
        self.assertIn("Connect Google", source)
        self.assertIn("Google Search Console", source)
        self.assertIn("Google Analytics 4", source)
        self.assertNotIn('<span class="sc-seo-badge">Planned</span>', source)
        self.assertIn("This module never writes to Shopify", source)
        self.assertIn("This workspace does not send outreach messages", source)
        self.assertNotIn("Klaviyo", source)
        self.assertNotIn("SOP", source)

    def test_prompt_templates_are_central_and_ui_has_preview_not_fake_generate(self):
        source = (ROOT / "seo_page.py").read_text(encoding="utf-8")
        state = seo.default_state()
        names = {row["name"] for row in state["prompt_templates"]}
        self.assertTrue({"Blog topic research", "Article writing", "Keyword extraction", "Site qualification"}.issubset(names))
        self.assertIn("render_prompt_template", source)
        self.assertNotIn('button("Generate', source)


if __name__ == "__main__":
    unittest.main()
