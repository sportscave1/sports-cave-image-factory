"""Read-only analytics and Shopify placement for the storefront quiz."""
from collections import Counter

import streamlit as st

from analytics_navigation import PRODUCT_QUIZ_ROUTE
import os_accounts
from product_quiz_store import QuizStore
from seo_phase1 import local_mode


INSTALL_HTML = (
    '<a href="/collections/all-sports-wall-art" data-sc-edition-finder '
    'aria-haspopup="dialog">Find your next edition</a>'
)


@st.cache_data(ttl=60, max_entries=1, show_spinner=False)
def quiz_totals():
    return QuizStore().report_totals()


@st.cache_data(ttl=60, max_entries=1, show_spinner=False)
def quiz_report():
    return QuizStore().report()


def quiz_metrics(rows):
    totals = Counter()
    for row in rows:
        totals[row["event"]] += row["count"]
    return [
        ("Starts", totals["started"]),
        ("Completions", totals["completed"]),
        ("Product clicks", totals["product_click"]),
    ]


def render_page(user, store=None):
    if not os_accounts.can_access_page(user, PRODUCT_QUIZ_ROUTE):
        st.error("Access not approved.")
        return

    from website_analytics import compact_styles, metric_row

    compact_styles()
    with st.container(key="website-compact"):
        heading, actions = st.columns([4, 1], vertical_alignment="center")
        heading.subheader("Product Quiz")
        with actions.popover("Install", icon=":material/code:"):
            st.caption("Paste this into a Shopify Custom HTML or Custom Liquid block on a theme that includes the Sports Cave edition finder.")
            st.code(INSTALL_HTML, language="html")
            st.caption("For collection-specific placement, add the collection handle as the data-sc-quiz-collection attribute.")

        st.caption("Last 30 days · Anonymous events collected with analytics consent. Purchases and revenue are not attributed to the quiz.")
        if store is None and local_mode():
            st.caption("Quiz analytics are unavailable in this local workspace.")
            return
        try:
            totals = store.report_totals() if store is not None else quiz_totals()
        except Exception:
            st.warning("Quiz analytics are temporarily unavailable.")
            return

        metric_row(quiz_metrics(totals), key="quiz-kpis")
        breakdown = st.expander("Event breakdown", key="quiz-event-breakdown", on_change="rerun")
        if not breakdown.open:
            return
        with breakdown:
            try:
                rows = store.report() if store is not None else quiz_report()
            except Exception:
                st.warning("Quiz event details are temporarily unavailable.")
                return
            if not rows:
                st.caption("No quiz activity recorded in the last 30 days.")
                return
            st.dataframe(
                rows,
                hide_index=True,
                height=280,
                column_config={
                    "event": "Event",
                    "question": "Question",
                    "source": "Source",
                    "version": "Version",
                    "count": "Events",
                    "sessions": "Distinct sessions",
                },
            )
