"""Facebook and Instagram community workspace in the existing Social Media tab."""
import html
import os
from datetime import datetime, timezone

import streamlit as st

import os_accounts
import social_media
from meta_social import CommunityError, MetaCommunity, reply_open
import social_collaborations
import social_community_store as ledger


def _profile_shortcuts():
    url = dict(social_media.SOCIAL_PROFILES)["Instagram"]
    st.markdown(
        '<a class="sc-instagram" href="' + html.escape(url, quote=True) +
        '" target="_blank" rel="noopener noreferrer" aria-label="Open Sports Cave Instagram">'
        '<svg viewBox="0 0 24 24" width="23" height="23" fill="none" stroke="currentColor" stroke-width="1.8">'
        '<rect x="3" y="3" width="18" height="18" rx="5"></rect><circle cx="12" cy="12" r="4"></circle>'
        '<circle cx="17.4" cy="6.7" r="1"></circle></svg> Instagram · @sportscaveshop ↗</a>',
        unsafe_allow_html=True,
    )


def _notice():
    notice = st.session_state.pop("community-notice", "")
    if notice:
        st.success(notice)


def _done(message):
    st.session_state["community-notice"] = message
    st.rerun()


def _next(key, page):
    left, right = st.columns(2)
    if left.button("First page", key=key + "-first", disabled=not st.session_state.get(key)):
        st.session_state[key] = ""
        st.rerun()
    if right.button("Next page", key=key + "-next", disabled=not page.get("after")):
        st.session_state[key] = page["after"]
        st.rerun()


def _peer(thread, api):
    people = [p for p in (thread.get("participants") or {}).get("data", [])
              if str(p.get("id")) not in {api.page, api.instagram}]
    return ", ".join(p.get("name") or p.get("username") or p.get("id", "") for p in people) or thread["id"]


def _inbox(api, platform):
    page = api.conversations(platform, after=st.session_state.get("community-threads-" + platform, ""))
    threads = page["data"]
    st.caption("Updated " + datetime.now(timezone.utc).strftime("%H:%M UTC") +
               " · refreshes every 60 seconds while open. Unread counts come from Meta.")
    if not threads:
        st.info("No conversations returned for this account.")
        return
    st.metric("Unread in this page", sum(int(row.get("unread_count") or 0) for row in threads))
    ids = [row["id"] for row in threads]
    mapping = {row["id"]: row for row in threads}
    key = "community-thread-" + platform
    if st.session_state.get(key) not in ids:
        st.session_state.pop(key, None)
    thread_id = st.selectbox("Conversation", ids, format_func=lambda value: _peer(mapping[value], api), key=key)
    _next("community-threads-" + platform, page)
    messages = api.messages(platform, thread_id)
    with st.container(height=430, border=True):
        for message in reversed(messages["data"]):
            sender = message.get("from") or {}
            outgoing = str(sender.get("id")) in {api.page, api.instagram}
            with st.chat_message("assistant" if outgoing else "user"):
                st.caption(("Sports Cave" if outgoing else sender.get("name") or "Customer") +
                           " · " + str(message.get("created_time", "")))
                st.text(message.get("message") or "[Attachment or unsupported message]")
                if message.get("attachments"):
                    st.caption("Attachment included · view the original in Business Suite.")
    if messages.get("after"):
        if st.button("Load older messages", key="older-" + platform + thread_id):
            st.session_state["older-cursor-" + thread_id] = messages["after"]
        if st.session_state.get("older-cursor-" + thread_id):
            older = api.messages(platform, thread_id, after=st.session_state["older-cursor-" + thread_id])
            for message in reversed(older["data"]):
                st.text((message.get("message") or "[Attachment]"))
            if older.get("after") and st.button("Earlier messages", key="earlier-" + thread_id):
                st.session_state["older-cursor-" + thread_id] = older["after"]
                st.rerun()
    can_send = (api.writes and mapping[thread_id].get("is_owner") is not False
                and reply_open(messages["data"], api.owner(platform)))
    if not can_send:
        st.caption("Replies require enabled sending and a customer message within the last 24 hours.")
    with st.form("reply-" + platform + thread_id, clear_on_submit=True):
        text = st.text_area("Reply", max_chars=1000)
        if st.form_submit_button("Send reply", disabled=not can_send, type="primary"):
            api.send(platform, thread_id, text)
            _done("Reply sent. The conversation has been refreshed.")


