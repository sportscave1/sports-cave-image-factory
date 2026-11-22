"""Facebook and Instagram community workspace in the existing Social Media tab."""
import html
import os

import streamlit as st

import os_accounts
import social_media
from meta_social import CommunityError, MetaCommunity
from social_community_feed import CommunityFeed
from social_community_views import render_inbox, render_comments, dated
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
    st.rerun()


def _creator_detail(api, store, creator):
    st.link_button("Instagram profile", "https://www.instagram.com/" + creator["username"] + "/")
    st.text(creator["reason"])
    st.caption(f"Fit score: {creator['score']}/100 · recent post engagement: {creator.get('engagement') if creator.get('engagement') is not None else 'unavailable'}%")
    st.caption("Suitable follower range and sports interests" if creator["fit"] else "Outside the current collaboration criteria")
    draft = st.text_area("Invitation", value=creator["draft"], max_chars=1000, key="draft-" + creator["username"])
    states = ("discovered", "shortlisted", "agreed", "declined")
    state = st.selectbox("Pipeline", states, index=states.index(creator["state"]) if creator["state"] in states else 0,
                         key="state-" + creator["username"])
    if st.button("Save collaboration", key="save-" + creator["username"]):
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
    heading, find = st.columns([3, 1])
    heading.subheader("Collaborations")
    with find.popover("Find creators", icon=":material/person_search:"):
        st.caption("Find engaged Instagram commenters and professional accounts with 1,000–50,000 followers.")
        handles = st.text_area("Optional Instagram usernames", placeholder="One username per line")
        if st.button("Discover and assess creators", type="primary"):
            with st.spinner("Finding creators…"):
                rows, errors = social_collaborations.discover(api, handles.splitlines(), store=store)
            st.success(f"Assessed {len(rows)} creators.")
            for error in errors:
                st.warning(error)
    creators = store.list_creators(api.user)
    search, stage = st.columns([3, 1])
    query = search.text_input("Search creators", placeholder="Search creators…", label_visibility="collapsed").strip().casefold()
    selected_stage = stage.selectbox("Stage", ("All stages", *ledger.STATES), label_visibility="collapsed")
    rows = [row for row in creators if (not query or query in row["username"].casefold())
            and (selected_stage == "All stages" or row["state"] == selected_stage)]
    if rows:
        table, details = st.columns([2, 1.25], gap="medium")
        with table:
            st.dataframe([{"Creator": "@" + row["username"], "Followers": row["followers"],
                           "Stage": row["state"].replace("_", " ").title(), "Fit": "Suitable" if row["fit"] else "Review",
                           "Score": row["score"]} for row in rows], hide_index=True, width="stretch", height=430,
                         key="community-creators-grid", selection_mode="single-row",
                         on_select=lambda: _select_creator(rows))
            st.caption(f"{len(rows)} collaborators · select a row for details")
        selected = st.session_state.get("community-selected-creator")
        creator = next((row for row in rows if row["username"] == selected), rows[0])
        with details, st.container(border=True):
            st.markdown("**@" + creator["username"] + "**")
            st.caption(creator["state"].replace("_", " ").title())
            _creator_detail(api, store, creator)
    else:
        st.info("No creators match these filters." if creators else "No collaborations yet. Use Find creators to get started.")
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
    st.subheader("Meta connection")
    st.caption("One workspace for the Facebook Page and linked Instagram account. Check each feature independently.")
    if st.button("Check Meta connection"):
        try:
            details = api.connection()
            st.success("Connected to " + str(details["name"]) + (" · @" + details["instagram"] if details["instagram"] else ""))
        except CommunityError as exc:
            st.warning(str(exc))
        st.session_state["community-connection-checks"] = api.connection_checks()
    checks = st.session_state.get("community-connection-checks")
    if checks:
        st.dataframe(checks, hide_index=True, width="stretch")
    with st.expander("Fix a connection problem"):
        st.markdown("**Instagram messages**: the Page connection needs `instagram_basic`, `instagram_manage_messages` "
                    "and `pages_manage_metadata`, a Page administrator with the Messaging task, and a verified Meta business. "
                    "Check Instagram’s connected tools settings allow access to messages. Missing permissions require reconnecting through Meta.")
        st.markdown("**Comments**: check `pages_read_engagement`, `pages_read_user_content` and `pages_manage_engagement` "
                    "for Facebook, and `instagram_manage_comments` for Instagram. The connection can only return posts and comments Meta permits this app to read.")
        st.caption("Checks verify reading only. Meta separately checks permission to send, reply, hide or delete when you use those actions.")
        st.link_button("Meta connection requirements", "https://developers.facebook.com/docs/graph-api/reference/page/conversations/")
    st.caption("Sending and moderation: " + ("enabled" if api.writes else "disabled"))
    st.link_button("Open Meta Business Suite", "https://business.facebook.com/latest/inbox/all")


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
    st.markdown("""<style>
[data-testid="stMainBlockContainer"]:has(.st-key-community-shell){padding-left:24px!important;padding-right:24px!important;max-width:100%!important}
.st-key-community-shell{--sc-social-gold:#ae8126}
.st-key-community-shell [data-testid="stVerticalBlock"]{gap:.6rem!important}
.st-key-community-shell [data-testid="stTextInput"] input{font-size:14px}
.st-key-community-shell [data-testid="stForm"]{background:#fff}
.st-key-community-shell [data-testid="stButton"] button{background:#fff!important;border:1px solid #deddd7!important;color:#27251f!important;min-height:34px!important}
.st-key-community-shell [data-testid="stFormSubmitButton"] button{background:#ae8126!important;border-color:#ae8126!important;color:#fff!important}
.st-key-community-shell [data-testid="stAlert"]{padding:8px 12px;font-size:13px}
.sc-message{padding:10px 13px;margin:0 0 8px;border-radius:8px;max-width:88%;font-size:14px;line-height:1.5;overflow-wrap:anywhere;white-space:normal}
.sc-message.incoming{background:#f2f3f5;margin-right:auto}.sc-message.outgoing{background:#f6eedc;margin-left:auto}
.sc-message-meta{font-size:11px;color:#747169;margin-bottom:5px}
.st-key-community-shell h1{font-size:1.65rem!important;line-height:1.2!important;padding:0!important;margin:0!important}
.st-key-community-shell [data-testid="stHeading"]{margin:0!important}
.sc-social-links{display:flex;justify-content:flex-end;align-items:center;gap:7px;flex-wrap:wrap;margin:0 0 10px}
.sc-social-link{display:inline-flex;align-items:center;gap:6px;border:1px solid #e4e1da;border-radius:7px;padding:7px 9px;color:#222!important;text-decoration:none!important;font-size:12px;white-space:nowrap;background:white}
.sc-social-link:hover{border-color:#b88c32;background:#fcf9f1}
.sc-social-link svg{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.sc-social-link svg .fill{fill:currentColor;stroke:none}.sc-social-link svg .fill-bg{fill:white;stroke:none}
.sc-social-link[aria-label$="Facebook"] svg{color:#1877f2}.sc-social-link[aria-label$="Instagram"] svg{color:#dc287b}
.sc-social-link[aria-label$="Pinterest"] svg,.sc-social-link[aria-label$="YouTube"] svg{color:#d0212b}
.st-key-community-shell [data-testid="stBaseButton-primary"]{background:#ae8126;border-color:#ae8126;color:white}
.st-key-community-shell [data-testid="stExpander"]{border-color:#e7e3db;border-radius:6px}
.st-key-community-shell [data-testid="stExpander"] summary{font-size:13px;min-height:43px}
.st-key-community-shell [data-testid="stButtonGroup"]{margin-bottom:5px}
.st-key-community-shell [data-testid="stButtonGroup"] [role="radio"]{background:#fff!important;border-color:#deddd7!important;color:#292720!important;min-height:34px!important;font-size:14px!important}
.st-key-community-shell [data-testid="stButtonGroup"] [aria-checked="true"]{background:#ecdab2!important;border-color:#d1ac5e!important;color:#191713!important;font-weight:600!important}
@media(max-width:760px){.sc-social-links{justify-content:flex-start;gap:5px}.sc-social-link{padding:6px 8px}.st-key-community-shell h1{font-size:1.45rem!important}}
</style>""", unsafe_allow_html=True)
    with st.container(key="community-shell"):
        heading, links = st.columns([1, 3], vertical_alignment="center")
        heading.title("Social Media", anchor=False)
        with links:
            _profile_shortcuts()
        _notice()
        navigation, refresh = st.columns([5, 1], vertical_alignment="center")
        with navigation:
            view = st.segmented_control("Social Media workspace", ("Inbox", "Comments", "Collaborations", "Connection"),
                                        default="Inbox", key="community-view", label_visibility="collapsed")
        if refresh.button("Refresh", icon=":material/sync:", key="community-refresh", width="stretch"):
            st.session_state.get("community-feed-state", {}).pop("cache", None)
        try:
            api = api_factory(user)
            if view in ("Inbox", "Comments"):
                _live_panel(api, view)
            elif view == "Collaborations":
                _collaborations(api, store)
                _automation_panel(api, store)
            else:
                _connection(api)
        except (CommunityError, PermissionError, ValueError) as exc:
            st.warning(str(exc))
        except Exception:
            st.warning("The community workspace could not load. Refresh to retry.")
