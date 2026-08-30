import csv
import inspect
import io
import json
import unittest
from unittest.mock import patch

import os_accounts
import seo_blog_workflow as workflow
import seo_page


SPORT_OPTIONS = (
    "All Sports / General Sports",
    "Australian Rules Football / AFL",
    "Rugby League / NRL",
    "Rugby Union",
    "Soccer / Football",
    "American Football / NFL",
    "College Football / NCAA",
    "Basketball / NBA",
    "College Basketball / NCAA",
    "WNBA",
    "Baseball / MLB",
    "Cricket",
    "Tennis",
    "Golf",
    "Formula 1",
    "Supercars",
    "Motorsport - General",
    "NASCAR",
    "IndyCar",
    "MotoGP / Motorcycle Racing",
    "Rally / WRC",
    "Le Mans / Endurance Racing",
    "Boxing",
    "MMA / UFC",
    "Professional Wrestling / WWE",
    "Ice Hockey / NHL",
    "Horse Racing",
    "Athletics / Track and Field",
    "Olympics",
    "Swimming",
    "Surfing",
    "Cycling",
    "Netball",
    "Darts",
    "Snooker / Pool",
    "Field Hockey",
    "Lacrosse",
    "Sailing",
    "Other",
)

SEARCH_INTENT_OPTIONS = (
    "Informational - Fan Education",
    "Informational - Athlete / Player Profile",
    "Informational - Team Story",
    "Informational - Career Retrospective",
    "Informational - Historical / Nostalgic Story",
    "Informational - Iconic Moment / Ultimate Moment",
    "Informational - Championship / Season Story",
    "Informational - Records / Statistics",
    "Informational - Rivalry / Head-to-Head",
    "Informational - Fan Debate",
    "Informational - FAQ / People Also Ask",
    "Informational - Evergreen Explainer",
    "Informational - Timely / Trending Story",
    "Informational - Anniversary / Milestone",
    "Informational - Legacy / Tribute",
    "Commercial - Sports Wall Art Guide",
    "Commercial - Collector Guide",
    "Commercial - Gift Guide",
    "Commercial - Best Of / Listicle",
    "Commercial - Product Comparison",
    "Commercial - Room / Man Cave Inspiration",
    "Commercial - Sports Decor Inspiration",
    "Commercial - Collection Buying Guide",
    "Product Support - Individual Product SEO",
    "Product Support - Collection SEO",
    "Product Support - Internal Linking Support",
    "Product Support - Product Story / Meaning",
    "Product Support - Athlete/Product Connection",
    "Search Opportunity - Low CTR Support",
    "Search Opportunity - Position 4-20 Support",
    "Search Opportunity - Long-Tail Keyword Support",
    "Search Opportunity - Topical Authority Support",
    "Other / Custom",
)


def setup_brief():
    return {
        "project_title": "Shane Warne Ashes brief",
        "gsc_seed_query": "shane warne wall art",
        "selected_opportunity": "shane warne wall art",
        "target_markets": ["Australia", "United Kingdom", "New Zealand"],
        "sport": "Cricket",
        "search_intent": "Informational - Historical / Nostalgic Story",
        "language": "English (International)",
        "publication_preference": "Draft",
        "target_entity_id": "gid://shopify/Product/1",
        "target_entity_type": "Product",
        "target_title": "King of Spin",
        "target_url": "https://www.sportscaveshop.com/products/king-of-spin",
        "author": "Nathan",
        "target_blog": "News",
    }


def completed_brief():
    return {
        **setup_brief(),
        "subject": "Shane Warne and the 2005 Ashes",
        "timely_hook": "Twenty years since the series",
        "recommended_article_angle": "Why Warne made every Ashes ball feel decisive",
        "working_article_title": "The Ashes Summer Shane Warne Made Unforgettable",
        "primary_keyword": "shane warne 2005 ashes",
        "supporting_keywords": ["2005 Ashes", "Shane Warne wickets"],
        "related_entities": ["Australia", "England", "Old Trafford"],
        "fan_questions": ["How many wickets did Warne take?", "Why was the 2005 Ashes iconic?"],
        "internal_links": [
            "https://www.sportscaveshop.com/collections/cricket",
            "https://www.sportscaveshop.com/products/king-of-spin",
        ],
        "link_building_authority_angle": "A sourced match-by-match Warne timeline",
        "youtube_url": "https://www.youtube.com/watch?v=verified",
        "target_length": "1400-1700",
        "tags": ["Cricket", "Ashes", "Shane Warne"],
    }


