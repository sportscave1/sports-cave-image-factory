"""Facebook and Instagram community workspace in the existing Social Media tab."""
import html
import logging
import os
import time

import streamlit as st

import os_accounts
import social_media
from meta_social import CommunityError, MetaCommunity
from social_community_feed import CommunityFeed
from social_community_views import render_inbox, render_comments, dated
import social_community_presentation as presentation
from page_presentation import inject_compact_page
import social_collaborations
import social_community_store as ledger


PLATFORM_ICONS = {
    "Instagram": """
        <rect x="3" y="3" width="18" height="18" rx="5"></rect>
        <circle cx="12" cy="12" r="4"></circle>
        <circle cx="17.4" cy="6.7" r="1" class="fill"></circle>
    """,
    "Facebook": """
        <path class="fill" d="M14.2 22v-8h2.8l.5-3.2h-3.3V8.7c0-.9.3-1.6 1.7-1.6h1.8V4.2c-.3 0-1.4-.2-2.6-.2-2.6 0-4.4 1.6-4.4 4.5v2.3H8v3.2h2.7v8h3.5z"></path>
    """,
    "Pinterest": """
        <circle cx="12" cy="12" r="9"></circle>
        <path d="M10.1 18.5c.7-2 1.1-3 1.4-4.3-.7-1.3.1-4 1.5-4 1.2 0 1.3 1.5.9 2.6-.4 1.1.1 2 1.1 2 1.4 0 2.4-1.8 2.4-4.3 0-2.3-1.7-4-4.2-4-2.9 0-4.6 2.2-4.6 4.4 0 .9.3 1.8.8 2.3"></path>
    """,
    "TikTok": """
        <path class="fill" d="M14.2 3h3.1c.2 1.7 1.2 3 2.7 3.7v3.1c-1.4 0-2.7-.4-3.8-1.2v6.2c0 3.6-2.5 6.2-6 6.2-3.2 0-5.8-2.6-5.8-5.8s2.6-5.8 5.8-5.8c.4 0 .8 0 1.2.1v3.2c-.4-.1-.7-.2-1.1-.2-1.5 0-2.7 1.2-2.7 2.7s1.2 2.7 2.7 2.7c1.7 0 2.8-1.1 2.8-3.2V3h1.1z"></path>
    """,
    "YouTube": """
        <rect x="2.5" y="5.5" width="19" height="13" rx="4"></rect>
        <path class="fill-bg" d="M10 9l6 3-6 3z"></path>
    """,
}


def _profile_shortcuts():
    links = []
    for platform, url in social_media.SOCIAL_PROFILES:
        links.append(
            '<a class="sc-social-link" href="' + html.escape(url, quote=True) +
            '" target="_blank" rel="noopener noreferrer" aria-label="Open Sports Cave ' + platform + '">' +
            '<svg viewBox="0 0 24 24" aria-hidden="true">' + " ".join(PLATFORM_ICONS[platform].split()) + '</svg>' +
            '<span>' + platform + '</span></a>'
        )
    st.markdown('<nav class="sc-social-links" aria-label="Social profiles">' + ''.join(links) + '</nav>', unsafe_allow_html=True)


def _notice():
    clear_key = st.session_state.pop("community-clear-draft", "")
    if clear_key:
        st.session_state.pop(clear_key, None)
    notice = st.session_state.pop("community-notice", "")
    if notice:
        st.success(notice)


def _done(message, *, draft_key=""):
    st.session_state["community-notice"] = message
    if draft_key:
        st.session_state["community-clear-draft"] = draft_key
    state = st.session_state.get("community-feed-state", {})
    state.pop("cache", None)
    st.session_state.pop("community-creators-cache", None)
    st.rerun()


