import csv
import inspect
import io
import json
import unittest
import zipfile
from unittest.mock import patch

import os_accounts
import seo_blog_workflow as workflow
import seo_page


FINAL_CSV_FIELDS = (
    "gsc_seed_query",
    "target_markets",
    "sport",
    "search_intent_article_type",
    "topic_entity",
    "timely_hook",
    "recommended_article_angle",
    "working_article_title",
    "primary_keyword",
    "supporting_keywords",
    "related_entities",
    "fan_questions",
    "product_collection_title",
    "product_collection_url",
    "verified_internal_links",
    "youtube_url",
    "target_word_count",
    "tags",
)


def seed_brief():
    return {
        "gsc_seed_query": "shane warne wall art",
        "selected_opportunity": "shane warne wall art",
        "author": "Nathan",
        "target_blog": "News",
        "publication_preference": "Draft",
    }


def completed_brief():
    return {
        **seed_brief(),
        "target_markets": ["Australia", "United Kingdom", "New Zealand"],
        "sport": "Cricket",
        "search_intent": "Informational - Historical / Nostalgic Story",
        "language": "English (International)",
        "subject": "Shane Warne and the 2005 Ashes",
        "timely_hook": "Twenty years since the series",
        "recommended_article_angle": "Why Warne made every Ashes ball feel decisive",
        "working_article_title": "The Ashes Summer Shane Warne Made Unforgettable",
        "primary_keyword": "shane warne 2005 ashes",
        "supporting_keywords": ["2005 Ashes", "Shane Warne wickets"],
        "related_entities": ["Australia", "England", "Old Trafford"],
        "fan_questions": [
            "How many wickets did Warne take?",
            "Why was the 2005 Ashes iconic?",
        ],
        "target_title": "King of Spin",
        "target_url": "https://www.sportscaveshop.com/products/king-of-spin",
        "internal_links": [
            "https://www.sportscaveshop.com/collections/cricket",
            "https://www.sportscaveshop.com/products/king-of-spin",
        ],
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


def product_context():
    return [
        {
            "id": "gid://shopify/Product/1",
            "entity_type": "Product",
            "title": "King of Spin",
            "url": "https://www.sportscaveshop.com/products/king-of-spin",
            "sport": "Cricket",
        },
        {
            "id": "collection-1",
            "entity_type": "Collection",
            "title": "Cricket Wall Art",
            "url": "https://www.sportscaveshop.com/collections/cricket",
            "sport": "Cricket",
        },
        {
            "entity_type": "Product",
            "title": "Ignore external",
            "url": "https://example.com/not-sports-cave",
        },
    ]


class BlogWorkflowTests(unittest.TestCase):
    def test_opportunity_selection_starts_fresh_research_and_preserves_operational_defaults(self):
        old = {**completed_brief(), "author": "Nathan", "target_blog": "News"}
        next_opportunity = {**gsc_opportunity(), "query": "allan border captain wall art"}
        result = workflow.prefill_from_opportunity(old, next_opportunity)

        self.assertEqual(result["gsc_seed_query"], "allan border captain wall art")
        self.assertEqual(result["selected_opportunity"], "allan border captain wall art")
        self.assertEqual(result["opportunity_snapshot"], next_opportunity)
        self.assertEqual(result["author"], "Nathan")
        self.assertEqual(result["target_blog"], "News")
        for researched_field in (
            "sport",
            "search_intent",
            "subject",
            "primary_keyword",
            "target_title",
            "target_url",
            "internal_links",
        ):
            self.assertFalse(result.get(researched_field))

    def test_blog_opportunity_scoring_is_unchanged_and_evidence_based(self):
        rows = [
            {
                "query": "shane warne art",
                "clicks": 4,
                "impressions": 120,
                "ctr": 0.03,
                "average_position": 8,
            }
        ]
        first = workflow.build_blog_opportunities(rows, data_through_date="2026-08-14")
        second = workflow.build_blog_opportunities(rows, data_through_date="2026-08-14")
        self.assertEqual(first, second)
        self.assertEqual(first[0]["data_through_date"], "2026-08-14")
        self.assertNotIn("search volume", json.dumps(first, default=str).casefold())

    def test_market_taxonomy_remains_available_for_chatgpt_validation(self):
        self.assertEqual(
            workflow.TARGET_MARKET_OPTIONS[:6],
            (workflow.GLOBAL_MARKET, *workflow.COMMON_TARGET_MARKETS),
        )
        self.assertEqual(len(workflow.ISO_COUNTRIES), 249)
        self.assertEqual(workflow.normalize_target_markets(None), [])
        with self.assertRaisesRegex(workflow.BlogWorkflowError, "not both"):
            workflow.normalize_target_markets(
                [workflow.GLOBAL_MARKET, "Australia"], reject_mixed=True
            )

    def test_final_research_csv_schema_is_concise(self):
        self.assertEqual(workflow.CSV_FIELDS, FINAL_CSV_FIELDS)
        for removed in (
            "project_title",
            "language",
            "draft_schedule_preference",
            "link_building_authority_angle",
            "author",
            "target_shopify_blog",
        ):
            self.assertNotIn(removed, workflow.CSV_FIELDS)

    def test_blank_template_contains_only_the_selected_gsc_query(self):
        exported = workflow.blog_brief_template_csv_bytes(
            seed_brief(), opportunity=gsc_opportunity()
        )
        self.assertTrue(exported.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.DictReader(io.StringIO(exported.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(tuple(rows[0]), FINAL_CSV_FIELDS)
        self.assertEqual(rows[0]["gsc_seed_query"], "shane warne wall art")
        self.assertTrue(
            all(not value for key, value in rows[0].items() if key != "gsc_seed_query")
        )

    def test_research_pack_contains_prompt_template_and_safe_product_reference(self):
        packed = workflow.build_research_pack(
            "project-1",
            seed_brief(),
            source_date="2026-08-14",
            opportunity=gsc_opportunity(),
            product_context=product_context(),
        )
        with zipfile.ZipFile(io.BytesIO(packed)) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {
                    "PROMPT_1_RESEARCH.txt",
                    "BLOG_BRIEF_TEMPLATE.csv",
                    "SPORTS_CAVE_PAGE_REFERENCE.csv",
                },
            )
            prompt = archive.read("PROMPT_1_RESEARCH.txt").decode("utf-8")
            template_rows = list(
                csv.DictReader(
                    io.StringIO(
                        archive.read("BLOG_BRIEF_TEMPLATE.csv").decode("utf-8-sig")
                    )
                )
            )
            reference = archive.read("SPORTS_CAVE_PAGE_REFERENCE.csv").decode("utf-8-sig")
        self.assertIn("shane warne wall art", prompt)
        self.assertEqual(template_rows[0]["gsc_seed_query"], "shane warne wall art")
        self.assertIn("King of Spin", reference)
        self.assertIn("Cricket Wall Art", reference)
        self.assertNotIn("example.com", reference)

    def test_prompt_1_is_the_strategy_brain_and_contains_real_gsc_evidence(self):
        prompt = workflow.build_prompt_1(
            "project-1",
            seed_brief(),
            source_date="2026-08-14",
            opportunity=gsc_opportunity(),
            product_context=product_context(),
        )
        for required in (
            "SPORTS CAVE SEO BLOG STRATEGY RESEARCH - PROMPT 1",
            "shane warne wall art",
            "Clicks: 4",
            "Impressions: 100",
            "Decide the best target country or countries",
            "Classify the sport",
            "Determine the dominant search intent",
            "Research the CURRENT public Sports Cave storefront",
            "choose the best genuine live product or",
            "collection for natural commercial support",
            "Never invent a URL",
            "Preserve gsc_seed_query exactly as supplied",
            ",".join(FINAL_CSV_FIELDS),
        ):
            self.assertIn(required, prompt)
        self.assertNotIn("SELECTED SPORTS CAVE PRODUCT OR COLLECTION", prompt)
        self.assertNotIn("IMAGE PACKAGE CONTRACT", prompt)

    def test_prompt_1_translates_raw_poster_demand_into_brand_vocabulary(self):
        brief = seed_brief()
        brief["gsc_seed_query"] = "messi poster"
        opportunity = {**gsc_opportunity(), "query": "messi poster"}
        prompt = workflow.build_prompt_1(
            "project-1",
            brief,
            source_date="2026-08-14",
            opportunity=opportunity,
            product_context=product_context(),
        )

        self.assertIn("messi poster", prompt)
        self.assertIn("Preserve gsc_seed_query exactly", prompt)
        self.assertIn("real Google demand evidence", prompt)
        self.assertIn("premium limited-edition sports wall-art and collector brand", prompt)
        self.assertIn('Never choose "poster" or "posters"', prompt)
        self.assertIn("Translate that demand", prompt)
        self.assertIn("athlete wall art", prompt)
        self.assertIn("verified legacy Sports Cave URL", prompt)

    def test_completed_csv_imports_and_multi_values_round_trip(self):
        first = workflow.blog_brief_csv_bytes("ignored", completed_brief())
        parsed = workflow.parse_blog_brief_csv(
            first,
            filename="completed-blog-brief.csv",
            current_brief=seed_brief(),
        )
        imported = parsed["brief"]
        self.assertEqual(imported["primary_keyword"], "shane warne 2005 ashes")
        self.assertEqual(imported["supporting_keywords"], ["2005 Ashes", "Shane Warne wickets"])
        self.assertEqual(imported["target_markets"], ["Australia", "United Kingdom", "New Zealand"])
        second = workflow.blog_brief_csv_bytes(
            "ignored", workflow.merge_imported_brief(seed_brief(), imported)
        )
        self.assertEqual(first.decode("utf-8-sig"), second.decode("utf-8-sig"))

    def test_import_rejects_wrong_schema_wrong_seed_and_non_sports_cave_target(self):
        with self.assertRaisesRegex(workflow.BlogBriefCSVError, "headers exactly"):
            workflow.parse_blog_brief_csv(b"wrong,header\n1,2\n", filename="bad.csv")

        wrong_seed = completed_brief()
        wrong_seed["gsc_seed_query"] = "different opportunity"
        with self.assertRaisesRegex(workflow.BlogBriefCSVError, "different GSC opportunity"):
            workflow.parse_blog_brief_csv(
                workflow.blog_brief_csv_bytes("ignored", wrong_seed),
                filename="wrong-seed.csv",
                current_brief=seed_brief(),
            )

        external = completed_brief()
        external["target_url"] = "https://example.com/fake-product"
        with self.assertRaisesRegex(workflow.BlogBriefCSVError, "Sports Cave storefront URL"):
            workflow.parse_blog_brief_csv(
                workflow.blog_brief_csv_bytes("ignored", external),
                filename="external.csv",
                current_brief=seed_brief(),
            )

    def test_raw_gsc_poster_query_and_legacy_url_are_preserved(self):
        brief = completed_brief()
        brief["gsc_seed_query"] = "messi poster"
        brief["selected_opportunity"] = "messi poster"
        brief["primary_keyword"] = "Lionel Messi wall art"
        brief["supporting_keywords"] = ["Messi framed wall art", "Argentina football wall art"]
        brief["working_article_title"] = "The Moments That Made Lionel Messi Immortal"
        brief["target_title"] = "Lionel Messi Collector Wall Art"
        brief["target_url"] = "https://www.sportscaveshop.com/products/legacy-messi-poster"
        brief["internal_links"] = [
            "https://www.sportscaveshop.com/products/legacy-messi-poster",
            "https://www.sportscaveshop.com/collections/football-wall-art",
        ]

        parsed = workflow.parse_blog_brief_csv(
            workflow.blog_brief_csv_bytes("ignored", brief),
            filename="completed.csv",
            current_brief={"gsc_seed_query": "messi poster"},
        )["brief"]

        self.assertEqual("messi poster", parsed["gsc_seed_query"])
        self.assertEqual(brief["target_url"], parsed["target_url"])
        self.assertEqual(brief["internal_links"], parsed["internal_links"])
        self.assertEqual("Lionel Messi wall art", parsed["primary_keyword"])

    def test_completed_csv_rejects_prohibited_customer_facing_vocabulary(self):
        invalid_values = (
            ("primary_keyword", "Shane Warne poster"),
            ("supporting_keywords", ["Cricket POSTERS"]),
            ("recommended_article_angle", "The collector poster every fan remembers"),
            ("working_article_title", "A pOsTeR Tribute to Shane Warne"),
            ("fan_questions", ["Which posters remember the 2005 Ashes?"]),
            ("tags", ["Cricket", "Poster"]),
        )
        for field, value in invalid_values:
            with self.subTest(field=field):
                brief = completed_brief()
                brief[field] = value
                with self.assertRaisesRegex(
                    workflow.BlogBriefCSVError,
                    "Sports Cave brand rule: replace 'poster' terminology",
                ):
                    workflow.parse_blog_brief_csv(
                        workflow.blog_brief_csv_bytes("ignored", brief),
                        filename="completed.csv",
                        current_brief=seed_brief(),
                    )

    def test_brand_vocabulary_guard_accepts_natural_wall_art_and_collector_language(self):
        brief = completed_brief()
        brief["primary_keyword"] = "Shane Warne limited-edition wall art"
        brief["supporting_keywords"] = [
            "Shane Warne framed wall art",
            "cricket collector edition",
        ]
        validated = workflow.validate_brief(brief, article_ready=True)
        self.assertEqual(brief["primary_keyword"], validated["primary_keyword"])

    def test_prompt_2_consumes_all_research_and_preserves_article_image_rules(self):
        prompt = workflow.build_prompt_2(
            {"project_id": "project-1", "brief": completed_brief()}
        )
        row = workflow.blog_brief_csv_row("ignored", completed_brief())
        for field, value in row.items():
            self.assertIn(field, prompt)
            if value:
                self.assertIn(value, prompt)
        for rule in (
            "no body H1",
            "final third",
            "1600x900",
            "1600x1067",
            "1600x1200",
            "SPORTS_CAVE_IMAGE_REALISM_RULES_V1",
            "actual image assets",
            "Do not write to Shopify",
            "CUSTOMER-FACING VOCABULARY LOCK",
            'Never use "poster" or "posters"',
            "Raw GSC evidence may remain unchanged",
        ):
            self.assertIn(rule, prompt)
        self.assertNotIn("Publish now", prompt)

    def test_publish_prompt_is_universal_conversation_bound_and_complete(self):
        project = {
            "project_id": "project-1",
            "brief": completed_brief(),
            "prompt_2": workflow.build_prompt_2(
                {"project_id": "project-1", "brief": completed_brief()}
            ),
        }
        prompt = workflow.build_publish_prompt(project)
        prompt_text = " ".join(prompt.split())

        for required in (
            "SPORTS CAVE SEO BLOG - FINAL SHOPIFY PUBLISH",
            "SAME ChatGPT conversation",
            "FINAL approved package",
            "source of truth",
            "Prompt 2 may have refined the strategy",
            "Featured / cover image - 16:9, target 1600x900",
            "Editorial / support image - 3:2, target 1600x1067",
            "Product / room mockup - 4:3, target 1600x1200",
            "permanent Shopify CDN URL",
            "PREVENT DUPLICATES",
            "global, key title_tag",
            "global, key description_tag",
            "PUBLISH THE APPROVED ARTICLE LIVE once validation succeeds",
            "PUBLISH AND READ BACK",
            "LIVE STOREFRONT QA",
            "SPORTS CAVE VOCABULARY SAFETY GATE",
            "legacy slug",
            "Sports Cave vocabulary: PASS",
            "PROJECT ID: project-1",
        ):
            self.assertIn(" ".join(required.split()), prompt_text)
        for article_specific in (
            "Messi",
            "Lionel",
            "Shane Warne",
            "King of Spin",
            "king-of-spin",
            "shane warne 2005 ashes",
        ):
            self.assertNotIn(article_specific, prompt_text)

        source = inspect.getsource(workflow.build_publish_prompt)
        self.assertNotIn("shopify_sync", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("graphql_request", source)

    def test_main_blog_ui_has_only_the_compact_normal_workflow(self):
        source = inspect.getsource(seo_page._render_blog_v2)
        for required in (
            'st.expander("Opportunity filters", expanded=False)',
            "_reporting_filters()",
            'st.expander("Opportunity evidence", expanded=False)',
            '"Saved GSC opportunity"',
            '"Download Research Pack"',
            '"Import completed brief"',
            'st.expander("Review brief", expanded=False)',
            '"Download Blog Prompt"',
            'st.expander("Prompt 2 preview", expanded=False)',
            'st.subheader("5. Publish the blog")',
            '"Download Publish Prompt"',
            '"seo_blog_publish_prompt_downloaded"',
            'st.expander("Publish Prompt preview", expanded=False)',
            'st.expander("History", expanded=False)',
        ):
            self.assertIn(required, source)
        for removed in (
            "Use opportunity",
            "Shopify product or collection",
            "Language",
            "Draft / schedule preference",
            "Save draft",
            "Export Brief CSV",
            "Create Prompt 1",
            "Download Prompt 1",
            "Create Prompt 2",
            "Create Prompt 3",
            "Validate package",
            "JSON package",
            "Approved source image",
        ):
            self.assertNotIn(removed, source)
        self.assertLess(source.index('st.expander("Review brief"'), source.index('"Target markets"'))
        self.assertLess(source.index('st.subheader("5. Publish the blog")'), source.index('st.expander("History"'))
        self.assertNotIn("edition_", source)

    def test_product_context_store_is_saved_read_only_data(self):
        source = inspect.getsource(workflow.PostgresBlogProjectStore.list_shopify_targets)
        self.assertIn("shopify_products", source)
        self.assertIn("seo_canonical_pages", source)
        self.assertIn("status", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("shopify_sync", source)
        self.assertNotIn("edition_products", source)


class RerunRequested(RuntimeError):
    pass


class UploadedCSV:
    def __init__(self, data, name="completed-blog-brief.csv"):
        self.data = data
        self.name = name

    def getvalue(self):
        return self.data


class FakeStreamlit:
    class Node:
        def __init__(self, owner):
            self.owner = owner

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def button(self, *args, **kwargs):
            return self.owner.button(*args, **kwargs)

        def caption(self, value, *_args, **_kwargs):
            self.owner.events.append(str(value))

        def download_button(self, *args, **kwargs):
            return self.owner.download_button(*args, **kwargs)

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

        def date_input(self, *args, **kwargs):
            return self.owner.date_input(*args, **kwargs)

    def __init__(self, uploaded_file=None):
        self.session_state = {}
        self.events = []
        self.uploaded_file = uploaded_file

    def columns(self, spec, *_args, **_kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [self.Node(self) for _ in range(count)]

    def expander(self, label, *args, **kwargs):
        self.events.append(f"expander:{label}:{kwargs.get('expanded')}")
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

    def selectbox(self, label, options, *_args, **kwargs):
        self.events.append(f"select:{label}")
        options = tuple(options)
        key = kwargs.get("key")
        if key and self.session_state.get(key) in options:
            return self.session_state[key]
        index = int(kwargs.get("index") or 0)
        selected = options[index]
        if key:
            self.session_state[key] = selected
        return selected

    def multiselect(self, label, _options, *_args, **kwargs):
        self.events.append(f"multiselect:{label}")
        key = kwargs.get("key")
        return list(self.session_state.get(key) or kwargs.get("default") or [])

    def text_input(self, label, *_args, **kwargs):
        self.events.append(f"input:{label}")
        key = kwargs.get("key")
        return str(self.session_state.get(key, kwargs.get("value") or ""))

    def text_area(self, label, *_args, **kwargs):
        self.events.append(f"textarea:{label}")
        key = kwargs.get("key")
        return str(self.session_state.get(key, kwargs.get("value") or ""))

    def file_uploader(self, label, *_args, **_kwargs):
        self.events.append(f"upload:{label}")
        return self.uploaded_file

    def download_button(self, label, *_args, **_kwargs):
        self.events.append(f"download:{label}")
        return False

    def date_input(self, *_args, **_kwargs):
        return None

    def dataframe(self, *_args, **_kwargs):
        return None

    def button(self, *_args, **_kwargs):
        return False

    def rerun(self):
        raise RerunRequested()


class FakeProjectStore:
    def __init__(self):
        self.project = {
            "project_id": "project-1",
            "owner_id": "admin-1",
            "owner_name": "Nathan",
            "status": "Idea",
            "title": "Shane Warne brief",
            "primary_keyword": "",
            "target_url": "",
            "brief": seed_brief(),
            "opportunity_snapshot": gsc_opportunity(),
            "prompt_1": "",
            "prompt_1_hash": "",
            "prompt_2": "",
            "prompt_2_hash": "",
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
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def snapshot(self, **_kwargs):
        return {
            "health": {"gsc": {"through_date": "2026-08-14"}},
            "top_queries": self.rows,
        }


class BlogPageLoadTests(unittest.TestCase):
    def setUp(self):
        self.user = {
            "id": "admin-1",
            "display_name": "Nathan",
            "role": os_accounts.ROLE_ADMIN,
            "is_active": True,
        }

    def test_blog_page_loads_without_external_calls_and_auto_persists_prompt_1(self):
        ui = FakeStreamlit()
        store = FakeProjectStore()
        with patch.object(seo_page, "st", ui), patch.object(
            seo_page, "_cached_blog_shopify_targets", return_value=product_context()
        ), patch.object(
            seo_page.google_seo, "refresh_access_token", side_effect=AssertionError("external Google call")
        ), patch.object(
            seo_page.google_seo_import, "queue_imports", side_effect=AssertionError("sync call")
        ):
            seo_page._render_blog_v2(
                {"target_library": []},
                self.user,
                reporting_reader=SavedReportingReader(),
                project_store=store,
            )

        rendered = " ".join(ui.events)
        self.assertIn("1. Choose an opportunity", rendered)
        self.assertIn("download:Download Research Pack", rendered)
        self.assertIn("upload:Import completed brief", rendered)
        self.assertIn("download:Download Blog Prompt", rendered)
        self.assertIn("expander:Opportunity filters:False", rendered)
        self.assertIn("expander:Opportunity evidence:False", rendered)
        self.assertIn("expander:History:False", rendered)
        self.assertTrue(store.project["prompt_1"])
        self.assertEqual(store.project["brief"]["gsc_seed_query"], "shane warne wall art")

    def test_completed_csv_import_automatically_persists_and_builds_prompt_2(self):
        uploaded = UploadedCSV(workflow.blog_brief_csv_bytes("ignored", completed_brief()))
        ui = FakeStreamlit(uploaded)
        store = FakeProjectStore()
        with patch.object(seo_page, "st", ui), patch.object(
            seo_page, "_cached_blog_shopify_targets", return_value=product_context()
        ), patch.object(
            seo_page.google_seo, "refresh_access_token", side_effect=AssertionError("external Google call")
        ), patch.object(
            seo_page.google_seo_import, "queue_imports", side_effect=AssertionError("sync call")
        ):
            with self.assertRaises(RerunRequested):
                seo_page._render_blog_v2(
                    {"target_library": []},
                    self.user,
                    reporting_reader=SavedReportingReader(),
                    project_store=store,
                )

        self.assertEqual(store.project["status"], "Brief ready")
        self.assertEqual(store.project["brief"]["primary_keyword"], "shane warne 2005 ashes")
        self.assertIn("shane warne 2005 ashes", store.project["prompt_2"])
        self.assertIn("1600x900", store.project["prompt_2"])

        rerun_ui = FakeStreamlit()
        rerun_ui.session_state.update(ui.session_state)
        with patch.object(seo_page, "st", rerun_ui), patch.object(
            seo_page, "_cached_blog_shopify_targets", return_value=product_context()
        ), patch.object(
            seo_page.google_seo, "refresh_access_token", side_effect=AssertionError("external Google call")
        ), patch.object(
            seo_page.google_seo_import, "queue_imports", side_effect=AssertionError("sync call")
        ):
            seo_page._render_blog_v2(
                {"target_library": []},
                self.user,
                reporting_reader=SavedReportingReader(),
                project_store=store,
            )

        rendered = " ".join(rerun_ui.events)
        self.assertIn("5. Publish the blog", rendered)
        self.assertIn("download:Download Publish Prompt", rendered)
        self.assertIn("expander:Publish Prompt preview:False", rendered)

    def test_dropdown_selection_automatically_replaces_the_current_seed(self):
        next_query = "allan border captain wall art"
        next_row = {
            "query": next_query,
            "clicks": 2,
            "impressions": 80,
            "ctr": 0.025,
            "average_position": 11,
        }
        ui = FakeStreamlit()
        ui.session_state[f"{workflow.STATE_PREFIX}opportunity::project-1"] = next_query
        store = FakeProjectStore()
        with patch.object(seo_page, "st", ui), patch.object(
            seo_page, "_cached_blog_shopify_targets", return_value=product_context()
        ):
            seo_page._render_blog_v2(
                {"target_library": []},
                self.user,
                reporting_reader=SavedReportingReader([next_row]),
                project_store=store,
            )

        self.assertEqual(store.project["brief"]["gsc_seed_query"], next_query)
        self.assertEqual(store.project["opportunity_snapshot"]["query"], next_query)
        self.assertEqual(store.project["title"], next_query)
        self.assertIn(next_query, store.project["prompt_1"])
        self.assertFalse(store.project["prompt_2"])


if __name__ == "__main__":
    unittest.main()
