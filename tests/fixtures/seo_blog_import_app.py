import streamlit as st
from unittest.mock import patch

import os_accounts
import seo_page


def _seed_brief():
    return {
        "gsc_seed_query": "shane warne wall art",
        "selected_opportunity": "shane warne wall art",
        "author": "Nathan",
        "target_blog": "News",
        "publication_preference": "Draft",
    }


def _opportunity():
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


def _product_context():
    return [
        {
            "id": "gid://shopify/Product/1",
            "entity_type": "Product",
            "title": "King of Spin",
            "url": "https://www.sportscaveshop.com/products/king-of-spin",
            "sport": "Cricket",
        }
    ]


class _ProjectStore:
    def __init__(self):
        self.project = {
            "project_id": "project-1",
            "owner_id": "admin-1",
            "owner_name": "Nathan",
            "status": "Idea",
            "title": "Shane Warne brief",
            "primary_keyword": "",
            "target_url": "",
            "brief": _seed_brief(),
            "opportunity_snapshot": _opportunity(),
            "prompt_1": "",
            "prompt_1_hash": "",
            "prompt_2": "",
            "prompt_2_hash": "",
        }
        self.save_count = 0

    def list_projects(self, **_kwargs):
        return [dict(self.project)]

    def save_project(self, project):
        self.project = dict(project)
        self.save_count += 1
        return dict(self.project)

    def record_event(self, *_args, **_kwargs):
        return False


class _ReportingReader:
    def snapshot(self, **_kwargs):
        return {
            "health": {"gsc": {"through_date": "2026-08-14"}},
            "top_queries": [],
        }


if "_seo_blog_import_store" not in st.session_state:
    st.session_state["_seo_blog_import_store"] = _ProjectStore()

route = st.radio("Test route", ("Blog", "Other"), key="_seo_blog_test_route")
if route == "Blog":
    user = {
        "id": "admin-1",
        "display_name": "Nathan",
        "role": os_accounts.ROLE_ADMIN,
        "is_active": True,
    }
    with patch.object(seo_page, "_cached_blog_shopify_targets", return_value=_product_context()), patch.object(
        seo_page.google_seo,
        "refresh_access_token",
        side_effect=AssertionError("Blog render must not call Google"),
    ), patch.object(
        seo_page.google_seo_import,
        "queue_imports",
        side_effect=AssertionError("Blog render must not start a sync"),
    ):
        seo_page._render_blog_v2(
            {"target_library": []},
            user,
            reporting_reader=_ReportingReader(),
            project_store=st.session_state["_seo_blog_import_store"],
        )
else:
    st.write("Other route")