def _creator_detail(api, store, creator):
    overview, invitation, history = st.tabs(("Overview", "Invitation", "History"))
    with overview:
        presentation.facts("Creator profile", (("Followers", f"{creator['followers']:,}"),
            ("Fit score", f"{creator['score']}/100"),
            ("Recent engagement", str(creator.get("engagement")) + "%" if creator.get("engagement") is not None else "Unavailable"),
            ("Channel", "Instagram")))
        st.text(creator["reason"])
        st.link_button("Open Instagram profile", "https://www.instagram.com/" + creator["username"] + "/", width="stretch")
        presentation.facts("Next action", (("Stage", creator["state"].replace("_", " ").title()),
            ("Action", _creator_action(creator)),))
    with history:
        presentation.facts("Collaboration history", (("Discovered", dated(creator.get("created_at"))),
            ("Last updated", dated(creator.get("updated_at"))),
            ("Invitation sent", dated(creator.get("sent_at")) if creator.get("sent_at") else "Not sent")))
        st.caption("Customer responses appear in the combined Inbox.")
    with invitation:
        _creator_invitation(api, store, creator)


def _creator_action(creator):
    return {"discovered": "Review creator", "shortlisted": "Send invitation", "sent": "Awaiting reply",
            "sending": "Check delivery", "unknown": "Check delivery", "agreed": "Arrange collaboration",
            "declined": "No action needed"}.get(creator["state"], "Review creator")


def _creator_invitation(api, store, creator):
    draft = st.text_area("Invitation", value=creator["draft"], max_chars=1000, key="community-creator-draft-" + creator["username"])
    states = ("discovered", "shortlisted", "agreed", "declined")
    state = st.selectbox("Pipeline", states, index=states.index(creator["state"]) if creator["state"] in states else 0,
                         key="community-creator-state-" + creator["username"])
    if st.button("Save collaboration", key="save-" + creator["username"], type="primary", width="stretch"):
        store.update_creator(api.user, creator["username"], state, draft)
        _done("Collaboration saved.")
    if st.button("Send saved invitation", key="invite-" + creator["username"],
                 disabled=not api.writes or not creator["fit"] or creator["state"] not in ("discovered", "shortlisted")):
        result = social_collaborations.invite(api, creator, store=store)
        if result == "waiting_for_inbound":
            st.info("This creator needs to message Sports Cave first. Use the saved draft for a personal introduction.")
        else:
            _done("Invitation " + result.replace("_", " ") + ". Replies appear in Inbox.")
    if creator["state"] in ("sending", "unknown"):
        st.warning("Delivery needs checking in Inbox before any further invitation. Automatic retries are blocked.")


def _select_creator(rows):
    selected = st.session_state.get("community-creators-grid", {}).get("selection", {}).get("rows", [])
    if selected and selected[0] < len(rows):
        st.session_state["community-selected-creator"] = rows[selected[0]]["username"]


