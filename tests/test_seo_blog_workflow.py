import json
import unittest

import seo_blog_workflow as workflow


def brief():
    return {
        "target_market": "AU",
        "sport": "Cricket",
        "subject": "Shane Warne and the 2005 Ashes",
        "timely_hook": "A generation still debates the series",
        "search_intent": "Historical explainer",
        "primary_keyword": "shane warne wall art",
        "supporting_keywords": ["2005 ashes", "cricket memorabilia"],
        "related_entities": ["Australia", "England"],
        "fan_questions": ["Why did the series matter?"],
        "target_entity_id": "gid://shopify/Product/1",
        "target_title": "King of Spin",
        "target_url": "https://www.sportscaveshop.com/products/king-of-spin",
        "target_sport": "Cricket",
        "source_artwork": "approved-product.webp",
        "internal_links": ["https://www.sportscaveshop.com/collections/cricket"],
        "author": "Nathan",
        "target_blog": "News",
        "tags": ["Cricket"],
        "approved_source_assets": ["approved-warne.jpg", "approved-product.webp"],
        "assets_permitted": True,
    }


def content_package(project_id):
    words = " ".join(["cricket"] * 720)
    url = brief()["target_url"]
    return {
        "project_id": project_id,
        "article_title": "The summer spin took over",
        "seo_title": "Shane Warne Wall Art and the 2005 Ashes",
        "meta_description": "A fact-checked look at Shane Warne's 2005 Ashes and why the rivalry still matters to cricket collectors.",
        "handle": "shane-warne-2005-ashes",
        "excerpt": "The series that turned every ball into theatre.",
        "author": "Nathan",
        "tags": ["Cricket"],
        "primary_query": "shane warne wall art",
        "supporting_queries": ["2005 ashes"],
        "search_intent": "Historical explainer",
        "source_fact_check_notes": ["Scores checked against an official source."],
        "final_html": f"<p>{words}</p><h2>For collectors</h2><p><a href=\"{url}\">King of Spin artwork</a></p>",
        "internal_link_map": [{"url": url, "anchor": "King of Spin artwork"}],
        "product_collection_link_placement": "final third",
        "image_manifest": [
            {
                "role": role, "aspect_ratio": ratio, "target_dimensions": dimensions,
                "purpose": role, "placement_marker": f"[[{role}]]",
                "filename": f"shane-warne-{role.replace('_', '-')}.webp",
                "alt_text": f"Editorial image for {role}",
                "source_asset_mapping": ["approved-warne.jpg"],
                "final_asset_reference": f"asset-{role}",
            }
            for role, ratio, dimensions in workflow.IMAGE_ROLES
        ],
    }


