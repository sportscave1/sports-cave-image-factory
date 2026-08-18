from datetime import date, datetime, timedelta, timezone
import hashlib
import html
import json
import logging
import os
import re
import time
import uuid

import streamlit as st
import streamlit.components.v1 as components

from activity_log import record_activity_log
import google_seo
import google_seo_import
import google_seo_phase4
import navigation_runtime
import os_accounts
import seo_growth_intelligence
import seo_blog_workflow
import seo_live_analytics
import seo_metrics
import seo_navigation as seo_nav
import seo_pagination
import seo_reporting_runtime
import seo_sync_progress
import seo_technical_audit
import seo_workspace as seo
from ui_option_ordering import alphabetize_options, selected_option_index


SEO_OVERVIEW_CACHE_TTL_SECONDS = 15
SEO_REPORTING_CACHE_TTL_SECONDS = 300
SEO_WATERMARK_CACHE_TTL_SECONDS = 15
SEO_PROGRESS_POLL_SECONDS = 15
SEO_ADMIN_OPEN_STATE_KEY = "seo-data-connections-open"
DATABASE_URL_ENV_KEYS = (
    "DATABASE_URL",
    "SUPABASE_DATABASE_URL",
    "SUPABASE_DB_URL",
    "POSTGRES_URL",
    "POSTGRES_PRISMA_URL",
    "POSTGRES_URL_NON_POOLING",
    "DATABASE_PRIVATE_URL",
    "DATABASE_PUBLIC_URL",
    "RENDER_DATABASE_URL",
)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_blog_shopify_targets():
    return seo_blog_workflow.PostgresBlogProjectStore().list_shopify_targets()


PAGE_SUBTITLES = {
    seo.SEO_OVERVIEW_ROUTE: "Google Search Console visibility, rankings and opportunities from saved source data.",
    seo.SEO_KEYWORDS_ROUTE: "Review one canonical row per Google Search Console query.",
    seo_nav.SEO_OPPORTUNITIES_ROUTE: "Prioritise explainable opportunities from observed search evidence.",
    seo_nav.SEO_LANDING_PAGES_ROUTE: "Review canonical pages using Search Console clicks, impressions, CTR and position.",
    seo_nav.SEO_MAPPING_ROUTE: "Map approved queries to one canonical target page and track conflicts.",
    seo_nav.SEO_HEALTH_ROUTE: "Review saved technical findings and administrator-only sync controls.",
    seo.SEO_REPORTS_ROUTE: "Prepare evidence-based growth reports, review recommendations and build strategy from saved data.",
    seo.SEO_TASKS_ROUTE: "Turn approved SEO recommendations into assigned work and measure results over time.",
    seo.SEO_CITATIONS_ROUTE: "Track reputable external profiles and business listings that display the Sports Cave brand and website.",
    seo.SEO_BLOG_ROUTE: "Create premium sports stories that attract search traffic and lead fans naturally toward Sports Cave collections.",
    seo.SEO_INTERNAL_LINKING_ROUTE: "Plan and verify links inside blog content without changing owner-controlled Shopify pages.",
    seo.SEO_BACKLINKS_ROUTE: "Build genuine authority through relevant websites, creators and editorial relationships.",
}

BLOG_REVIEW_ITEMS = (
    "Topic is clear in the first 100 words",
    "Article focuses on one search intent",
    "Specific sporting details are used",
    "Facts, seasons, teams and achievements are verified",
    "Writing sounds human",
    "No generic AI phrasing, filler or repetition",
    "Primary keyword is used naturally",
    "Headings are descriptive",
    "Internal links are verified",
    "Product link is relevant or omitted",
    "Collector connection appears naturally in the final third",
    "Meta title and description pass validation",
    "Images and alt text are prepared",
    "CTA is present but does not overwhelm the article",
    "Ready for owner to publish",
)