def _collaborations(api, store):
    search, stage, find = st.columns([3, 1.2, 1.3], vertical_alignment="bottom")
    query = search.text_input("Search creators", placeholder="Search creators…", icon=":material/search:",
                              label_visibility="collapsed", key="community-creator-search").strip().casefold()
    selected_stage = stage.selectbox("Stage", ("All stages", *ledger.STATES), label_visibility="collapsed",
                                     key="community-creator-stage", format_func=lambda value: value.replace("_", " ").title())
    with find.popover("Find creators", icon=":material/add:", width="stretch"):
        st.caption("Find engaged Instagram commenters and professional accounts with 1,000–50,000 followers.")
        handles = st.text_area("Optional Instagram usernames", placeholder="One username per line")
        if st.button("Discover and assess creators", type="primary"):
            with st.spinner("Finding creators…"):
                rows, errors = social_collaborations.discover(api, handles.splitlines(), store=store)
            st.session_state.pop("community-creators-cache", None)
            st.success(f"Assessed {len(rows)} creators.")
            for error in errors:
                st.warning(error)
    cache = st.session_state.get("community-creators-cache")
    identity = (str(api.user.get("id")), api.page, api.instagram)
    if not cache or cache["identity"] != identity or time.monotonic() - cache["at"] >= 30:
        cache = {"identity": identity, "at": time.monotonic(), "rows": store.list_creators(api.user)}
        st.session_state["community-creators-cache"] = cache
    creators = cache["rows"]
    rows = [row for row in creators if (not query or query in row["username"].casefold())
            and (selected_stage == "All stages" or row["state"] == selected_stage)]
    table, details = st.columns([1.8, 1.25], gap="large")
    if rows:
        with table:
            st.dataframe([{"Creator": "@" + row["username"], "Followers": row["followers"],
                           "Stage": row["state"].replace("_", " ").title(), "Fit": "Suitable" if row["fit"] else "Review",
                           "Next action": _creator_action(row)} for row in rows], hide_index=True, width="stretch", height=505, row_height=56,
                         key="community-creators-grid", selection_mode="single-row",
                         on_select=lambda: _select_creator(rows))
            st.caption(f"{len(rows)} collaborators · select a row for details")
        selected = st.session_state.get("community-selected-creator")
        creator = next((row for row in rows if row["username"] == selected), rows[0])
        with details, st.container(key="community-detail"):
            presentation.detail_header("@" + creator["username"], f"Instagram · {creator['followers']:,} followers",
                creator["state"].replace("_", " ").title(), "green" if creator["state"] == "agreed" else "gold")
            _creator_detail(api, store, creator)
    else:
        with table:
            presentation.empty_state("No creators match" if creators else "Build your next collaboration",
                "Try another name or stage." if creators else "Find suitable sports creators, review their fit and prepare a personal invitation.")
        with details, st.container(key="community-detail"):
            presentation.empty_state("Creator details", "Select a creator to review their profile and collaboration history.")
    if os_accounts.is_admin(api.user):
        with st.popover("Automatic invitations", icon=":material/bolt:"):
            enabled = store.automation(api.user)["automation_enabled"]
            desired = st.checkbox("Automatically discover and invite eligible creators while this workspace is open",
                                  value=enabled, disabled=not api.writes or os.getenv("META_SOCIAL_AUTOMATION_ENABLED") != "1")
            if desired != enabled:
                store.automation(api.user, desired)
                st.rerun()
            st.caption("Runs every five minutes while Collaborations is open, with up to five invitations per run. "
                       "One invitation per creator; a recent inbound message is required.")
            st.caption("Meta does not support unrestricted creator search or unsolicited cold DMs through this connection. "
                       "Audience authenticity and willingness to collaborate need review.")


def _connection(api):
    toolbar, check = st.columns([3, 1])
    toolbar.caption("Facebook and Instagram · one connection, four independent checks")
    if check.button("Check Meta connection", icon=":material/sync:", type="primary", width="stretch"):
        try:
            details = api.connection()
            st.session_state["community-connection-account"] = details
            st.success("Connected to " + str(details["name"]) + (" · @" + details["instagram"] if details["instagram"] else ""))
        except CommunityError as exc:
            st.session_state.pop("community-connection-account", None)
            st.warning(str(exc))
        st.session_state["community-connection-checks"] = api.connection_checks()
        from datetime import datetime, timezone
        st.session_state["community-connection-checked-at"] = datetime.now(timezone.utc).isoformat()
    checks = st.session_state.get("community-connection-checks")
    table, details = st.columns([1.8, 1.25], gap="large")
    with table:
        if checks:
            st.dataframe(checks, hide_index=True, width="stretch", row_height=56)
            st.caption("Last checked " + dated(st.session_state.get("community-connection-checked-at")))
        else:
            presentation.empty_state("Check your Meta connection", "Run a read-only check of messages and comments for both accounts.")
        with st.expander("Fix a connection problem"):
            st.markdown("**Instagram messages**: in the Instagram app, allow access to messages under Connected tools. "
                        "The connected Page administrator also needs the Messaging task.")
            st.markdown("**Comments**: only posts and comments available to this app can be returned. "
                        "Advertising comments are checked for live ads only.")
            st.caption("Checks verify reading. Meta separately checks permission when you send a reply or moderate a comment.")
            st.link_button("Meta connection requirements", "https://developers.facebook.com/docs/graph-api/reference/page/conversations/")
    with details, st.container(key="community-detail"):
        account = st.session_state.get("community-connection-account") or {}
        available = sum(row.get("Status") == "Available" for row in checks or [])
        presentation.detail_header(account.get("name") or "Sports Cave", "Facebook + Instagram",
                                   "Checked" if checks else "Not checked", "green" if checks and available == len(checks) else "neutral")
        presentation.facts("Workspace connection", (("Features available", f"{available} of {len(checks)}" if checks else "Run check"),
            ("Sending and moderation", "Enabled" if api.writes else "Disabled"),
            ("Refresh", "Every 60 seconds"), ("Advertising posts", "Live ads only")))
        st.link_button("Open Meta Business Suite", "https://business.facebook.com/latest/inbox/all", width="stretch")


