from datetime import date, datetime, timezone
import html
import json
import re

import streamlit as st

from activity_log import record_activity_log
import google_seo
import google_seo_import
import google_seo_phase4
import navigation_runtime
import os_accounts
import seo_sync_progress
import seo_workspace as seo


SEO_OVERVIEW_CACHE_TTL_SECONDS = 15
SEO_PROGRESS_POLL_SECONDS = 15
SEO_ADMIN_OPEN_STATE_KEY = "seo-data-connections-open"


PAGE_SUBTITLES = {
    seo.SEO_OVERVIEW_ROUTE: "Plan content, track authority work and monitor organic growth from one place.",
    seo.SEO_CITATIONS_ROUTE: "Track reputable external profiles and business listings that display the Sports Cave brand and website.",
    seo.SEO_BLOG_ROUTE: "Create premium sports stories that attract search traffic and lead fans naturally toward Sports Cave collections.",
    seo.SEO_INTERNAL_LINKING_ROUTE: "Plan and verify links inside blog content without changing owner-controlled Shopify pages.",
    seo.SEO_BACKLINKS_ROUTE: "Build genuine authority through relevant websites, creators and editorial relationships.",
    seo.SEO_KEYWORDS_ROUTE: "Turn real Google Search Console queries into buyer-focused page and content opportunities.",
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


def _header(route):
    st.markdown(
        f"""
        <div class="sc-seo-header">
            <div>
                <div class="sc-seo-kicker">Growth / SEO</div>
                <h1>{html.escape(route)}</h1>
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
        metadata={"seo_area": area, **dict(metadata or {})},
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
    st.dataframe(rows, use_container_width=True, hide_index=True, height=height)


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
        tuple(by_id),
        format_func=lambda record_id: str(by_id[record_id].get(title_field) or "Untitled"),
        key=key,
    )


def _rule_expander(title, lines):
    with st.expander(title, expanded=False):
        for line in lines:
            st.markdown(f"- {line}")


def _navigate(navigate, route):
    if navigate is not None:
        navigate(route)
        st.rerun()


def _google_badge_class(status):
    if status == "Connected":
        return "sc-seo-badge-connected"
    if status == "Needs attention":
        return "sc-seo-badge-attention"
    if status == "Configuration required":
        return "sc-seo-badge-required"
    return ""


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


@st.cache_data(ttl=SEO_OVERVIEW_CACHE_TTL_SECONDS, show_spinner=False, max_entries=24)
def _cached_default_reporting_snapshot(
    preset,
    market,
    device,
    search,
    custom_start,
    custom_end,
):
    phase4_store = google_seo_phase4.default_phase4_store()
    reader = google_seo_phase4.PostgresSEOReportingReader(phase4_store)
    return reader.snapshot(
        preset=preset,
        market=market,
        device=device,
        search=search,
        custom_start=custom_start,
        custom_end=custom_end,
    )


def invalidate_seo_overview_summary_cache():
    _cached_default_shopify_health.clear()
    _cached_default_google_connection.clear()
    _cached_default_phase4_health.clear()
    _cached_default_reporting_snapshot.clear()


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

    controls = st.columns(2)
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
    if reconnect_required:
        controls[1].link_button(
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
            gsc_ids = tuple(gsc_by_id)
            ga4_ids = tuple(ga4_by_id)
            selectors = st.columns(2)
            gsc_value = selectors[0].selectbox(
                "Search Console property",
                gsc_ids,
                index=gsc_ids.index(selected_gsc) if selected_gsc in gsc_ids else 0,
                format_func=lambda value: f"{gsc_by_id[value].get('name') or value} ({value})",
                key="seo-google-gsc-property",
            )
            ga4_value = selectors[1].selectbox(
                "Google Analytics 4 property",
                ga4_ids,
                index=ga4_ids.index(selected_ga4) if selected_ga4 in ga4_ids else 0,
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
        _phase4_status_card("URL mapping", "Saved", f"{health.get('unmapped_page_count', 0):,} unmapped"),
        unsafe_allow_html=True,
    )
    health_columns[2].markdown(
        _phase4_status_card("Revenue matching", "Saved", f"{health.get('unmatched_transaction_count', 0):,} unmatched or disputed"),
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


def _load_reporting_health(phase4_store=None):
    try:
        if phase4_store is not None:
            return dict(phase4_store.saved_health())
        return dict(_cached_default_phase4_health())
    except google_seo_phase4.SEOPhase4Error:
        return {}


def _reporting_filters():
    columns = st.columns([1.2, 1, 1, 1])
    preset = columns[0].selectbox(
        "Period",
        ("Last 28 days", "Last 90 days", "Last 12 months", "Custom dates"),
        key="seo-phase4-period",
    )
    market = columns[1].selectbox(
        "Market",
        ("All markets", "Australia", "United States", "United Kingdom"),
        key="seo-phase4-market",
    )
    device = columns[2].selectbox(
        "Device",
        ("All devices", "Desktop", "Mobile"),
        key="seo-phase4-device",
    )
    search = columns[3].selectbox(
        "Search",
        ("All searches", "Brand", "Non-brand"),
        key="seo-phase4-search",
    )
    custom_start = custom_end = None
    if preset == "Custom dates":
        date_columns = st.columns(2)
        custom_start = date_columns[0].date_input("Start date", key="seo-phase4-start")
        custom_end = date_columns[1].date_input("End date", key="seo-phase4-end")
    return {
        "preset": preset,
        "market": market,
        "device": device,
        "search": search,
        "custom_start": custom_start,
        "custom_end": custom_end,
    }


def _load_reporting_snapshot(filters, *, phase4_store=None, reporting_reader=None):
    arguments = {
        "preset": filters["preset"],
        "market": filters["market"],
        "device": filters["device"],
        "search": filters["search"],
        "custom_start": filters["custom_start"],
        "custom_end": filters["custom_end"],
    }
    if reporting_reader is not None:
        return reporting_reader.snapshot(**arguments)
    if phase4_store is not None:
        return google_seo_phase4.PostgresSEOReportingReader(phase4_store).snapshot(
            **arguments
        )
    return _cached_default_reporting_snapshot(
        arguments["preset"],
        arguments["market"],
        arguments["device"],
        arguments["search"],
        arguments["custom_start"],
        arguments["custom_end"],
    )


def _numeric_value(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_value(value, *, style="number"):
    numeric = _numeric_value(value)
    if numeric is None:
        return "—"
    if style == "percent":
        return f"{numeric * 100:.1f}%"
    if style == "position":
        return f"{numeric:.1f}"
    return f"{round(numeric):,}"


def _metric_delta(current, previous, *, position=False):
    current_value = _numeric_value(current)
    previous_value = _numeric_value(previous)
    if current_value is None or previous_value in (None, 0):
        return None
    if position:
        return f"{current_value - previous_value:+.1f} vs previous"
    change = ((current_value - previous_value) / abs(previous_value)) * 100
    return f"{change:+.1f}% vs previous"


def _render_reporting_metrics(snapshot):
    current = snapshot.get("current") or {}
    previous = snapshot.get("previous") or {}
    metrics = (
        ("Organic Clicks", "organic_clicks", "number", False),
        ("Organic Impressions", "organic_impressions", "number", False),
        ("CTR", "ctr", "percent", False),
        ("Average Position", "average_position", "position", True),
        ("Organic Sessions", "organic_sessions", "number", False),
    )
    columns = st.columns(len(metrics))
    for column, (label, key, style, inverse) in zip(columns, metrics):
        column.metric(
            label,
            _metric_value(current.get(key), style=style),
            _metric_delta(current.get(key), previous.get(key), position=inverse),
            delta_color="inverse" if inverse else "normal",
        )
    note = str(current.get("search_scope_note") or "")
    if note:
        st.caption(note)


def _render_reporting_tables(snapshot):
    pages = []
    for row in list(snapshot.get("top_pages") or [])[:8]:
        pages.append(
            {
                "Landing page": row.get("title") or row.get("canonical_url") or "Untitled",
                "Clicks": row.get("clicks") or 0,
                "Impressions": row.get("impressions") or 0,
                "Position": _metric_value(row.get("average_position"), style="position"),
                "Sessions": row.get("sessions") or 0,
            }
        )
    _section_heading("Top Landing Pages")
    _table(
        pages,
        empty="No mapped landing-page results are available for this period.",
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
            }
        )
    _section_heading("Top Search Queries")
    _table(
        queries,
        empty="No search-query results are available for this period.",
        height=285,
    )


def _render_reporting_dashboard(*, phase4_store=None, reporting_reader=None):
    health = _load_reporting_health(phase4_store)
    through_date = str(health.get("common_reporting_date") or "")
    if through_date:
        filters = _reporting_filters()
        st.markdown(
            f'<div class="sc-seo-data-date">Reporting data through {html.escape(_display_progress_date(through_date))}</div>',
            unsafe_allow_html=True,
        )
        try:
            snapshot = _load_reporting_snapshot(
                filters,
                phase4_store=phase4_store,
                reporting_reader=reporting_reader,
            )
        except google_seo_phase4.SEOPhase4Error:
            snapshot = {}
    else:
        snapshot = {}

    _section_heading("Main SEO metrics")
    if snapshot.get("ready"):
        _render_reporting_metrics(snapshot)
    else:
        st.info(
            "SEO reporting will appear here when GSC, GA4 and Shopify share a reliable completed date."
        )

    _section_heading("Organic Performance")
    st.markdown(
        '<div class="sc-seo-empty-chart">A saved daily trend is not available yet. No live services are queried from this dashboard.</div>',
        unsafe_allow_html=True,
    )

    if snapshot.get("ready"):
        _section_heading("SEO opportunities")
        st.caption("No stored SEO opportunities are available yet.")
        _render_reporting_tables(snapshot)


def _render_current_work(state, user, navigate):
    _section_heading("Current work")
    actions = st.columns(4)
    if actions[0].button("Create Blog Brief", icon=":material/edit_note:", use_container_width=True):
        _navigate(navigate, seo.SEO_BLOG_ROUTE)
    if actions[1].button("Import GSC Keywords", icon=":material/upload_file:", use_container_width=True):
        st.session_state["seo-keyword-view"] = "Import GSC CSV"
        _navigate(navigate, seo.SEO_KEYWORDS_ROUTE)
    if actions[2].button("Add Outreach Prospect", icon=":material/person_add:", use_container_width=True):
        st.session_state["seo-open-outreach-dialog"] = True
        _navigate(navigate, seo.SEO_BACKLINKS_ROUTE)
    if actions[3].button("Add Citation", icon=":material/add_link:", use_container_width=True):
        st.session_state["seo-open-citation-dialog"] = True
        _navigate(navigate, seo.SEO_CITATIONS_ROUTE)

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
        _section_heading("Completed work")
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
):
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
        gsc_status = google_seo.connection_status_label(
            config_status, connection, service="gsc"
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
            last_sync=connection.get("last_successful_sync_at") or "",
            data_date=connection.get("gsc_data_through_date") or "",
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
            "Shopify",
            shopify["status"],
            property_name="Sports Cave store" if shopify["status"] == "Connected" else "",
            last_sync=shopify["last_sync"],
            extra_class="sc-seo-shopify-health",
            show_data_date=False,
        ),
        unsafe_allow_html=True,
    )
    _render_google_controls(user, google_store, config_status, connection)

    _render_historical_import_controls(
        user,
        connection,
        import_store=import_store,
        phase4_store=phase4_store,
        connection_store=google_store,
        config_ready=config_status.get("ready", False),
    )
    _render_phase4_foundation(
        user,
        phase4_store,
        reporting_reader,
        google_store,
    )


def _render_overview(
    state,
    user,
    navigate,
    google_store=None,
    import_store=None,
    phase4_store=None,
    reporting_reader=None,
):
    _header(seo.SEO_OVERVIEW_ROUTE)
    _consume_google_oauth_notice()
    _render_reporting_dashboard(
        phase4_store=phase4_store,
        reporting_reader=reporting_reader,
    )
    _render_current_work(state, user, navigate)

    with st.expander("Core rules and markets", expanded=False):
        st.markdown(
            """
            <div class="sc-seo-rule-grid">
                <div class="sc-seo-rule">Organic sales are the primary goal.</div>
                <div class="sc-seo-rule">Write for sports fans first.</div>
                <div class="sc-seo-rule">Use one primary keyword per target page.</div>
                <div class="sc-seo-rule">Quality beats quantity.</div>
                <div class="sc-seo-rule">Never use spam links or fake profiles.</div>
                <div class="sc-seo-rule">If a page, URL or fact is uncertain, stop and verify it.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("Primary markets: Australia, United States and United Kingdom")
        st.caption("Secondary markets: Canada and New Zealand")

    _render_data_connections_admin(
        user,
        google_store=google_store,
        import_store=import_store,
        phase4_store=phase4_store,
        reporting_reader=reporting_reader,
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
        category_values = sorted({row.get("category") for row in citations if row.get("category")})
        category_filter = filters[2].selectbox("Category", ("All", *category_values), key="seo-citation-category-filter")
        owner_values = sorted({row.get("owner") for row in citations if row.get("owner")})
        owner_filter = filters[3].selectbox("Owner", ("All", *owner_values), key="seo-citation-owner-filter")
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
        search_intent = columns[0].selectbox(
            "Search intent",
            ("Player Legacy", "Greatest Moments", "Historic Rivalry", "Sports Culture", "Memorabilia Collecting", "Man Cave Inspiration", "Gift Guide", "Sports Decor Ideas", "Other"),
            index=0,
        )
        target_market = columns[1].selectbox(
            "Target market",
            seo.TARGET_MARKETS,
            index=seo.TARGET_MARKETS.index(record.get("target_market")) if record.get("target_market") in seo.TARGET_MARKETS else 0,
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
    blog_id = st.selectbox("Blog record", tuple(by_id), format_func=lambda key: by_id[key].get("article_title") or by_id[key].get("primary_keyword") or "Untitled", key="seo-blog-builder-record")
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
            target_market = columns[0].selectbox("Target market", seo.TARGET_MARKETS, index=seo.TARGET_MARKETS.index(blog.get("target_market")) if blog.get("target_market") in seo.TARGET_MARKETS else 0)
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
    selected_id = st.selectbox("Saved template", tuple(by_id), format_func=lambda key: by_id[key].get("name"), key="seo-template-preview")
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
        market_filter = filters[2].selectbox("Target market", ("All", *seo.TARGET_MARKETS), key="seo-blog-market-filter")
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
            source_blog_id = st.selectbox("Source blog *", tuple(blog_options), format_func=lambda key: blog_options[key].get("article_title") or blog_options[key].get("primary_keyword") or "Untitled", index=list(blog_options).index(record.get("source_blog_id")) if record.get("source_blog_id") in blog_options else 0)
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
            target_id = st.selectbox("Target to verify", tuple(by_id), format_func=lambda key: by_id[key].get("label"), key="seo-target-verify-select")
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
        target_market = columns[0].selectbox("Target market", seo.TARGET_MARKETS, index=seo.TARGET_MARKETS.index(record.get("target_market")) if record.get("target_market") in seo.TARGET_MARKETS else 0)
        opportunity_type = columns[1].selectbox("Opportunity type", ("Editorial Mention", "Guest Article", "Creator Feature", "Gift Guide", "Resource/List", "Podcast Show Notes", "Genuine Community Contribution", "Other"), index=0)
        relevant_article_url = st.text_input("Relevant article URL", value=record.get("relevant_article_url") or "")
        observed_topic = st.text_input("Specific article or topic observed", value=record.get("observed_topic") or "")
        target_page = st.text_input("Sports Cave target page", value=record.get("target_page") or "")
        anchor_columns = st.columns(2)
        anchor_category = anchor_columns[0].selectbox("Proposed anchor category", ("Brand / Naked URL", "Descriptive / Partial Match", "Exact Keyword", "Unknown"), index=0)
        anchor_text = anchor_columns[1].text_input("Proposed anchor text", value=record.get("anchor_text") or "")
        quality_result = columns[0].selectbox("Quality result", ("Needs Review", "Approved", "Rejected"), index=("Needs Review", "Approved", "Rejected").index(record.get("quality_result")) if record.get("quality_result") in ("Needs Review", "Approved", "Rejected") else 0)
        status = columns[1].selectbox("Status", seo.OUTREACH_STATUSES, index=seo.OUTREACH_STATUSES.index(record.get("status")) if record.get("status") in seo.OUTREACH_STATUSES else 0)
        rejection_reason = st.text_input("Rejection reason", value=record.get("rejection_reason") or "", disabled=status != "Rejected" and quality_result != "Rejected")
        quality_checks = st.multiselect("Qualification checklist", ("Site is active", "Content appears written for humans", "Topic is relevant to Sports Cave", "Site is brand-safe", "Outbound links appear reasonable", "Page can be indexed", "Site is not a link farm", "Site is not a PBN", "Site is not primarily selling backlinks", "A real reader could benefit"), default=record.get("quality_checks") or [])
        outreach_draft = st.text_area("Outreach draft", value=record.get("outreach_draft") or "", height=160)
        dates = st.columns(3)
        date_contacted = dates[0].date_input("Date contacted", value=date.fromisoformat(record["date_contacted"]) if record.get("date_contacted") else None)
        follow_up_due = dates[1].date_input("Follow-up due", value=date.fromisoformat(record["follow_up_due"]) if record.get("follow_up_due") else None)
        follow_up_count = dates[2].number_input("Follow-ups sent", min_value=0, max_value=1, value=int(record.get("follow_up_count") or 0))
        live_url = st.text_input("Live URL", value=record.get("live_url") or "")
        relevant_placement = st.checkbox("Placement is relevant", value=bool(record.get("relevant_placement")))
        verification_date = st.date_input("Verification date", value=date.fromisoformat(record["verification_date"]) if record.get("verification_date") else None)
        disclosure = st.selectbox("Link disclosure", ("Unknown/Needs Review", "Sponsored", "Nofollow", "Editorial with no material exchange"), index=0)
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
        page_type = columns[0].selectbox("Intended page type", seo.KEYWORD_PAGE_TYPES, index=seo.KEYWORD_PAGE_TYPES.index(record.get("page_type")) if record.get("page_type") in seo.KEYWORD_PAGE_TYPES else 2)
        buyer_intent = columns[1].selectbox("Buyer intent", seo.KEYWORD_INTENTS, index=seo.KEYWORD_INTENTS.index(record.get("buyer_intent")) if record.get("buyer_intent") in seo.KEYWORD_INTENTS else 4)
        priority = columns[0].selectbox("Priority", seo.KEYWORD_PRIORITIES, index=seo.KEYWORD_PRIORITIES.index(record.get("priority")) if record.get("priority") in seo.KEYWORD_PRIORITIES else 1)
        mapping_status = columns[1].selectbox("Mapping status", seo.KEYWORD_MAPPING_STATUSES, index=seo.KEYWORD_MAPPING_STATUSES.index(record.get("mapping_status")) if record.get("mapping_status") in seo.KEYWORD_MAPPING_STATUSES else 0)
        target_market = columns[0].selectbox("Target market", ("", *seo.TARGET_MARKETS), index=("", *seo.TARGET_MARKETS).index(record.get("target_market")) if record.get("target_market") in ("", *seo.TARGET_MARKETS) else 0)
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
    page_type_filter = filters[1].selectbox("Page type", ("All", *seo.KEYWORD_PAGE_TYPES), key="seo-keyword-type-filter")
    intent_filter = filters[2].selectbox("Intent", ("All", *seo.KEYWORD_INTENTS), key="seo-keyword-intent-filter")
    status_filter = filters[3].selectbox("Mapping status", ("All", *seo.KEYWORD_MAPPING_STATUSES), key="seo-keyword-status-filter")
    second = st.columns(4)
    market_filter = second[0].selectbox("Target market", ("All", "Unassigned", *seo.TARGET_MARKETS), key="seo-keyword-market-filter")
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
    keyword_id = st.selectbox("Keyword", tuple(by_id), format_func=lambda key: by_id[key].get("keyword"), key="seo-map-keyword")
    keyword = by_id[keyword_id]
    with st.form("seo-keyword-map-form"):
        columns = st.columns(2)
        page_type = columns[0].selectbox("Page type", seo.KEYWORD_PAGE_TYPES, index=seo.KEYWORD_PAGE_TYPES.index(keyword.get("page_type")) if keyword.get("page_type") in seo.KEYWORD_PAGE_TYPES else 2)
        market = columns[1].selectbox("Market", seo.TARGET_MARKETS, index=seo.TARGET_MARKETS.index(keyword.get("target_market")) if keyword.get("target_market") in seo.TARGET_MARKETS else 0)
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


def _render_keywords(store, state, user):
    _header(seo.SEO_KEYWORDS_ROUTE)
    st.caption("Use real search data only. This workspace never invents search volume, clicks, impressions, CTR or position.")
    keywords = seo.active_records(state, "keywords")
    tab_names = ("Keyword Library", "Import GSC CSV", "Page Mapping", "Analysis Prompt", "Rules")
    view = _active_view(
        tab_names,
        key="seo-keyword-view",
        default=st.session_state.get("seo-keyword-view") or tab_names[0],
    )
    if view == "Keyword Library":
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
):
    state = {}
    if route != seo.SEO_OVERVIEW_ROUTE:
        try:
            state = store.load()
        except seo.SEOStoreError as error:
            _header(route)
            st.error(str(error))
            st.caption("SEO records were not changed. Ask an administrator to check the shared data store.")
            return
    consume_summary = getattr(store, "consume_import_summary", None)
    summary = (
        consume_summary()
        if route != seo.SEO_OVERVIEW_ROUTE and callable(consume_summary)
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
    navigation_runtime.dispatch_selected(
        route,
        {
            seo.SEO_OVERVIEW_ROUTE: lambda: _render_overview(
                state,
                user,
                navigate,
                google_store,
                import_store,
                phase4_store,
                reporting_reader,
            ),
            seo.SEO_CITATIONS_ROUTE: lambda: _render_citations(store, state, user),
            seo.SEO_BLOG_ROUTE: lambda: _render_blog(store, state, user),
            seo.SEO_INTERNAL_LINKING_ROUTE: lambda: _render_internal_linking(store, state, user),
            seo.SEO_BACKLINKS_ROUTE: lambda: _render_outreach(store, state, user),
            seo.SEO_KEYWORDS_ROUTE: lambda: _render_keywords(store, state, user),
        },
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
    )