def gsc_opportunity():
    return {
        "query": "shane warne wall art",
        "clicks": 4,
        "impressions": 100,
        "ctr": 0.04,
        "average_position": 9,
        "matched_page": "https://www.sportscaveshop.com/collections/cricket",
        "confidence": "High",
        "score_explanation": "Observed impressions and striking-distance position.",
        "data_through_date": "2026-08-14",
        "recommended_article_type": "Supporting guide or existing article refresh",
    }


class BlogWorkflowTests(unittest.TestCase):
    def test_opportunity_prefill_preserves_manual_values_and_uses_query_as_seed(self):
        result = workflow.prefill_from_opportunity(
            {"gsc_seed_query": "manual seed", "search_intent": "Commercial - Collector Guide"},
            gsc_opportunity(),
        )
        self.assertEqual(result["gsc_seed_query"], "manual seed")
        self.assertEqual(result["search_intent"], "Commercial - Collector Guide")
        self.assertNotIn("primary_keyword", result)
        fresh = workflow.prefill_from_opportunity({}, gsc_opportunity())
        self.assertEqual(fresh["gsc_seed_query"], "shane warne wall art")
        self.assertEqual(fresh["search_intent"], "Search Opportunity - Position 4-20 Support")
        self.assertEqual(fresh["opportunity_snapshot"]["clicks"], 4)

    def test_blog_opportunity_scoring_is_deterministic_and_never_claims_volume(self):
        rows = [{"query": "shane warne art", "clicks": 4, "impressions": 120, "ctr": 0.03, "average_position": 8}]
        first = workflow.build_blog_opportunities(rows, data_through_date="2026-08-14")
        second = workflow.build_blog_opportunities(rows, data_through_date="2026-08-14")
        self.assertEqual(first, second)
        self.assertEqual(first[0]["data_through_date"], "2026-08-14")
        self.assertNotIn("search volume", json.dumps(first, default=str).casefold())

    def test_target_markets_are_full_searchable_iso_options_with_global_exclusivity(self):
        self.assertEqual(workflow.TARGET_MARKET_OPTIONS[:6], (workflow.GLOBAL_MARKET, *workflow.COMMON_TARGET_MARKETS))
        self.assertEqual(len(workflow.ISO_COUNTRIES), 249)
        self.assertEqual(len(set(workflow.ISO_COUNTRIES)), 249)
        self.assertEqual(
            workflow.normalize_target_markets(
                [workflow.GLOBAL_MARKET, "Australia"], previous=[workflow.GLOBAL_MARKET]
            ),
            ["Australia"],
        )
        self.assertEqual(
            workflow.normalize_target_markets(
                ["Australia", workflow.GLOBAL_MARKET], previous=["Australia"]
            ),
            [workflow.GLOBAL_MARKET],
        )
        self.assertEqual(workflow.normalize_target_markets(None), [workflow.GLOBAL_MARKET])
        with self.assertRaisesRegex(workflow.BlogWorkflowError, "not both"):
            workflow.normalize_target_markets(
                [workflow.GLOBAL_MARKET, "Australia"], reject_mixed=True
            )

    def test_sport_and_search_intent_taxonomies_are_exact(self):
        self.assertEqual(workflow.SPORT_OPTIONS, SPORT_OPTIONS)
        self.assertEqual(workflow.SEARCH_INTENT_OPTIONS, SEARCH_INTENT_OPTIONS)

    def test_csv_export_contains_current_selections_and_uses_one_row(self):
        exported = workflow.blog_brief_csv_bytes(
            "Shane Warne Ashes brief", setup_brief(), opportunity=gsc_opportunity()
        )
        self.assertTrue(exported.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.DictReader(io.StringIO(exported.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(tuple(rows[0]), workflow.CSV_FIELDS)
        self.assertEqual(rows[0]["gsc_seed_query"], "shane warne wall art")
        self.assertEqual(rows[0]["target_markets"], "Australia;United Kingdom;New Zealand")
        self.assertEqual(rows[0]["sport"], "Cricket")
        self.assertEqual(rows[0]["product_collection_title"], "King of Spin")
        self.assertEqual(rows[0]["product_collection_url"], setup_brief()["target_url"])

    def test_completed_csv_import_populates_and_round_trips_all_supported_fields(self):
        first_export = workflow.blog_brief_csv_bytes("Shane Warne Ashes brief", completed_brief())
        imported = workflow.parse_blog_brief_csv(
            first_export,
            filename="completed-blog-brief.csv",
            current_brief=setup_brief(),
        )
        self.assertFalse(imported["target_conflict"])
        brief = imported["brief"]
        self.assertEqual(brief["primary_keyword"], "shane warne 2005 ashes")
        self.assertEqual(brief["supporting_keywords"], ["2005 Ashes", "Shane Warne wickets"])
        self.assertEqual(len(brief["fan_questions"]), 2)
        self.assertEqual(len(brief["internal_links"]), 2)
        second_export = workflow.blog_brief_csv_bytes(
            imported["row"]["project_title"],
            workflow.merge_imported_brief(setup_brief(), brief),
        )
        self.assertEqual(first_export.decode("utf-8-sig"), second_export.decode("utf-8-sig"))

    def test_csv_import_rejects_wrong_schema_and_mixed_global_markets(self):
        with self.assertRaisesRegex(workflow.BlogBriefCSVError, "headers exactly"):
            workflow.parse_blog_brief_csv(b"wrong,header\n1,2\n", filename="bad.csv")
        text = workflow.blog_brief_csv_bytes("Brief", completed_brief()).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
        rows[0]["target_markets"] = f"{workflow.GLOBAL_MARKET};Australia"
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=workflow.CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        with self.assertRaisesRegex(workflow.BlogBriefCSVError, "not both"):
            workflow.parse_blog_brief_csv(output.getvalue(), filename="mixed.csv")

    def test_mismatched_shopify_target_requires_a_deliberate_resolution(self):
        different = {
            **completed_brief(),
            "target_title": "Different Product",
            "target_url": "https://www.sportscaveshop.com/products/different-product",
        }
        parsed = workflow.parse_blog_brief_csv(
            workflow.blog_brief_csv_bytes("Different", different),
            filename="different.csv",
            current_brief=setup_brief(),
        )
        self.assertTrue(parsed["target_conflict"])
        self.assertIn("current Shopify selection", parsed["target_conflict_message"])
        kept = workflow.merge_imported_brief(
            setup_brief(), parsed["brief"], keep_current_target=True
        )
        self.assertEqual(kept["target_url"], setup_brief()["target_url"])
        self.assertEqual(kept["primary_keyword"], different["primary_keyword"])

        unselected = workflow.parse_blog_brief_csv(
            workflow.blog_brief_csv_bytes("Different", different),
            filename="unselected.csv",
            current_brief={},
        )
        self.assertTrue(unselected["target_conflict"])
        self.assertIn("No Shopify product/collection is selected", unselected["target_conflict_message"])

    def test_prompt_1_is_a_csv_research_brief_with_real_gsc_and_shopify_context(self):
        prompt = workflow.build_prompt_1(
            "project-1",
            setup_brief(),
            source_date="2026-08-14",
            opportunity=gsc_opportunity(),
        )
        for value in (
            "SPORTS CAVE RESEARCH BLOG BRIEF - PROMPT 1",
            "shane warne wall art",
            "2026-08-14",
            setup_brief()["target_title"],
            setup_brief()["target_url"],
            ",".join(workflow.CSV_FIELDS),
            "header row and exactly one completed data row",
            "Never invent an internal URL",
            "leave timely_hook blank",
        ):
            self.assertIn(value, prompt)
        self.assertNotIn("IMAGE PACKAGE CONTRACT", prompt)
        self.assertNotIn("Return one JSON object", prompt)

    def test_prompt_2_consumes_imported_brief_and_preserves_article_image_rules(self):
        prompt = workflow.build_prompt_2(
            {"project_id": "project-1", "brief": completed_brief()}
        )
        for value in (
            completed_brief()["working_article_title"],
            completed_brief()["primary_keyword"],
            completed_brief()["fan_questions"][0],
            completed_brief()["internal_links"][0],
            setup_brief()["target_url"],
            "no body H1",
            "final third",
            "1600x900",
            "1600x1067",
            "1600x1200",
            "SPORTS_CAVE_IMAGE_REALISM_RULES_V1",
            "actual image assets",
        ):
            self.assertIn(value, prompt)
        self.assertIn("Do not output JSON", prompt)
        self.assertIn("Do not write to Shopify", prompt)
        self.assertNotIn("Publish now", prompt)
        self.assertNotIn("Admin token", prompt)

    def test_blog_specific_json_and_image_permission_workflows_are_removed(self):
        page_source = inspect.getsource(seo_page._render_blog_v2)
        for removed in (
            "Approved source image references",
            "Approved source image uploads",
            "Supplied athlete/product assets are permitted for use",
            "Use non-identifiable editorial imagery",
            "Import Content Package",
            "JSON package",
            "paste the JSON package",
            "Validate package",
            "manual review",
        ):
            self.assertNotIn(removed, page_source)
        for preserved in (
            "_reporting_filters()",
            "Opportunity evidence",
            "Saved GSC opportunity",
            "Use opportunity",
            "Shopify product or collection",
            "Export Brief CSV",
            "Import Completed CSV",
            "Create Prompt 1",
            "Create Prompt 2",
        ):
            self.assertIn(preserved, page_source)

    def test_blog_target_store_remains_a_saved_read_only_selector(self):
        source = inspect.getsource(workflow.PostgresBlogProjectStore.list_shopify_targets)
        self.assertIn("shopify_products", source)
        self.assertIn("seo_canonical_pages", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("shopify_sync", source)


class FakeStreamlit:
    class Node:
        def __init__(self, owner):
            self.owner = owner

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def button(self, *_args, **_kwargs):
            return False

        def caption(self, value, *_args, **_kwargs):
            self.owner.events.append(str(value))

        def download_button(self, *_args, **_kwargs):
            return False

        def markdown(self, value, *_args, **_kwargs):
            self.owner.events.append(str(value))

        def selectbox(self, label, options, *args, **kwargs):
            return self.owner.selectbox(label, options, *args, **kwargs)

        def multiselect(self, label, options, *args, **kwargs):
            return self.owner.multiselect(label, options, *args, **kwargs)

        def text_input(self, label, *args, **kwargs):
            return self.owner.text_input(label, *args, **kwargs)

        def text_area(self, label, *args, **kwargs):
            return self.owner.text_area(label, *args, **kwargs)

        def date_input(self, *_args, **_kwargs):
            return None

    def __init__(self):
        self.session_state = {}
        self.events = []

    def columns(self, spec, *_args, **_kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [self.Node(self) for _ in range(count)]

    def expander(self, label, *_args, **_kwargs):
        self.events.append(label)
        return self.Node(self)

    def popover(self, label, *_args, **_kwargs):
        self.events.append(label)
        return self.Node(self)

    def markdown(self, value, *_args, **_kwargs):
        self.events.append(str(value))

    def subheader(self, value, *_args, **_kwargs):
        self.events.append(str(value))

    def caption(self, value, *_args, **_kwargs):
        self.events.append(str(value))

    def info(self, value, *_args, **_kwargs):
        self.events.append(str(value))

    warning = info
    error = info
    success = info

    def selectbox(self, _label, options, *_args, **kwargs):
        options = tuple(options)
        key = kwargs.get("key")
        if key and self.session_state.get(key) in options:
            return self.session_state[key]
        index = int(kwargs.get("index") or 0)
        selected = options[index]
        if key:
            self.session_state[key] = selected
        return selected

    def multiselect(self, _label, _options, *_args, **kwargs):
        key = kwargs.get("key")
        return list(self.session_state.get(key) or kwargs.get("default") or [])

    def text_input(self, _label, *_args, **kwargs):
        key = kwargs.get("key")
        return str(self.session_state.get(key, kwargs.get("value") or ""))

    def text_area(self, _label, *_args, **kwargs):
        key = kwargs.get("key")
        return str(self.session_state.get(key, kwargs.get("value") or ""))

    def file_uploader(self, *_args, **_kwargs):
        return None

    def dataframe(self, *_args, **_kwargs):
        return None

    def button(self, *_args, **_kwargs):
        return False


class FakeProjectStore:
    def __init__(self):
        self.project = {
            "project_id": "project-1",
            "owner_id": "admin-1",
            "owner_name": "Nathan",
            "status": "Idea",
            "title": "Shane Warne brief",
            "primary_keyword": "",
            "target_url": setup_brief()["target_url"],
            "brief": setup_brief(),
            "opportunity_snapshot": gsc_opportunity(),
            "prompt_1": "",
            "prompt_2": "",
        }
        self.saved = []

    def list_projects(self, **_kwargs):
        return [dict(self.project)]

    def save_project(self, project):
        self.project = dict(project)
        self.saved.append(dict(project))
        return dict(project)

    def record_event(self, *_args, **_kwargs):
        return False


class SavedReportingReader:
    def snapshot(self, **_kwargs):
        return {
            "health": {"gsc": {"through_date": "2026-08-14"}},
            "top_queries": [],
        }


class BlogPageLoadTests(unittest.TestCase):
    def test_imported_brief_widget_state_survives_reruns(self):
        ui = FakeStreamlit()
        imported = completed_brief()
        with patch.object(seo_page, "st", ui):
            seo_page._seed_blog_widget_state("project-1", imported, overwrite=True)
            first = seo_page._brief_from_blog_widget_state("project-1", imported)
            second = seo_page._brief_from_blog_widget_state("project-1", first)

        self.assertEqual(second["target_markets"], imported["target_markets"])
        self.assertEqual(second["sport"], imported["sport"])
        self.assertEqual(second["search_intent"], imported["search_intent"])
        self.assertEqual(second["primary_keyword"], imported["primary_keyword"])
        self.assertEqual(second["supporting_keywords"], imported["supporting_keywords"])
        self.assertEqual(second["fan_questions"], imported["fan_questions"])
        self.assertEqual(second["target_url"], imported["target_url"])

    def test_blog_page_loads_from_saved_data_without_external_calls(self):
        ui = FakeStreamlit()
        store = FakeProjectStore()
        target = {
            "id": setup_brief()["target_entity_id"],
            "entity_type": "Product",
            "title": setup_brief()["target_title"],
            "url": setup_brief()["target_url"],
            "sport": "Cricket",
        }
        user = {
            "id": "admin-1",
            "display_name": "Nathan",
            "role": os_accounts.ROLE_ADMIN,
            "is_active": True,
        }
        with patch.object(seo_page, "st", ui), patch.object(
            seo_page, "_cached_blog_shopify_targets", return_value=[target]
        ), patch.object(
            seo_page.google_seo, "refresh_access_token", side_effect=AssertionError("external Google call")
        ), patch.object(
            seo_page.google_seo_import, "queue_imports", side_effect=AssertionError("sync call")
        ):
            seo_page._render_blog_v2(
                {"target_library": []},
                user,
                reporting_reader=SavedReportingReader(),
                project_store=store,
            )

        rendered = " ".join(ui.events)
        self.assertIn("1. Find the opportunity", rendered)
        self.assertIn("2. Build the blog brief", rendered)
        self.assertIn("3. Create the blog", rendered)
        self.assertTrue(store.saved)


if __name__ == "__main__":
    unittest.main()