@st.fragment(run_every="60s")
def _live_panel(api, view):
    state = st.session_state.setdefault("community-feed-state", {})
    feed = CommunityFeed(api, state)
    try:
        if view == "Inbox":
            render_inbox(api, feed, _done)
        else:
            render_comments(api, feed, _done)
        if state.get("synced_at"):
            st.caption("Updated " + dated(state["synced_at"]))
    except CommunityError as exc:
        st.warning(str(exc))
    except (PermissionError, ValueError) as exc:
        st.warning(str(exc))
    except Exception as exc:
        logging.getLogger(__name__).error("community_panel_failed view=%s kind=%s", view, type(exc).__name__)
        st.warning("This view could not load. Your draft is kept; use Refresh to try again.")


@st.fragment(run_every="300s")
def _automation_panel(api, store):
    if not api.writes or os.getenv("META_SOCIAL_AUTOMATION_ENABLED") != "1":
        return
    try:
        if store.automation(api.user)["automation_enabled"]:
            result = social_collaborations.run_automation(api, store=store)
            st.caption(f"Automatic invitations: {result['sent']} sent; {result['waiting_for_inbound']} awaiting an eligible inbound conversation.")
    except CommunityError as exc:
        st.warning(str(exc))
    except Exception:
        st.warning("Collaboration automation could not complete. Check the ledger and connection before retrying.")


def render_page(user, *, store=ledger, account_store=None, api_factory=MetaCommunity):
    if not os_accounts.can_access_page(user, social_media.SOCIAL_MEDIA_ROUTE):
        st.title("Access not approved")
        return
    if not st.session_state.get("community-legacy-state-cleared"):
        # Release old content/reel blobs retained by sessions opened before the
        # replacement. Only the retired workspace namespaces are removed.
        for key in list(st.session_state):
            if str(key).startswith(("social-media-", "social-create-", "social_creator_",
                                    "smrs_", "social-reels-", "reels_")):
                del st.session_state[key]
        st.session_state["community-legacy-state-cleared"] = True
    inject_compact_page(st)
    presentation.inject()
    with st.container(key="community-shell"):
        heading, links, refresh = st.columns([1.2, 2.5, .65], vertical_alignment="center")
        heading.title("Social Media", anchor=False)
        with links:
            _profile_shortcuts()
        if refresh.button("Refresh", icon=":material/sync:", key="community-refresh", width="stretch"):
            st.session_state.get("community-feed-state", {}).pop("cache", None)
            st.session_state.pop("community-creators-cache", None)
        _notice()
        view = st.segmented_control("Social Media workspace", ("Inbox", "Comments", "Collaborations", "Connection"),
                                    default="Inbox", key="community-view", label_visibility="collapsed", required=True)
        st.divider()
        try:
            api = api_factory(user)
            # Apply account/user isolation to every tab, including diagnostics.
            state = st.session_state.setdefault("community-feed-state", {})
            previous_identity = state.get("identity")
            CommunityFeed(api, state)
            if previous_identity and previous_identity != state["identity"]:
                for key in ("community-connection-account", "community-connection-checks", "community-connection-checked-at",
                            "community-selected-thread", "community-selected-comment", "community-selected-creator"):
                    st.session_state.pop(key, None)
                for key in list(st.session_state):
                    if str(key).startswith(("community-reply-", "community-comment-reply-", "community-message-pages-",
                                            "community-comment-open-", "community-delete-confirm-", "community-creator-draft-",
                                            "community-creator-state-")) or key in ("community-inbox-grid", "community-creators-grid",
                                                                                 "community-creators-cache"):
                        st.session_state.pop(key, None)
            if view in ("Inbox", "Comments"):
                _live_panel(api, view)
            elif view == "Collaborations":
                _collaborations(api, store)
                _automation_panel(api, store)
            else:
                _connection(api)
        except (CommunityError, PermissionError, ValueError) as exc:
            st.warning(str(exc))
        except Exception as exc:
            logging.getLogger(__name__).error("community_workspace_failed view=%s kind=%s", view, type(exc).__name__)
            st.warning("The community workspace could not load. Refresh to retry.")
