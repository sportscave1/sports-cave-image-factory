import html
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

import seo_blog_workflow as workflow


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "tests" / "fixtures" / "seo_blog_import_app.py"


def completed_brief(*, title="The Ashes Summer Shane Warne Made Unforgettable", keyword="shane warne 2005 ashes"):
    return {
        "gsc_seed_query": "shane warne wall art",
        "selected_opportunity": "shane warne wall art",
        "target_markets": ["Australia", "United Kingdom", "New Zealand"],
        "sport": "Cricket",
        "search_intent": "Informational - Historical / Nostalgic Story",
        "language": "English (International)",
        "publication_preference": "Draft",
        "subject": "Shane Warne and the 2005 Ashes",
        "timely_hook": "Twenty years since the series",
        "recommended_article_angle": "Why Warne made every Ashes ball feel decisive",
        "working_article_title": title,
        "primary_keyword": keyword,
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
        "author": "Nathan",
        "target_blog": "News",
    }


def upload_value(brief, name="completed-blog-brief.csv"):
    return [(name, workflow.blog_brief_csv_bytes("ignored", brief), "text/csv")]


def rendered_text(app):
    values = []
    for element_type in ("markdown", "caption", "error", "warning", "success", "subheader"):
        values.extend(str(item.value) for item in getattr(app, element_type))
    values.extend(item.label for item in app.button)
    values.extend(item.label for item in app.expander)
    values.extend(item.label for item in app.get("download_button"))
    return "\n".join(values)


class SEOBlogStreamlitLifecycleTests(unittest.TestCase):
    def run_blog(self):
        app = AppTest.from_file(str(APP), default_timeout=20).run(timeout=20)
        self.assertEqual([], list(app.exception))
        return app

    def assert_ready_ui(self, app, *, title, keyword):
        text = rendered_text(app)
        self.assertEqual([], list(app.exception))
        self.assertIn("Research imported", text)
        self.assertIn(html.escape(title), text)
        self.assertIn(keyword, text)
        self.assertIn("Review brief", [item.label for item in app.expander])
        self.assertIn("Prompt 2 preview", [item.label for item in app.expander])
        self.assertIn("History", [item.label for item in app.expander])
        self.assertIn("Download Blog Prompt", text)
        self.assertEqual(1, len(app.file_uploader))

    def test_successful_import_rerun_navigation_and_review_edit(self):
        brief = completed_brief()
        app = self.run_blog()
        app.file_uploader[0].set_value(upload_value(brief))
        app.run(timeout=20)

        self.assert_ready_ui(
            app,
            title=brief["working_article_title"],
            keyword=brief["primary_keyword"],
        )
        store = app.session_state["_seo_blog_import_store"]
        self.assertEqual(brief["primary_keyword"], store.project["brief"]["primary_keyword"])
        self.assertIn(brief["primary_keyword"], store.project["prompt_2"])

        app.run(timeout=20)
        self.assert_ready_ui(
            app,
            title=brief["working_article_title"],
            keyword=brief["primary_keyword"],
        )

        app.radio[0].set_value("Other").run(timeout=20)
        self.assertIn("Other route", [item.value for item in app.markdown])
        app.radio[0].set_value("Blog").run(timeout=20)
        self.assert_ready_ui(
            app,
            title=brief["working_article_title"],
            keyword=brief["primary_keyword"],
        )

        primary_keyword = next(item for item in app.text_input if item.label == "Primary keyword")
        primary_keyword.set_value("shane warne ashes legacy").run(timeout=20)
        self.assertEqual([], list(app.exception))
        store = app.session_state["_seo_blog_import_store"]
        self.assertEqual("shane warne ashes legacy", store.project["brief"]["primary_keyword"])
        self.assertIn("shane warne ashes legacy", store.project["prompt_2"])

    def test_uploader_rotates_and_accepts_a_replacement_csv(self):
        first = completed_brief()
        replacement = completed_brief(
            title="Shane Warne's Ashes Legacy, Revisited",
            keyword="shane warne ashes legacy",
        )
        app = self.run_blog()
        first_key = app.file_uploader[0].key
        app.file_uploader[0].set_value(upload_value(first, "first.csv")).run(timeout=20)
        self.assert_ready_ui(
            app,
            title=first["working_article_title"],
            keyword=first["primary_keyword"],
        )
        second_key = app.file_uploader[0].key
        self.assertNotEqual(first_key, second_key)

        app.file_uploader[0].set_value(upload_value(replacement, "replacement.csv")).run(timeout=20)
        self.assert_ready_ui(
            app,
            title=replacement["working_article_title"],
            keyword=replacement["primary_keyword"],
        )
        self.assertNotEqual(second_key, app.file_uploader[0].key)
        store = app.session_state["_seo_blog_import_store"]
        self.assertEqual(replacement["primary_keyword"], store.project["brief"]["primary_keyword"])
        self.assertIn(replacement["primary_keyword"], store.project["prompt_2"])

    def test_target_market_callback_keeps_global_mutually_exclusive(self):
        brief = completed_brief()
        app = self.run_blog()
        app.file_uploader[0].set_value(upload_value(brief)).run(timeout=20)

        markets = next(item for item in app.multiselect if item.label == "Target markets")
        markets.set_value([workflow.GLOBAL_MARKET, "Australia"]).run(timeout=20)

        self.assertEqual([], list(app.exception))
        market_key = f"{workflow.STATE_PREFIX}project-1-markets"
        self.assertEqual([workflow.GLOBAL_MARKET], app.session_state[market_key])
        store = app.session_state["_seo_blog_import_store"]
        self.assertEqual([workflow.GLOBAL_MARKET], store.project["brief"]["target_markets"])

    def test_invalid_csv_shows_validation_without_breaking_the_uploader(self):
        app = self.run_blog()
        app.file_uploader[0].set_value(
            [("invalid.csv", b"wrong_header\nwrong_value\n", "text/csv")]
        ).run(timeout=20)

        self.assertEqual([], list(app.exception))
        self.assertTrue(app.error)
        self.assertIn("use the blog brief csv headers exactly", " ".join(item.value for item in app.error).casefold())
        self.assertEqual(1, len(app.file_uploader))
        self.assertFalse(app.session_state["_seo_blog_import_store"].project.get("prompt_2"))


if __name__ == "__main__":
    unittest.main()