def _comments(api, platform):
    # Notifications cover the latest ten owned posts, with bounded API reads.
    posts = api.posts(platform, after=st.session_state.get("community-posts-" + platform, ""))
    post_map = {p["id"]: p for p in posts["data"]}
    if not post_map:
        st.info("No published posts returned for this account.")
        return
    notifications = []
    for post in posts["data"][:10]:
        try:
            for comment in api.comments(platform, post["id"])["data"]:
                notifications.append((post, comment))
        except CommunityError:
            st.warning("Comments for one post could not load. Other available comments are shown.")
    notifications.sort(key=lambda pair: str(pair[1].get("created_time") or pair[1].get("timestamp") or ""), reverse=True)
    st.caption("Recent activity · latest 10 posts on this page, up to 30 comments per post. Refreshes every 60 seconds.")
    with st.expander(f"Recent comment notifications ({len(notifications)})", expanded=bool(notifications)):
        for post, comment in notifications[:30]:
            author = comment.get("username") or (comment.get("from") or {}).get("name") or "Customer"
            st.text(f"{author}: {comment.get('text') or comment.get('message') or '[Comment]'}")
            if st.button("Open comment", key="notification-" + platform + comment["id"]):
                st.session_state["community-post-" + platform] = post["id"]
                st.session_state["community-comment-" + platform + post["id"]] = comment["id"]
                st.rerun()
    key = "community-post-" + platform
    if st.session_state.get(key) not in post_map:
        st.session_state.pop(key, None)
    post_id = st.selectbox("Post", list(post_map), key=key,
                           format_func=lambda value: (post_map[value].get("message") or post_map[value].get("caption") or value)[:120])
    _next("community-posts-" + platform, posts)
    post = post_map[post_id]
    link = post.get("permalink") or post.get("permalink_url")
    if link and str(link).startswith("https://"):
        st.link_button("Open original post", link)
    page = api.comments(platform, post_id, after=st.session_state.get("community-comments-" + post_id, ""))
    comments = {row["id"]: row for row in page["data"]}
    if not comments:
        st.info("No comments on this page of the selected post.")
        return
    key = "community-comment-" + platform + post_id
    if st.session_state.get(key) not in comments:
        st.session_state.pop(key, None)
    comment_id = st.selectbox("Comment", list(comments), key=key,
                              format_func=lambda value: (comments[value].get("text") or comments[value].get("message") or value)[:160])
    _next("community-comments-" + post_id, page)
    st.text(comments[comment_id].get("text") or comments[comment_id].get("message") or "[Comment]")
    with st.form("comment-reply-" + platform + comment_id, clear_on_submit=True):
        text = st.text_area("Public reply", max_chars=1000)
        if st.form_submit_button("Reply to comment", disabled=not api.writes):
            api.moderate(platform, post_id, comment_id, "reply", text)
            _done("Public reply sent.")
    actions = ("like", "unlike", "hide", "unhide") if platform == "Facebook" else ("hide", "unhide")
    columns = st.columns(len(actions))
    for column, action in zip(columns, actions):
        if column.button(action.title(), key=action + platform + comment_id, disabled=not api.writes):
            api.moderate(platform, post_id, comment_id, action)
            _done("Comment updated.")
    if platform == "Instagram":
        st.caption("Use the original Instagram post to like a comment; this integration supports replies, hide and delete.")
    confirm = st.checkbox("Confirm permanent deletion of this comment", key="delete-confirm-" + comment_id)
    if st.button("Delete comment", key="delete-" + comment_id, disabled=not (confirm and api.writes)):
        api.moderate(platform, post_id, comment_id, "delete")
        _done("Comment deleted.")


