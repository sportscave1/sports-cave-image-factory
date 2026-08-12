from datetime import date, datetime, timezone
import html
import json
import re

import streamlit as st

from activity_log import record_activity_log
import os_accounts
import seo_workspace as seo


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
        .sc-seo-badge { background: #f3ecdc; border: 1px solid #d9c28d; border-radius: 999px; color: #6d531c; display: inline-block; font-size: .67rem; font-weight: 700; padding: .16rem .42rem; }
        .sc-seo-empty-chart { align-items: center; background: #fbfaf7; border: 1px dashed #d7d2c7; border-radius: 8px; color: #6e6b65; display: flex; justify-content: center; min-height: 13rem; padding: 2rem; text-align: center; }
        .sc-seo-future-metric { background: #fff; border: 1px solid #dfdbd1; border-top: 2px solid #c5a45c; border-radius: 8px; min-height: 7rem; padding: .85rem; }
        .sc-seo-future-label { color: #393734; font-size: .78rem; font-weight: 650; line-height: 1.25; min-height: 2rem; }
        .sc-seo-future-value { color: #171614; font-size: 1.7rem; line-height: 1; margin: .45rem 0 .55rem; }
        .sc-seo-future-source { color: #77736b; font-size: .7rem; line-height: 1.3; }
        .sc-seo-rule-grid { display: grid; gap: .55rem; grid-template-columns: repeat(3, minmax(0, 1fr)); }
        .sc-seo-rule { background: #faf8f2; border-left: 2px solid #b79243; border-radius: 4px; font-size: .8rem; padding: .65rem .75rem; }
        .sc-seo-note { background: #faf8f2; border: 1px solid #e1d9c8; border-radius: 6px; padding: .8rem; }
        .sc-seo-note strong { color: #242321; }
        .sc-seo-danger { border-left-color: #a74b42; }
        [data-testid="stDataFrame"] { border-radius: 6px !important; overflow: hidden !important; }
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


def _render_overview(state, user, navigate):
    _header(seo.SEO_OVERVIEW_ROUTE)
    integration_columns = st.columns(2)
    integration_columns[0].markdown(
        """
        <div class="sc-seo-integration">
            <span class="sc-seo-badge">Planned</span>
            <h3>Google Search Console</h3>
            <strong>Not connected</strong>
            <p>Clicks, impressions, CTR and search position will appear here later.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    integration_columns[1].markdown(
        """
        <div class="sc-seo-integration">
            <span class="sc-seo-badge">Planned</span>
            <h3>Google Analytics 4</h3>
            <strong>Not connected</strong>
            <p>Organic sessions, revenue and conversions will appear here later.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Future organic reporting")
    future_metrics = (
        ("Organic Clicks", "GSC"),
        ("Organic Impressions", "GSC"),
        ("Average Position", "GSC"),
        ("Organic Sessions", "GA4"),
        ("Organic Revenue", "GA4"),
    )
    future_columns = st.columns(5)
    for column, (label, source) in zip(future_columns, future_metrics):
        column.markdown(
            f'<div class="sc-seo-future-metric">'
            f'<div class="sc-seo-future-label">{html.escape(label)}</div>'
            f'<div class="sc-seo-future-value">—</div>'
            f'<div class="sc-seo-future-source">{html.escape(source)} · Awaiting connection</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.subheader("Organic Performance")
    st.markdown(
        '<div class="sc-seo-empty-chart">Connect Google Search Console and GA4 in a later update to view organic performance over time.</div>',
        unsafe_allow_html=True,
    )

    st.subheader("Current work")
    metrics = seo.overview_metrics(state)
    columns = st.columns(5)
    for column, (label, value) in zip(columns, metrics.items()):
        column.metric(label, value)

    st.subheader("Quick actions")
    actions = st.columns(4)
    if actions[0].button("Create Blog Brief", icon=":material/edit_note:", use_container_width=True):
        _navigate(navigate, seo.SEO_BLOG_ROUTE)
    if actions[1].button("Import GSC Keywords", icon=":material/upload_file:", use_container_width=True):
        st.session_state["seo-keyword-default-tab"] = "Import GSC CSV"
        _navigate(navigate, seo.SEO_KEYWORDS_ROUTE)
    if actions[2].button("Add Outreach Prospect", icon=":material/person_add:", use_container_width=True):
        st.session_state["seo-open-outreach-dialog"] = True
        _navigate(navigate, seo.SEO_BACKLINKS_ROUTE)
    if actions[3].button("Add Citation", icon=":material/add_link:", use_container_width=True):
        st.session_state["seo-open-citation-dialog"] = True
        _navigate(navigate, seo.SEO_CITATIONS_ROUTE)

    left, right = st.columns([1, 1.4])
    with left:
        st.subheader("Weekly focus")
        targets = state.get("settings", {}).get("weekly_targets") or list(seo.WEEKLY_TARGETS)
        selected = st.multiselect(
            "Completed this week",
            targets,
            default=[],
            key="seo-weekly-focus-completed",
            label_visibility="collapsed",
        )
        st.progress(len(selected) / max(len(targets), 1), text=f"{len(selected)} of {len(targets)} complete")
    with right:
        st.subheader("Recent SEO activity")
        entries = []
        if os_accounts.can_view_activity_log(user):
            try:
                import sports_cave_dashboard

                rows = sports_cave_dashboard.list_activity_entries(
                    local_now=datetime.now(timezone.utc),
                    limit=40,
                    user=user,
                )
                entries = [row for row in rows if str(row.get("Page/Area") or "").startswith("SEO /")][:8]
            except Exception:
                entries = []
        _table(entries, empty="SEO activity will appear here as work is recorded.", height=250)

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
    statuses = {status: sum(row.get("status") == status for row in citations) for status in seo.CITATION_STATUSES}
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

    tabs = st.tabs(("All Citations", "To Do", "Pending", "Live", "Rules and Business Details"))
    with tabs[0]:
        filters = st.columns(4)
        search = filters[0].text_input("Search platform", key="seo-citation-search")
        status_filter = filters[1].selectbox("Status", ("All", *seo.CITATION_STATUSES), key="seo-citation-status-filter")
        category_values = sorted({row.get("category") for row in citations if row.get("category")})
        category_filter = filters[2].selectbox("Category", ("All", *category_values), key="seo-citation-category-filter")
        owner_values = sorted({row.get("owner") for row in citations if row.get("owner")})
        owner_filter = filters[3].selectbox("Owner", ("All", *owner_values), key="seo-citation-owner-filter")
        filtered = [
            row for row in citations
            if (not search or search.casefold() in str(row.get("platform") or "").casefold())
            and (status_filter == "All" or row.get("status") == status_filter)
            and (category_filter == "All" or row.get("category") == category_filter)
            and (owner_filter == "All" or row.get("owner") == owner_filter)
        ]
        _table(
            [
                {
                    "Platform": row.get("platform"), "Category": row.get("category"), "Signup URL": row.get("signup_url"),
                    "Profile URL": row.get("profile_url"), "Username or Handle": row.get("username_handle"),
                    "Website Displayed": row.get("website_displayed"), "Logo Uploaded": row.get("logo_uploaded"),
                    "Status": row.get("status"), "Owner": row.get("owner"), "Date Completed": row.get("date_completed"),
                    "Notes": row.get("notes"),
                }
                for row in filtered
            ],
            empty="No citations match these filters. Add a reputable profile when work begins.",
        )
        st.download_button(
            "Export citations CSV",
            seo.records_csv_bytes(filtered, ("platform", "category", "signup_url", "profile_url", "username_handle", "website_displayed", "logo_uploaded", "status", "owner", "date_completed", "notes")),
            file_name="sports-cave-citations.csv",
            mime="text/csv",
            icon=":material/download:",
        )
    for tab, status_set, empty in (
        (tabs[1], {"To Do", "In Progress"}, "No citations are waiting to start."),
        (tabs[2], {"Pending Verification"}, "No citations are pending verification."),
        (tabs[3], {"Live"}, "No citations are marked Live yet."),
    ):
        with tab:
            _table([row for row in citations if row.get("status") in status_set], empty=empty)
    with tabs[4]:
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
    steps = st.tabs(("1 Brief", "2 Article", "3 SEO and Links", "4 Assets", "5 Review"))
    with steps[0]:
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
    with steps[1]:
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
    with steps[2]:
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
    with steps[3]:
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
    with steps[4]:
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
    tabs = st.tabs(("Pipeline", "Blog Builder", "Templates", "Rules"))
    with tabs[0]:
        filters = st.columns(3)
        search = filters[0].text_input("Search articles", key="seo-blog-search")
        status_filter = filters[1].selectbox("Status", ("All", *seo.BLOG_STATUSES), key="seo-blog-status-filter")
        market_filter = filters[2].selectbox("Target market", ("All", *seo.TARGET_MARKETS), key="seo-blog-market-filter")
        filtered = [row for row in blogs if (not search or search.casefold() in json.dumps(row).casefold()) and (status_filter == "All" or row.get("status") == status_filter) and (market_filter == "All" or row.get("target_market") == market_filter)]
        _table([{"Article Title": row.get("article_title"), "Sport or Topic": row.get("sport_topic"), "Primary Keyword": row.get("primary_keyword"), "Search Intent": row.get("search_intent"), "Target Market": row.get("target_market"), "Target Collection": row.get("target_collection") or row.get("collection_name"), "Status": row.get("status"), "Owner": row.get("owner"), "Due Date": row.get("due_date"), "Last Updated": row.get("updated_at")} for row in filtered], empty="No blog records yet. Create a brief to start the editorial pipeline.")
    with tabs[1]:
        _render_blog_builder(store, state, user, blogs)
    with tabs[2]:
        _render_prompt_templates(state)
    with tabs[3]:
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
    tabs = st.tabs(("Link Plans", "Target Library", "Link Opportunities", "Rules"))
    with tabs[0]:
        _table([{"Blog Article": row.get("source_blog"), "Sport": row.get("sport"), "Homepage Link": row.get("homepage_url"), "Collection Target": row.get("collection_url"), "Product Target": row.get("product_url") or "No Product Link", "Anchor Text": row.get("collection_anchor_text"), "Placement": row.get("placement"), "Verification Status": row.get("verification_status"), "Last Checked": row.get("last_checked"), "Owner": row.get("owner")} for row in plans], empty="No internal link plans yet. Add one when a blog brief is ready for link planning.")
    with tabs[1]:
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
    with tabs[2]:
        _table(seo.internal_link_opportunities(state), empty="No missing internal-link opportunities are visible from the stored blog records.")
    with tabs[3]:
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
    tabs = st.tabs(("Prospects", "Outreach", "Live Links", "Templates", "Rules"))
    with tabs[0]:
        filters = st.columns(3)
        search = filters[0].text_input("Search sites or creators", key="seo-outreach-search")
        status_filter = filters[1].selectbox("Status", ("All", *seo.OUTREACH_STATUSES), key="seo-outreach-status-filter")
        quality_filter = filters[2].selectbox("Quality result", ("All", "Needs Review", "Approved", "Rejected"), key="seo-outreach-quality-filter")
        filtered = [row for row in records if (not search or search.casefold() in json.dumps(row).casefold()) and (status_filter == "All" or row.get("status") == status_filter) and (quality_filter == "All" or row.get("quality_result") == quality_filter)]
        _table([{"Site or Creator": row.get("site_creator"), "Website": row.get("website"), "Contact": row.get("contact_name") or row.get("contact_email"), "Niche": row.get("niche"), "Opportunity Type": row.get("opportunity_type"), "Target Page": row.get("target_page"), "Quality Result": row.get("quality_result"), "Status": row.get("status"), "Last Contact": row.get("date_contacted"), "Follow-up Due": row.get("follow_up_due"), "Owner": row.get("owner")} for row in filtered], empty="No outreach prospects yet. Add a relevant, human-run site or creator after research.")
        st.download_button("Export outreach CSV", seo.records_csv_bytes(filtered, ("site_creator", "website", "contact_name", "contact_email", "niche", "opportunity_type", "target_page", "quality_result", "status", "date_contacted", "follow_up_due", "owner", "live_url")), file_name="sports-cave-outreach.csv", mime="text/csv", icon=":material/download:")
    with tabs[1]:
        _table([row for row in records if row.get("status") in {"Outreach Draft", "Sent", "Follow-up Due", "Replied"}], empty="No outreach conversations are active.")
    with tabs[2]:
        _table([{"Site or Creator": row.get("site_creator"), "Live URL": row.get("live_url"), "Target Page": row.get("target_page"), "Anchor Text": row.get("anchor_text"), "Disclosure": row.get("disclosure"), "Verified": row.get("verification_date")} for row in records if row.get("status") == "Live"], empty="No editorial backlinks are marked Live yet.")
    with tabs[3]:
        _render_prompt_templates(state)
    with tabs[4]:
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
    st.markdown('<div class="sc-seo-note"><strong>GSC Connection — Planned</strong><br>Use a real Performance Queries CSV now. Live OAuth is deliberately deferred.</div>', unsafe_allow_html=True)
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
    tabs = st.tabs(tab_names)
    with tabs[0]:
        _render_keyword_library(store, state, user, keywords)
    with tabs[1]:
        _render_gsc_import(store, state, user, keywords)
    with tabs[2]:
        _render_page_mapping(store, state, user, keywords)
    with tabs[3]:
        template = next((row for row in state.get("prompt_templates", []) if row.get("name") == "Keyword extraction"), {})
        st.code(template.get("template") or seo.KEYWORD_EXTRACTION_TEMPLATE, language=None)
        st.caption("Copy this prompt and supply the real GSC data. The workspace does not fabricate an AI result.")
    with tabs[4]:
        _rule_expander("Core rule", ["Use only real Google Search Console data.", "Keep low-intent terms for human review instead of automatically deleting them."])
        _rule_expander("Mapping", ["Use one primary keyword per target page.", "Warn about likely cannibalisation.", "Do not change live URLs or create pages automatically."])


def render_page(user, route, *, store=None, navigate=None):
    if route not in seo.SEO_ROUTES:
        raise ValueError(f"Unknown SEO route: {route}")
    _inject_styles()
    _render_notice()
    store = store or seo.default_store()
    try:
        state = store.load()
    except seo.SEOStoreError as error:
        _header(route)
        st.error(str(error))
        st.caption("SEO records were not changed. Ask an administrator to check the shared data store.")
        return
    if route == seo.SEO_OVERVIEW_ROUTE:
        _render_overview(state, user, navigate)
    elif route == seo.SEO_CITATIONS_ROUTE:
        _render_citations(store, state, user)
    elif route == seo.SEO_BLOG_ROUTE:
        _render_blog(store, state, user)
    elif route == seo.SEO_INTERNAL_LINKING_ROUTE:
        _render_internal_linking(store, state, user)
    elif route == seo.SEO_BACKLINKS_ROUTE:
        _render_outreach(store, state, user)
    elif route == seo.SEO_KEYWORDS_ROUTE:
        _render_keywords(store, state, user)