class BlogWorkflowTests(unittest.TestCase):
    def test_opportunity_prefill_never_overwrites_manual_values(self):
        result = workflow.prefill_from_opportunity(
            {"primary_keyword": "manual keyword", "target_url": "https://example.test/manual"},
            {"query": "suggested", "current_page": "https://example.test/suggested", "recommended_article_type": "Guide"},
        )
        self.assertEqual(result["primary_keyword"], "manual keyword")
        self.assertEqual(result["target_url"], "https://example.test/manual")
        self.assertEqual(result["search_intent"], "Guide")

    def test_blog_opportunity_scoring_is_deterministic_and_never_claims_volume(self):
        rows = [{"query": "shane warne art", "clicks": 4, "impressions": 120, "ctr": 0.03, "average_position": 8}]
        first = workflow.build_blog_opportunities(rows, data_through_date="2026-08-14")
        second = workflow.build_blog_opportunities(rows, data_through_date="2026-08-14")
        self.assertEqual(first, second)
        self.assertEqual(first[0]["data_through_date"], "2026-08-14")
        self.assertNotIn("search volume", json.dumps(first, default=str).casefold())

    def test_prompt_1_is_self_contained_and_uses_shared_image_contract(self):
        prompt = workflow.build_prompt_1(
            "project-1",
            brief(),
            source_date="2026-08-14",
            opportunity={"query": "shane warne wall art", "clicks": 4, "impressions": 100, "ctr": 0.04, "average_position": 9},
        )
        for value in ("project-1", "2026-08-14", brief()["target_url"], "approved-product.webp", "1600x900", "1600x1067", "1600x1200"):
            self.assertIn(value, prompt)
        self.assertIn("SPORTS_CAVE_IMAGE_REALISM_RULES_V1", prompt)
        self.assertIn("no body H1", prompt)
        self.assertIn("final third", prompt)
        self.assertIn("never generate or approximate an athlete likeness", prompt)

    def test_missing_asset_permission_blocks_prompt(self):
        unsafe = {**brief(), "assets_permitted": False}
        with self.assertRaises(workflow.BlogWorkflowError):
            workflow.build_prompt_1("project-1", unsafe)

    def test_content_package_requires_no_h1_final_third_link_and_complete_manifest(self):
        result = workflow.validate_content_package(
            content_package("project-1"),
            project_id="project-1",
            target_url=brief()["target_url"],
        )
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["image_manifest"]), 3)
        broken = content_package("project-1")
        broken["final_html"] = "<h1>Duplicate</h1><p>TODO</p>"
        with self.assertRaises(workflow.ContentPackageError) as caught:
            workflow.validate_content_package(broken, project_id="project-1", target_url=brief()["target_url"])
        self.assertTrue(any("H1" in issue for issue in caught.exception.issues))

    def test_prompt_2_stops_without_capability_and_requires_publish_confirmation(self):
        validation = workflow.validate_content_package(
            content_package("project-1"), project_id="project-1", target_url=brief()["target_url"]
        )
        project = {"project_id": "project-1", "brief": brief(), "content_package": validation["package"]}
        with self.assertRaises(workflow.BlogWorkflowError):
            workflow.build_prompt_2(project, validation, capability={"available": False})
        prompt = workflow.build_prompt_2(project, validation, capability={"available": True})
        self.assertIn("UNPUBLISHED DRAFT", prompt)
        self.assertIn('explicit "Publish now"', prompt)
        self.assertIn("resume or update the same article ID", prompt)
        self.assertIn("Never request an Admin token", prompt)

    def test_shopify_readback_requires_an_exact_unpublished_draft(self):
        package = content_package("project-1")
        project = {"project_id": "project-1", "content_package": package}
        readback = {
            "article_id": "gid://shopify/Article/1",
            "title": package["article_title"],
            "html": package["final_html"],
            "handle": package["handle"],
            "excerpt": package["excerpt"],
            "author": package["author"],
            "tags": package["tags"],
            "seo_title": package["seo_title"],
            "meta_description": package["meta_description"],
            "admin_url": "https://admin.shopify.com/store/sports-cave/articles/1",
            "preview_url": "https://example.test/blogs/news/example?preview_key=1",
            "visibility": "unpublished",
            "images": [
                {"role": row["role"], "alt_text": row["alt_text"], "url": f"https://cdn.shopify.com/{row['filename']}"}
                for row in package["image_manifest"]
            ],
        }
        self.assertTrue(workflow.validate_shopify_readback(project, readback)["valid"])
        with self.assertRaises(workflow.BlogWorkflowError):
            workflow.validate_shopify_readback(project, {**readback, "visibility": "published"})

    def test_capability_never_returns_credentials(self):
        status = workflow.shopify_write_capability(
            {
                "SHOPIFY_STORE_DOMAIN": "sports-cave.myshopify.com",
                "SHOPIFY_ADMIN_ACCESS_TOKEN": "secret",
                "SHOPIFY_BLOG_WRITE_ENABLED": "true",
                "SHOPIFY_FILE_WRITE_ENABLED": "true",
            }
        )
        self.assertTrue(status["available"])
        self.assertNotIn("secret", json.dumps(status))


if __name__ == "__main__":
    unittest.main()