def _collaborations(api, store):
    st.subheader("Find your next Sports Cave collaborator")
    st.caption("Discover engaged Instagram commenters and assess professional accounts with 1,000–50,000 followers. "
               "Sports fit and engagement are signals for review; audience location and willingness to collaborate are unverified.")
    handles = st.text_area("Optional Instagram usernames", placeholder="One username per line")
    if st.button("Discover and assess creators", type="primary"):
        rows, errors = social_collaborations.discover(api, handles.splitlines(), store=store)
        st.success(f"Assessed {len(rows)} creators.")
        for error in errors:
            st.warning(error)
    creators = store.list_creators(api.user)
    for creator in creators:
        with st.expander(f"@{creator['username']} · {creator['followers']:,} followers · {creator['state']}"):
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
    if not creators:
        st.info("No saved creators yet. Discover commenters or enter professional account usernames above.")
    st.info("Meta does not provide unrestricted creator search or cold automated DMs. Invitations can be sent "
            "when the creator has an eligible inbound Instagram conversation. Their replies appear in Inbox.")
    if os_accounts.is_admin(api.user):
        enabled = store.automation(api.user)["automation_enabled"]
        desired = st.checkbox("Automatically discover and invite eligible creators while this workspace is open",
                              value=enabled, disabled=not api.writes or os.getenv("META_SOCIAL_AUTOMATION_ENABLED") != "1")
        if desired != enabled:
            store.automation(api.user, desired)
            st.rerun()
        st.caption("When enabled, runs every five minutes while Collaborations is open. Up to five invitations per run; "
                   "one invitation per creator. A recent inbound message is always required.")


def _connection(api):
    st.subheader("Meta connection")
    st.caption("Uses the existing Facebook Page and its linked Instagram professional account.")
    if st.button("Check Meta connection"):
        details = api.connection()
        st.success("Connected to " + str(details["name"]) + (" · @" + details["instagram"] if details["instagram"] else ""))
    st.text("Sending and moderation: " + ("enabled" if api.writes else "disabled"))
    if os_accounts.is_admin(api.user):
        st.code("META_FACEBOOK_PAGE_ID\nMETA_INSTAGRAM_ACTOR_ID\nMETA_PAGE_ACCESS_TOKEN\nMETA_SOCIAL_DISCOVERY_TOKEN\nMETA_SOCIAL_WRITES_ENABLED=0\nMETA_SOCIAL_AUTOMATION_ENABLED=0", language="text")
        st.caption("A Page token needs pages_messaging, pages_manage_metadata, pages_read_engagement, pages_read_user_content, "
                   "pages_manage_engagement, instagram_basic, instagram_manage_messages and instagram_manage_comments. "
                   "Business Discovery uses a separate Facebook User token. Advanced access/App Review may be required. "
                   "Configure tokens securely on the server. Never paste tokens into this page.")
    st.link_button("Open Meta Business Suite", "https://business.facebook.com/latest/inbox/all")


@st.fragment(run_every="60s")
def _live_panel(api, platform, view):
    try:
        if view == "Inbox":
            _inbox(api, platform)
        else:
            _comments(api, platform)
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
    st.markdown("""<style>
        .sc-community{border-bottom:1px solid #d8d4ca;padding:0 0 14px;margin-bottom:14px}
        .sc-community h1{font-size:1.8rem;margin:0}.sc-community p{color:#767166;margin:4px 0 0}
        .sc-instagram{display:inline-flex;align-items:center;gap:9px;border:1px solid #dedbd3;
        border-radius:8px;padding:10px 14px;text-decoration:none;color:inherit!important;margin-bottom:16px}
        </style><div class="sc-community"><h1>Social Media</h1>
        <p>Your community. Every conversation, in one place.</p></div>""", unsafe_allow_html=True)
    _profile_shortcuts()
    _notice()
    view = st.segmented_control("Social Media workspace", ("Inbox", "Comments", "Collaborations", "Connection"),
                                default="Inbox", key="community-view")
    try:
        api = api_factory(user)
        if view in ("Inbox", "Comments"):
            platform = st.radio("Account", ("Facebook", "Instagram"), horizontal=True)
            st.button("Refresh", key="community-refresh")
            _live_panel(api, platform, view)
            st.link_button("Open Meta Business Suite", "https://business.facebook.com/latest/inbox/all")
        elif view == "Collaborations":
            _collaborations(api, store)
            _automation_panel(api, store)
        else:
            _connection(api)
    except (CommunityError, PermissionError, ValueError) as exc:
        st.warning(str(exc))
    except Exception:
        st.warning("The collaboration ledger is unavailable. Provision its schema and check the server connection.")