def _inject_styles():
    st.markdown(
        """
        <style>
        .sc-seo-shell { max-width: 1500px; }
        .sc-seo-header { align-items: flex-end; display: flex; justify-content: space-between; margin: 0 0 1rem; }
        .sc-seo-header h1 { font-size: 1.75rem; line-height: 1.15; margin: 0; }
        .sc-seo-header p { color: #6e6b65; font-size: .92rem; margin: .35rem 0 0; }
        .sc-seo-kicker { color: #9a7426; font-size: .7rem; font-weight: 750; letter-spacing: .12em; margin-bottom: .35rem; text-transform: uppercase; }
        .sc-seo-integration { border-left: 3px solid #b79243; min-height: 8rem; padding: .15rem .2rem .15rem .75rem; }
        .sc-seo-integration h3 { font-size: 1rem; margin: 0 0 .35rem; }
        .sc-seo-integration p { color: #6e6b65; font-size: .82rem; margin: .25rem 0; }
        .sc-seo-integration dl { display: grid; font-size: .75rem; gap: .24rem .55rem; grid-template-columns: max-content minmax(0, 1fr); margin: .65rem 0 0; }
        .sc-seo-integration dt { color: #77736b; }
        .sc-seo-integration dd { color: #242321; margin: 0; overflow-wrap: anywhere; }
        .sc-seo-badge { background: #f3ecdc; border: 1px solid #d9c28d; border-radius: 999px; color: #6d531c; display: inline-block; font-size: .67rem; font-weight: 700; padding: .16rem .42rem; }
        .sc-seo-badge-connected { background: #e8f3e9; border-color: #b8d5bb; color: #286332; }
        .sc-seo-badge-attention { background: #f8eadf; border-color: #dfb99c; color: #8a481c; }
        .sc-seo-badge-required { background: #f1f0ed; border-color: #d1cec6; color: #5f5c56; }
        .sc-seo-shopify-health { min-height: 8rem; }
        .sc-seo-import-status { border-left: 2px solid #c5a45c; min-height: 8rem; padding: .35rem .7rem; }
        .sc-seo-import-status h4 { font-size: .88rem; margin: 0 0 .45rem; }
        .sc-seo-import-status dl { display: grid; font-size: .75rem; gap: .25rem .55rem; grid-template-columns: max-content minmax(0, 1fr); margin: 0; }
        .sc-seo-import-status dt { color: #77736b; }
        .sc-seo-import-status dd { margin: 0; overflow-wrap: anywhere; }
        .sc-seo-progress-track { background: #e6e2d9; border-radius: 999px; height: 6px; margin: .55rem 0 .35rem; overflow: hidden; }
        .sc-seo-progress-fill { background: #b79243; height: 100%; min-width: 0; transition: width .2s ease; }
        .sc-seo-progress-summary { color: #292724; font-size: .78rem; font-weight: 700; margin: 0 0 .25rem; }
        .sc-seo-progress-detail { color: #6e6b65; font-size: .71rem; line-height: 1.4; margin: .15rem 0; }
        .sc-seo-empty-chart { align-items: center; background: #fbfaf7; border: 1px dashed #d7d2c7; border-radius: 6px; color: #6e6b65; display: flex; justify-content: center; min-height: 3.75rem; padding: .8rem 1rem; text-align: center; }
        .sc-seo-rule-grid { display: grid; gap: .55rem; grid-template-columns: repeat(3, minmax(0, 1fr)); }
        .sc-seo-rule { background: #faf8f2; border-left: 2px solid #b79243; border-radius: 4px; font-size: .8rem; padding: .65rem .75rem; }
        .sc-seo-note { background: #faf8f2; border: 1px solid #e1d9c8; border-radius: 6px; padding: .8rem; }
        .sc-seo-note strong { color: #242321; }
        .sc-seo-danger { border-left-color: #a74b42; }
        .sc-seo-section-title { color: #1d1c1a; font-size: 1.05rem; line-height: 1.25; margin: 1rem 0 .55rem; }
        .sc-seo-data-date { color: #77736b; font-size: .72rem; margin: -.1rem 0 .65rem; }
        .sc-seo-health-pill { border-left: 2px solid #b79243; min-height: 3.2rem; padding: .25rem .65rem; }
        .sc-seo-health-pill span { color: #77736b; display: block; font-size: .67rem; font-weight: 700; text-transform: uppercase; }
        .sc-seo-health-pill strong { color: #242321; display: block; font-size: .82rem; line-height: 1.25; margin-top: .18rem; overflow-wrap: anywhere; }
        [data-testid="stDataFrame"] { border-radius: 6px !important; overflow: hidden !important; }
        [data-testid="stSegmentedControl"] { margin-bottom: .7rem; }
        [data-testid="stSegmentedControl"] button { border-radius: 4px !important; }
        @media (max-width: 900px) {
            .sc-seo-header { align-items: flex-start; flex-direction: column; }
            .sc-seo-rule-grid { grid-template-columns: 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _header(route, *, title=""):
    st.markdown(
        f"""
        <div class="sc-seo-header">
            <div>
                <div class="sc-seo-kicker">Growth / SEO</div>
                <h1>{html.escape(title or route)}</h1>
                <p>{html.escape(PAGE_SUBTITLES[route])}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _section_heading(title):
    st.markdown(
        f'<h2 class="sc-seo-section-title">{html.escape(str(title))}</h2>',
        unsafe_allow_html=True,
    )


def _actor_name(user):
    return str(user.get("display_name") or user.get("email") or user.get("id") or "Sports Cave")


def _persist(store, state, user, *, action, area, message, entity_type="seo_record", entity_id="", metadata=None):
    try:
        store.save(state, actor_id=user.get("id") or "")
    except seo.SEOStoreError as error:
        st.error(str(error))
        return False
    record_activity_log(
        action,
        area,
        message,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata={
            "actor_id": user.get("id") or "",
            "actor_email": user.get("email") or "",
            "actor_role": user.get("role") or "",
            "actor_timezone": os_accounts.timezone_for_user(user),
            "seo_area": area,
            **dict(metadata or {}),
        },
        actor=_actor_name(user),
    )
    return True


def _set_notice(message, *, success=True):
    st.session_state["seo-notice"] = {"message": message, "success": success}


def _render_notice():
    notice = st.session_state.pop("seo-notice", None)
    if not notice:
        return
    (st.success if notice.get("success") else st.warning)(notice.get("message") or "")


def _open_external_link(url, label="Open link"):
    if url:
        st.link_button(label, url, use_container_width=True)


def _table(rows, *, empty, height=360):
    if not rows:
        st.info(empty)
        return
    started = time.perf_counter()
    st.dataframe(rows, use_container_width=True, hide_index=True, height=height)
    logging.info(
        "SEO_PERF operation=table_construction duration_ms=%.2f rows=%s",
        (time.perf_counter() - started) * 1000,
        len(rows),
    )


def _active_view(options, *, key, default=None):
    choices = tuple(options)
    selected = st.segmented_control(
        "View",
        choices,
        default=default or choices[0],
        key=key,
        selection_mode="single",
        label_visibility="collapsed",
    )
    return selected or default or choices[0]


def _paginated_rows(rows, *, key, default_page_size=25):
    rows = list(rows or [])
    controls = st.columns([1, 1, 4])
    page_size = controls[0].selectbox(
        "Rows per page",
        (25, 50),
        index=0 if default_page_size == 25 else 1,
        key=f"{key}-page-size",
    )
    initial = seo.paginate_records(rows, page=1, page_size=page_size)
    page_count = initial["page_count"]
    page = controls[1].number_input(
        "Page",
        min_value=1,
        max_value=page_count,
        value=min(int(st.session_state.get(f"{key}-page", 1)), page_count),
        step=1,
        key=f"{key}-page",
    )
    result = seo.paginate_records(rows, page=page, page_size=page_size)
    start = result["start"]
    controls[2].caption(
        f"Showing {start + 1 if rows else 0}-{min(start + page_size, len(rows))} of {len(rows)}"
    )
    return result["rows"]


def _citation_table_rows(rows):
    return [
        {
            "Platform": row.get("platform"),
            "Category": row.get("category"),
            "Signup URL": row.get("signup_url"),
            "Profile URL": row.get("profile_url"),
            "Username or Handle": row.get("username_handle"),
            "Website Displayed": row.get("website_displayed"),
            "Website Link Type": row.get("website_link_type"),
            "Logo Uploaded": row.get("logo_uploaded"),
            "Status": row.get("status"),
            "Owner": row.get("owner"),
            "Date Completed": row.get("date_completed"),
            "Notes": row.get("notes"),
        }
        for row in rows
    ]


def _record_selector(records, label, key, *, title_field):
    if not records:
        return ""
    by_id = {str(row.get("id")): row for row in records}
    return st.selectbox(
        label,
        alphabetize_options(
            by_id,
            label=lambda record_id: str(by_id[record_id].get(title_field) or "Untitled"),
        ),
        format_func=lambda record_id: str(by_id[record_id].get(title_field) or "Untitled"),
        key=key,
    )


def _rule_expander(title, lines):
    with st.expander(title, expanded=False):
        for line in lines:
            st.markdown(f"- {line}")


def _navigate(navigate, route, *, force=False):
    if navigate is not None:
        if force:
            navigate(route, force=True)
        else:
            navigate(route)
        st.rerun()


def _google_badge_class(status):
    if status in {"Connected", "Connected and data ready"}:
        return "sc-seo-badge-connected"
    if status == "Needs attention" or str(status).startswith((
        "Connected -", "Reconnection required", "Permission/property error"
    )):
        return "sc-seo-badge-attention"
    if status == "Configuration required":
        return "sc-seo-badge-required"
    return ""


def _gsc_health_notice(health):
    health = dict(health or {})
    status = str(health.get("status") or "")
    messages = {
        "missing_migration": (
            "The canonical Search Console reporting migration is missing. "
            "Apply the additive GSC migrations before syncing."
        ),
        "canonical_backfill_required": (
            "Search Console is connected and legacy rows exist, but the canonical SEO datasets "
            "still require backfill or refetch."
        ),
        "initial_data_sync_required": (
            "Search Console is configured, but the canonical SEO datasets have not been synced yet."
        ),
        "sync_failed": "The latest canonical Search Console sync failed and no readable last-good data exists.",
        "stale_last_good": "The latest Search Console sync failed; the metrics below use preserved last-good canonical data.",
        "not_configured": "Select and test a Search Console property before syncing SEO data.",
    }
    return messages.get(status, "")


def _integration_card(
    title,
    status,
    *,
    property_name="",
    property_id="",
    last_sync="",
    data_date="",
    extra_class="",
    show_data_date=True,
):
    details = []
    if property_name or property_id:
        details.extend(
            (
                ("Property", property_name or "Not selected"),
                ("Identifier", property_id or "Not selected"),
            )
        )
    else:
        details.append(("Property", "Not selected"))
    details.append(("Last successful sync", last_sync or "Not yet synced"))
    if show_data_date:
        details.append(("Data available through", data_date or "Not yet checked"))
    detail_html = "".join(
        f"<dt>{html.escape(label)}</dt><dd>{html.escape(str(value))}</dd>"
        for label, value in details
    )
    return (
        f'<div class="sc-seo-integration {html.escape(extra_class)}">'
        f'<span class="sc-seo-badge {_google_badge_class(status)}">{html.escape(status)}</span>'
        f'<h3>{html.escape(title)}</h3><dl>{detail_html}</dl></div>'
    )


def _consume_google_oauth_notice():
    try:
        result = st.query_params.get("google_oauth", "")
    except Exception:
        return
    if isinstance(result, (list, tuple)):
        result = result[0] if result else ""
    messages = {
        "connected": ("Google connected. Select the Sports Cave properties to finish setup.", True),
        "denied": ("Google access was not approved. No connection changes were made.", False),
        "attention": ("Google could not be connected. Please try again.", False),
        "state_invalid": ("That Google connection request expired or was already used. Please try again.", False),
        "configuration_required": ("Google connection configuration is incomplete.", False),
        "access_denied": ("Administrator access is required to manage Google.", False),
    }
    message = messages.get(str(result or ""))
    if not message:
        return
    if str(result or "") == "connected":
        st.session_state[SEO_ADMIN_OPEN_STATE_KEY] = True
        invalidate_seo_overview_summary_cache()
    (st.success if message[1] else st.warning)(message[0])
    try:
        del st.query_params["google_oauth"]
    except Exception:
        pass


def _shopify_health():
    try:
        import shopify_sync

        config = shopify_sync.get_config()
    except Exception:
        return {"status": "Needs attention", "last_sync": "Unavailable"}
    status = "Connected" if config.get("configured") else "Configuration required"
    last_sync = "Not yet synced"
    if config.get("configured"):
        try:
            import supabase_backend

            sync_state = supabase_backend.get_sync_state_read_only()
            last_sync = str(sync_state.get("last_successful_order_sync_at") or "Not yet synced")
        except Exception:
            last_sync = "Unavailable"
    return {"status": status, "last_sync": last_sync}


@st.cache_data(ttl=SEO_OVERVIEW_CACHE_TTL_SECONDS, show_spinner=False, max_entries=1)
def _cached_default_shopify_health():
    return _shopify_health()


@st.cache_data(ttl=SEO_OVERVIEW_CACHE_TTL_SECONDS, show_spinner=False, max_entries=1)
def _cached_default_google_connection():
    return google_seo.default_store().get_connection()


@st.cache_data(ttl=SEO_OVERVIEW_CACHE_TTL_SECONDS, show_spinner=False, max_entries=1)
def _cached_default_phase4_health():
    return google_seo_phase4.default_phase4_store().saved_health()


@st.cache_data(ttl=SEO_OVERVIEW_CACHE_TTL_SECONDS, show_spinner=False, max_entries=1)
def _cached_default_live_source_health(cache_revision=0):
    del cache_revision
    return seo_live_analytics.default_reader().source_health()


@st.cache_data(ttl=SEO_OVERVIEW_CACHE_TTL_SECONDS, show_spinner=False, max_entries=24)
def _cached_default_reporting_snapshot(
    preset,
    market,
    device,
    compare,
    comparison,
    search_type,
    query_class,
    source_scope,
    custom_start,
    custom_end,
    source_health,
    cache_revision,
):
    del cache_revision
    reader = seo_live_analytics.default_reader()
    return reader.snapshot(
        preset=preset,
        market=market,
        device=device,
        compare=compare,
        comparison=comparison,
        search_type=search_type,
        query_class=query_class,
        source_scope=source_scope,
        custom_start=custom_start,
        custom_end=custom_end,
        source_health=source_health,
    )


@st.cache_data(ttl=SEO_WATERMARK_CACHE_TTL_SECONDS, show_spinner=False, max_entries=1)
def _cached_interactive_reporting_context():
    return seo_reporting_runtime.default_reader().reporting_context()


@st.cache_data(ttl=SEO_REPORTING_CACHE_TTL_SECONDS, show_spinner=False, max_entries=48)
def _cached_interactive_overview(filters_json, context_json, watermark):
    del watermark
    return seo_reporting_runtime.default_reader().overview_base(
        json.loads(filters_json),
        context=json.loads(context_json),
    )


@st.cache_data(ttl=SEO_REPORTING_CACHE_TTL_SECONDS, show_spinner=False, max_entries=96)
def _cached_interactive_landing_pages(filters_json, context_json, watermark, limit):
    del watermark
    return seo_reporting_runtime.default_reader().landing_pages(
        json.loads(filters_json),
        context=json.loads(context_json),
        limit=limit,
    )


@st.cache_data(ttl=SEO_REPORTING_CACHE_TTL_SECONDS, show_spinner=False, max_entries=48)
def _cached_interactive_rank_distribution(filters_json, context_json, watermark):
    del watermark
    return seo_reporting_runtime.default_reader().rank_distribution(
        json.loads(filters_json),
        context=json.loads(context_json),
    )


@st.cache_data(ttl=SEO_OVERVIEW_CACHE_TTL_SECONDS, show_spinner=False, max_entries=1)
def _cached_default_growth_pipeline_status():
    return seo_growth_intelligence.default_store().recent_pipeline_status()


def invalidate_seo_overview_summary_cache():
    _cached_default_shopify_health.clear()
    _cached_default_google_connection.clear()
    _cached_default_phase4_health.clear()
    _cached_default_live_source_health.clear()
    _cached_default_reporting_snapshot.clear()
    _cached_interactive_reporting_context.clear()
    _cached_interactive_overview.clear()
    _cached_interactive_landing_pages.clear()
    _cached_interactive_rank_distribution.clear()
    _cached_default_growth_pipeline_status.clear()


def _render_google_controls(user, store, config_status, connection):
    if not os_accounts.is_admin(user):
        return
    connected = bool(connection.get("has_refresh_token"))
    reconnect_required = bool(connection.get("reconnect_required"))
    if not config_status.get("ready"):
        st.info("Google connection configuration is required before an administrator can connect.")
        return
    if not connected:
        st.link_button(
            "Connect Google",
            google_seo.GOOGLE_OAUTH_CONNECT_PATH,
            type="primary",
            icon=":material/link:",
        )
        return

    controls = st.columns(3)
    if controls[0].button(
        "Refresh properties",
        icon=":material/refresh:",
        key="seo-google-refresh-properties",
    ):
        result = google_seo.refresh_properties(store, user, google_seo.load_config())
        _set_notice(
            result.get("message") or "Accessible Google properties refreshed.",
            success=bool(result.get("ok")),
        )
        invalidate_seo_overview_summary_cache()
        st.rerun()
    if controls[1].button(
        "Test GSC connection",
        icon=":material/health_and_safety:",
        key="seo-google-test-gsc",
    ):
        result = google_seo.test_gsc_connection(
            store,
            user,
            google_seo.load_config(),
        )
        _set_notice(
            result.get("message") or (
                "Search Console token, property permission and read access verified."
                if result.get("ok")
                else "Search Console connection test failed."
            ),
            success=bool(result.get("ok")),
        )
        invalidate_seo_overview_summary_cache()
        st.rerun()
    if reconnect_required:
        controls[2].link_button(
            "Reconnect",
            google_seo.GOOGLE_OAUTH_CONNECT_PATH,
            icon=":material/link:",
        )

    with st.expander(
        "Manage connection",
        expanded=not (connection.get("gsc_site_url") and connection.get("ga4_property_id")),
    ):
        gsc_rows = list(connection.get("available_gsc_properties") or [])
        ga4_rows = list(connection.get("available_ga4_properties") or [])
        if not gsc_rows or not ga4_rows:
            st.warning("No selectable Search Console or Analytics properties are currently available.")
        else:
            gsc_by_id = {
                str(row.get("id") or ""): row for row in gsc_rows if row.get("id")
            }
            ga4_by_id = {
                str(row.get("id") or ""): row for row in ga4_rows if row.get("id")
            }
            selected_gsc = str(connection.get("gsc_site_url") or "")
            selected_ga4 = str(connection.get("ga4_property_id") or "")
            gsc_ids = alphabetize_options(
                gsc_by_id,
                label=lambda value: f"{gsc_by_id[value].get('name') or value} ({value})",
            )
            ga4_ids = alphabetize_options(
                ga4_by_id,
                label=lambda value: f"{ga4_by_id[value].get('name') or value} ({value})",
            )
            selectors = st.columns(2)
            gsc_value = selectors[0].selectbox(
                "Search Console property",
                gsc_ids,
                index=selected_option_index(gsc_ids, selected_gsc),
                format_func=lambda value: f"{gsc_by_id[value].get('name') or value} ({value})",
                key="seo-google-gsc-property",
            )
            ga4_value = selectors[1].selectbox(
                "Google Analytics 4 property",
                ga4_ids,
                index=selected_option_index(ga4_ids, selected_ga4),
                format_func=lambda value: f"{ga4_by_id[value].get('name') or value} ({value})",
                key="seo-google-ga4-property",
            )
            if st.button("Save property selection", key="seo-google-save-properties"):
                try:
                    google_seo.save_property_selection(
                        store,
                        user,
                        gsc_site_url=gsc_value,
                        ga4_property_id=ga4_value,
                    )
                except google_seo.GoogleSEOError as error:
                    _set_notice(error.public_message, success=False)
                else:
                    _set_notice("Google property selection saved.")
                    invalidate_seo_overview_summary_cache()
                st.rerun()

        st.divider()
        confirm_disconnect = st.checkbox(
            "Disconnect Search Console and Analytics",
            key="seo-google-confirm-disconnect",
        )
        if st.button(
            "Disconnect Google",
            disabled=not confirm_disconnect,
            key="seo-google-disconnect",
        ):
            try:
                google_seo.disconnect_google(store, user, google_seo.load_config())
            except google_seo.GoogleSEOError as error:
                _set_notice(error.public_message, success=False)
            else:
                _set_notice("Google disconnected.")
                invalidate_seo_overview_summary_cache()
            st.rerun()


def _display_progress_date(value, fallback="Not available"):
    if isinstance(value, datetime):
        parsed = value.date()
        return f"{parsed.day} {parsed.strftime('%B %Y')}"
    if isinstance(value, date):
        return f"{value.day} {value.strftime('%B %Y')}"
    text = str(value or "").strip()
    if not text:
        return fallback
    try:
        parsed = date.fromisoformat(text[:10])
        return f"{parsed.day} {parsed.strftime('%B %Y')}"
    except ValueError:
        return text


def _display_progress_time(value, fallback="Not available"):
    if not value:
        return fallback
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    return parsed.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


def _import_status_card(source, run):
    progress = seo_sync_progress.calculate_sync_progress(run)
    status = str(progress["status"] or "not started").replace("_", " ").title()
    percent = progress["percentage"]
    bar_percent = max(0, min(round(percent), 100))
    if progress["range_valid"]:
        summary = (
            f"{bar_percent}% complete • {progress['completed_dates']:,} of "
            f"{progress['total_dates']:,} dates"
        )
    elif progress["status"] == "completed":
        summary = "100% complete"
    elif progress["status"] == "queued":
        summary = "0% complete • Preparing date range"
    else:
        summary = "Progress range unavailable • Calculating…"

    rate = progress.get("rate_per_minute")
    eta = progress.get("eta_seconds")
    rate_text = f"{rate:.1f} dates/minute" if rate is not None else "Calculating…"
    eta_text = (
        f"Approximately {seo_sync_progress.format_duration(eta)} remaining"
        if eta is not None
        else "Approximate time remaining: Calculating…"
    )
    current = _display_progress_date(
        progress.get("current_checkpoint_date"),
        "Waiting to start" if progress["status"] == "queued" else "Not available",
    )
    error = run.get("error_summary") or "None"
    return (
        '<div class="sc-seo-import-status">'
        f'<h4>{html.escape(source)} import</h4>'
        f'<div class="sc-seo-progress-summary">{html.escape(summary)}</div>'
        f'<div class="sc-seo-progress-track" role="progressbar" aria-valuemin="0" '
        f'aria-valuemax="100" aria-valuenow="{bar_percent}" aria-label="{html.escape(source)} import progress">'
        f'<div class="sc-seo-progress-fill" style="width:{bar_percent}%"></div></div>'
        f'<p class="sc-seo-progress-detail">Current: {html.escape(current)} • {html.escape(rate_text)} • {html.escape(eta_text)}</p>'
        '<dl>'
        f'<dt>Status</dt><dd>{html.escape(status)}</dd>'
        f'<dt>Rows received</dt><dd>{progress["rows_received"]:,}</dd>'
        f'<dt>Rows stored</dt><dd>{progress["rows_stored"]:,}</dd>'
        f'<dt>Elapsed</dt><dd>{html.escape(seo_sync_progress.format_duration(progress["elapsed_seconds"]))}</dd>'
        f'<dt>Last progress</dt><dd>{html.escape(_display_progress_time(progress.get("last_progress_at")))}</dd>'
        f'<dt>Error</dt><dd>{html.escape(str(error))}</dd>'
        '</dl></div>'
    )


def _load_sync_progress_statuses(import_store, phase4_store):
    if (
        isinstance(import_store, google_seo_import.PostgresSEOImportStore)
        and isinstance(phase4_store, google_seo_phase4.PostgresSEOPhase4Store)
        and import_store.backend is phase4_store.backend
    ):
        return phase4_store.progress_status()
    return {
        "phase3": import_store.recent_status(),
        "phase4": phase4_store.recent_status(),
    }


@st.fragment(run_every=SEO_PROGRESS_POLL_SECONDS)
def _render_historical_import_controls(
    user,
    connection,
    import_store=None,
    phase4_store=None,
    connection_store=None,
    config_ready=True,
):
    import_store = import_store or google_seo_import.default_import_store()
    phase4_store = phase4_store or google_seo_phase4.default_phase4_store()
    st.subheader("Google data import")
    try:
        progress_statuses = _load_sync_progress_statuses(import_store, phase4_store)
    except (google_seo_import.SEOImportError, google_seo_phase4.SEOPhase4Error) as error:
        st.warning(getattr(error, "public_message", "Import status is temporarily unavailable."))
        return
    statuses = progress_statuses.get("phase3") or {}
    columns = st.columns(2)
    for column, source in zip(columns, google_seo_import.SOURCES):
        column.markdown(
            _import_status_card(source, statuses.get(source) or {}),
            unsafe_allow_html=True,
        )

    phase4_statuses = progress_statuses.get("phase4") or {}
    if phase4_statuses:
        st.caption("Phase 4 joined-data jobs")
        for offset in range(0, len(google_seo_phase4.PHASE4_SOURCES), 3):
            phase4_columns = st.columns(3)
            for column, source in zip(
                phase4_columns,
                google_seo_phase4.PHASE4_SOURCES[offset:offset + 3],
            ):
                column.markdown(
                    _import_status_card(
                        source.replace("_", " ").title(),
                        phase4_statuses.get(source) or {},
                    ),
                    unsafe_allow_html=True,
                )

    if not os_accounts.is_admin(user):
        return

    can_import = bool(
        config_ready
        and connection.get("has_refresh_token")
        and connection.get("gsc_site_url")
        and connection.get("ga4_property_id")
    )
    actions = st.columns(3)
    if actions[0].button(
        "Import historical data",
        type="primary",
        icon=":material/history:",
        disabled=not can_import,
        key="seo-google-import-history",
    ):
        try:
            google_seo_import.queue_imports(
                user,
                "historical",
                import_store=import_store,
                connection_store=connection_store,
            )
        except (google_seo.GoogleSEOError, google_seo_import.SEOImportError) as error:
            _set_notice(getattr(error, "public_message", str(error)), success=False)
        else:
            _set_notice("Historical GSC and GA4 imports queued.")
            invalidate_seo_overview_summary_cache()
        st.rerun(scope="fragment")
    if actions[1].button(
        "Sync now",
        icon=":material/sync:",
        disabled=not can_import,
        key="seo-google-import-sync-now",
    ):
        try:
            google_seo_import.queue_imports(
                user,
                "manual",
                import_store=import_store,
                connection_store=connection_store,
            )
        except (google_seo.GoogleSEOError, google_seo_import.SEOImportError) as error:
            _set_notice(getattr(error, "public_message", str(error)), success=False)
        else:
            _set_notice("GSC and GA4 refresh queued.")
            invalidate_seo_overview_summary_cache()
        st.rerun(scope="fragment")

    failed = next(
        (
            row for row in statuses.values()
            if row.get("status") in {"failed", "partial"} and row.get("id")
        ),
        None,
    )
    if actions[2].button(
        "Retry failed import",
        icon=":material/replay:",
        disabled=not bool(failed),
        key="seo-google-import-retry",
    ):
        try:
            google_seo_import.retry_import(user, failed["id"], import_store=import_store)
        except (google_seo.GoogleSEOError, google_seo_import.SEOImportError) as error:
            _set_notice(getattr(error, "public_message", str(error)), success=False)
        else:
            _set_notice(f"{failed.get('source') or 'Google'} import queued for retry.")
            invalidate_seo_overview_summary_cache()
        st.rerun(scope="fragment")


def _phase4_status_card(label, value, detail=""):
    return (
        '<div class="sc-seo-import-status">'
        f'<h4>{html.escape(str(label))}</h4><dl>'
        f'<dt>Status</dt><dd>{html.escape(str(value or "Not available").replace("_", " ").title())}</dd>'
        f'<dt>Detail</dt><dd>{html.escape(str(detail or "No saved data"))}</dd>'
        '</dl></div>'
    )


def _render_phase4_foundation(
    user,
    phase4_store=None,
    reporting_reader=None,
    connection_store=None,
    saved_health=None,
):
    using_default_store = phase4_store is None
    phase4_store = phase4_store or google_seo_phase4.default_phase4_store()
    st.subheader("Phase 4 mapping and reconciliation")
    try:
        health = dict(
            saved_health
            if saved_health is not None
            else (
                _cached_default_phase4_health()
                if using_default_store
                else phase4_store.saved_health()
            )
        )
    except google_seo_phase4.SEOPhase4Error as error:
        st.caption(error.public_message)
        return

    health_columns = st.columns(4)
    health_columns[0].markdown(
        _phase4_status_card("Common reporting date", health.get("data_status"), health.get("common_reporting_date")),
        unsafe_allow_html=True,
    )
    health_columns[1].markdown(
        _phase4_status_card(
            "URL mapping",
            "Saved" if health.get("mapping_source_url_count") else "Not started",
            (
                f"{health.get('unmapped_page_count', 0):,} unmapped from "
                f"{health.get('mapping_source_url_count', 0):,} checked"
                if health.get("mapping_source_url_count")
                else "No source URLs processed"
            ),
        ),
        unsafe_allow_html=True,
    )
    health_columns[2].markdown(
        _phase4_status_card(
            "Revenue matching",
            "Saved" if health.get("reconciled_transaction_count") else "Not started",
            (
                f"{health.get('unmatched_transaction_count', 0):,} unmatched or disputed from "
                f"{health.get('reconciled_transaction_count', 0):,} evaluated"
                if health.get("reconciled_transaction_count")
                else "No GA4 transactions evaluated"
            ),
        ),
        unsafe_allow_html=True,
    )
    health_columns[3].markdown(
        _phase4_status_card(
            "GA4 history",
            health.get("data_status") or "Not started",
            health.get("latest_ga4_date") or "No completed date",
        ),
        unsafe_allow_html=True,
    )

    if not os_accounts.is_admin(user):
        return
    settings = phase4_store.get_settings()
    brand_text = st.text_input(
        "Brand terms",
        value=", ".join(settings.get("brand_terms") or []),
        help="Comma-separated terms used only for GSC Brand and Non-brand query filtering.",
        key="seo-phase4-brand-terms",
    )
    locale_text = st.text_input(
        "Known locale prefixes",
        value=", ".join(settings.get("known_locale_prefixes") or []),
        help="Locale paths remain distinct; this list labels them for market review.",
        key="seo-phase4-locales",
    )
    if st.button("Save reporting settings", key="seo-phase4-save-settings"):
        phase4_store.save_settings(
            brand_terms=brand_text.split(","), known_locale_prefixes=locale_text.split(","),
            updated_by=str(user.get("id") or ""),
        )
        _set_notice("SEO reporting settings saved.")
        invalidate_seo_overview_summary_cache()
        st.rerun()
    action_columns = st.columns(2)
    if action_columns[0].button(
        "Build joined reporting data", type="primary", icon=":material/account_tree:",
        key="seo-phase4-historical",
    ):
        try:
            google_seo_phase4.queue_phase4_pipeline(
                user, "historical", phase4_store=phase4_store,
                connection_store=connection_store,
            )
        except (google_seo.GoogleSEOError, google_seo_phase4.SEOPhase4Error) as error:
            _set_notice(getattr(error, "public_message", str(error)), success=False)
        else:
            _set_notice("Joined SEO history queued. Existing Phase 3 checkpoints were preserved.")
            invalidate_seo_overview_summary_cache()
        st.rerun()
    if action_columns[1].button(
        "Refresh joined data", icon=":material/sync:", key="seo-phase4-manual",
    ):
        try:
            google_seo_phase4.queue_phase4_pipeline(
                user, "manual", phase4_store=phase4_store,
                connection_store=connection_store,
            )
        except (google_seo.GoogleSEOError, google_seo_phase4.SEOPhase4Error) as error:
            _set_notice(getattr(error, "public_message", str(error)), success=False)
        else:
            _set_notice("Joined SEO refresh queued.")
            invalidate_seo_overview_summary_cache()
        st.rerun()
    _render_manual_url_mapping_admin(user, phase4_store)


def _render_manual_url_mapping_admin(user, phase4_store):
    if not os_accounts.is_admin(user):
        return
    with st.expander("Unmatched URL review", expanded=False):
        search_columns = st.columns([1.2, 1.2, 2])
        url_search = search_columns[0].text_input("Search unmatched URLs", key="seo-url-review-search")
        page_search = search_columns[1].text_input("Search saved pages", key="seo-url-review-page-search")
        search_columns[2].caption("Manual mappings override automatic URL matching and survive later syncs.")
        try:
            aliases = phase4_store.unmatched_url_aliases(search=url_search, status="Needs review", limit=50)
            pages = phase4_store.canonical_page_options(search=page_search, limit=50)
        except Exception:
            st.info("Unmatched URL review is unavailable until Phase 4 tables are migrated.")
            return
        _table(
            [
                {
                    "Source": row.get("source"),
                    "URL": row.get("raw_url"),
                    "Path": row.get("normalized_path"),
                    "Status": row.get("mapping_status"),
                    "Reason": row.get("review_reason") or row.get("mapping_reason"),
                    "Last seen": row.get("last_seen_at"),
                }
                for row in aliases
            ],
            empty="No unmatched, ambiguous or invalid source URLs need review.",
            height=260,
        )
        if not aliases or not pages:
            return
        alias_by_key = {row["alias_key"]: row for row in aliases}
        page_by_key = {row["page_key"]: row for row in pages}
        selectors = st.columns(2)
        alias_key = selectors[0].selectbox(
            "Source URL",
            alphabetize_options(
                alias_by_key,
                label=lambda key: alias_by_key[key].get("raw_url") or key,
            ),
            format_func=lambda key: alias_by_key[key].get("raw_url") or key,
            key="seo-url-review-alias",
        )
        page_key = selectors[1].selectbox(
            "Canonical Shopify page",
            alphabetize_options(
                page_by_key,
                label=lambda key: page_by_key[key].get("title") or page_by_key[key].get("canonical_url") or key,
            ),
            format_func=lambda key: page_by_key[key].get("title") or page_by_key[key].get("canonical_url") or key,
            key="seo-url-review-page",
        )
        if st.button("Save manual mapping", icon=":material/link:", key="seo-url-review-save"):
            try:
                phase4_store.save_manual_url_mapping(
                    alias_key,
                    page_key,
                    updated_by=str(user.get("id") or ""),
                )
            except google_seo_phase4.SEOPhase4Error as error:
                _set_notice(error.public_message, success=False)
            else:
                _set_notice("Manual URL mapping saved. The next mapping refresh will apply it to source rows.")
                invalidate_seo_overview_summary_cache()
            st.rerun()


def _render_growth_pipeline_admin(user, *, growth_store=None):
    if not os_accounts.is_admin(user):
        return
    st.subheader("Daily Growth Intelligence pipeline")
    using_default = growth_store is None
    growth_store = growth_store or seo_growth_intelligence.default_store()
    try:
        status = (
            _cached_default_growth_pipeline_status()
            if using_default
            else growth_store.recent_pipeline_status()
        )
    except seo_growth_intelligence.SEOGrowthError as error:
        st.caption(error.public_message)
        status = {}
    run = dict((status or {}).get("run") or {})
    stages = list((status or {}).get("stages") or [])
    summary_columns = st.columns(4)
    summary_columns[0].metric("Last run", str(run.get("status") or "Not started").replace("_", " ").title())
    summary_columns[1].metric("Common date", run.get("common_reporting_date") or "Not available")
    summary_columns[2].metric("Confirmed revenue date", run.get("confirmed_revenue_through_date") or "Not available")
    summary_columns[3].metric(
        "Next scheduled run",
        str(os.getenv("SEO_GROWTH_DAILY_SCHEDULE_LOCAL_TIME", "Render morning job")),
    )
    actions = st.columns([1.2, 4])
    if actions[0].button(
        "Run daily pipeline now",
        type="primary",
        icon=":material/play_arrow:",
        key="seo-growth-pipeline-run-now",
        use_container_width=True,
    ):
        try:
            seo_growth_intelligence.queue_growth_pipeline(user, store=growth_store, mode="manual")
        except (google_seo.GoogleSEOError, seo_growth_intelligence.SEOGrowthError, PermissionError) as error:
            _set_notice(getattr(error, "public_message", str(error)), success=False)
        else:
            _set_notice("Daily SEO Growth Intelligence pipeline queued.")
            invalidate_seo_overview_summary_cache()
        st.rerun()
    actions[1].caption("The scheduled command is safe to run repeatedly; each stage uses durable locks and idempotent writes.")
    if stages:
        _table(
            [
                {
                    "Stage": str(row.get("stage_key") or "").replace("_", " ").title(),
                    "Status": str(row.get("status") or "").replace("_", " ").title(),
                    "Data through": row.get("data_through_date") or "",
                    "Rows processed": row.get("rows_processed") or 0,
                    "Rows written": row.get("rows_written") or 0,
                    "Issue": row.get("error_summary") or "",
                }
                for row in stages
            ],
            empty="No daily pipeline stage history has been saved yet.",
            height=280,
        )


def _render_analytics_refresh_admin(user, *, growth_store=None):
    if not os_accounts.is_admin(user):
        return
    growth_store = growth_store or seo_growth_intelligence.default_store()
    if st.button(
        "Refresh analytics",
        type="primary",
        icon=":material/refresh:",
        key="seo-refresh-analytics",
        use_container_width=True,
    ):
        try:
            result = seo_growth_intelligence.run_daily_analytics_refresh(
                store=growth_store,
                requested_by=str(user.get("id") or "manual")[:200],
            )
        except (google_seo.GoogleSEOError, google_seo_import.SEOImportError, seo_growth_intelligence.SEOGrowthError) as error:
            _set_notice(getattr(error, "public_message", str(error)), success=False)
        else:
            failed = list(result.get("failed_stages") or [])
            if result.get("status") == "completed":
                _set_notice("Analytics refreshed from the latest saved source data.")
            elif result.get("status") == "already_running":
                _set_notice("An analytics refresh is already running.")
            else:
                _set_notice(
                    result.get("error_summary")
                    or "Saved analytics remain available; the analytics refresh needs attention.",
                    success=False,
                )
            if failed:
                st.session_state["seo-refresh-failed-stages"] = failed
            invalidate_seo_overview_summary_cache()
        st.rerun()

    st.caption("Refreshes recent Google data, reads the existing Shopify/Supabase ledger and updates saved reporting.")
    with st.expander("Developer details", expanded=False):
        try:
            status = growth_store.recent_pipeline_status()
        except Exception:
            status = {}
        run = dict((status or {}).get("run") or {})
        if not run:
            st.caption("No analytics refresh has been recorded yet.")
        else:
            st.caption(
                f"Last refresh: {str(run.get('status') or 'unknown').replace('_', ' ').title()}"
                f" | Completed: {run.get('completed_at') or 'Not completed'}"
            )
            if run.get("error_summary"):
                st.caption(str(run.get("error_summary")))


def _load_reporting_health(phase4_store=None):
    try:
        if phase4_store is not None:
            return dict(phase4_store.saved_health())
        return dict(_cached_default_phase4_health())
    except google_seo_phase4.SEOPhase4Error:
        return {}


def _reporting_filters():
    columns = st.columns([1.25, 1, 1, 1, 1, 1.2])
    preset = columns[0].selectbox(
        "Period",
        (
            "Today", "Yesterday", "Last 7 days", "Last 28 days", "Last 30 days",
            "Last 90 days", "Last 16 months", "Custom range",
        ),
        index=3,
        key="seo-phase4-period",
    )
    market = columns[1].selectbox(
        "Market",
        alphabetize_options(
            ("All markets", "Australia", "United States", "United Kingdom", "Canada", "New Zealand"),
            first=("All markets",),
        ),
        key="seo-phase4-market",
    )
    device = columns[2].selectbox(
        "Device",
        alphabetize_options(("All devices", "Desktop", "Mobile", "Tablet"), first=("All devices",)),
        key="seo-phase4-device",
    )
    search_type_options = alphabetize_options(("web", "image", "video", "news"))
    search_type = columns[3].selectbox(
        "Search type",
        search_type_options,
        index=selected_option_index(search_type_options, "web"),
        key="seo-phase4-search-type",
    )
    query_class = columns[4].selectbox(
        "Queries",
        alphabetize_options(("All known queries", "Branded", "Non-branded"), first=("All known queries",)),
        key="seo-phase4-query-class",
    )
    comparison = columns[5].selectbox(
        "Compare",
        ("Off", "Previous period", "Previous year"),
        index=1,
        key="seo-phase4-compare",
    )
    if preset == "Today":
        comparison = "Off"
        st.caption("Preliminary - Search Console may still update today's data; comparison badges are disabled.")
    custom_start = custom_end = None
    if preset == "Custom range":
        date_columns = st.columns(2)
        custom_start = date_columns[0].date_input("Start date", key="seo-phase4-start")
        custom_end = date_columns[1].date_input("End date", key="seo-phase4-end")
    return {
        "preset": preset,
        "market": market,
        "device": device,
        "compare": comparison != "Off",
        "comparison": comparison,
        "search_type": search_type,
        "query_class": query_class,
        "custom_start": custom_start,
        "custom_end": custom_end,
    }


def _load_reporting_snapshot(
    filters,
    *,
    phase4_store=None,
    reporting_reader=None,
    source_health=None,
    source_scope="seo",
):
    arguments = {
        "preset": filters["preset"],
        "market": filters["market"],
        "device": filters["device"],
        "compare": filters["compare"],
        "comparison": filters["comparison"],
        "search_type": filters["search_type"],
        "query_class": filters["query_class"],
        "source_scope": source_scope,
        "custom_start": filters["custom_start"],
        "custom_end": filters["custom_end"],
    }
    if reporting_reader is not None:
        if isinstance(reporting_reader, seo_live_analytics.PostgresSEOLiveAnalyticsReader):
            return reporting_reader.snapshot(**arguments, source_health=source_health)
        legacy_arguments = {key: value for key, value in arguments.items() if key != "source_scope"}
        return reporting_reader.snapshot(**legacy_arguments)
    if phase4_store is not None:
        return seo_live_analytics.PostgresSEOLiveAnalyticsReader(phase4_store).snapshot(
            **arguments, source_health=source_health
        )
    return _cached_default_reporting_snapshot(
        arguments["preset"],
        arguments["market"],
        arguments["device"],
        arguments["compare"],
        arguments["comparison"],
        arguments["search_type"],
        arguments["query_class"],
        arguments["source_scope"],
        arguments["custom_start"],
        arguments["custom_end"],
        source_health or {},
        seo_live_analytics.default_reader().cache_revision(),
    )


def _numeric_value(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _legacy_metric_value(value, *, style="number"):
    numeric = _numeric_value(value)
    if numeric is None:
        return "—"
    if style == "percent":
        return f"{numeric * 100:.1f}%"
    if style == "position":
        return f"{numeric:.1f}"
    return f"{round(numeric):,}"


def _legacy_metric_delta(current, previous, *, position=False):
    current_value = _numeric_value(current)
    previous_value = _numeric_value(previous)
    if current_value is None or previous_value in (None, 0):
        return None
    if position:
        return f"{current_value - previous_value:+.1f} vs previous"
    change = ((current_value - previous_value) / abs(previous_value)) * 100
    return f"{change:+.1f}% vs previous"


def _metric_value(value, *, style="number", currency=""):
    numeric = _numeric_value(value)
    if numeric is None:
        return "Unavailable"
    if style == "currency":
        prefix = f"{currency} " if currency else ""
        return f"{prefix}{numeric:,.0f}"
    if style == "percent":
        return f"{numeric * 100:.1f}%"
    if style == "position":
        return f"{numeric:.1f}"
    return f"{round(numeric):,}"


def _metric_delta(current, previous, *, position=False):
    current_value = _numeric_value(current)
    previous_value = _numeric_value(previous)
    if current_value is None or previous_value is None:
        return None, None
    absolute = current_value - previous_value
    if previous_value == 0:
        return f"{absolute:+,.0f}", None
    if position:
        return f"{absolute:+.1f}", None
    change = ((current_value - previous_value) / abs(previous_value)) * 100
    return f"{absolute:+,.0f}", f"{change:+.1f}%"


def _single_currency(rows):
    currencies = sorted({str(row.get("currency") or "").upper() for row in rows or [] if row.get("currency")})
    return currencies[0] if len(currencies) == 1 else ""


def _status_label(value):
    labels = {
        "ready": "Ready",
        "import_running": "Import Running",
        "awaiting_delayed_data": "Awaiting Delayed Data",
        "no_saved_rows": "No Saved Rows",
        "stale_data": "Stale Data",
        "partial_failure": "Partial Failure",
        "configuration_required": "Configuration Required",
    }
    return labels.get(str(value or ""), str(value or "Not Available").replace("_", " ").title())


def _render_data_health_strip(health):
    def source_value(key):
        source = dict(health.get(key) or {})
        through = source.get("through_date")
        if source.get("available"):
            suffix = f" through {_display_progress_date(through)}" if through else ""
            return f"{_status_label(source.get('status'))}{suffix}"
        return _status_label(source.get("status") or "no_saved_rows")

    snapshot = dict(health.get("snapshot") or {})
    items = (
        ("Search Console", source_value("gsc")),
        ("Analytics 4", source_value("ga4")),
        ("Store data", source_value("shopify")),
        (
            "Joined reporting",
            (
                f"Ready through {_display_progress_date(snapshot.get('through_date'))}"
                if snapshot.get("available")
                else "Refresh pending"
            ),
        ),
    )
    columns = st.columns(len(items))
    for column, (label, value) in zip(columns, items):
        column.markdown(
            '<div class="sc-seo-health-pill">'
            f'<span>{html.escape(label)}</span><strong>{html.escape(str(value))}</strong>'
            '</div>',
            unsafe_allow_html=True,
        )


def _render_reporting_metrics(snapshot):
    current = snapshot.get("current") or {}
    previous = snapshot.get("previous") or {}
    health = snapshot.get("health") or {}
    organic_revenue_key = (
        "confirmed_organic_revenue"
        if current.get("confirmed_organic_revenue") is not None
        else "ga4_attributed_revenue"
    )
    organic_revenue_confirmed = organic_revenue_key == "confirmed_organic_revenue"
    metrics = (
        {
            "label": "Store Revenue",
            "key": "store_revenue",
            "style": "currency",
            "currency_key": "store_currency",
            "source": "Shopify/Supabase operational data",
            "source_key": "shopify",
            "status": "Confirmed",
        },
        {
            "label": "Store Orders",
            "key": "store_orders",
            "style": "number",
            "source": "Shopify/Supabase operational data",
            "source_key": "shopify",
            "status": "Confirmed",
        },
        {
            "label": "Organic Revenue" if organic_revenue_confirmed else "Organic Revenue (attributed)",
            "key": organic_revenue_key,
            "style": "currency",
            "currency_key": "confirmed_organic_currency" if organic_revenue_confirmed else "ga4_currency",
            "source": "Shopify-confirmed reconciliation" if organic_revenue_confirmed else "Google Analytics 4",
            "source_key": "reconciliation" if organic_revenue_confirmed else "ga4",
            "status": "Confirmed" if organic_revenue_confirmed else "Attributed, not Shopify-confirmed",
        },
        {
            "label": "Organic Sessions",
            "key": "organic_sessions",
            "style": "number",
            "source": "Google Analytics 4",
            "source_key": "ga4",
            "status": "Attributed",
        },
        {
            "label": "Organic Clicks",
            "key": "organic_clicks",
            "style": "number",
            "source": "Google Search Console",
            "source_key": "gsc",
            "status": "Saved source data",
        },
        {
            "label": "Organic Impressions",
            "key": "organic_impressions",
            "style": "number",
            "source": "Google Search Console",
            "source_key": "gsc",
            "status": "Saved source data",
        },
        {
            "label": "CTR",
            "key": "ctr",
            "style": "percent",
            "source": "Google Search Console",
            "source_key": "gsc",
            "status": "Weighted",
        },
        {
            "label": "Average Position",
            "key": "average_position",
            "style": "position",
            "source": "Google Search Console",
            "source_key": "gsc",
            "status": "Impression-weighted",
            "inverse": True,
        },
        {
            "label": "Engagement Rate",
            "key": "engagement_rate",
            "style": "percent",
            "source": "Google Analytics 4",
            "source_key": "ga4",
            "status": "Attributed",
        },
        {
            "label": "Conversion Rate",
            "key": "conversion_rate",
            "style": "percent",
            "source": "Google Analytics 4",
            "source_key": "ga4",
            "status": "GA4-attributed purchases / sessions",
        },
    )
    for start in range(0, len(metrics), 4):
        columns = st.columns(4)
        for column, metric in zip(columns, metrics[start:start + 4]):
            key = metric["key"]
            inverse = bool(metric.get("inverse"))
            currency = str(current.get(metric.get("currency_key") or "") or previous.get(metric.get("currency_key") or "") or "")
            absolute, percent = _metric_delta(current.get(key), previous.get(key), position=inverse)
            column.metric(
                metric["label"],
                _metric_value(
                    current.get(key),
                    style=metric["style"],
                    currency=currency if metric["style"] == "currency" else "",
                ),
                percent or absolute,
                delta_color="inverse" if inverse else "normal",
            )
            previous_value = _metric_value(
                previous.get(key),
                style=metric["style"],
                currency=currency if metric["style"] == "currency" else "",
            )
            source_health = health.get(metric["source_key"]) or {}
            through = source_health.get("through_date")
            detail = f"Previous: {previous_value} | {metric['source']}"
            if through:
                detail += f" | Available through {_display_progress_date(through)}"
            detail += f" | {metric['status']}" if current.get(key) is not None else " | Unavailable for these filters"
            if absolute and percent:
                detail += f" | Change: {absolute}"
            column.caption(detail)


TREND_METRICS = {
    "Store revenue": "store_revenue",
    "Store orders": "store_orders",
    "Organic sessions": "organic_sessions",
    "Organic clicks": "organic_clicks",
    "Organic impressions": "organic_impressions",
    "CTR": "ctr",
    "Average position": "average_position",
}

TREND_SOURCES = {
    "store_revenue": ("Shopify/Supabase operational data", "shopify"),
    "store_orders": ("Shopify/Supabase operational data", "shopify"),
    "organic_sessions": ("Google Analytics 4", "ga4"),
    "organic_clicks": ("Google Search Console", "gsc"),
    "organic_impressions": ("Google Search Console", "gsc"),
    "ctr": ("Google Search Console", "gsc"),
    "average_position": ("Google Search Console", "gsc"),
}


def _render_performance_chart(snapshot):
    metric_options = alphabetize_options(TREND_METRICS)
    selected = st.selectbox(
        "Chart metric",
        metric_options,
        index=selected_option_index(metric_options, next(iter(TREND_METRICS))),
        key="seo-performance-chart-metric",
    )
    key = TREND_METRICS[selected]
    chart_rows = []
    for period_label, rows in (
        ("Current period", snapshot.get("daily_trend") or []),
        ("Previous period", snapshot.get("previous_daily_trend") or []),
    ):
        for row in rows:
            value = _numeric_value(row.get(key))
            if value is None:
                continue
            chart_rows.append({"Date": row.get("date"), "Value": value, "Period": period_label})
    if not chart_rows:
        st.markdown(
            '<div class="sc-seo-empty-chart">This saved metric is unavailable for the active filters.</div>',
            unsafe_allow_html=True,
        )
        return
    st.line_chart(chart_rows, x="Date", y="Value", color="Period", height=260)
    source_label, source_key = TREND_SOURCES[key]
    through = ((snapshot.get("health") or {}).get(source_key) or {}).get("through_date")
    detail = f"Source: {source_label}"
    if through:
        detail += f" | Available through {_display_progress_date(through)}"
    st.caption(detail)


def _opportunity_label(value):
    labels = {
        "keywords_near_page_one": "Near Page One",
        "high_impressions_weak_ctr": "Weak CTR",
        "declining_pages": "Declining Page",
        "new_search_queries": "New Query",
        "trending_queries": "Trending Query",
        "ranking_gains": "Ranking Gain",
        "ranking_losses": "Ranking Loss",
        "growing_pages": "Growing Page",
        "unmapped_keywords": "Unmapped Keyword",
        "competing_pages_same_keyword": "Competing Pages",
        "product_seo_gaps": "Product Gap",
        "landing_pages_weak_engagement": "Weak Engagement",
        "landing_pages_weak_conversion": "Weak Conversion",
        "blogs_traffic_not_supporting_products": "Blog Support Gap",
        "internal_link_opportunities": "Internal Link",
        "products_strong_sales_weak_organic_visibility": "Sales / Visibility Gap",
        "market_keyword_gaps": "Market Gap",
    }
    return labels.get(str(value or ""), str(value or "").replace("_", " ").title())


def _evidence_summary(evidence):
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except (TypeError, ValueError, json.JSONDecodeError):
            evidence = {}
    evidence = dict(evidence or {})
    parts = []
    for label, key, style in (
        ("Clicks", "clicks", "number"),
        ("Impressions", "impressions", "number"),
        ("CTR", "ctr", "percent"),
        ("Position", "average_position", "position"),
        ("Pages", "page_count", "number"),
    ):
        if key in evidence:
            parts.append(f"{label}: {_metric_value(evidence.get(key), style=style)}")
    return " | ".join(parts)


def _render_reporting_opportunities(snapshot):
    rows = []
    for row in list(snapshot.get("opportunities") or [])[:8]:
        rows.append(
            {
                "Type": _opportunity_label(row.get("opportunity_type")),
                "Query/Page": row.get("query") or row.get("normalized_path") or "Mapped landing page",
                "Evidence": _evidence_summary(row.get("evidence")),
            }
        )
    _table(
        rows,
        empty="No deterministic SEO opportunities are saved for the active data date.",
        height=250,
    )


def _render_reporting_tables(snapshot, *, navigate=None):
    pages = []
    for row in list(snapshot.get("top_pages") or [])[:8]:
        currency = _single_currency([{"currency": value} for value in row.get("currencies") or []])
        pages.append(
            {
                "Landing page": row.get("title") or row.get("canonical_url") or row.get("path") or "Untitled",
                "Type": row.get("page_type") or "Page",
                "Sessions": _metric_value(row.get("sessions")),
                "Clicks": _metric_value(row.get("clicks")),
                "Impressions": _metric_value(row.get("impressions")),
                "Engagement": _metric_value(row.get("engagement_rate"), style="percent"),
                "Attributed orders": _metric_value(row.get("attributed_purchases")),
                "Attributed revenue": _metric_value(row.get("attributed_revenue"), style="currency", currency=currency),
                "Previous change": _metric_value(row.get("previous_change")),
            }
        )
    _section_heading("Top Landing Pages")
    _table(
        pages,
        empty="No saved GSC page or GA4 landing-page results are available for this period.",
        height=285,
    )

    queries = []
    for row in list(snapshot.get("top_queries") or [])[:8]:
        queries.append(
            {
                "Search query": row.get("query") or "(not provided)",
                "Clicks": row.get("clicks") or 0,
                "Impressions": row.get("impressions") or 0,
                "CTR": _metric_value(row.get("ctr"), style="percent"),
                "Position": _metric_value(row.get("average_position"), style="position"),
                "Previous clicks": _metric_value(row.get("previous_clicks")),
                "Ranking gain/loss": _metric_value(row.get("ranking_change"), style="position"),
                "Market": row.get("market") or "Other",
                "Device": str(row.get("device") or "").title(),
            }
        )
    _section_heading("Top Search Queries")
    _table(
        queries,
        empty="No search-query results are available for this period.",
        height=285,
    )
    if navigate is not None and st.button(
        "Keyword Research & Mapping",
        icon=":material/search:",
        key="seo-open-keyword-research",
    ):
        _navigate(navigate, seo.SEO_KEYWORDS_ROUTE)


def _render_country_device_breakdowns(snapshot):
    _section_heading("Countries and Devices")
    columns = st.columns(2)
    with columns[0]:
        _table(
            [
                {
                    "Market": row.get("market"),
                    "GSC clicks": _metric_value(row.get("gsc_clicks")),
                    "GSC impressions": _metric_value(row.get("gsc_impressions")),
                    "GA4 sessions": _metric_value(row.get("ga4_sessions")),
                }
                for row in snapshot.get("countries") or []
            ],
            empty="No saved country breakdown is available.",
            height=225,
        )
    with columns[1]:
        _table(
            [
                {
                    "Device": row.get("device"),
                    "GSC clicks": _metric_value(row.get("gsc_clicks")),
                    "GSC impressions": _metric_value(row.get("gsc_impressions")),
                    "GA4 sessions": _metric_value(row.get("ga4_sessions")),
                }
                for row in snapshot.get("devices") or []
            ],
            empty="No saved device breakdown is available.",
            height=225,
        )


def _render_reporting_dashboard(*, phase4_store=None, reporting_reader=None, navigate=None):
    if reporting_reader is not None and hasattr(reporting_reader, "source_health"):
        health = reporting_reader.source_health()
    elif phase4_store is not None:
        reporting_reader = seo_live_analytics.PostgresSEOLiveAnalyticsReader(phase4_store)
        health = reporting_reader.source_health()
    else:
        try:
            health = dict(_cached_default_live_source_health(
                seo_live_analytics.default_reader().cache_revision()
            ))
        except Exception:
            health = {}
    _render_data_health_strip(health)
    filters = _reporting_filters()
    try:
        snapshot = _load_reporting_snapshot(
            filters,
            phase4_store=phase4_store,
            reporting_reader=reporting_reader,
            source_health=health,
        )
    except google_seo_phase4.SEOPhase4Error:
        snapshot = {}
    health = snapshot.get("health") or health
    if snapshot.get("fallback_mode") and snapshot.get("ready"):
        st.caption("Showing saved source data. Joined reporting refresh is pending.")
    if snapshot.get("stale"):
        st.warning("The latest analytics refresh needs attention. Previously saved analytics remain available.")

    _section_heading("Main analytics")
    if snapshot.get("ready"):
        _render_reporting_metrics(snapshot)
    else:
        st.info("No saved GSC, GA4 or Shopify operational rows are available for these analytics yet.")

    _section_heading("Performance")
    if snapshot.get("ready"):
        _render_performance_chart(snapshot)
    else:
        st.markdown(
            '<div class="sc-seo-empty-chart">A saved daily trend is not available for the current reporting state.</div>',
            unsafe_allow_html=True,
        )

    if snapshot.get("ready"):
        _render_reporting_tables(snapshot, navigate=navigate)
        _render_country_device_breakdowns(snapshot)


def _render_current_work(state, user, navigate):
    left, right = st.columns([1, 1.4])
    with left:
        _section_heading("Approved Weekly Plan")
        targets = state.get("settings", {}).get("weekly_targets") or list(seo.WEEKLY_TARGETS)
        selected = st.multiselect(
            "Completed this week",
            targets,
            default=[],
            key="seo-weekly-focus-completed",
            label_visibility="collapsed",
        )
        st.progress(
            len(selected) / max(len(targets), 1),
            text=f"{len(selected)} of {len(targets)} complete",
        )
    with right:
        _section_heading("Completed Work and Measured Results")
        entries = []
        if os_accounts.can_view_activity_log(user):
            try:
                import sports_cave_dashboard

                rows = sports_cave_dashboard.list_activity_entries(
                    local_now=datetime.now(timezone.utc),
                    limit=40,
                    user=user,
                )
                entries = [
                    row
                    for row in rows
                    if str(row.get("Page/Area") or "").startswith("SEO /")
                ][:8]
            except Exception:
                entries = []
        _table(
            entries,
            empty="Completed SEO work will appear here as activity is recorded.",
            height=250,
        )


def _render_data_connections_admin(
    user,
    *,
    google_store=None,
    import_store=None,
    phase4_store=None,
    reporting_reader=None,
    growth_store=None,
    embedded=False,
):
    if not embedded:
        st.divider()
        is_open = bool(st.session_state.get(SEO_ADMIN_OPEN_STATE_KEY, False))
        if st.button(
            "Data Connections & Sync Settings",
            icon=":material/expand_less:" if is_open else ":material/expand_more:",
            key="seo-data-connections-toggle",
            use_container_width=True,
        ):
            st.session_state[SEO_ADMIN_OPEN_STATE_KEY] = not is_open
            st.rerun()
        if not is_open:
            return

    config_status = google_seo.configuration_status()
    using_default_google_store = google_store is None
    google_store = google_store or google_seo.default_store()
    gsc_health = {}
    try:
        connection = (
            _cached_default_google_connection()
            if using_default_google_store
            else google_store.get_connection()
        )
    except google_seo.GoogleSEOError:
        connection = {}
        fallback = "Needs attention" if config_status.get("ready") else "Configuration required"
        gsc_status = ga4_status = fallback
    else:
        try:
            source_health = (
                reporting_reader.source_health()
                if reporting_reader is not None
                else _cached_default_live_source_health(
                    seo_live_analytics.default_reader().cache_revision()
                )
            )
        except Exception:
            source_health = {}
        gsc_health = dict((source_health or {}).get("gsc") or {})
        gsc_status = google_seo.gsc_connection_status_label(
            config_status,
            connection,
            gsc_health,
        )
        ga4_status = google_seo.connection_status_label(
            config_status, connection, service="ga4"
        )
    shopify = _cached_default_shopify_health() if using_default_google_store else _shopify_health()

    st.subheader("Connections")
    integration_columns = st.columns([1.1, 1.1, .8])
    integration_columns[0].markdown(
        _integration_card(
            "Google Search Console",
            gsc_status,
            property_name=connection.get("gsc_property_name") or "",
            property_id=connection.get("gsc_site_url") or "",
            last_sync=(
                connection.get("gsc_canonical_synced_at")
                or connection.get("last_successful_sync_at")
                or ""
            ),
            data_date=(
                connection.get("gsc_canonical_data_through_date")
                or connection.get("gsc_data_through_date")
                or ""
            ),
        ),
        unsafe_allow_html=True,
    )
    integration_columns[1].markdown(
        _integration_card(
            "Google Analytics 4",
            ga4_status,
            property_name=connection.get("ga4_property_name") or "",
            property_id=connection.get("ga4_property_id") or "",
            last_sync=connection.get("last_successful_sync_at") or "",
            data_date=connection.get("ga4_data_through_date") or "",
        ),
        unsafe_allow_html=True,
    )
    integration_columns[2].markdown(
        _integration_card(
            "Shopify/Supabase operational data",
            shopify["status"],
            property_name="Sports Cave operational order ledger",
            property_id="Sports Cave OS",
            last_sync=shopify["last_sync"],
            extra_class="sc-seo-shopify-health",
            show_data_date=False,
        ),
        unsafe_allow_html=True,
    )
    canonical_counts = dict(gsc_health.get("canonical_counts") or {})
    if any(int(value or 0) for value in canonical_counts.values()):
        st.caption(
            "Canonical GSC rows: "
            f"{int(canonical_counts.get('property_totals') or 0):,} property totals, "
            f"{int(canonical_counts.get('queries') or 0):,} queries, "
            f"{int(canonical_counts.get('pages') or 0):,} pages and "
            f"{int(canonical_counts.get('query_pages') or 0):,} query/page rows."
        )
    _render_google_controls(user, google_store, config_status, connection)

    _render_analytics_refresh_admin(user, growth_store=growth_store)
    with st.expander("Historical import recovery", expanded=False):
        _render_historical_import_controls(
            user,
            connection,
            import_store=import_store,
            phase4_store=phase4_store,
            connection_store=google_store,
            config_ready=config_status.get("ready", False),
        )


def _render_overview(
    state,
    user,
    navigate,
    google_store=None,
    import_store=None,
    phase4_store=None,
    reporting_reader=None,
    growth_store=None,
):
    _header(seo.SEO_OVERVIEW_ROUTE, title="SEO / Store Analytics")
    _consume_google_oauth_notice()
    _render_reporting_dashboard(
        phase4_store=phase4_store,
        reporting_reader=reporting_reader,
        navigate=navigate,
    )

    _render_data_connections_admin(
        user,
        google_store=google_store,
        import_store=import_store,
        phase4_store=phase4_store,
        reporting_reader=reporting_reader,
        growth_store=growth_store,
    )


@st.dialog("Citation record", width="large")
def _citation_dialog(store, state, user, record=None):
    record = dict(record or {})
    record_id = record.get("id") or ""
    with st.form(f"seo-citation-form::{record_id or 'new'}"):
        first = st.columns(2)
        platform = first[0].text_input("Platform name *", value=record.get("platform") or "", max_chars=160)
        category = first[1].text_input("Platform category", value=record.get("category") or "", max_chars=120)
        signup_url = st.text_input("Signup URL", value=record.get("signup_url") or "")
        profile_url = st.text_input("Profile URL", value=record.get("profile_url") or "")
        second = st.columns(2)
        username_handle = second[0].text_input("Username or handle", value=record.get("username_handle") or "")
        status = second[1].selectbox(
            "Status",
            seo.CITATION_STATUSES,
            index=seo.CITATION_STATUSES.index(record.get("status")) if record.get("status") in seo.CITATION_STATUSES else 0,
        )
        checks = st.columns(3)
        website_displayed = checks[0].selectbox(
            "Website displayed",
            ("No", "Yes"),
            index=1 if record.get("website_displayed") == "Yes" else 0,
        )
        website_link_type = checks[1].selectbox(
            "Website link type",
            ("None", "Clickable", "Plain Text"),
            index=("None", "Clickable", "Plain Text").index(record.get("website_link_type")) if record.get("website_link_type") in ("None", "Clickable", "Plain Text") else 0,
        )
        logo_uploaded = checks[2].selectbox("Logo uploaded", ("No", "Yes"), index=1 if record.get("logo_uploaded") == "Yes" else 0)
        publicly_accessible = st.checkbox("Profile is publicly accessible", value=bool(record.get("publicly_accessible")))
        dates = st.columns(2)
        date_started = dates[0].date_input("Date started", value=date.fromisoformat(record["date_started"]) if record.get("date_started") else None)
        date_completed = dates[1].date_input("Date completed", value=date.fromisoformat(record["date_completed"]) if record.get("date_completed") else None)
        owner = st.text_input("Owner", value=record.get("owner") or _actor_name(user))
        login_reference = st.text_input(
            "Accounts & Access login reference",
            value=record.get("login_reference") or "",
            help="Reference an existing account record only. Never enter a password.",
        )
        notes = st.text_area("Notes", value=record.get("notes") or "", max_chars=3000)
        submitted = st.form_submit_button("Update citation" if record_id else "Add citation", type="primary", use_container_width=True)
    if submitted:
        payload = {
            "platform": platform,
            "category": category,
            "signup_url": signup_url,
            "profile_url": profile_url,
            "username_handle": username_handle,
            "website_displayed": website_displayed,
            "website_link_type": website_link_type,
            "logo_uploaded": logo_uploaded,
            "publicly_accessible": publicly_accessible,
            "status": status,
            "owner": owner,
            "date_started": date_started.isoformat() if date_started else "",
            "date_completed": date_completed.isoformat() if date_completed else "",
            "notes": notes,
            "login_reference": login_reference,
        }
        try:
            payload = seo.validate_citation(payload)
            saved = seo.upsert_record(state, "citations", payload, actor=user, record_id=record_id)
        except seo.SEOValidationError as error:
            st.warning(str(error))
            return
        if _persist(
            store,
            state,
            user,
            action="citation_updated" if record_id else "citation_created",
            area="SEO / Citations",
            message=f"Citation {'updated' if record_id else 'created'}: {saved.get('platform')}",
            entity_type="seo_citation",
            entity_id=saved["id"],
            metadata={"status": saved.get("status") or ""},
        ):
            _set_notice("Citation saved.")
            st.rerun()
    if record_id:
        st.divider()
        confirm = st.checkbox("Confirm archive", key=f"seo-citation-archive-confirm::{record_id}")
        if st.button("Archive citation", disabled=not confirm, icon=":material/archive:", use_container_width=True):
            seo.archive_record(state, "citations", record_id, actor=user)
            if _persist(store, state, user, action="citation_archived", area="SEO / Citations", message=f"Citation archived: {record.get('platform')}", entity_id=record_id):
                _set_notice("Citation archived.")
                st.rerun()


def _render_citations(store, state, user):
    _header(seo.SEO_CITATIONS_ROUTE)
    citations = seo.active_records(state, "citations")
    statuses = seo.citation_status_counts(state)
    columns = st.columns(4)
    columns[0].metric("To Do", statuses["To Do"])
    columns[1].metric("Pending Verification", statuses["Pending Verification"])
    columns[2].metric("Live", statuses["Live"])
    columns[3].metric("Skipped", statuses["Skipped"])
    action_columns = st.columns([1, 1, 4])
    add_clicked = action_columns[0].button("Add citation", type="primary", icon=":material/add:", use_container_width=True)
    selected_id = _record_selector(citations, "Citation to edit", "seo-citation-edit-select", title_field="platform") if citations else ""
    edit_clicked = action_columns[1].button("Edit", icon=":material/edit:", use_container_width=True, disabled=not selected_id)
    if add_clicked or st.session_state.pop("seo-open-citation-dialog", False):
        _citation_dialog(store, state, user)
    if edit_clicked:
        _citation_dialog(store, state, user, next(row for row in citations if str(row.get("id")) == selected_id))

    view = _active_view(
        ("All Citations", "To Do", "Pending", "Live", "Rules and Business Details"),
        key="seo-citations-view",
    )
    if view == "All Citations":
        filters = st.columns(4)
        search = filters[0].text_input("Search platform", key="seo-citation-search")
        status_filter = filters[1].selectbox("Status", ("All", *seo.CITATION_STATUSES), key="seo-citation-status-filter")
        category_values = alphabetize_options({row.get("category") for row in citations if row.get("category")})
        category_filter = filters[2].selectbox("Category", alphabetize_options(("All", *category_values)), key="seo-citation-category-filter")
        owner_values = alphabetize_options({row.get("owner") for row in citations if row.get("owner")})
        owner_filter = filters[3].selectbox("Owner", alphabetize_options(("All", *owner_values)), key="seo-citation-owner-filter")
        filtered = seo.filter_citations(
            citations,
            search=search,
            status=status_filter,
            category=category_filter,
            owner=owner_filter,
        )
        visible = _paginated_rows(filtered, key="seo-citations-all")
        _table(
            _citation_table_rows(visible),
            empty="No citations match these filters. Add a reputable profile when work begins.",
        )
        st.download_button(
            "Export citations CSV",
            seo.records_csv_bytes(filtered, ("platform", "category", "signup_url", "profile_url", "username_handle", "website_displayed", "logo_uploaded", "status", "owner", "date_completed", "notes")),
            file_name="sports-cave-citations.csv",
            mime="text/csv",
            icon=":material/download:",
        )
    elif view in {"To Do", "Pending", "Live"}:
        status_sets = {
            "To Do": {"To Do", "In Progress"},
            "Pending": {"Pending Verification"},
            "Live": {"Live"},
        }
        empty_messages = {
            "To Do": "No citations are waiting to start.",
            "Pending": "No citations are pending verification.",
            "Live": "No citations are marked Live yet.",
        }
        filtered = [row for row in citations if row.get("status") in status_sets[view]]
        visible = _paginated_rows(filtered, key=f"seo-citations-{view.casefold().replace(' ', '-')}")
        _table(_citation_table_rows(visible), empty=empty_messages[view])
    else:
        details = state.get("settings", {}).get("business_details") or seo.BUSINESS_DETAILS
        for label, key in (("Business name", "business_name"), ("Website", "website"), ("Base description", "base_description")):
            st.markdown(f"**{label}**")
            st.code(details.get(key) or "", language=None)
        _rule_expander("Objective", ["Display the Sports Cave brand name and website on reputable third-party platforms."])
        _rule_expander("Quality rules", [
            "Use legitimate profiles and consistent business information.",
            "Add the Sports Cave logo where available.",
            "Do not keyword-stuff descriptions or create duplicate profiles.",
            "Do not use bulk account-creation automation or pay merely for a citation link.",
            "Skip unsafe or low-quality platforms and record the reason.",
        ])
        _rule_expander("Tracking rule", ["If the work is not recorded in this tracker, it does not count as completed."])
        _rule_expander("Important distinction", ["Citations are profiles and business listings. They are not editorial backlinks."])


@st.dialog("Blog record", width="large")
def _blog_dialog(store, state, user, record=None):
    record = dict(record or {})
    record_id = record.get("id") or ""
    with st.form(f"seo-blog-record-form::{record_id or 'new'}"):
        article_title = st.text_input("Article title", value=record.get("article_title") or "", max_chars=240)
        columns = st.columns(2)
        sport_topic = columns[0].text_input("Sport or topic", value=record.get("sport_topic") or "")
        primary_keyword = columns[1].text_input("Primary keyword", value=record.get("primary_keyword") or "")
        search_intent_options = alphabetize_options(
            ("Player Legacy", "Greatest Moments", "Historic Rivalry", "Sports Culture", "Memorabilia Collecting", "Man Cave Inspiration", "Gift Guide", "Sports Decor Ideas", "Other")
        )
        search_intent = columns[0].selectbox(
            "Search intent",
            search_intent_options,
            index=selected_option_index(search_intent_options, record.get("search_intent") or "Player Legacy"),
        )
        target_market_options = alphabetize_options(seo.TARGET_MARKETS)
        target_market = columns[1].selectbox(
            "Target market",
            target_market_options,
            index=selected_option_index(target_market_options, record.get("target_market") or seo.TARGET_MARKETS[0]),
        )
        target_collection = columns[0].text_input("Target collection", value=record.get("target_collection") or "")
        status = columns[1].selectbox(
            "Status",
            seo.BLOG_STATUSES,
            index=seo.BLOG_STATUSES.index(record.get("status")) if record.get("status") in seo.BLOG_STATUSES else 0,
        )
        owner = columns[0].text_input("Owner", value=record.get("owner") or _actor_name(user))
        due_date = columns[1].date_input("Due date", value=date.fromisoformat(record["due_date"]) if record.get("due_date") else None)
        submitted = st.form_submit_button("Update blog record" if record_id else "Create blog brief", type="primary", use_container_width=True)
    if submitted:
        if not article_title.strip() and not primary_keyword.strip():
            st.warning("Add an article title or primary keyword.")
            return
        warning = seo.duplicate_primary_keyword_warning(state.get("blog_records"), primary_keyword, excluding_id=record_id)
        if warning:
            st.warning(warning)
            return
        saved = seo.upsert_record(
            state,
            "blog_records",
            {
                "article_title": article_title,
                "sport_topic": sport_topic,
                "primary_keyword": primary_keyword,
                "search_intent": search_intent,
                "target_market": target_market,
                "target_collection": target_collection,
                "status": status,
                "owner": owner,
                "due_date": due_date.isoformat() if due_date else "",
            },
            actor=user,
            record_id=record_id,
        )
        if _persist(store, state, user, action="blog_updated" if record_id else "blog_created", area="SEO / Blog Content", message=f"Blog record {'updated' if record_id else 'created'}: {saved.get('article_title') or saved.get('primary_keyword')}", entity_type="seo_blog", entity_id=saved["id"], metadata={"status": saved.get("status") or ""}):
            _set_notice("Blog record saved.")
            st.rerun()


def _save_blog_step(store, state, user, blog, payload, message):
    saved = seo.upsert_record(state, "blog_records", payload, actor=user, record_id=blog["id"])
    if _persist(store, state, user, action="blog_updated", area="SEO / Blog Content", message=message, entity_type="seo_blog", entity_id=saved["id"], metadata={"status": saved.get("status") or ""}):
        _set_notice("Blog work saved.")
        st.rerun()


def _render_blog_builder(store, state, user, blogs):
    if not blogs:
        st.info("Create a blog brief to start the builder.")
        return
    by_id = {str(row["id"]): row for row in blogs}
    blog_id = st.selectbox(
        "Blog record",
        alphabetize_options(
            by_id,
            label=lambda key: by_id[key].get("article_title") or by_id[key].get("primary_keyword") or "Untitled",
        ),
        format_func=lambda key: by_id[key].get("article_title") or by_id[key].get("primary_keyword") or "Untitled",
        key="seo-blog-builder-record",
    )
    blog = by_id[blog_id]
    step = _active_view(
        ("1 Brief", "2 Article", "3 SEO and Links", "4 Assets", "5 Review"),
        key=f"seo-blog-builder-step::{blog_id}",
    )
    if step == "1 Brief":
        with st.form(f"seo-blog-brief::{blog_id}"):
            columns = st.columns(2)
            article_title = columns[0].text_input("Article title", value=blog.get("article_title") or "")
            sport_topic = columns[1].text_input("Sport, player, team, rivalry or topic", value=blog.get("sport_topic") or "")
            target_market_options = alphabetize_options(seo.TARGET_MARKETS)
            target_market = columns[0].selectbox("Target market", target_market_options, index=selected_option_index(target_market_options, blog.get("target_market") or seo.TARGET_MARKETS[0]))
            content_angle = columns[1].text_input("Content angle", value=blog.get("content_angle") or "")
            search_intent = columns[0].text_input("Search intent", value=blog.get("search_intent") or "")
            primary_keyword = columns[1].text_input("Primary keyword", value=blog.get("primary_keyword") or "")
            supporting_keywords = columns[0].text_input("Supporting keywords", value=blog.get("supporting_keywords") or "")
            collection_name = columns[1].text_input("Related collection name", value=blog.get("collection_name") or "")
            collection_url = st.text_input("Related collection URL", value=blog.get("collection_url") or "")
            product_url = st.text_input("Related product URL (optional)", value=blog.get("product_url") or "")
            due_date = columns[0].date_input("Due date", value=date.fromisoformat(blog["due_date"]) if blog.get("due_date") else None)
            owner = columns[1].text_input("Owner", value=blog.get("owner") or _actor_name(user))
            submitted = st.form_submit_button("Save brief", type="primary")
        if submitted:
            try:
                collection_url = seo.validate_public_url(collection_url, label="Collection URL")
                product_url = seo.validate_public_url(product_url, label="Product URL")
            except seo.SEOValidationError as error:
                st.warning(str(error))
            else:
                warning = seo.duplicate_primary_keyword_warning(blogs, primary_keyword, excluding_id=blog_id)
                if warning:
                    st.warning(warning)
                else:
                    _save_blog_step(store, state, user, blog, {"article_title": article_title, "sport_topic": sport_topic, "target_market": target_market, "content_angle": content_angle, "search_intent": search_intent, "primary_keyword": primary_keyword, "supporting_keywords": supporting_keywords, "collection_name": collection_name, "collection_url": collection_url, "product_url": product_url, "product_url_omitted": not bool(product_url), "due_date": due_date.isoformat() if due_date else "", "owner": owner, "status": "Brief"}, "Blog brief updated")
    elif step == "2 Article":
        with st.form(f"seo-blog-article::{blog_id}"):
            article_draft = st.text_area("Article draft", value=blog.get("article_draft") or "", height=420)
            reviewer_notes = st.text_area("Notes from reviewer", value=blog.get("reviewer_notes") or "", height=100)
            submitted = st.form_submit_button("Save article draft", type="primary")
        metric_columns = st.columns(3)
        metric_columns[0].metric("Word count", seo.word_count(article_draft))
        metric_columns[1].metric("H2 count", seo.heading_count(article_draft))
        metric_columns[2].metric("Target", "1,100-1,700")
        if submitted:
            _save_blog_step(store, state, user, blog, {"article_draft": article_draft, "reviewer_notes": reviewer_notes, "status": "Draft"}, "Blog article draft updated")
        prompt_by_name = {row.get("name"): row for row in state.get("prompt_templates", [])}
        with st.expander("Topic research prompt", expanded=False):
            template = prompt_by_name.get("Blog topic research", {}).get("template") or seo.BLOG_TOPIC_RESEARCH_TEMPLATE
            st.code(seo.render_prompt_template(template, {"name": blog.get("collection_name"), "url": blog.get("collection_url"), "sport": blog.get("sport_topic"), "market": blog.get("target_market"), "keyword_data": blog.get("primary_keyword")}), language=None)
        with st.expander("Article writing prompt", expanded=False):
            template = prompt_by_name.get("Article writing", {}).get("template") or seo.ARTICLE_WRITING_TEMPLATE
            st.code(seo.render_prompt_template(template, {"title": blog.get("article_title"), "search_intent": blog.get("search_intent"), "primary_keyword": blog.get("primary_keyword"), "supporting_keywords": blog.get("supporting_keywords"), "sport_or_player": blog.get("sport_topic"), "market": blog.get("target_market"), "collection_name": blog.get("collection_name"), "collection_url": blog.get("collection_url"), "product_url_or_none": blog.get("product_url") or "None"}), language=None)
    elif step == "3 SEO and Links":
        with st.form(f"seo-blog-seo::{blog_id}"):
            seo_title = st.text_input("SEO title", value=blog.get("seo_title") or "", max_chars=80)
            meta_title = st.text_input("Meta title", value=blog.get("meta_title") or "", max_chars=80)
            meta_description = st.text_area("Meta description", value=blog.get("meta_description") or "", max_chars=220, height=90)
            url_slug = st.text_input("Suggested URL slug", value=blog.get("url_slug") or seo.slugify(blog.get("article_title")))
            excerpt = st.text_area("Excerpt", value=blog.get("excerpt") or "", height=80)
            homepage_url = st.text_input("Homepage link", value=blog.get("homepage_url") or seo.BUSINESS_DETAILS["website"])
            collection_url = st.text_input("Collection link", value=blog.get("collection_url") or "")
            omit_product = st.checkbox("No verified product link", value=bool(blog.get("product_url_omitted", not blog.get("product_url"))))
            product_url = st.text_input("Product link", value=blog.get("product_url") or "", disabled=omit_product)
            anchor_text = st.text_input("Anchor text", value=blog.get("anchor_text") or "")
            shopify_tags = st.text_input("Shopify blog tags", value=blog.get("shopify_tags") or "")
            submitted = st.form_submit_button("Save SEO and links", type="primary")
        validation = seo.meta_validation(meta_title, meta_description)
        status_columns = st.columns(2)
        status_columns[0].caption(f"Meta title: {validation['meta_title_length']} characters · target 50-60")
        status_columns[1].caption(f"Meta description: {validation['meta_description_length']} characters · target 140-160")
        if submitted:
            try:
                homepage_url = seo.validate_public_url(homepage_url, required=True, label="Homepage URL")
                collection_url = seo.validate_public_url(collection_url, label="Collection URL")
                product_url = "" if omit_product else seo.validate_public_url(product_url, label="Product URL")
            except seo.SEOValidationError as error:
                st.warning(str(error))
            else:
                _save_blog_step(store, state, user, blog, {"seo_title": seo_title, "meta_title": meta_title, "meta_description": meta_description, "url_slug": seo.slugify(url_slug), "excerpt": excerpt, "homepage_url": homepage_url, "collection_url": collection_url, "product_url": product_url, "product_url_omitted": omit_product, "anchor_text": anchor_text, "shopify_tags": shopify_tags}, "Blog SEO and links updated")
    elif step == "4 Assets":
        with st.form(f"seo-blog-assets::{blog_id}"):
            asset_columns = st.columns(2)
            hero_status = asset_columns[0].selectbox("Hero image status", ("Not started", "In progress", "Ready"), index=("Not started", "In progress", "Ready").index(blog.get("hero_image_status")) if blog.get("hero_image_status") in ("Not started", "In progress", "Ready") else 0)
            hero_filename = asset_columns[1].text_input("Hero image filename", value=blog.get("hero_image_filename") or "")
            hero_alt = st.text_input("Hero image alt text", value=blog.get("hero_image_alt") or "")
            support_status = asset_columns[0].selectbox("Supporting image status", ("Not started", "In progress", "Ready"), index=("Not started", "In progress", "Ready").index(blog.get("supporting_image_status")) if blog.get("supporting_image_status") in ("Not started", "In progress", "Ready") else 0)
            support_filename = asset_columns[1].text_input("Supporting image filename", value=blog.get("supporting_image_filename") or "")
            support_alt = st.text_input("Supporting image alt text", value=blog.get("supporting_image_alt") or "")
            youtube_url = st.text_input("YouTube URL (optional)", value=blog.get("youtube_url") or "")
            asset_notes = st.text_area("Asset notes", value=blog.get("asset_notes") or "", height=80)
            submitted = st.form_submit_button("Save assets", type="primary")
        st.caption("Prepare WebP assets at approximately 1600px for the hero and 1200px for supporting images. Preserve aspect ratio and write natural alt text.")
        if submitted:
            try:
                youtube_url = seo.validate_public_url(youtube_url, label="YouTube URL")
            except seo.SEOValidationError as error:
                st.warning(str(error))
            else:
                _save_blog_step(store, state, user, blog, {"hero_image_status": hero_status, "hero_image_filename": hero_filename, "hero_image_alt": hero_alt, "supporting_image_status": support_status, "supporting_image_filename": support_filename, "supporting_image_alt": support_alt, "youtube_url": youtube_url, "asset_notes": asset_notes}, "Blog asset plan updated")
    else:
        selected = st.multiselect("Review checklist", BLOG_REVIEW_ITEMS, default=blog.get("review_checklist") or [], key=f"seo-blog-review::{blog_id}")
        complete = len(selected) == len(BLOG_REVIEW_ITEMS)
        st.progress(len(selected) / len(BLOG_REVIEW_ITEMS), text=f"{len(selected)} of {len(BLOG_REVIEW_ITEMS)} checks complete")
        action_columns = st.columns(3)
        if action_columns[0].button("Save checklist", use_container_width=True, key=f"seo-save-checklist::{blog_id}"):
            _save_blog_step(store, state, user, blog, {"review_checklist": selected}, "Blog review checklist updated")
        if action_columns[1].button("Mark Ready for Owner", type="primary", disabled=not complete, use_container_width=True, key=f"seo-ready-owner::{blog_id}"):
            _save_blog_step(store, state, user, blog, {"review_checklist": selected, "status": "Ready for Owner"}, "Blog marked Ready for Owner")
        pack = seo.build_publish_ready_pack({**blog, "review_checklist": selected})
        action_columns[2].download_button("Export Publish-Ready Pack", pack.encode("utf-8"), file_name=f"{seo.slugify(blog.get('article_title') or 'sports-cave-blog')}-publish-pack.txt", mime="text/plain", use_container_width=True)
        with st.expander("Publish-ready pack preview", expanded=False):
            st.code(pack, language=None)


def _render_prompt_templates(state):
    templates = seo.active_records(state, "prompt_templates")
    by_id = {row["id"]: row for row in templates}
    selected_id = st.selectbox(
        "Saved template",
        alphabetize_options(by_id, label=lambda key: by_id[key].get("name")),
        format_func=lambda key: by_id[key].get("name"),
        key="seo-template-preview",
    )
    template = by_id[selected_id]
    placeholders = sorted(set(re.findall(r"{{([a-zA-Z0-9_]+)}}", template.get("template") or "")))
    variables = {}
    if placeholders:
        with st.expander("Preview variables", expanded=True):
            for placeholder in placeholders:
                variables[placeholder] = st.text_input(placeholder.replace("_", " ").title(), key=f"seo-template-variable::{selected_id}::{placeholder}")
    st.code(seo.render_prompt_template(template.get("template"), variables), language=None)
    st.caption("Copy from the preview and review the result before using it. This workspace does not pretend to run an AI service.")


def _render_blog(store, state, user):
    _header(seo.SEO_BLOG_ROUTE)
    blogs = seo.active_records(state, "blog_records")
    action_columns = st.columns([1, 1, 4])
    if action_columns[0].button("Create blog brief", type="primary", icon=":material/add:", use_container_width=True):
        _blog_dialog(store, state, user)
    selected_id = _record_selector(blogs, "Blog to edit", "seo-blog-edit-select", title_field="article_title") if blogs else ""
    if action_columns[1].button("Edit", icon=":material/edit:", use_container_width=True, disabled=not selected_id):
        _blog_dialog(store, state, user, next(row for row in blogs if str(row.get("id")) == selected_id))
    view = _active_view(("Pipeline", "Blog Builder", "Templates", "Rules"), key="seo-blog-view")
    if view == "Pipeline":
        filters = st.columns(3)
        search = filters[0].text_input("Search articles", key="seo-blog-search")
        status_filter = filters[1].selectbox("Status", ("All", *seo.BLOG_STATUSES), key="seo-blog-status-filter")
        market_filter = filters[2].selectbox("Target market", alphabetize_options(("All", *seo.TARGET_MARKETS)), key="seo-blog-market-filter")
        filtered = [row for row in blogs if (not search or search.casefold() in json.dumps(row).casefold()) and (status_filter == "All" or row.get("status") == status_filter) and (market_filter == "All" or row.get("target_market") == market_filter)]
        _table([{"Article Title": row.get("article_title"), "Sport or Topic": row.get("sport_topic"), "Primary Keyword": row.get("primary_keyword"), "Search Intent": row.get("search_intent"), "Target Market": row.get("target_market"), "Target Collection": row.get("target_collection") or row.get("collection_name"), "Status": row.get("status"), "Owner": row.get("owner"), "Due Date": row.get("due_date"), "Last Updated": row.get("updated_at")} for row in filtered], empty="No blog records yet. Create a brief to start the editorial pipeline.")
    elif view == "Blog Builder":
        _render_blog_builder(store, state, user, blogs)
    elif view == "Templates":
        _render_prompt_templates(state)
    else:
        _rule_expander("Fans first", ["Write like a premium sports journal.", "Use human rhythm, emotional storytelling and details real fans recognise.", "Avoid vague claims without explaining why."])
        _rule_expander("Structure", ["Establish the topic within the first 100 words.", "Use one central search intent and meaningful headings.", "Connect naturally to collecting or fan spaces in the final third.", "Finish with a calm, relevant call to action."])
        _rule_expander("Commercial balance", ["The article is a sports story first, never a disguised product page."])
        _rule_expander("Human review", ["Every article must be read, fact-checked and human-edited before it is marked ready."])


@st.dialog("Internal link plan", width="large")
def _link_plan_dialog(store, state, user, record=None):
    record = dict(record or {})
    record_id = record.get("id") or ""
    blogs = seo.active_records(state, "blog_records")
    blog_options = {row["id"]: row for row in blogs}
    with st.form(f"seo-link-plan-form::{record_id or 'new'}"):
        if blog_options:
            source_blog_options = alphabetize_options(
                blog_options,
                label=lambda key: blog_options[key].get("article_title") or blog_options[key].get("primary_keyword") or "Untitled",
            )
            source_blog_id = st.selectbox("Source blog *", source_blog_options, format_func=lambda key: blog_options[key].get("article_title") or blog_options[key].get("primary_keyword") or "Untitled", index=selected_option_index(source_blog_options, record.get("source_blog_id")))
            source_blog = blog_options[source_blog_id].get("article_title") or blog_options[source_blog_id].get("primary_keyword")
        else:
            source_blog_id = ""
            source_blog = st.text_input("Source blog *", value=record.get("source_blog") or "")
        sport = st.text_input("Sport", value=record.get("sport") or "")
        homepage_url = st.text_input("Homepage URL *", value=record.get("homepage_url") or seo.BUSINESS_DETAILS["website"])
        collection_url = st.text_input("Collection URL *", value=record.get("collection_url") or "")
        collection_anchor_text = st.text_input("Collection anchor text", value=record.get("collection_anchor_text") or "")
        no_product_link = st.checkbox("No Product Link", value=bool(record.get("no_product_link", not record.get("product_url"))))
        product_url = st.text_input("Product URL", value=record.get("product_url") or "", disabled=no_product_link)
        product_anchor_text = st.text_input("Product anchor text", value=record.get("product_anchor_text") or "", disabled=no_product_link)
        columns = st.columns(3)
        placement = columns[0].text_input("Placement", value=record.get("placement") or "")
        verification_status = columns[1].selectbox("Verification status", seo.LINK_VERIFICATION_STATUSES, index=seo.LINK_VERIFICATION_STATUSES.index(record.get("verification_status")) if record.get("verification_status") in seo.LINK_VERIFICATION_STATUSES else 0)
        last_checked = columns[2].date_input("Last checked", value=date.fromisoformat(record["last_checked"]) if record.get("last_checked") else None)
        notes = st.text_area("Notes", value=record.get("notes") or "")
        submitted = st.form_submit_button("Update link plan" if record_id else "Add link plan", type="primary", use_container_width=True)
    if submitted:
        try:
            payload = seo.validate_link_plan({"source_blog_id": source_blog_id, "source_blog": source_blog, "sport": sport, "homepage_url": homepage_url, "collection_url": collection_url, "collection_anchor_text": collection_anchor_text, "no_product_link": no_product_link, "product_url": product_url, "product_anchor_text": product_anchor_text, "placement": placement, "verification_status": verification_status, "last_checked": last_checked.isoformat() if last_checked else "", "notes": notes})
            saved = seo.upsert_record(state, "link_plans", payload, actor=user, record_id=record_id)
        except seo.SEOValidationError as error:
            st.warning(str(error))
            return
        if _persist(store, state, user, action="link_plan_updated" if record_id else "link_plan_created", area="SEO / Internal Linking", message=f"Internal link plan {'updated' if record_id else 'created'}: {saved.get('source_blog')}", entity_type="seo_link_plan", entity_id=saved["id"], metadata={"status": saved.get("verification_status") or ""}):
            _set_notice("Internal link plan saved.")
            st.rerun()


def _render_internal_linking(store, state, user):
    _header(seo.SEO_INTERNAL_LINKING_ROUTE)
    st.markdown('<div class="sc-seo-note sc-seo-danger"><strong>Planning only.</strong> This module never writes to Shopify. Do not change links on product pages, collection pages, homepage sections, theme code or conversion blocks.</div>', unsafe_allow_html=True)
    plans = seo.active_records(state, "link_plans")
    action_columns = st.columns([1, 1, 4])
    if action_columns[0].button("Add link plan", type="primary", icon=":material/add_link:", use_container_width=True):
        _link_plan_dialog(store, state, user)
    selected_id = _record_selector(plans, "Plan to edit", "seo-link-plan-select", title_field="source_blog") if plans else ""
    if action_columns[1].button("Edit", icon=":material/edit:", use_container_width=True, disabled=not selected_id):
        _link_plan_dialog(store, state, user, next(row for row in plans if str(row.get("id")) == selected_id))
    view = _active_view(
        ("Link Plans", "Target Library", "Link Opportunities", "Rules"),
        key="seo-internal-linking-view",
    )
    if view == "Link Plans":
        _table([{"Blog Article": row.get("source_blog"), "Sport": row.get("sport"), "Homepage Link": row.get("homepage_url"), "Collection Target": row.get("collection_url"), "Product Target": row.get("product_url") or "No Product Link", "Anchor Text": row.get("collection_anchor_text"), "Placement": row.get("placement"), "Verification Status": row.get("verification_status"), "Last Checked": row.get("last_checked"), "Owner": row.get("owner")} for row in plans], empty="No internal link plans yet. Add one when a blog brief is ready for link planning.")
    elif view == "Target Library":
        targets = seo.active_records(state, "target_library")
        _table([{"Label": row.get("label"), "URL": row.get("url"), "Verification Status": row.get("verification_status")} for row in targets], empty="No internal-link targets are available.")
        st.caption("Seeded targets are deliberately marked Needs Verification until an owner confirms the current live URL.")
        if targets:
            by_id = {row["id"]: row for row in targets}
            target_id = st.selectbox(
                "Target to verify",
                alphabetize_options(by_id, label=lambda key: by_id[key].get("label")),
                format_func=lambda key: by_id[key].get("label"),
                key="seo-target-verify-select",
            )
            with st.form(f"seo-target-edit::{target_id}"):
                label = st.text_input("Label", value=by_id[target_id].get("label") or "")
                url = st.text_input("URL", value=by_id[target_id].get("url") or "")
                verification_status = st.selectbox("Verification status", ("Needs Verification", "Verified", "Needs Update"), index=("Needs Verification", "Verified", "Needs Update").index(by_id[target_id].get("verification_status")) if by_id[target_id].get("verification_status") in ("Needs Verification", "Verified", "Needs Update") else 0)
                submitted = st.form_submit_button("Save target")
            if submitted:
                try:
                    url = seo.validate_public_url(url, required=True, label="Target URL")
                except seo.SEOValidationError as error:
                    st.warning(str(error))
                else:
                    saved = seo.upsert_record(state, "target_library", {"label": label, "url": url, "verification_status": verification_status}, actor=user, record_id=target_id)
                    if _persist(store, state, user, action="internal_target_updated", area="SEO / Internal Linking", message=f"Internal link target updated: {saved.get('label')}", entity_id=saved["id"]):
                        _set_notice("Target library updated.")
                        st.rerun()
    elif view == "Link Opportunities":
        _table(seo.internal_link_opportunities(state), empty="No missing internal-link opportunities are visible from the stored blog records.")
    else:
        _rule_expander("Simplified linking rule", ["Use one natural homepage link.", "Use one relevant sport collection link.", "Use one verified product link only when the article clearly relates to that artwork."])
        _rule_expander("Placement", ["Place the collection link naturally in the first 40% when it fits.", "Place an optional product link in the middle or final third.", "Link the homepage naturally in the conclusion.", "Use descriptive anchor text; never use 'click here'."])


@st.dialog("Outreach prospect", width="large")
def _outreach_dialog(store, state, user, record=None):
    record = dict(record or {})
    record_id = record.get("id") or ""
    with st.form(f"seo-outreach-form::{record_id or 'new'}"):
        columns = st.columns(2)
        site_creator = columns[0].text_input("Site or creator name *", value=record.get("site_creator") or "")
        website = columns[1].text_input("Website URL *", value=record.get("website") or "")
        contact_name = columns[0].text_input("Contact name", value=record.get("contact_name") or "")
        contact_email = columns[1].text_input("Contact email", value=record.get("contact_email") or "")
        creator_profile = columns[0].text_input("Creator or social profile", value=record.get("creator_profile") or "")
        niche = columns[1].text_input("Niche", value=record.get("niche") or "")
        target_market_options = alphabetize_options(seo.TARGET_MARKETS)
        target_market = columns[0].selectbox("Target market", target_market_options, index=selected_option_index(target_market_options, record.get("target_market") or seo.TARGET_MARKETS[0]))
        opportunity_options = alphabetize_options(("Editorial Mention", "Guest Article", "Creator Feature", "Gift Guide", "Resource/List", "Podcast Show Notes", "Genuine Community Contribution", "Other"))
        opportunity_type = columns[1].selectbox("Opportunity type", opportunity_options, index=selected_option_index(opportunity_options, record.get("opportunity_type") or "Editorial Mention"))
        relevant_article_url = st.text_input("Relevant article URL", value=record.get("relevant_article_url") or "")
        observed_topic = st.text_input("Specific article or topic observed", value=record.get("observed_topic") or "")
        target_page = st.text_input("Sports Cave target page", value=record.get("target_page") or "")
        anchor_columns = st.columns(2)
        anchor_options = alphabetize_options(("Brand / Naked URL", "Descriptive / Partial Match", "Exact Keyword", "Unknown"), last=("Unknown",))
        anchor_category = anchor_columns[0].selectbox("Proposed anchor category", anchor_options, index=selected_option_index(anchor_options, record.get("anchor_category") or "Brand / Naked URL"))
        anchor_text = anchor_columns[1].text_input("Proposed anchor text", value=record.get("anchor_text") or "")
        quality_result = columns[0].selectbox("Quality result", ("Needs Review", "Approved", "Rejected"), index=("Needs Review", "Approved", "Rejected").index(record.get("quality_result")) if record.get("quality_result") in ("Needs Review", "Approved", "Rejected") else 0)
        status = columns[1].selectbox("Status", seo.OUTREACH_STATUSES, index=seo.OUTREACH_STATUSES.index(record.get("status")) if record.get("status") in seo.OUTREACH_STATUSES else 0)
        rejection_reason = st.text_input("Rejection reason", value=record.get("rejection_reason") or "", disabled=status != "Rejected" and quality_result != "Rejected")
        quality_checks = st.multiselect("Qualification checklist", alphabetize_options(("Site is active", "Content appears written for humans", "Topic is relevant to Sports Cave", "Site is brand-safe", "Outbound links appear reasonable", "Page can be indexed", "Site is not a link farm", "Site is not a PBN", "Site is not primarily selling backlinks", "A real reader could benefit")), default=record.get("quality_checks") or [])
        outreach_draft = st.text_area("Outreach draft", value=record.get("outreach_draft") or "", height=160)
        dates = st.columns(3)
        date_contacted = dates[0].date_input("Date contacted", value=date.fromisoformat(record["date_contacted"]) if record.get("date_contacted") else None)
        follow_up_due = dates[1].date_input("Follow-up due", value=date.fromisoformat(record["follow_up_due"]) if record.get("follow_up_due") else None)
        follow_up_count = dates[2].number_input("Follow-ups sent", min_value=0, max_value=1, value=int(record.get("follow_up_count") or 0))
        live_url = st.text_input("Live URL", value=record.get("live_url") or "")
        relevant_placement = st.checkbox("Placement is relevant", value=bool(record.get("relevant_placement")))
        verification_date = st.date_input("Verification date", value=date.fromisoformat(record["verification_date"]) if record.get("verification_date") else None)
        disclosure_options = alphabetize_options(("Unknown/Needs Review", "Sponsored", "Nofollow", "Editorial with no material exchange"), first=("Unknown/Needs Review",))
        disclosure = st.selectbox("Link disclosure", disclosure_options, index=selected_option_index(disclosure_options, record.get("disclosure") or "Unknown/Needs Review"))
        owner = st.text_input("Owner", value=record.get("owner") or _actor_name(user))
        notes = st.text_area("Notes", value=record.get("notes") or "", height=80)
        submitted = st.form_submit_button("Update prospect" if record_id else "Add prospect", type="primary", use_container_width=True)
    if submitted:
        try:
            relevant_article_url = seo.validate_public_url(relevant_article_url, label="Relevant article URL")
            creator_profile = seo.validate_public_url(creator_profile, label="Creator profile")
            payload = seo.validate_outreach({"site_creator": site_creator, "website": website, "contact_name": contact_name, "contact_email": contact_email, "creator_profile": creator_profile, "niche": niche, "target_market": target_market, "opportunity_type": opportunity_type, "relevant_article_url": relevant_article_url, "observed_topic": observed_topic, "target_page": target_page, "anchor_category": anchor_category, "anchor_text": anchor_text, "quality_result": quality_result, "quality_checks": quality_checks, "status": status, "rejection_reason": rejection_reason, "outreach_draft": outreach_draft, "date_contacted": date_contacted.isoformat() if date_contacted else "", "follow_up_due": follow_up_due.isoformat() if follow_up_due else "", "follow_up_count": follow_up_count, "live_url": live_url, "relevant_placement": relevant_placement, "verification_date": verification_date.isoformat() if verification_date else "", "disclosure": disclosure, "owner": owner, "notes": notes})
            saved = seo.upsert_record(state, "outreach_records", payload, actor=user, record_id=record_id)
        except seo.SEOValidationError as error:
            st.warning(str(error))
            return
        action = "backlink_live" if saved.get("status") == "Live" else "outreach_updated" if record_id else "outreach_created"
        if _persist(store, state, user, action=action, area="SEO / Backlinks & Outreach", message=f"Outreach prospect {'updated' if record_id else 'created'}: {saved.get('site_creator')}", entity_type="seo_outreach", entity_id=saved["id"], metadata={"status": saved.get("status") or "", "quality_result": saved.get("quality_result") or ""}):
            _set_notice("Outreach prospect saved.")
            st.rerun()


def _render_outreach(store, state, user):
    _header(seo.SEO_BACKLINKS_ROUTE)
    st.caption("Quality first. This workspace does not send outreach messages.")
    records = seo.active_records(state, "outreach_records")
    status_counts = {status: sum(row.get("status") == status for row in records) for status in seo.OUTREACH_STATUSES}
    metrics = st.columns(6)
    metrics[0].metric("Qualified Prospects", status_counts["Qualified"])
    metrics[1].metric("Outreach Drafts", status_counts["Outreach Draft"])
    metrics[2].metric("Sent", status_counts["Sent"])
    metrics[3].metric("Replies", status_counts["Replied"])
    metrics[4].metric("Live Backlinks", status_counts["Live"])
    metrics[5].metric("Follow-ups Due", status_counts["Follow-up Due"])
    action_columns = st.columns([1, 1, 4])
    add_clicked = action_columns[0].button("Add prospect", type="primary", icon=":material/person_add:", use_container_width=True)
    selected_id = _record_selector(records, "Prospect to edit", "seo-outreach-select", title_field="site_creator") if records else ""
    edit_clicked = action_columns[1].button("Edit", icon=":material/edit:", use_container_width=True, disabled=not selected_id)
    if add_clicked or st.session_state.pop("seo-open-outreach-dialog", False):
        _outreach_dialog(store, state, user)
    if edit_clicked:
        _outreach_dialog(store, state, user, next(row for row in records if str(row.get("id")) == selected_id))
    view = _active_view(
        ("Prospects", "Outreach", "Live Links", "Templates", "Rules"),
        key="seo-outreach-view",
    )
    if view == "Prospects":
        filters = st.columns(3)
        search = filters[0].text_input("Search sites or creators", key="seo-outreach-search")
        status_filter = filters[1].selectbox("Status", ("All", *seo.OUTREACH_STATUSES), key="seo-outreach-status-filter")
        quality_filter = filters[2].selectbox("Quality result", ("All", "Needs Review", "Approved", "Rejected"), key="seo-outreach-quality-filter")
        filtered = [row for row in records if (not search or search.casefold() in json.dumps(row).casefold()) and (status_filter == "All" or row.get("status") == status_filter) and (quality_filter == "All" or row.get("quality_result") == quality_filter)]
        _table([{"Site or Creator": row.get("site_creator"), "Website": row.get("website"), "Contact": row.get("contact_name") or row.get("contact_email"), "Niche": row.get("niche"), "Opportunity Type": row.get("opportunity_type"), "Target Page": row.get("target_page"), "Quality Result": row.get("quality_result"), "Status": row.get("status"), "Last Contact": row.get("date_contacted"), "Follow-up Due": row.get("follow_up_due"), "Owner": row.get("owner")} for row in filtered], empty="No outreach prospects yet. Add a relevant, human-run site or creator after research.")
        st.download_button("Export outreach CSV", seo.records_csv_bytes(filtered, ("site_creator", "website", "contact_name", "contact_email", "niche", "opportunity_type", "target_page", "quality_result", "status", "date_contacted", "follow_up_due", "owner", "live_url")), file_name="sports-cave-outreach.csv", mime="text/csv", icon=":material/download:")
    elif view == "Outreach":
        _table([row for row in records if row.get("status") in {"Outreach Draft", "Sent", "Follow-up Due", "Replied"}], empty="No outreach conversations are active.")
    elif view == "Live Links":
        _table([{"Site or Creator": row.get("site_creator"), "Live URL": row.get("live_url"), "Target Page": row.get("target_page"), "Anchor Text": row.get("anchor_text"), "Disclosure": row.get("disclosure"), "Verified": row.get("verification_date")} for row in records if row.get("status") == "Live"], empty="No editorial backlinks are marked Live yet.")
    elif view == "Templates":
        _render_prompt_templates(state)
    else:
        _rule_expander("Allowed opportunities", ["Relevant sports and fan publications", "Man cave, home decor, collectibles and memorabilia sites", "Gift guides, podcasts with show notes, creator collaborations and useful resource articles"])
        _rule_expander("Prohibited practices", ["No gig backlinks, link farms, PBNs or spam directories", "No comment spam, forum signatures or mass-generated guest posts", "No automated blasts, fake personas or repeated copy-paste messages", "Do not pay purely for ranking links"])
        _rule_expander("Paid or gifted collaborations", ["Do not demand a followed SEO link when money, products or another benefit is exchanged.", "Record Sponsored, Nofollow, Editorial with no material exchange, or Unknown/Needs Review."])
        _rule_expander("Anchor portfolio guide", ["Approximately 70% brand or naked URL", "Approximately 20% descriptive or partial-match", "Maximum approximately 10% exact keyword"])


@st.dialog("Keyword record", width="large")
def _keyword_dialog(store, state, user, record):
    record = dict(record or {})
    with st.form(f"seo-keyword-form::{record.get('id')}"):
        st.text_input("Raw query", value=record.get("raw_query") or record.get("keyword") or "", disabled=True)
        columns = st.columns(2)
        category = columns[0].text_input("Category", value=record.get("category") or "")
        sport_player = columns[1].text_input("Sport or player", value=record.get("sport_player") or "")
        page_type_options = alphabetize_options(seo.KEYWORD_PAGE_TYPES)
        page_type = columns[0].selectbox("Intended page type", page_type_options, index=selected_option_index(page_type_options, record.get("page_type"), default=selected_option_index(page_type_options, "Blog")))
        buyer_intent = columns[1].selectbox("Buyer intent", seo.KEYWORD_INTENTS, index=seo.KEYWORD_INTENTS.index(record.get("buyer_intent")) if record.get("buyer_intent") in seo.KEYWORD_INTENTS else 4)
        priority = columns[0].selectbox("Priority", seo.KEYWORD_PRIORITIES, index=seo.KEYWORD_PRIORITIES.index(record.get("priority")) if record.get("priority") in seo.KEYWORD_PRIORITIES else 1)
        mapping_status = columns[1].selectbox("Mapping status", seo.KEYWORD_MAPPING_STATUSES, index=seo.KEYWORD_MAPPING_STATUSES.index(record.get("mapping_status")) if record.get("mapping_status") in seo.KEYWORD_MAPPING_STATUSES else 0)
        target_market_options = alphabetize_options(("", *seo.TARGET_MARKETS))
        target_market = columns[0].selectbox("Target market", target_market_options, index=selected_option_index(target_market_options, record.get("target_market") or ""))
        target_url = st.text_input("Target URL", value=record.get("target_url") or "")
        notes = st.text_input("Notes or tags", value=record.get("notes") or "")
        submitted = st.form_submit_button("Save keyword review", type="primary", use_container_width=True)
    if submitted:
        try:
            target_url = seo.validate_public_url(target_url, label="Target URL")
        except seo.SEOValidationError as error:
            st.warning(str(error))
            return
        saved = seo.upsert_record(state, "keywords", {**record, "category": category, "sport_player": sport_player, "page_type": page_type, "buyer_intent": buyer_intent, "priority": priority, "mapping_status": mapping_status, "target_market": target_market, "target_url": target_url, "notes": notes}, actor=user, record_id=record["id"])
        if _persist(store, state, user, action="keyword_updated", area="SEO / Keyword Research", message=f"Keyword reviewed: {saved.get('keyword')}", entity_type="seo_keyword", entity_id=saved["id"], metadata={"status": saved.get("mapping_status") or ""}):
            _set_notice("Keyword review saved.")
            st.rerun()


def _render_keyword_library(store, state, user, keywords):
    filters = st.columns(4)
    search = filters[0].text_input("Search keywords", key="seo-keyword-search")
    page_type_filter = filters[1].selectbox("Page type", alphabetize_options(("All", *seo.KEYWORD_PAGE_TYPES)), key="seo-keyword-type-filter")
    intent_filter = filters[2].selectbox("Intent", ("All", *seo.KEYWORD_INTENTS), key="seo-keyword-intent-filter")
    status_filter = filters[3].selectbox("Mapping status", ("All", *seo.KEYWORD_MAPPING_STATUSES), key="seo-keyword-status-filter")
    second = st.columns(4)
    market_filter = second[0].selectbox("Target market", alphabetize_options(("All", "Unassigned", *seo.TARGET_MARKETS), first=("Unassigned",)), key="seo-keyword-market-filter")
    has_target = second[1].selectbox("Has target URL", ("All", "Yes", "No"), key="seo-keyword-target-filter")
    max_position = second[2].number_input("Maximum position", min_value=0.0, value=0.0, step=1.0)
    min_impressions = second[3].number_input("Minimum impressions", min_value=0, value=0, step=10)
    filtered = []
    for row in keywords:
        if search and search.casefold() not in json.dumps(row).casefold():
            continue
        if page_type_filter != "All" and row.get("page_type") != page_type_filter:
            continue
        if intent_filter != "All" and row.get("buyer_intent") != intent_filter:
            continue
        if status_filter != "All" and row.get("mapping_status") != status_filter:
            continue
        if market_filter == "Unassigned" and row.get("target_market"):
            continue
        if market_filter not in {"All", "Unassigned"} and row.get("target_market") != market_filter:
            continue
        if has_target == "Yes" and not row.get("target_url"):
            continue
        if has_target == "No" and row.get("target_url"):
            continue
        if max_position and float(row.get("average_position") or 0) > max_position:
            continue
        if int(row.get("impressions") or 0) < min_impressions:
            continue
        filtered.append(row)
    _table([{"Category": row.get("category"), "Keyword": row.get("keyword"), "Sport or Player": row.get("sport_player"), "Intended Page Type": row.get("page_type"), "Buyer Intent": row.get("buyer_intent"), "Priority": row.get("priority"), "Notes": row.get("notes"), "Clicks": row.get("clicks"), "Impressions": row.get("impressions"), "CTR": row.get("ctr"), "Average Position": row.get("average_position"), "Target URL": row.get("target_url"), "Mapping Status": row.get("mapping_status"), "Source": row.get("source"), "Imported Date": row.get("imported_date")} for row in filtered], empty="No real keyword data has been imported yet. Use a Google Search Console Performance Queries CSV to begin.")
    controls = st.columns([1.7, 1.7, 2])
    selected_id = _record_selector(filtered, "Keyword to review", "seo-keyword-edit-select", title_field="keyword") if filtered else ""
    if controls[0].button("Review", icon=":material/edit:", disabled=not selected_id, use_container_width=True):
        _keyword_dialog(store, state, user, next(row for row in filtered if str(row.get("id")) == selected_id))
    controls[1].download_button("Export CSV", seo.keyword_csv_bytes(filtered), file_name="sports-cave-keywords.csv", mime="text/csv", icon=":material/download:", use_container_width=True)


def _render_gsc_import(store, state, user, keywords):
    st.markdown(
        '<div class="sc-seo-note"><strong>Manual GSC keyword import</strong><br>'
        'Use a real Performance Queries CSV for keyword records. The Phase 1 live connection '
        'checks access and freshness only; it does not import reporting rows.</div>',
        unsafe_allow_html=True,
    )
    upload = st.file_uploader("Google Search Console Performance Queries CSV", type=["csv"], key="seo-gsc-upload")
    if st.button("Preview import", type="primary", disabled=upload is None, icon=":material/preview:"):
        try:
            preview = seo.parse_gsc_csv(upload.getvalue(), existing_keywords=keywords)
        except (UnicodeDecodeError, seo.SEOValidationError) as error:
            st.warning(str(error))
        else:
            st.session_state["seo-gsc-preview"] = preview
    preview = st.session_state.get("seo-gsc-preview")
    if not preview:
        st.info("Choose a CSV and preview it before committing any records.")
        return
    summary = st.columns(3)
    summary[0].metric("Ready to import", preview.get("importable_count", 0))
    summary[1].metric("Skipped duplicates", preview.get("skipped_count", 0))
    summary[2].metric("Invalid rows", preview.get("invalid_count", 0))
    _table([{"Query": row.get("keyword"), "Clicks": row.get("clicks"), "Impressions": row.get("impressions"), "CTR": row.get("ctr"), "Position": row.get("average_position"), "Suggested Intent": row.get("buyer_intent"), "Suggested Type": row.get("page_type")} for row in preview.get("rows", [])], empty="No valid rows are ready to import.", height=280)
    if preview.get("invalid"):
        with st.expander("Invalid rows", expanded=False):
            st.dataframe(preview["invalid"], use_container_width=True, hide_index=True)
    action_columns = st.columns(2)
    if action_columns[0].button("Commit import", type="primary", disabled=not preview.get("rows"), use_container_width=True):
        result = seo.commit_gsc_import(state, preview, actor=user)
        if _persist(store, state, user, action="gsc_csv_imported", area="SEO / Keyword Research", message=f"GSC CSV imported: {result['imported']} keywords", entity_type="seo_import", metadata={"imported": result["imported"], "skipped": result["skipped"], "invalid": result["invalid"]}):
            st.session_state.pop("seo-gsc-preview", None)
            _set_notice(f"Imported {result['imported']} keywords. Skipped {result['skipped']}; invalid {result['invalid']}.")
            st.rerun()
    if action_columns[1].button("Cancel import", use_container_width=True):
        st.session_state.pop("seo-gsc-preview", None)
        _set_notice("Import cancelled. No keyword records were changed.")
        st.rerun()


def _render_page_mapping(store, state, user, keywords):
    mappings = seo.active_records(state, "keyword_mappings")
    conflicts = seo.mapping_conflicts(mappings)
    _table([{"Primary Keyword": row.get("primary_keyword"), "Page Type": row.get("page_type"), "Target Page": row.get("target_page"), "Supporting Keywords": row.get("supporting_keywords"), "Market": row.get("market"), "Mapping Status": "Conflict" if row.get("id") in conflicts else row.get("mapping_status"), "Potential Conflict": "Review" if row.get("id") in conflicts else ""} for row in mappings], empty="No page mappings yet. Review a real keyword and assign it to a verified target page.")
    if not keywords:
        return
    by_id = {row["id"]: row for row in keywords}
    keyword_id = st.selectbox(
        "Keyword",
        alphabetize_options(by_id, label=lambda key: by_id[key].get("keyword")),
        format_func=lambda key: by_id[key].get("keyword"),
        key="seo-map-keyword",
    )
    keyword = by_id[keyword_id]
    with st.form("seo-keyword-map-form"):
        columns = st.columns(2)
        page_type_options = alphabetize_options(seo.KEYWORD_PAGE_TYPES)
        market_options = alphabetize_options(seo.TARGET_MARKETS)
        page_type = columns[0].selectbox("Page type", page_type_options, index=selected_option_index(page_type_options, keyword.get("page_type"), default=selected_option_index(page_type_options, "Blog")))
        market = columns[1].selectbox("Market", market_options, index=selected_option_index(market_options, keyword.get("target_market") or seo.TARGET_MARKETS[0]))
        target_page = st.text_input("Verified target page URL", value=keyword.get("target_url") or "")
        supporting_keywords = st.text_input("Supporting keywords")
        submitted = st.form_submit_button("Save mapping", type="primary")
    if submitted:
        try:
            target_page = seo.validate_public_url(target_page, required=True, label="Target page URL")
        except seo.SEOValidationError as error:
            st.warning(str(error))
        else:
            saved = seo.upsert_record(state, "keyword_mappings", {"keyword_id": keyword_id, "primary_keyword": keyword.get("keyword"), "page_type": page_type, "target_page": target_page, "supporting_keywords": supporting_keywords, "market": market, "mapping_status": "Mapped"}, actor=user)
            seo.upsert_record(state, "keywords", {**keyword, "page_type": page_type, "target_market": market, "target_url": target_page, "mapping_status": "Mapped"}, actor=user, record_id=keyword_id)
            if _persist(store, state, user, action="keyword_mapped", area="SEO / Keyword Research", message=f"Keyword mapped: {keyword.get('keyword')}", entity_type="seo_keyword_mapping", entity_id=saved["id"]):
                _set_notice("Keyword mapping saved.")
                st.rerun()
    if st.button("Create Blog Brief from Keyword", icon=":material/post_add:"):
        brief = seo.create_blog_brief_from_keyword(state, keyword, actor=user)
        if _persist(store, state, user, action="blog_brief_from_keyword", area="SEO / Keyword Research", message=f"Blog brief created from keyword: {keyword.get('keyword')}", entity_type="seo_blog", entity_id=brief["id"]):
            _set_notice("Blog brief created without publishing anything.")
            st.rerun()
    st.caption("This workspace never changes live URLs or creates Shopify pages. Product and collection changes require owner approval.")


def _render_saved_query_intelligence(*, growth_store=None):
    filters = _reporting_filters()
    opportunity_options = (
        "All",
        "new_search_queries",
        "trending_queries",
        "ranking_gains",
        "ranking_losses",
        "keywords_near_page_one",
        "high_impressions_weak_ctr",
        "unmapped_keywords",
        "competing_pages_same_keyword",
        "product_seo_gaps",
        "market_keyword_gaps",
    )
    opportunity_type = st.selectbox(
        "Opportunity type",
        alphabetize_options(
            opportunity_options,
            label=lambda value: "All opportunities" if value == "All" else _opportunity_label(value),
            first=("All opportunities",),
        ),
        format_func=lambda value: "All opportunities" if value == "All" else _opportunity_label(value),
        key="seo-keyword-saved-opportunity-type",
    )
    growth_store = growth_store or seo_growth_intelligence.default_store()
    try:
        rows = growth_store.keyword_workspace_rows(
            filters=filters,
            opportunity_type=opportunity_type,
        )
    except Exception:
        st.info("Saved query intelligence is unavailable until reporting snapshots have been built.")
        return
    prepared = []
    for row in rows:
        prepared.append(
            {
                "Query": row.get("query") or "",
                "Opportunity": _opportunity_label(row.get("opportunity_type")),
                "Status": str(row.get("opportunity_status") or "").replace("_", " ").title(),
                "Priority": row.get("priority_score") or 0,
                "Current page": row.get("current_page") or "Unmapped",
                "Page type": row.get("page_type") or "",
                "Clicks": row.get("clicks") or 0,
                "Impressions": row.get("impressions") or 0,
                "CTR": _metric_value(row.get("ctr"), style="percent"),
                "Position": _metric_value(row.get("average_position"), style="position"),
            }
        )
    _table(
        prepared,
        empty="No saved query intelligence matches the current filters.",
        height=420,
    )
    st.caption("Approve, ignore, snooze and task conversion happen from Reports & Strategy or Tasks & Results after owner review.")


def _render_keywords(store, state, user, *, growth_store=None):
    _header(seo_nav.SEO_MAPPING_ROUTE)
    st.caption("Use real search data only. This workspace never invents search volume, clicks, impressions, CTR or position.")
    keywords = seo.active_records(state, "keywords")
    tab_names = ("Saved Query Intelligence", "Keyword Library", "Import GSC CSV", "Page Mapping", "Analysis Prompt", "Rules")
    view = _active_view(
        tab_names,
        key="seo-keyword-view",
        default=st.session_state.get("seo-keyword-view") or tab_names[0],
    )
    if view == "Saved Query Intelligence":
        _render_saved_query_intelligence(growth_store=growth_store)
    elif view == "Keyword Library":
        _render_keyword_library(store, state, user, keywords)
    elif view == "Import GSC CSV":
        _render_gsc_import(store, state, user, keywords)
    elif view == "Page Mapping":
        _render_page_mapping(store, state, user, keywords)
    elif view == "Analysis Prompt":
        template = next((row for row in state.get("prompt_templates", []) if row.get("name") == "Keyword extraction"), {})
        st.code(template.get("template") or seo.KEYWORD_EXTRACTION_TEMPLATE, language=None)
        st.caption("Copy this prompt and supply the real GSC data. The workspace does not fabricate an AI result.")
    else:
        _rule_expander("Core rule", ["Use only real Google Search Console data.", "Keep low-intent terms for human review instead of automatically deleting them."])
        _rule_expander("Mapping", ["Use one primary keyword per target page.", "Warn about likely cannibalisation.", "Do not change live URLs or create pages automatically."])


def _analysis_bundle_key(route_key):
    return f"seo-growth-analysis-bundle::{route_key}"


def _build_current_analysis_bundle(state, *, analysis_mode, filters, phase4_store=None, reporting_reader=None):
    snapshot = _load_reporting_snapshot(
        filters,
        phase4_store=phase4_store,
        reporting_reader=reporting_reader,
    )
    return seo_growth_intelligence.build_analysis_bundle(
        snapshot,
        state,
        analysis_mode=analysis_mode,
        filters=filters,
    )


def _render_analysis_bundle(bundle):
    if not bundle:
        return
    st.caption(f"Prepared for {bundle.get('analysis_mode') or 'SEO analysis'} | Data through {bundle.get('data_through') or 'Not available'}")
    st.text_area(
        "Master prompt",
        value=bundle.get("prompt") or "",
        height=280,
        key="seo-growth-master-prompt-preview",
    )
    st.text_area(
        "Sanitised JSON analysis snapshot",
        value=bundle.get("snapshot_json") or "",
        height=260,
        key="seo-growth-snapshot-json-preview",
    )
    st.download_button(
        "Download JSON snapshot",
        data=(bundle.get("snapshot_json") or "{}").encode("utf-8"),
        file_name="sports-cave-seo-analysis-snapshot.json",
        mime="application/json",
        icon=":material/download:",
        use_container_width=True,
    )
    with st.expander("Human-readable analytics summary", expanded=False):
        st.code(bundle.get("summary") or "", language=None)


def _render_report_history(growth_store):
    try:
        reports = growth_store.list_reports(limit=30)
        snapshots = growth_store.list_snapshots(limit=10)
    except Exception:
        st.info("Saved report history is unavailable until the Growth Intelligence migration is applied.")
        return
    _section_heading("Report History")
    _table(
        [
            {
                "Report type": row.get("report_type") or "",
                "Status": str(row.get("status") or "").replace("_", " ").title(),
                "Model": row.get("model_name") or "Manual snapshot",
                "Created": row.get("created_at") or "",
                "Snapshot": row.get("snapshot_id") or "",
            }
            for row in reports
        ],
        empty="No saved reports yet. Prepare a snapshot or generate a report to start the history.",
        height=260,
    )
    with st.expander("Recent source snapshots", expanded=False):
        _table(
            [
                {
                    "Mode": row.get("analysis_mode") or "",
                    "Data through": row.get("data_through") or "",
                    "Created": row.get("created_at") or "",
                    "Created by": row.get("created_by") or "",
                    "Snapshot ID": row.get("id") or "",
                }
                for row in snapshots
            ],
            empty="No analysis snapshots saved yet.",
            height=220,
        )


def _render_recommendation_review(user, growth_store):
    _section_heading("Recommendations")
    try:
        recommendations = growth_store.list_recommendations(limit=100)
    except Exception:
        st.info("Recommendations will appear after a structured report is saved.")
        return
    _table(
        [
            {
                "Status": str(row.get("status") or "").replace("_", " ").title(),
                "Priority": row.get("priority") or "",
                "Target keyword": row.get("target_keyword") or "",
                "Market": row.get("target_market") or "",
                "Recommended action": row.get("recommended_action") or "",
                "Owner": row.get("proposed_owner") or "",
            }
            for row in recommendations
        ],
        empty="No saved recommendations yet.",
        height=300,
    )
    if not os_accounts.is_admin(user) or not recommendations:
        return
    by_id = {str(row.get("id")): row for row in recommendations}
    selected_id = st.selectbox(
        "Recommendation to review",
        tuple(by_id),
        format_func=lambda key: by_id[key].get("target_keyword") or by_id[key].get("recommended_action") or key,
        key="seo-growth-recommendation-review-select",
    )
    selected = by_id[selected_id]
    controls = st.columns([1, 1, 1, 1, 2])
    if controls[0].button("Approve", icon=":material/check:", use_container_width=True):
        growth_store.update_recommendation_status(selected_id, status="approved", actor=str(user.get("id") or ""))
        _set_notice("Recommendation approved.")
        st.rerun()
    if controls[1].button("Reject", icon=":material/close:", use_container_width=True):
        growth_store.update_recommendation_status(selected_id, status="rejected", actor=str(user.get("id") or ""))
        _set_notice("Recommendation rejected.")
        st.rerun()
    if controls[2].button("Snooze", icon=":material/schedule:", use_container_width=True):
        growth_store.update_recommendation_status(
            selected_id,
            status="snoozed",
            actor=str(user.get("id") or ""),
            snoozed_until=date.today() + timedelta(days=14),
        )
        _set_notice("Recommendation snoozed for 14 days.")
        st.rerun()
    if controls[3].button("Create task", icon=":material/assignment:", use_container_width=True):
        growth_store.convert_recommendation_to_task(
            selected_id,
            actor=str(user.get("id") or ""),
            owner=selected.get("proposed_owner") or "",
        )
        _set_notice("Approved SEO task created with 28/56/90-day measurements.")
        st.rerun()
    controls[4].caption("Recommendations never publish website changes automatically.")


def _render_reports_strategy(
    store,
    state,
    user,
    *,
    phase4_store=None,
    reporting_reader=None,
    growth_store=None,
):
    _header(seo.SEO_REPORTS_ROUTE)
    growth_store = growth_store or seo_growth_intelligence.default_store()
    analysis_modes = alphabetize_options(seo_growth_intelligence.ANALYSIS_MODES)
    mode = st.selectbox(
        "Report type",
        analysis_modes,
        index=selected_option_index(analysis_modes, seo_growth_intelligence.ANALYSIS_MODES[0]),
        key="seo-growth-analysis-mode",
    )
    filters = _reporting_filters()
    openai_status = seo_growth_intelligence.openai_config_status()
    st.caption(
        "OpenAI mode is server-side only. Prepare for ChatGPT always works without an API key."
    )
    action_columns = st.columns([1.2, 1.25, 2.5])
    bundle_key = _analysis_bundle_key("reports")
    if action_columns[0].button(
        "Generate Weekly Growth Report",
        type="primary",
        icon=":material/auto_awesome:",
        use_container_width=True,
        key="seo-growth-generate-report",
    ):
        bundle = _build_current_analysis_bundle(
            state,
            analysis_mode=mode,
            filters=filters,
            phase4_store=phase4_store,
            reporting_reader=reporting_reader,
        )
        st.session_state[bundle_key] = bundle
        result = seo_growth_intelligence.generate_openai_report(
            bundle,
            store=growth_store,
            created_by=str(user.get("id") or ""),
        )
        if result.get("ok"):
            _set_notice("Structured SEO growth report saved.")
        else:
            _set_notice(result.get("message") or "OpenAI report unavailable. Use the prepared prompt.", success=False)
        st.rerun()
    if action_columns[1].button(
        "Prepare for ChatGPT",
        icon=":material/content_copy:",
        use_container_width=True,
        key="seo-growth-prepare-chatgpt",
    ):
        bundle = _build_current_analysis_bundle(
            state,
            analysis_mode=mode,
            filters=filters,
            phase4_store=phase4_store,
            reporting_reader=reporting_reader,
        )
        st.session_state[bundle_key] = bundle
        try:
            growth_store.save_analysis_snapshot(bundle, created_by=str(user.get("id") or ""))
        except Exception:
            pass
        _set_notice("Sanitised ChatGPT evidence pack prepared.")
        st.rerun()
    action_columns[2].caption(
        f"In-app OpenAI: {'Configured' if openai_status.get('configured') else 'Not configured'}"
        f" | Model: {openai_status.get('model') or 'Server default'}"
    )
    _render_analysis_bundle(st.session_state.get(bundle_key))
    _render_report_history(growth_store)
    _render_recommendation_review(user, growth_store)


def _render_tasks_results(user, *, growth_store=None):
    _header(seo.SEO_TASKS_ROUTE)
    growth_store = growth_store or seo_growth_intelligence.default_store()
    try:
        tasks = growth_store.list_tasks(limit=100)
        measurements = growth_store.list_measurements(limit=100)
    except Exception:
        st.info("Approved SEO tasks and measurements will appear after the Growth Intelligence migration is applied.")
        return
    _section_heading("Approved SEO Tasks")
    visible_tasks = tasks if os_accounts.is_admin(user) else [row for row in tasks if row.get("status") in {"approved", "assigned", "in_progress", "completed", "measuring", "measured"}]
    _table(
        [
            {
                "Status": str(row.get("status") or "").replace("_", " ").title(),
                "Task": row.get("title") or "",
                "Keyword": row.get("target_keyword") or "",
                "Market": row.get("target_market") or "",
                "Target page": row.get("target_page") or "",
                "Owner": row.get("owner") or "",
                "Due": row.get("due_date") or "",
            }
            for row in visible_tasks
        ],
        empty="No approved SEO tasks yet.",
        height=320,
    )
    if os_accounts.is_admin(user) and tasks:
        by_id = {str(row.get("id")): row for row in tasks}
        selected_id = st.selectbox(
            "Task to update",
            tuple(by_id),
            format_func=lambda key: by_id[key].get("title") or key,
            key="seo-growth-task-status-select",
        )
        update_columns = st.columns([1, 1, 1, 3])
        for label, status in (
            ("Assign", "assigned"),
            ("Complete", "completed"),
            ("Measuring", "measuring"),
        ):
            if update_columns[("Assign", "Complete", "Measuring").index(label)].button(label, use_container_width=True):
                growth_store.update_task_status(selected_id, status=status, actor=str(user.get("id") or ""))
                _set_notice(f"Task marked {status.replace('_', ' ')}.")
                st.rerun()
        update_columns[3].caption("Tasks require proof and owner review; nothing publishes automatically.")
    _section_heading("Measured Results")
    _table(
        [
            {
                "Task": row.get("title") or "",
                "Window": f"{row.get('window_days') or ''} days",
                "Status": str(row.get("measurement_status") or "").replace("_", " ").title(),
                "Baseline": row.get("baseline_date") or "",
                "Due": row.get("due_date") or "",
                "Measured": row.get("measured_at") or "",
                "Result": (row.get("change_summary") or {}).get("result") if isinstance(row.get("change_summary"), dict) else "",
                "Confidence": row.get("measurement_confidence") or "",
            }
            for row in measurements
        ],
        empty="No 28/56/90-day measurements have been scheduled yet.",
        height=300,
    )


def _saved_search_snapshot(
    *,
    phase4_store=None,
    reporting_reader=None,
    include_organic_ga4=False,
):
    filters = _reporting_filters()
    if (
        phase4_store is None
        and reporting_reader is None
        and not any(str(os.getenv(key) or "").strip() for key in DATABASE_URL_ENV_KEYS)
    ):
        return {
            "ready": False,
            "reason": "database_not_configured",
            "health": {
                "gsc": {
                    "available": False,
                    "status": "configuration_required",
                    "through_date": "",
                }
            },
            "current": {},
            "previous": {},
            "daily_trend": [],
            "top_queries": [],
            "top_pages": [],
        }
    try:
        return _load_reporting_snapshot(
            filters,
            phase4_store=phase4_store,
            reporting_reader=reporting_reader,
            source_scope="seo_landing" if include_organic_ga4 else "seo",
        )
    except Exception:
        return {"ready": False, "reason": "saved_data_unavailable", "top_queries": [], "top_pages": []}


def _filter_json(filters):
    return json.dumps(filters or {}, sort_keys=True, default=str, separators=(",", ":"))


def _interactive_reader(*, phase4_store=None, reporting_reader=None):
    if reporting_reader is not None:
        if all(hasattr(reporting_reader, name) for name in ("overview_base", "query_page", "landing_pages")):
            return reporting_reader, False
        return None, False
    if phase4_store is not None:
        backend = phase4_store._backend() if hasattr(phase4_store, "_backend") else None
        return seo_reporting_runtime.PostgresSEOInteractiveReader(backend), False
    return seo_reporting_runtime.default_reader(), True


def _interactive_context(reader, *, use_cache):
    started = time.perf_counter()
    cache_state = _cache_observation("interactive-reporting-context") if use_cache else "bypass"
    context = _cached_interactive_reporting_context() if use_cache else reader.reporting_context()
    logging.info(
        "SEO_PERF operation=snapshot_reader_total duration_ms=%.2f cache=%s watermark=%s",
        (time.perf_counter() - started) * 1000,
        cache_state,
        context.get("watermark") or "none",
    )
    return context


def _cache_observation(key):
    """Record session-observed reporting cache hits without storing user decisions."""
    observed = set(st.session_state.get("seo-reporting-cache-observed") or ())
    hit = key in observed
    observed.add(key)
    st.session_state["seo-reporting-cache-observed"] = sorted(observed)[-160:]
    return "hit" if hit else "miss"


def _load_interactive_overview(filters, reader, context, *, use_cache, route):
    started = time.perf_counter()
    filters_json = _filter_json(filters)
    context_json = json.dumps(context, sort_keys=True, default=str, separators=(",", ":"))
    cache_key = hashlib.sha256(
        f"overview|{filters_json}|{context.get('watermark', '')}".encode("utf-8")
    ).hexdigest()[:24]
    cache_state = _cache_observation(cache_key) if use_cache else "bypass"
    snapshot = (
        _cached_interactive_overview(filters_json, context_json, context.get("watermark") or "")
        if use_cache
        else reader.overview_base(filters, context=context)
    )
    diagnostics = dict(snapshot.get("diagnostics") or {})
    seo_reporting_runtime.log_diagnostics(route, "overview_base", diagnostics, cache=cache_state)
    logging.info(
        "SEO_PERF route=%s operation=overview_base_total duration_ms=%.2f cache=%s",
        route,
        (time.perf_counter() - started) * 1000,
        cache_state,
    )
    return snapshot


def _snapshot_unavailable_notice(snapshot):
    reason = str((snapshot or {}).get("reason") or "")
    if reason == "search_type_snapshot_unavailable":
        st.info("This search type is not in the saved interactive reporting snapshot yet. Select Web or wait for the next background reporting refresh.")
    elif reason in {"reporting_snapshot_unavailable", "saved_data_unavailable"}:
        st.warning(
            "The compact SEO reporting snapshot is unavailable. Background sync can repair it; "
            "this page will not scan or rebuild full Search Console history while you wait."
        )


def _progressive_query_rows(
    reader,
    filters,
    context,
    *,
    view,
    search,
    key,
    use_cache=False,
    signature_extra=None,
    excluded_queries=(),
):
    del use_cache  # Pages live in session state so prior rows are never refetched.
    controls = st.columns([1, 1.2, 2.3, 2.4])
    page_size = controls[0].selectbox(
        "Rows",
        (25, 50, 100),
        index=0,
        key=f"{key}-rows-control",
    )
    signature = seo_pagination.pagination_signature(
        {
            "filters": filters,
            "view": view,
            "search": str(search or "").strip().casefold(),
            "sort": "view-default-v1",
            "watermark": context.get("watermark") or "",
            "page_size": page_size,
            "extra": signature_extra or {},
            "excluded_queries": sorted(excluded_queries),
        }
    )
    state_key = f"{key}-progressive-state"
    state = seo_pagination.state_for(
        st.session_state,
        state_key,
        signature=signature,
        page_size=page_size,
    )

    def fetch(limit):
        started = time.perf_counter()
        page = reader.query_page(
            filters,
            view=view,
            search=search,
            limit=limit,
            cursor=state.get("cursor"),
            context=context,
            excluded_queries=excluded_queries,
        )
        seo_reporting_runtime.log_diagnostics(
            view,
            "query_page",
            page.get("diagnostics"),
            cache="session-miss",
        )
        logging.info(
            "SEO_PERF route=%s operation=query_page_total duration_ms=%.2f requested_rows=%s returned_rows=%s",
            view,
            (time.perf_counter() - started) * 1000,
            limit,
            len(page.get("rows") or []),
        )
        return page

    if not state.get("rows") and not state.get("complete"):
        state = seo_pagination.append_page(state, fetch(page_size))
        st.session_state[state_key] = state
    controls[1].caption(seo_pagination.visible_count_label(state))
    load_more = controls[2].button(
        "Load 25 more",
        key=f"{key}-load-more::{signature}::{len(state.get('rows') or [])}",
        disabled=bool(state.get("complete")),
        help="Append the next 25 keywords using stable server-side ordering.",
    )
    if load_more and not state.get("complete"):
        controls[2].caption("Loading the next 25 keywords…")
        state = seo_pagination.append_page(state, fetch(25))
        st.session_state[state_key] = state
    export_key = f"{key}-csv-export"
    export_state = dict(st.session_state.get(export_key) or {})
    if export_state.get("signature") != signature:
        export_state = {}
        st.session_state[export_key] = export_state
    if export_state.get("data"):
        controls[3].download_button(
            f"Download {int(export_state.get('count') or 0):,} rows",
            export_state["data"],
            file_name=f"sports-cave-{key.replace('seo-v2-', '')}.csv",
            mime="text/csv",
            key=f"{key}-download::{signature}",
            use_container_width=True,
        )
    elif controls[3].button(
        "Prepare filtered CSV",
        key=f"{key}-prepare-export::{signature}",
        help="Query the complete filtered result without rendering it in the browser.",
        use_container_width=True,
    ):
        controls[3].caption("Preparing the filtered CSV…")
        export = reader.query_export(
            filters,
            view=view,
            search=search,
            context=context,
            excluded_queries=excluded_queries,
        )
        seo_reporting_runtime.log_diagnostics(
            view,
            "query_export",
            export.get("diagnostics"),
            cache="explicit-export",
        )
        export_rows = []
        for row in export.get("rows") or []:
            export_rows.append(
                {
                    "query": row.get("query") or "",
                    "clicks": row.get("clicks") or 0,
                    "impressions": row.get("impressions") or 0,
                    "ctr": row.get("ctr") or 0,
                    "average_position": row.get("average_position") or 0,
                    "click_change": row.get("click_change") or 0,
                    "ranking_change": row.get("ranking_change") or 0,
                    "current_page": row.get("current_page") or "",
                    "markets": ", ".join(row.get("market_mix") or []),
                    "devices": ", ".join(row.get("device_mix") or []),
                }
            )
        export_state = {
            "signature": signature,
            "count": len(export_rows),
            "data": seo.records_csv_bytes(
                export_rows,
                (
                    "query", "clicks", "impressions", "ctr", "average_position",
                    "click_change", "ranking_change", "current_page", "markets", "devices",
                ),
            ),
        }
        st.session_state[export_key] = export_state
        st.rerun(scope="fragment")
    return list(state.get("rows") or []), state


def _query_table_rows(snapshot):
    started = time.perf_counter()
    rows = []
    for row in snapshot.get("top_queries") or []:
        rows.append(
            {
                "Query": row.get("query") or row.get("normalized_query") or "",
                "Clicks": _metric_value(row.get("clicks")),
                "Impressions": _metric_value(row.get("impressions")),
                "CTR": _metric_value(row.get("ctr"), style="percent"),
                "Position": _metric_value(row.get("average_position"), style="position"),
                "Click change": _metric_value(row.get("click_change")),
                "Rank change": _metric_value(row.get("ranking_change"), style="position"),
                "Markets": ", ".join(row.get("market_mix") or []),
                "Devices": ", ".join(row.get("device_mix") or []),
            }
        )
    logging.info(
        "SEO_PERF operation=python_query_transformation duration_ms=%.2f rows=%s",
        (time.perf_counter() - started) * 1000,
        len(rows),
    )
    return rows


def _render_search_overview(
    state,
    user,
    navigate,
    google_store=None,
    import_store=None,
    phase4_store=None,
    reporting_reader=None,
    growth_store=None,
):
    _header(seo.SEO_OVERVIEW_ROUTE)
    filters = _reporting_filters()
    view = st.segmented_control(
        "Overview detail",
        ("Top queries", "Quick wins", "Rising", "Declining", "Rank distribution", "Landing pages"),
        default="Top queries",
        key="seo-v2-overview-detail",
        label_visibility="collapsed",
    ) or "Top queries"
    reader, use_cache = _interactive_reader(
        phase4_store=phase4_store,
        reporting_reader=reporting_reader,
    )
    context = None
    if reader is not None:
        context = _interactive_context(reader, use_cache=use_cache)
        snapshot = _load_interactive_overview(
            filters,
            reader,
            context,
            use_cache=use_cache,
            route=seo.SEO_OVERVIEW_ROUTE,
        )
    else:
        snapshot = _load_reporting_snapshot(
            filters,
            phase4_store=phase4_store,
            reporting_reader=reporting_reader,
            source_scope="seo",
        )
    _snapshot_unavailable_notice(snapshot)
    current = snapshot.get("current") or {}
    previous = snapshot.get("previous") or {}
    columns = st.columns(5)
    for column, label, key, style, inverse in (
        (columns[0], "Organic clicks", "organic_clicks", "number", False),
        (columns[1], "Impressions", "organic_impressions", "number", False),
        (columns[2], "CTR", "ctr", "percent", False),
        (columns[3], "Average position", "average_position", "position", True),
    ):
        absolute, percent = _metric_delta(current.get(key), previous.get(key), position=inverse)
        column.metric(
            label,
            _metric_value(current.get(key), style=style),
            percent or absolute,
            delta_color="inverse" if inverse else "normal",
        )
    quality = snapshot.get("rank_quality") or seo_metrics.rank_quality(snapshot.get("top_queries") or [])
    known_clicks = _numeric_value(snapshot.get("known_query_clicks"))
    known_impressions = _numeric_value(snapshot.get("known_query_impressions"))
    property_clicks = _numeric_value(current.get("organic_clicks"))
    property_impressions = _numeric_value(current.get("organic_impressions"))
    coverage = {
        "click_coverage": (
            known_clicks / property_clicks
            if known_clicks is not None and property_clicks
            else None
        ),
        "impression_coverage": (
            known_impressions / property_impressions
            if known_impressions is not None and property_impressions
            else None
        )
    }
    columns[4].metric(
        "Rank Quality",
        "Unavailable" if quality["score"] is None else f"{float(quality['score']):.1f}/100",
    )
    health = (snapshot.get("health") or {}).get("gsc") or {}
    health_notice = _gsc_health_notice(health)
    if health_notice:
        if health.get("available"):
            st.warning(health_notice)
        else:
            st.error(health_notice)
    through = health.get("through_date") or "Unavailable"
    st.caption(
        f"Source: Google Search Console | Exact saved property totals | Data through {through} | "
        "Rank Quality is impression-weighted across known query rows."
    )
    if coverage.get("click_coverage") is not None:
        st.caption(
            f"Known-query coverage: {float(coverage['click_coverage']) * 100:.1f}% of property clicks "
            f"and {float(coverage['impression_coverage']) * 100:.1f}% of property impressions. "
            "The remainder may be unavailable because of Search Console privacy filtering or row limits."
        )
    trend = [
        {
            "Date": row.get("date"),
            "Clicks": float(_numeric_value(row.get("organic_clicks")) or 0),
            "Impressions": float(_numeric_value(row.get("organic_impressions")) or 0),
        }
        for row in snapshot.get("daily_trend") or []
    ]
    if trend:
        _section_heading("Organic visibility")
        chart_started = time.perf_counter()
        st.line_chart(trend, x="Date", y=("Clicks", "Impressions"), height=250)
        logging.info(
            "SEO_PERF route=%s operation=chart_construction duration_ms=%.2f rows=%s",
            seo.SEO_OVERVIEW_ROUTE,
            (time.perf_counter() - chart_started) * 1000,
            len(trend),
        )
    if view in {"Top queries", "Quick wins", "Rising", "Declining"} and reader is not None:
        query_view = "All" if view == "Top queries" else view
        query_rows, _pagination = _progressive_query_rows(
            reader,
            filters,
            context,
            view=query_view,
            search="",
            key=f"seo-v2-overview-{query_view.casefold().replace(' ', '-')}",
            use_cache=use_cache,
        )
        rows = _query_table_rows({"top_queries": query_rows})
        empty = {
            "Top queries": "No saved query rows are available.",
            "Quick wins": "No striking-distance query opportunities are available.",
            "Rising": "No rising queries are available.",
            "Declining": "No declining queries are available.",
        }[view]
    elif view == "Rank distribution" and reader is not None and hasattr(reader, "rank_distribution"):
        filters_json = _filter_json(filters)
        context_json = json.dumps(context, sort_keys=True, default=str, separators=(",", ":"))
        cache_key = hashlib.sha256(
            f"rank|{filters_json}|{context.get('watermark', '')}".encode("utf-8")
        ).hexdigest()[:24]
        cache_state = _cache_observation(cache_key) if use_cache else "bypass"
        result = (
            _cached_interactive_rank_distribution(
                filters_json,
                context_json,
                context.get("watermark") or "",
            )
            if use_cache
            else reader.rank_distribution(filters, context=context)
        )
        seo_reporting_runtime.log_diagnostics(
            seo.SEO_OVERVIEW_ROUTE,
            "rank_distribution",
            result.get("diagnostics"),
            cache=cache_state,
        )
        rows = [
            {"Bucket": label, "Known impressions": _metric_value(value)}
            for label, value in (result.get("distribution") or {}).items()
        ]
        empty = "No rank distribution is available."
    elif view == "Rank distribution":
        rows = [
            {"Bucket": label, "Known impressions": _metric_value(value)}
            for label, value in (quality.get("distribution") or {}).items()
        ]
        empty = "No rank distribution is available."
    elif view == "Landing pages" and reader is not None:
        filters_json = _filter_json(filters)
        context_json = json.dumps(context, sort_keys=True, default=str, separators=(",", ":"))
        cache_key = hashlib.sha256(
            f"landing|{filters_json}|{context.get('watermark', '')}".encode("utf-8")
        ).hexdigest()[:24]
        cache_state = _cache_observation(cache_key) if use_cache else "bypass"
        result = (
            _cached_interactive_landing_pages(
                filters_json,
                context_json,
                context.get("watermark") or "",
                25,
            )
            if use_cache
            else reader.landing_pages(filters, context=context, limit=25)
        )
        seo_reporting_runtime.log_diagnostics(
            seo.SEO_OVERVIEW_ROUTE,
            "landing_pages",
            result.get("diagnostics"),
            cache=cache_state,
        )
        rows = [
            {
                "Page": row.get("canonical_url") or row.get("path") or "",
                "Type": row.get("page_type") or "",
                "Clicks": _metric_value(row.get("clicks")),
                "Impressions": _metric_value(row.get("impressions")),
                "CTR": _metric_value(row.get("ctr"), style="percent"),
                "Position": _metric_value(row.get("average_position"), style="position"),
            }
            for row in (result.get("rows") or [])
        ]
        empty = "No saved Search Console landing-page rows are available."
    else:
        queries = list(snapshot.get("top_queries") or [])
        if view == "Top queries":
            selected = queries[:25]
            empty = "No saved query rows are available."
        elif view == "Quick wins":
            selected = sorted(
                (row for row in queries if 4 <= (_numeric_value(row.get("average_position")) or 0) <= 20),
                key=lambda row: seo_metrics.opportunity_score(row)["score"],
                reverse=True,
            )[:25]
            empty = "No striking-distance query opportunities are available."
        elif view == "Rising":
            selected = sorted(queries, key=lambda row: _numeric_value(row.get("ranking_change")) or 0, reverse=True)[:25]
            empty = "No rising queries are available."
        elif view == "Declining":
            selected = sorted(queries, key=lambda row: _numeric_value(row.get("ranking_change")) or 0)[:25]
            empty = "No declining queries are available."
        else:
            selected = snapshot.get("top_pages") or []
            empty = "No saved Search Console landing-page rows are available."
        rows = _query_table_rows({"top_queries": selected}) if view != "Landing pages" else list(selected)
    _table(rows, empty=empty, height=310)
    _render_data_connections_admin(
        user,
        google_store=google_store,
        import_store=import_store,
        phase4_store=phase4_store,
        reporting_reader=reporting_reader,
        growth_store=growth_store,
    )


def _render_keywords_rankings(state, *, phase4_store=None, reporting_reader=None):
    _header(seo.SEO_KEYWORDS_ROUTE)
    st.caption("One row represents one normalised query. Country and device are filters or mix labels, never duplicate rows.")
    filters = _reporting_filters()
    mapping_targets = {
        str(row.get("primary_keyword") or "").strip().casefold(): row.get("target_page") or ""
        for row in seo.active_records(state, "keyword_mappings")
    }
    keyword_status = {
        str(row.get("keyword") or row.get("raw_query") or "").strip().casefold():
        row.get("opportunity_status") or row.get("mapping_status") or ""
        for row in seo.active_records(state, "keywords")
    }
    view = st.segmented_control(
        "View",
        ("All", "Rising", "Declining", "New", "Top 3", "Positions 4-10", "Positions 11-20", "Unmapped"),
        default="All",
        key="seo-v2-query-view",
    ) or "All"
    search = st.text_input("Search queries", key="seo-v2-query-search")
    reader, use_cache = _interactive_reader(
        phase4_store=phase4_store,
        reporting_reader=reporting_reader,
    )
    if reader is not None:
        context = _interactive_context(reader, use_cache=use_cache)
        query_rows, _pagination = _progressive_query_rows(
            reader,
            filters,
            context,
            view=view,
            search=search,
            key="seo-v2-query-table",
            use_cache=use_cache,
            signature_extra={
                "mapping_revision": seo_pagination.pagination_signature(mapping_targets),
                "status_revision": seo_pagination.pagination_signature(keyword_status),
            },
            excluded_queries=tuple(mapping_targets),
        )
        source_rows = query_rows
        if not context.get("available"):
            _snapshot_unavailable_notice({"reason": "reporting_snapshot_unavailable"})
    else:
        snapshot = _load_reporting_snapshot(
            filters,
            phase4_store=phase4_store,
            reporting_reader=reporting_reader,
            source_scope="seo",
        )
        source_rows = list(snapshot.get("top_queries") or [])
        if view == "Rising":
            source_rows = [row for row in source_rows if (_numeric_value(row.get("ranking_change")) or 0) > 0]
        elif view == "Declining":
            source_rows = [row for row in source_rows if (_numeric_value(row.get("ranking_change")) or 0) < 0]
        elif view == "New":
            source_rows = [row for row in source_rows if (_numeric_value(row.get("previous_clicks")) or 0) == 0]
        elif view == "Top 3":
            source_rows = [row for row in source_rows if 0 < (_numeric_value(row.get("average_position")) or 0) <= 3]
        elif view == "Positions 4-10":
            source_rows = [row for row in source_rows if 4 <= (_numeric_value(row.get("average_position")) or 0) <= 10]
        elif view == "Positions 11-20":
            source_rows = [row for row in source_rows if 11 <= (_numeric_value(row.get("average_position")) or 0) <= 20]
        elif view == "Unmapped":
            source_rows = [
                row for row in source_rows
                if not mapping_targets.get(str(row.get("query") or "").strip().casefold())
            ]
        if search:
            source_rows = [row for row in source_rows if search.casefold() in str(row.get("query") or "").casefold()]
    rows = _query_table_rows({"top_queries": source_rows})
    for row in rows:
        key = str(row.get("Query") or "").strip().casefold()
        row["Mapped target"] = mapping_targets.get(key) or "Unmapped"
        row["Opportunity status"] = keyword_status.get(key) or "Open"
    if reader is None:
        rows = _paginated_rows(rows, key="seo-v2-query-table-legacy", default_page_size=25)
    _table(rows, empty="No saved Search Console query rows match these filters.", height=520)


def _render_opportunities(
    store,
    state,
    user,
    navigate,
    *,
    phase4_store=None,
    reporting_reader=None,
    project_store=None,
):
    _header(seo_nav.SEO_OPPORTUNITIES_ROUTE)
    filters = _reporting_filters()
    prepared = []
    source_by_query = {}
    dismissed = {
        str(row.get("keyword") or row.get("raw_query") or "").strip().casefold()
        for row in seo.active_records(state, "keywords")
        if row.get("opportunity_status") == "Dismissed"
    }
    search = st.text_input("Search opportunities", key="seo-v2-opportunity-search")
    reader, use_cache = _interactive_reader(
        phase4_store=phase4_store,
        reporting_reader=reporting_reader,
    )
    snapshot = {"health": {}}
    if reader is not None:
        context = _interactive_context(reader, use_cache=use_cache)
        source_rows, _pagination = _progressive_query_rows(
            reader,
            filters,
            context,
            view="Opportunities",
            search=search,
            key="seo-v2-opportunities",
            use_cache=use_cache,
            signature_extra={"dismissed_revision": seo_pagination.pagination_signature(sorted(dismissed))},
            excluded_queries=tuple(dismissed),
        )
        snapshot = {"health": seo_reporting_runtime.PostgresSEOInteractiveReader._health(context)}
        if not context.get("available"):
            _snapshot_unavailable_notice({"reason": "reporting_snapshot_unavailable"})
    else:
        snapshot = _load_reporting_snapshot(
            filters,
            phase4_store=phase4_store,
            reporting_reader=reporting_reader,
            source_scope="seo",
        )
        source_rows = list(snapshot.get("top_queries") or [])
        if search:
            source_rows = [row for row in source_rows if search.casefold() in str(row.get("query") or "").casefold()]
    for row in source_rows:
        query = str(row.get("query") or row.get("normalized_query") or "").strip()
        if not query or query.casefold() in dismissed:
            continue
        candidate = {
            **row,
            "mapped_target": bool(row.get("current_page")),
            "content_gap": not bool(row.get("current_page")),
            "cannibalisation_risk": row.get("cannibalisation_risk") or 0,
        }
        scored = seo_metrics.opportunity_score(candidate)
        source_by_query[query] = {**row, **scored}
        prepared.append(
            {
                "Score": float(scored["score"]),
                "Query": query,
                "Clicks": _metric_value(row.get("clicks")),
                "Impressions": _metric_value(row.get("impressions")),
                "CTR": _metric_value(row.get("ctr"), style="percent"),
                "Position": _metric_value(row.get("average_position"), style="position"),
                "Matched page": row.get("current_page") or "Unmapped",
                "Why": scored["explanation"],
            }
        )
    prepared.sort(key=lambda row: (-row["Score"], row["Query"].casefold()))
    rendered_opportunities = (
        prepared
        if reader is not None
        else _paginated_rows(prepared, key="seo-v2-opportunities-legacy")
    )
    _table(rendered_opportunities, empty="No explainable opportunities are available for the selected saved data.", height=520)
    st.caption("Scores use only observed impressions, position, CTR, movement, mapping, content-gap and cannibalisation evidence. No search volume is inferred.")
    if not prepared:
        return
    selected_query = st.selectbox(
        "Opportunity action",
        tuple(row["Query"] for row in prepared),
        key="seo-v2-opportunity-action",
    )
    selected = source_by_query[selected_query]
    actions = st.columns(3)
    if actions[0].button("Add to Mapping", use_container_width=True, key="seo-v2-opportunity-map"):
        saved = seo.upsert_record(
            state,
            "keywords",
            {
                "keyword": selected_query,
                "raw_query": selected_query,
                "clicks": selected.get("clicks") or 0,
                "impressions": selected.get("impressions") or 0,
                "ctr": selected.get("ctr") or 0,
                "average_position": selected.get("average_position") or 0,
                "target_url": selected.get("current_page") or "",
                "mapping_status": "Unreviewed",
                "opportunity_status": "Open",
            },
            actor=user,
        )
        if _persist(
            store,
            state,
            user,
            action="seo_opportunity_added_to_mapping",
            area="SEO / Opportunities",
            message=f"SEO opportunity added to mapping: {selected_query}",
            entity_type="seo_keyword",
            entity_id=saved["id"],
        ):
            _navigate(navigate, seo_nav.SEO_MAPPING_ROUTE)
    if actions[1].button("Create Blog Brief", use_container_width=True, key="seo-v2-opportunity-blog"):
        project_store = project_store or seo_blog_workflow.PostgresBlogProjectStore()
        opportunity = {
            **selected,
            "query": selected_query,
            "matched_page": selected.get("current_page") or "",
            "data_through_date": ((snapshot.get("health") or {}).get("gsc") or {}).get("through_date") or "",
            "score_explanation": selected.get("explanation") or "",
        }
        project = project_store.save_project(
            {
                "project_id": str(uuid.uuid4()),
                "owner_id": user.get("id") or "",
                "owner_name": _actor_name(user),
                "status": "Idea",
                "primary_keyword": selected_query,
                "target_url": opportunity["matched_page"],
                "opportunity_snapshot": opportunity,
                "brief": seo_blog_workflow.prefill_from_opportunity({}, opportunity),
            }
        )
        _blog_activity(
            project_store,
            project,
            user,
            "seo_blog_brief_created",
            f"Blog brief created from SEO opportunity: {selected_query}",
            content_hash=seo_blog_workflow.prompt_hash(selected_query),
        )
        st.session_state[f"{seo_blog_workflow.STATE_PREFIX}project"] = project["project_id"]
        _navigate(navigate, seo.SEO_BLOG_ROUTE)
    if actions[2].button("Dismiss", use_container_width=True, key="seo-v2-opportunity-dismiss"):
        saved = seo.upsert_record(
            state,
            "keywords",
            {
                "keyword": selected_query,
                "raw_query": selected_query,
                "mapping_status": "Rejected",
                "opportunity_status": "Dismissed",
            },
            actor=user,
        )
        if _persist(
            store,
            state,
            user,
            action="seo_opportunity_dismissed",
            area="SEO / Opportunities",
            message=f"SEO opportunity dismissed: {selected_query}",
            entity_type="seo_keyword",
            entity_id=saved["id"],
        ):
            st.rerun()


def _render_search_landing_pages(*, phase4_store=None, reporting_reader=None):
    _header(seo_nav.SEO_LANDING_PAGES_ROUTE)
    filters = _reporting_filters()
    reader, use_cache = _interactive_reader(
        phase4_store=phase4_store,
        reporting_reader=reporting_reader,
    )
    if reader is not None:
        context = _interactive_context(reader, use_cache=use_cache)
        filters_json = _filter_json(filters)
        context_json = json.dumps(context, sort_keys=True, default=str, separators=(",", ":"))
        result = (
            _cached_interactive_landing_pages(
                filters_json,
                context_json,
                context.get("watermark") or "",
                25,
            )
            if use_cache
            else reader.landing_pages(filters, context=context, limit=25)
        )
        source_rows = result.get("rows") or []
        st.caption(f"Showing {len(source_rows):,} of {int(result.get('total') or 0):,} landing pages")
        if not context.get("available"):
            _snapshot_unavailable_notice({"reason": "reporting_snapshot_unavailable"})
    else:
        snapshot = _load_reporting_snapshot(
            filters,
            phase4_store=phase4_store,
            reporting_reader=reporting_reader,
            source_scope="seo_landing",
        )
        source_rows = snapshot.get("top_pages") or []
    rows = []
    for row in source_rows:
        impressions = _numeric_value(row.get("impressions")) or 0
        clicks = _numeric_value(row.get("clicks")) or 0
        rows.append(
            {
                "Canonical URL": row.get("canonical_url") or row.get("page_url") or row.get("path") or "",
                "Title": row.get("title") or "",
                "Page type": row.get("page_type") or "Page",
                "GSC clicks": _metric_value(clicks),
                "Impressions": _metric_value(impressions),
                "CTR": _metric_value((clicks / impressions) if impressions else None, style="percent"),
                "Avg position": _metric_value(
                    row.get("average_position"),
                    style="position",
                ),
                "Movement": _metric_value(row.get("previous_change")),
                "Organic sessions (supporting)": _metric_value(row.get("sessions")),
            }
        )
    if reader is None:
        rows = _paginated_rows(rows, key="seo-v2-pages-legacy")
    _table(rows, empty="No saved Search Console page rows are available.", height=520)


def _render_seo_health(user, *, google_store=None, import_store=None, phase4_store=None, reporting_reader=None, growth_store=None):
    _header(seo_nav.SEO_HEALTH_ROUTE)
    reader = reporting_reader or seo_live_analytics.PostgresSEOLiveAnalyticsReader(phase4_store)
    try:
        rows = reader._query_all(
            "technical",
            """
            SELECT canonical_url, source, severity, issue_summary, correction_steps,
                   likely_impact, index_state, coverage_state, fetch_state,
                   status, first_seen_at, last_seen_at, checked_at
            FROM seo_technical_url_audits_v2
            WHERE workspace_key=%s
            ORDER BY CASE severity WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
                     WHEN 'Medium' THEN 3 ELSE 4 END, last_seen_at DESC
            LIMIT 500
            """,
            (google_seo.GOOGLE_SEO_WORKSPACE_KEY,),
        )
    except Exception:
        rows = []
    _table(rows, empty="No saved technical URL findings are available yet.", height=480)
    st.caption(
        "URL Inspection evidence, sitemap checks and HTML audits run in background jobs. "
        "URL Inspection is Google's saved indexed-version evidence, not a live test. Opening this page performs no crawl or Google request."
    )
    urls = sorted({str(row.get("canonical_url") or "") for row in rows if row.get("canonical_url")})
    if urls:
        controls = st.columns([3, 1, 1])
        selected_url = controls[0].selectbox("Affected URL", alphabetize_options(urls), key="seo-v2-technical-url")
        if controls[1].button("Queue recheck", use_container_width=True, key="seo-v2-technical-recheck"):
            try:
                queued = seo_technical_audit.PostgresTechnicalAuditStore().queue_recheck(
                    selected_url,
                    requested_by=user.get("id") or "",
                )
            except Exception:
                st.warning("The background recheck could not be queued. No live page was changed.")
            else:
                record_activity_log(
                    "seo_technical_recheck_queued",
                    "SEO / Health",
                    f"Technical SEO recheck queued: {selected_url}",
                    entity_type="seo_url",
                    entity_id=selected_url,
                    event_key=f"seo-technical-recheck:{queued.get('id') or selected_url}",
                    actor=_actor_name(user),
                    metadata={
                        "actor_id": user.get("id") or "",
                        "actor_role": user.get("role") or "",
                        "origin": "human",
                    },
                )
                st.success("Background recheck queued.")
        import urllib.parse
        connection = (google_store or google_seo.default_store()).get_connection()
        resource = str(connection.get("gsc_site_url") or "")
        inspection_url = (
            "https://search.google.com/search-console/inspect?resource_id="
            + urllib.parse.quote(resource, safe="")
            + "&id="
            + urllib.parse.quote(selected_url, safe="")
        )
        controls[2].link_button(
            "Open in Search Console",
            inspection_url,
            use_container_width=True,
        )
    if os_accounts.is_admin(user):
        with st.expander("Administrator connection and recovery tools", expanded=False):
            _render_data_connections_admin(
                user,
                google_store=google_store,
                import_store=import_store,
                phase4_store=phase4_store,
                reporting_reader=reporting_reader,
                growth_store=growth_store,
                embedded=True,
            )


def _json_object(value, default):
    if isinstance(value, type(default)):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, type(default)) else default
        except (TypeError, ValueError):
            return default
    return default


def _copy_text_button(text, *, key, label="Copy"):
    import streamlit.components.v1 as components
    payload = json.dumps(str(text or "")).replace("<", "\\u003c")
    components.html(
        f"""
        <button id="{html.escape(key)}" style="height:34px;border:1px solid #c9b071;background:#d8aa48;
          border-radius:5px;padding:0 14px;font:600 13px sans-serif;cursor:pointer">{html.escape(label)}</button>
        <span id="{html.escape(key)}-status" style="font:12px sans-serif;margin-left:8px"></span>
        <script>
        document.getElementById({json.dumps(key)}).onclick = async () => {{
          await navigator.clipboard.writeText({payload});
          document.getElementById({json.dumps(key + '-status')}).textContent = 'Copied';
        }};
        </script>
        """,
        height=45,
    )


def _blog_activity(project_store, project, user, action, message, *, content_hash=""):
    key = f"{action}:{content_hash or seo_blog_workflow.utc_timestamp()}"
    created = project_store.record_event(
        project["project_id"],
        actor_id=user.get("id") or "",
        actor_name=_actor_name(user),
        action_type=action,
        idempotency_key=key,
        metadata={"status": project.get("status") or ""},
    )
    if created:
        record_activity_log(
            action,
            "SEO / Blog",
            message,
            entity_type="seo_blog_project",
            entity_id=project["project_id"],
            event_key=f"seo-blog:{project['project_id']}:{key}",
            actor=_actor_name(user),
            metadata={
                "actor_id": user.get("id") or "",
                "actor_role": user.get("role") or "",
                "origin": "human",
                "status": project.get("status") or "",
            },
        )


def _render_blog_v2(state, user, *, phase4_store=None, reporting_reader=None, project_store=None):
    _header(seo.SEO_BLOG_ROUTE)
    with st.expander("How to create and publish a blog", expanded=False):
        st.markdown(
            "1. Choose a saved SEO opportunity and product or collection.\n"
            "2. Complete the brief and create Prompt 1.\n"
            "3. Keep the same ChatGPT conversation while the article and images are created.\n"
            "4. Import and review the returned content package.\n"
            "5. Create Prompt 2 for a Shopify draft.\n"
            "6. Review the draft, then explicitly approve publishing or scheduling."
        )
    project_store = project_store or seo_blog_workflow.PostgresBlogProjectStore()
    try:
        projects = project_store.list_projects(
            owner_id=user.get("id") or "",
            include_all=os_accounts.is_admin(user),
        )
    except Exception:
        st.info("The Blog project store is not ready. Apply the additive Analytics/SEO migration first.")
        return
    actions = st.columns([1, 2, 4])
    if actions[0].button("New brief", type="primary", icon=":material/add:", use_container_width=True):
        created = project_store.save_project(
            {
                "project_id": str(uuid.uuid4()),
                "owner_id": user.get("id") or "",
                "owner_name": _actor_name(user),
                "status": "Idea",
                "brief": {},
            }
        )
        _blog_activity(project_store, created, user, "seo_blog_brief_created", "Blog brief created")
        st.session_state[f"{seo_blog_workflow.STATE_PREFIX}project"] = created["project_id"]
        st.rerun()
    if not projects:
        st.caption("No blog projects yet. Create a brief to begin.")
        return
    by_id = {str(row.get("project_id")): row for row in projects}
    selected_id = actions[1].selectbox(
        "Project",
        alphabetize_options(
            by_id,
            label=lambda key: by_id[key].get("title") or by_id[key].get("primary_keyword") or "Untitled brief",
        ),
        format_func=lambda key: by_id[key].get("title") or by_id[key].get("primary_keyword") or "Untitled brief",
        key=f"{seo_blog_workflow.STATE_PREFIX}project",
    )
    project = dict(by_id[selected_id])
    brief = _json_object(project.get("brief"), {})
    opportunity = _json_object(project.get("opportunity_snapshot"), {})
    actions[2].caption(f"Status: {project.get('status') or 'Idea'} | Project {selected_id}")

    filters = _reporting_filters()
    reader, use_cache = _interactive_reader(
        phase4_store=phase4_store,
        reporting_reader=reporting_reader,
    )
    if reader is not None:
        reporting_context = _interactive_context(reader, use_cache=use_cache)
        opportunity_page = reader.query_page(
            filters,
            view="Opportunities",
            limit=25,
            context=reporting_context,
        )
        snapshot = {
            "health": seo_reporting_runtime.PostgresSEOInteractiveReader._health(reporting_context),
            "top_queries": opportunity_page.get("rows") or [],
        }
    else:
        snapshot = _load_reporting_snapshot(
            filters,
            phase4_store=phase4_store,
            reporting_reader=reporting_reader,
            source_scope="seo",
        )
    gsc_through = ((snapshot.get("health") or {}).get("gsc") or {}).get("through_date") or ""
    opportunity_rows = seo_blog_workflow.build_blog_opportunities(
        (snapshot.get("top_queries") or [])[:25],
        data_through_date=gsc_through,
    )
    opportunities = {
        str(row.get("normalized_query") or row.get("query") or ""): row
        for row in opportunity_rows
    }
    if opportunities:
        with st.expander("Opportunity evidence", expanded=False):
            _table(
                [
                    {
                        "Query": row.get("query") or "",
                        "Clicks": _metric_value(row.get("clicks")),
                        "Impressions": _metric_value(row.get("impressions")),
                        "CTR": _metric_value(row.get("ctr"), style="percent"),
                        "Position": _metric_value(row.get("average_position"), style="position"),
                        "Change": _metric_value(row.get("click_change")),
                        "Matched page": row.get("matched_page") or "Unmapped",
                        "Article type": row.get("recommended_article_type") or "",
                        "Confidence": row.get("confidence") or "",
                        "Data through": row.get("data_through_date") or "",
                        "Why": row.get("score_explanation") or "",
                    }
                    for row in opportunity_rows[:25]
                ],
                empty="No saved GSC blog opportunities are available.",
                height=300,
            )
        selected_opportunity = st.selectbox(
            "Saved GSC opportunity",
            ("", *opportunities),
            format_func=lambda key: "Choose an opportunity" if not key else key,
            key=f"{seo_blog_workflow.STATE_PREFIX}opportunity::{selected_id}",
        )
        if st.button("Use opportunity", disabled=not selected_opportunity, key=f"seo-blog-use-opportunity::{selected_id}"):
            brief = seo_blog_workflow.prefill_from_opportunity(brief, opportunities[selected_opportunity])
            project.update(brief=brief, opportunity_snapshot=opportunities[selected_opportunity])
            project_store.save_project(project)
            st.rerun()

    saved_targets = list(seo.active_records(state, "target_library"))
    try:
        live_targets = _cached_blog_shopify_targets()
    except Exception:
        live_targets = []
    targets = {
        str(row.get("id") or row.get("url") or ""): row
        for row in [*live_targets, *saved_targets]
        if row.get("id") or row.get("url")
    }
    target_id = st.selectbox(
        "Shopify product or collection",
        alphabetize_options(
            ("", *targets),
            label=lambda key: "Choose a saved Shopify target" if not key else targets[key].get("title") or targets[key].get("name") or targets[key].get("url") or key,
        ),
        format_func=lambda key: "Choose a saved Shopify target" if not key else targets[key].get("title") or targets[key].get("name") or targets[key].get("url") or key,
        key=f"{seo_blog_workflow.STATE_PREFIX}target::{selected_id}",
    ) if targets else ""
    if target_id and target_id != brief.get("target_entity_id"):
        target = targets[target_id]
        brief = {
            **brief,
            "target_entity_id": target_id,
            "target_title": brief.get("target_title") or target.get("title") or target.get("name") or "",
            "target_url": brief.get("target_url") or target.get("url") or "",
            "target_sport": brief.get("target_sport") or target.get("sport") or "",
            "source_artwork": brief.get("source_artwork") or target.get("source_artwork") or target.get("source_asset") or "",
        }

    key_root = f"{seo_blog_workflow.STATE_PREFIX}{selected_id}"
    first = st.columns(3)
    blog_market_options = alphabetize_options(seo_blog_workflow.MARKETS)
    brief["target_market"] = first[0].selectbox("Target market", blog_market_options, index=selected_option_index(blog_market_options, brief.get("target_market") or seo_blog_workflow.MARKETS[0]), key=f"{key_root}-market")
    brief["sport"] = first[1].text_input("Sport", value=brief.get("sport") or "", key=f"{key_root}-sport")
    brief["search_intent"] = first[2].text_input("Search intent / article type", value=brief.get("search_intent") or "", key=f"{key_root}-intent")
    context = st.columns(2)
    default_language = brief.get("language") or seo_blog_workflow.MARKET_LANGUAGE.get(brief["target_market"])
    language_options = alphabetize_options(seo_blog_workflow.LANGUAGES)
    brief["language"] = context[0].selectbox(
        "Language",
        language_options,
        index=selected_option_index(language_options, default_language),
        key=f"{key_root}-language",
    )
    brief["publication_preference"] = context[1].selectbox(
        "Draft / schedule preference",
        seo_blog_workflow.PUBLICATION_PREFERENCES,
        index=seo_blog_workflow.PUBLICATION_PREFERENCES.index(brief.get("publication_preference")) if brief.get("publication_preference") in seo_blog_workflow.PUBLICATION_PREFERENCES else 0,
        key=f"{key_root}-publication",
    )
    second = st.columns(2)
    brief["subject"] = second[0].text_input("Athlete, team, rivalry, event or season", value=brief.get("subject") or "", key=f"{key_root}-subject")
    brief["timely_hook"] = second[1].text_input("Timely hook", value=brief.get("timely_hook") or "", key=f"{key_root}-hook")
    brief["primary_keyword"] = st.text_input("Primary keyword", value=brief.get("primary_keyword") or "", key=f"{key_root}-primary")
    brief["supporting_keywords"] = st.text_input("Supporting keywords", value=", ".join(brief.get("supporting_keywords") or []), key=f"{key_root}-supporting")
    brief["related_entities"] = st.text_input("Related entities", value=", ".join(brief.get("related_entities") or []), key=f"{key_root}-entities")
    brief["fan_questions"] = st.text_input("Fan questions", value=", ".join(brief.get("fan_questions") or []), key=f"{key_root}-questions")
    target_columns = st.columns(2)
    brief["target_title"] = target_columns[0].text_input("Product / collection title", value=brief.get("target_title") or "", key=f"{key_root}-target-title")
    brief["target_url"] = target_columns[1].text_input("Exact product / collection URL", value=brief.get("target_url") or "", key=f"{key_root}-target-url")
    brief["internal_links"] = st.text_area("Verified internal links", value="\n".join(brief.get("internal_links") or []), height=80, key=f"{key_root}-links")
    with st.expander("Advanced brief", expanded=False):
        brief["backlink_objective"] = st.text_input("Backlink objective", value=brief.get("backlink_objective") or "", key=f"{key_root}-backlink")
        brief["link_worthy_angle"] = st.text_input("Link-worthy asset or angle", value=brief.get("link_worthy_angle") or "", key=f"{key_root}-angle")
        brief["outreach_audience"] = st.text_input("Intended outreach publications / audience", value=brief.get("outreach_audience") or "", key=f"{key_root}-outreach")
        brief["youtube_url"] = st.text_input("YouTube URL", value=brief.get("youtube_url") or "", key=f"{key_root}-youtube")
        brief["target_length"] = st.text_input("Target length override", value=brief.get("target_length") or "", key=f"{key_root}-length")
        brief["tags"] = st.text_input("Tags", value=", ".join(brief.get("tags") or []), key=f"{key_root}-tags")
    third = st.columns(2)
    brief["author"] = third[0].text_input("Author", value=brief.get("author") or _actor_name(user), key=f"{key_root}-author")
    brief["target_blog"] = third[1].text_input("Target Shopify blog", value=brief.get("target_blog") or "News", key=f"{key_root}-blog")
    brief["approved_source_assets"] = st.text_area("Approved source image references", value="\n".join(brief.get("approved_source_assets") or []), height=80, key=f"{key_root}-assets")
    uploaded_sources = st.file_uploader(
        "Approved source image uploads",
        type=("png", "jpg", "jpeg", "webp"),
        accept_multiple_files=True,
        key=f"{key_root}-source-uploads",
        help="Only file names are persisted in the brief; image bytes remain in the current upload control.",
    )
    if uploaded_sources:
        existing_sources = seo_blog_workflow._clean_list(brief.get("approved_source_assets"))
        brief["approved_source_assets"] = list(dict.fromkeys([
            *existing_sources,
            *(str(item.name) for item in uploaded_sources),
        ]))
    permissions = st.columns(2)
    brief["assets_permitted"] = permissions[0].checkbox("Supplied athlete/product assets are permitted for use", value=bool(brief.get("assets_permitted")), key=f"{key_root}-permitted")
    brief["safe_non_identifiable_images"] = permissions[1].checkbox("Use non-identifiable editorial imagery when approved athlete imagery is absent", value=bool(brief.get("safe_non_identifiable_images")), key=f"{key_root}-fallback")

    draft_hash = seo_blog_workflow.prompt_hash(json.dumps(brief, sort_keys=True, default=str))
    autosave_key = f"{key_root}-autosaved"
    if st.session_state.get(autosave_key) != draft_hash:
        project.update(
            brief=brief,
            title=brief.get("article_title") or brief.get("subject") or "",
            primary_keyword=brief.get("primary_keyword") or "",
            target_url=brief.get("target_url") or "",
        )
        project = project_store.save_project(project)
        st.session_state[autosave_key] = draft_hash

    action_row = st.columns(5)
    if action_row[0].button("Save draft", use_container_width=True, key=f"seo-blog-save::{selected_id}"):
        _blog_activity(project_store, project, user, "seo_blog_brief_saved", f"Blog brief saved: {brief.get('primary_keyword') or brief.get('subject')}", content_hash=draft_hash)
        st.success("Draft saved.")
    if action_row[1].button("Create Prompt 1", type="primary", use_container_width=True, key=f"seo-blog-prompt1::{selected_id}"):
        try:
            prompt = seo_blog_workflow.build_prompt_1(
                selected_id,
                brief,
                source_date=gsc_through,
                opportunity=opportunity,
            )
        except seo_blog_workflow.BlogWorkflowError as error:
            st.warning(str(error))
        else:
            prompt_hash = seo_blog_workflow.prompt_hash(prompt)
            project.update(status="Brief ready", prompt_1=prompt, prompt_1_hash=prompt_hash, brief=seo_blog_workflow.validate_brief(brief))
            project = project_store.save_project(project)
            _blog_activity(project_store, project, user, "seo_blog_prompt_1_created", f"Blog Prompt 1 created: {brief.get('primary_keyword')}", content_hash=prompt_hash)
            st.rerun()
    prompt_1 = str(project.get("prompt_1") or "")
    action_row[2].download_button("Download Prompt 1", prompt_1.encode("utf-8"), file_name=f"{selected_id}-prompt-1.txt", mime="text/plain", disabled=not prompt_1, use_container_width=True)

    with st.expander("Prompt 1", expanded=bool(prompt_1)):
        if prompt_1:
            st.text_area("Prompt 1 output", prompt_1, height=320, key=f"{key_root}-prompt1-preview")
            _copy_text_button(prompt_1, key=f"copy-prompt1-{selected_id}", label="Copy Prompt 1")
        else:
            st.caption("Complete the required brief fields, then create Prompt 1.")

    st.subheader("Import Content Package")
    uploaded = st.file_uploader("JSON package", type=("json",), key=f"{key_root}-package-file")
    pasted = st.text_area("Or paste the JSON package", height=180, key=f"{key_root}-package-paste")
    manual_review = st.checkbox("Allow manual review for clearly listed validation issues", key=f"{key_root}-manual-review")
    validation = _json_object(project.get("qa_results"), {})
    if st.button("Validate package", disabled=not (uploaded or pasted.strip()), key=f"seo-blog-validate::{selected_id}"):
        payload = uploaded.getvalue().decode("utf-8") if uploaded else pasted
        try:
            validation = seo_blog_workflow.validate_content_package(
                payload,
                project_id=selected_id,
                target_url=brief.get("target_url") or "",
                allow_manual_review=manual_review,
            )
        except seo_blog_workflow.ContentPackageError as error:
            for issue in error.issues:
                st.warning(issue)
        else:
            project.update(
                status="Needs review" if validation.get("issues") else "Approved",
                content_package=validation["package"],
                image_manifest=validation["image_manifest"],
                qa_results={key: value for key, value in validation.items() if key not in {"package", "image_manifest"}},
            )
            project = project_store.save_project(project)
            package_hash = seo_blog_workflow.prompt_hash(json.dumps(validation["package"], sort_keys=True))
            _blog_activity(project_store, project, user, "seo_blog_content_package_imported", f"Blog content package imported: {brief.get('primary_keyword')}", content_hash=package_hash)
            st.rerun()
    if validation:
        if validation.get("issues"):
            st.warning("Review required: " + "; ".join(validation.get("issues") or []))
        else:
            st.success(f"Content package validated. {validation.get('word_count') or 0} words.")

    capability = seo_blog_workflow.shopify_write_capability()
    if action_row[3].button("Create Prompt 2", disabled=not validation, use_container_width=True, key=f"seo-blog-prompt2::{selected_id}"):
        try:
            prompt_2 = seo_blog_workflow.build_prompt_2(project, validation, capability=capability)
        except seo_blog_workflow.BlogWorkflowError as error:
            st.warning(str(error))
        else:
            prompt_hash = seo_blog_workflow.prompt_hash(prompt_2)
            project.update(prompt_2=prompt_2, prompt_2_hash=prompt_hash, status="Approved")
            project = project_store.save_project(project)
            _blog_activity(project_store, project, user, "seo_blog_prompt_2_created", f"Blog Prompt 2 created: {brief.get('primary_keyword')}", content_hash=prompt_hash)
            st.rerun()
    prompt_2 = str(project.get("prompt_2") or "")
    action_row[4].download_button("Download Prompt 2", prompt_2.encode("utf-8"), file_name=f"{selected_id}-prompt-2.txt", mime="text/plain", disabled=not prompt_2, use_container_width=True)
    with st.expander("Prompt 2", expanded=bool(prompt_2)):
        if prompt_2:
            st.text_area("Prompt 2 output", prompt_2, height=320, key=f"{key_root}-prompt2-preview")
            _copy_text_button(prompt_2, key=f"copy-prompt2-{selected_id}", label="Copy Prompt 2")
        else:
            st.caption("Prompt 2 is available only after package validation and a confirmed Shopify article/file-write capability.")

    st.subheader("History")
    _table(
        [
            {
                "Title": row.get("title") or "Untitled",
                "Primary keyword": row.get("primary_keyword") or "",
                "Target page": row.get("target_url") or "",
                "Owner": row.get("owner_name") or "",
                "Status": row.get("status") or "Idea",
                "Updated": row.get("updated_at") or "",
            }
            for row in projects
        ],
        empty="No blog history is available.",
        height=260,
    )


@st.fragment
def _render_active_route(
    user,
    route,
    store,
    navigate,
    google_store=None,
    import_store=None,
    phase4_store=None,
    reporting_reader=None,
    growth_store=None,
):
    route_started = time.perf_counter()
    state = {}
    state_routes = {
        seo.SEO_KEYWORDS_ROUTE,
        seo_nav.SEO_OPPORTUNITIES_ROUTE,
        seo_nav.SEO_MAPPING_ROUTE,
        seo.SEO_BLOG_ROUTE,
    }
    if route in state_routes:
        state_started = time.perf_counter()
        try:
            state = store.load()
        except seo.SEOStoreError as error:
            _header(route)
            st.error(str(error))
            st.caption("SEO records were not changed. Ask an administrator to check the shared data store.")
            return
        logging.info(
            "SEO_PERF route=%s operation=workspace_state duration_ms=%.2f",
            route,
            (time.perf_counter() - state_started) * 1000,
        )
    consume_summary = getattr(store, "consume_import_summary", None)
    summary = (
        consume_summary()
        if route in state_routes and callable(consume_summary)
        else None
    )
    if summary:
        record_activity_log(
            "legacy_citations_imported",
            "SEO / Citations",
            (
                f"Legacy citation tracker imported: {summary['source_rows_processed']} source rows; "
                f"{summary['records_created']} created; {summary['existing_records_updated']} updated; "
                f"{summary['duplicate_rows_merged']} duplicates merged; "
                f"{summary['live_records_imported']} Live; {summary['pending_records_imported']} pending; "
                f"{summary['records_skipped']} skipped; {len(summary.get('conflicts') or [])} conflicts; "
                f"{summary['invalid_rows']} invalid."
            ),
            entity_type="seo_import",
            entity_id=seo.LEGACY_CITATION_IMPORT_VERSION,
            metadata={
                **{key: value for key, value in summary.items() if key != "conflicts"},
                "conflict_count": len(summary.get("conflicts") or []),
            },
            event_key=f"seo-import:{seo.LEGACY_CITATION_IMPORT_VERSION}",
            actor=_actor_name(user),
        )
        if summary.get("conflicts"):
            st.warning(
                f"{len(summary['conflicts'])} archived or intentionally skipped citation records "
                "were left unchanged. Review the stored migration summary before resolving them."
            )
    handlers = {
            seo.SEO_OVERVIEW_ROUTE: lambda: _render_search_overview(
                state,
                user,
                navigate,
                google_store,
                import_store,
                phase4_store,
                reporting_reader,
                growth_store,
            ),
            seo.SEO_KEYWORDS_ROUTE: lambda: _render_keywords_rankings(
                state,
                phase4_store=phase4_store,
                reporting_reader=reporting_reader,
            ),
            seo_nav.SEO_OPPORTUNITIES_ROUTE: lambda: _render_opportunities(
                store,
                state,
                user,
                navigate,
                phase4_store=phase4_store,
                reporting_reader=reporting_reader,
            ),
            seo_nav.SEO_LANDING_PAGES_ROUTE: lambda: _render_search_landing_pages(
                phase4_store=phase4_store,
                reporting_reader=reporting_reader,
            ),
            seo_nav.SEO_MAPPING_ROUTE: lambda: _render_keywords(
                store,
                state,
                user,
                growth_store=growth_store,
            ),
            seo.SEO_BLOG_ROUTE: lambda: _render_blog_v2(
                state,
                user,
                phase4_store=phase4_store,
                reporting_reader=reporting_reader,
            ),
            seo_nav.SEO_HEALTH_ROUTE: lambda: _render_seo_health(
                user,
                google_store=google_store,
                import_store=import_store,
                phase4_store=phase4_store,
                reporting_reader=reporting_reader,
                growth_store=growth_store,
            ),
        }
    render_status = "ready"
    try:
        navigation_runtime.dispatch_selected(route, handlers)
    except Exception as error:
        render_status = "error"
        logging.exception("SEO route render failed route=%s", route)
        st.error("This SEO view could not be loaded, but the workspace is still available.")
        st.caption("Retry this view or return to SEO Overview. No saved SEO data was changed.")
        retry_col, back_col, _ = st.columns([1, 1, 6])
        if retry_col.button("Retry", key=f"seo-route-retry::{route}"):
            _navigate(navigate, route, force=True)
        if back_col.button("Back", key=f"seo-route-back::{route}"):
            _navigate(navigate, seo.SEO_OVERVIEW_ROUTE)
        if os_accounts.is_admin(user):
            st.caption(f"Error type: {error.__class__.__name__}")
    finally:
        completion_payload = json.dumps(
            {
                "routeKey": os_accounts.page_key_for_route(route) or "",
                "epoch": int(st.session_state.get("navigation_epoch") or 0),
                "status": render_status,
            },
            ensure_ascii=True,
        ).replace("</", "<\\/")
        components.html(
            f"<script>window.parent.SportsCaveTopBar?.completeNavigation?.({completion_payload});</script>",
            height=0,
            width=0,
        )
        logging.info(
            "SEO_PERF route=%s operation=route_dispatch duration_ms=%.2f",
            route,
            (time.perf_counter() - route_started) * 1000,
        )


def render_page(
    user,
    route,
    *,
    store=None,
    navigate=None,
    google_store=None,
    import_store=None,
    phase4_store=None,
    reporting_reader=None,
    growth_store=None,
):
    if route not in seo.SEO_ROUTES:
        raise ValueError(f"Unknown SEO route: {route}")
    _inject_styles()
    _render_notice()
    store = store or seo.default_store()
    _render_active_route(
        user,
        route,
        store,
        navigate,
        google_store,
        import_store,
        phase4_store,
        reporting_reader,
        growth_store,
    )
