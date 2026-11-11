"""Compact Website report presentation and summaries of the storefront tools."""
from html import escape

import streamlit as st

from analytics_navigation import PRODUCT_QUIZ_ROUTE
import os_accounts
from social_media import WALL_PREVIEW_ROUTE


def compact_styles():
    st.html(
        """
        <style>
        [data-testid="stMainBlockContainer"]:has(.st-key-website-compact) {
            padding-top: calc(var(--sc-topbar-height, 3.5rem) + .5rem) !important;
        }
        .st-key-website-compact [data-testid="stVerticalBlock"] { gap: .6rem; }
        .st-key-website-compact [data-testid="stHorizontalBlock"] { gap: .55rem; }
        .st-key-website-compact [data-testid="stHeading"] h3 {
            font-size: 1.35rem;
            padding: 0;
        }
        .st-key-website-compact [data-testid="stMetric"] {
            min-height: 0 !important;
            padding: .45rem .6rem !important;
            border: 1px solid #ddd9d0 !important;
            border-radius: 5px !important;
            box-shadow: none !important;
        }
        .st-key-website-compact [data-testid="stMetricLabel"] {
            min-height: 0;
            height: auto;
        }
        .st-key-website-compact [data-testid="stMetricLabel"] p {
            white-space: normal !important;
            font-size: .78rem;
            line-height: 1.25;
        }
        .st-key-website-compact [data-testid="stMetricValue"] {
            font-size: 1.28rem !important;
            line-height: 1.25;
        }
        .st-key-website-compact [data-testid="stMetricDelta"] {
            font-size: .72rem !important;
        }
        .st-key-website-compact :is([data-testid="stSelectbox"], [data-testid="stTextInput"], [data-testid="stDateInput"]) label p {
            font-size: .8rem;
        }
        .sc-website-tools {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(min(100%, 21rem), 1fr));
            gap: .5rem;
            font: .82rem/1.35 "Segoe UI", sans-serif;
        }
        .sc-website-tool {
            border: 1px solid #ddd9d0;
            border-radius: 5px;
            padding: .4rem .65rem;
            background: #fff;
            color: #242321;
        }
        .sc-website-tool h4 { font: 600 .83rem/1.3 "Segoe UI", sans-serif; margin: 0; padding: 0; }
        .sc-website-tool p { margin: .2rem 0 0; font: inherit; color: #5f5c56; }
        .sc-website-tool strong { color: #242321; }
        </style>
        """
    )


def metric_row(values, *, key):
    with st.container(key=key):
        for column, (label, value) in zip(st.columns(len(values), gap="small"), values):
            column.metric(label, f"{value:,}")


def tool_summaries(user):
    from seo_phase1 import local_mode

    if local_mode():
        return
    summaries = []
    if os_accounts.can_access_page(user, WALL_PREVIEW_ROUTE):
        from wall_preview_analytics_ui import bounds, engagement as wall_engagement

        try:
            engagement = wall_engagement(*bounds(30))
            values = [
                ("Preview opens", engagement["opens"]),
                ("Placements", engagement["confirmed"]),
                ("Add-to-cart visits", engagement["atc"]),
            ]
        except Exception:
            values = None
        summaries.append(("Wall Preview", values))

    if os_accounts.can_access_page(user, PRODUCT_QUIZ_ROUTE):
        from product_quiz_page import quiz_metrics, quiz_totals

        try:
            values = quiz_metrics(quiz_totals())
        except Exception:
            values = None
        summaries.append(("Product Quiz", values))

    if not summaries:
        return

    panels = []
    for title, values in summaries:
        metrics = " · ".join(
            f"{escape(label)} <strong>{value:,}</strong>" for label, value in values
        ) if values is not None else "Analytics temporarily unavailable."
        panels.append(f'<section class="sc-website-tool"><h4>{escape(title)} · Last 30 days</h4><p>{metrics}</p></section>')
    st.markdown('<div class="sc-website-tools">' + "".join(panels) + "</div>", unsafe_allow_html=True)
