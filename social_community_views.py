"""Compact merged inbox and lazy comment rows for the Social Media page."""
import re
import html
from datetime import datetime

import streamlit as st

from meta_social import reply_open
from social_community_feed import timestamp
from social_media import SYDNEY_TZ
from social_community_presentation import detail_header, empty_state, facts


def dated(value):
    if isinstance(value, datetime):
        value = value.isoformat()
    if not timestamp(value):
        return "Date unavailable"
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(SYDNEY_TZ).strftime("%d %b %Y · %I:%M %p %Z")


def label_text(value, limit=110):
    text = " ".join(str(value or "").split())[:limit]
    return re.sub(r"([\\`*_[\]{}()<>!|#])", r"\\\1", text)


def author(row):
    return row.get("username") or (row.get("from") or {}).get("name") or "Name not returned by Meta"


def peer(thread, api):
    people = [p for p in (thread.get("participants") or {}).get("data", [])
              if str(p.get("id")) not in {api.page, api.instagram}]
    return ", ".join(p.get("name") or p.get("username") or p.get("id", "") for p in people) or thread["id"]


def _errors(snapshot):
    for error in snapshot["errors"]:
        # A verified account with a few unavailable ad objects is a partial
        # history result, not a disconnected inbox. Keep its details available.
        unavailable = re.match(r"Instagram: (\d+) advertising posts could not be read", error)
        if unavailable and "individual advertising media are unavailable" in error:
            with st.expander(unavailable[1] + " Instagram advertising posts unavailable from Meta"):
                st.caption(error)
        else:
            st.warning(error)


def _select_thread(rows):
    selection = st.session_state.get("community-inbox-grid", {}).get("selection", {}).get("rows", [])
    if selection and selection[0] < len(rows):
        row = rows[selection[0]]
        st.session_state["community-selected-thread"] = (row["platform"], row["id"])


def _messages(api, feed, thread, done):
    platform, thread_id = thread["platform"], thread["id"]
    suffix = platform + "-" + thread_id
    detail_header(peer(thread, api), platform + " · " + dated(thread.get("updated_time")),
                  "Unread" if thread.get("unread_count") else "Conversation",
                  "gold" if thread.get("unread_count") else "neutral")
    first = feed.read("messages", platform, thread_id)
    messages = {row["id"]: row for row in first["data"]}
    after = first.get("after")
    cursors = st.session_state.setdefault("community-message-pages-" + suffix, [])
    for cursor in cursors:
        page = feed.read("messages", platform, thread_id, after=cursor)
        messages.update((row["id"], row) for row in page["data"])
        after = page.get("after")
    if after and st.button("Older messages", key="community-older-" + suffix):
        if after not in cursors:
            cursors.append(after)
        st.rerun()
    with st.container(height=370, border=True):
        for message in sorted(messages.values(), key=lambda row: timestamp(row.get("created_time"))):
            outgoing = str((message.get("from") or {}).get("id")) in {api.page, api.instagram}
            text = str(message.get("message") or "[Attachment]")
            # Messenger includes a Page comment referral as a system event. Keep
            # its context and link, without dumping a long tracking URL in chat.
            referral = text.startswith("You are responding to a user comment to a post on your Page.")
            links = re.findall(r"https://(?:www\.)?facebook\.com/[^\s)]+", text) if referral else []
            if referral:
                st.caption("Conversation started from a Facebook comment")
                if links:
                    st.link_button("View original comment", links[0])
                continue
            name = "Sports Cave" if outgoing else author(message)
            markup = ('<div class="sc-message ' + ('outgoing' if outgoing else 'incoming') + '"><div class="sc-message-meta">' +
                      html.escape(name + " · " + dated(message.get("created_time"))) + '</div><div>' +
                      html.escape(text).replace('\n', '<br>') + '</div></div>')
            st.markdown(markup, unsafe_allow_html=True)
            if message.get("attachments"):
                st.caption("Attachment · open in Business Suite")
    can_send = (api.writes and thread.get("is_owner") is not False
                and reply_open(messages.values(), api.owner(platform)))
    draft_key = "community-reply-" + suffix
    with st.form("community-reply-form-" + suffix):
        text = st.text_area("Reply", max_chars=1000, key=draft_key, height=80,
                            placeholder="Write a reply…", label_visibility="collapsed")
        if st.form_submit_button("Send reply", disabled=not can_send, type="primary", width="stretch"):
            api.send(platform, thread_id, text)
            done("Reply sent.", draft_key=draft_key)
    if not can_send:
        reason = ("Sending is disabled for this environment." if not api.writes else
                  "Another app controls this conversation." if thread.get("is_owner") is False else
                  "The 24-hour reply window has closed. The customer needs to message again before an API reply can be sent.")
        st.caption(reason)
        st.link_button("Open in Business Suite", "https://business.facebook.com/latest/inbox/all", key="suite-" + suffix)


def render_inbox(api, feed, done):
    snapshot = feed.threads()
    _errors(snapshot)
    search, status = st.columns([3, 1])
    query = search.text_input("Search inbox", placeholder="Search conversations…", key="community-inbox-search",
                              icon=":material/search:", label_visibility="collapsed").strip().casefold()
    unread_only = status.selectbox("Conversation status", ("All conversations", "Unread"),
                                  key="community-inbox-filter", label_visibility="collapsed") == "Unread"
    rows = [row for row in snapshot["items"] if (not query or query in (peer(row, api) + " " + row["platform"]).casefold())
            and (not unread_only or int(row.get("unread_count") or 0) > 0)]
    unread = sum(int(row.get("unread_count") or 0) for row in snapshot["items"])
    st.caption(f"{len(rows)} conversations · {unread} unread · Facebook + Instagram")
    if rows:
        left, right = st.columns([1.55, 1.3], gap="large")
        with left:
            st.dataframe([{"Customer": peer(row, api), "Channel": row["platform"],
                           "Updated": dated(row.get("updated_time")), "Unread": int(row.get("unread_count") or 0)}
                          for row in rows], hide_index=True, height=505, width="stretch", row_height=52,
                         key="community-inbox-grid", selection_mode="single-row",
                         on_select=lambda: _select_thread(rows))
            st.caption("Select a conversation to read and reply.")
        selected = st.session_state.get("community-selected-thread")
        thread = next((row for row in rows if (row["platform"], row["id"]) == selected), rows[0])
        with right, st.container(key="community-detail"):
            _messages(api, feed, thread, done)
    elif not snapshot["errors"]:
        empty_state("No conversations match" if query or unread_only else "Your inbox is clear",
                    "Try another name or change the unread filter." if query or unread_only else
                    "Facebook and Instagram messages will appear here together.")
    if any(snapshot["more"].values()) and st.button("Load more conversations", key="community-more-threads"):
        feed.more_threads(snapshot)
        st.rerun()


def comment_context(row):
    if row["platform"] == "Instagram" and row["post"].get("ad_id"):
        return {"ad_id": row["post"]["ad_id"],
                "comment_edge": (row["post"].get("comments") or {}).get("comment_edge", "")}
    return {}


def _comment_actions(api, row, done):
    """Only the selected editor is built; every card's actions stay visible."""
    platform, post_id, comment_id = row["platform"], row["post"]["id"], row["id"]
    suffix = platform + "-" + comment_id
    context = comment_context(row)
    actions = st.columns([1, 1.2, 1, 1, 1.2])
    actions[0].button("Reply", icon=":material/reply:", key="comment-select-" + suffix, width="stretch",
                      on_click=lambda: st.session_state.__setitem__("community-selected-comment", (platform, comment_id)))
    if platform == "Facebook":
        action = "unlike" if row.get("user_likes") else "like"
        if actions[1].button(action.title(), icon=":material/thumb_up:", key="like-" + suffix,
                             disabled=not api.writes, width="stretch"):
            api.moderate(platform, post_id, comment_id, action, **context)
            done("Like removed." if action == "unlike" else "Comment liked.")
    else:
        from social_media import SOCIAL_PROFILES
        link = row["post"].get("permalink") or dict(SOCIAL_PROFILES)["Instagram"]
        actions[1].link_button("Like in Instagram", link, width="stretch")
    action = "unhide" if row.get("is_hidden") or row.get("hidden") else "hide"
    if actions[2].button(action.title(), key="hide-" + suffix, disabled=not api.writes, width="stretch"):
        api.moderate(platform, post_id, comment_id, action, **context)
        done("Comment restored." if action == "unhide" else "Comment hidden.")
    actions[3].button("Delete", icon=":material/delete:", key="comment-delete-" + suffix,
                      disabled=not api.writes, width="stretch",
                      on_click=lambda: st.session_state.__setitem__("community-selected-delete", (platform, comment_id)))
    link = row["post"].get("permalink") or row["post"].get("permalink_url")
    if str(link or "").startswith("https://"):
        actions[4].link_button("Open post", link, width="stretch")
    if st.session_state.get("community-selected-delete") == (platform, comment_id):
        confirm = st.checkbox("Confirm permanent deletion", key="community-delete-confirm-" + suffix)
        remove, cancel = st.columns(2)
        if remove.button("Delete comment", key="delete-" + suffix, disabled=not (api.writes and confirm), type="primary"):
            api.moderate(platform, post_id, comment_id, "delete", **context)
            done("Comment deleted.")
        if cancel.button("Cancel deletion", key="delete-cancel-" + suffix):
            st.session_state.pop("community-selected-delete", None)
            st.rerun()
    if st.session_state.get("community-selected-comment") == (platform, comment_id):
        draft_key = "community-comment-reply-" + suffix
        with st.form("community-comment-form-" + suffix):
            text = st.text_area("Public reply", max_chars=1000, key=draft_key, height=80,
                                placeholder="Reply to this comment…", label_visibility="collapsed")
            if st.form_submit_button("Send public reply", icon=":material/reply:", type="primary",
                                     disabled=not api.writes, width="stretch"):
                api.moderate(platform, post_id, comment_id, "reply", text, **context)
                done("Reply sent.", draft_key=draft_key)


def _comment_body(row):
    text = row.get("text") or row.get("message")
    attachment = row.get("attachment") or {}
    if text:
        st.markdown('<div class="sc-comment-body">' + html.escape(str(text)).replace('\n', '<br>') + '</div>', unsafe_allow_html=True)
    elif attachment:
        st.caption("Photo, sticker or attachment comment")
    else:
        st.caption("Meta did not return this comment's text. Open the original post to view it.")
    image = ((attachment.get("media") or {}).get("image") or {}).get("src")
    if str(image or "").startswith("https://"):
        st.markdown('<img class="sc-comment-attachment" loading="lazy" alt="Comment attachment" src="' +
                    html.escape(image, quote=True) + '">', unsafe_allow_html=True)


def render_comments(api, feed, done):
    # First paint checks one organic batch per channel. Scrolling performs
    # bounded additional reads instead of a long empty-history scan up front.
    for platform in ("Facebook", "Instagram"):
        feed.state.setdefault("post_scan_targets", {}).setdefault(platform, 1)
    snapshot = feed.comments()
    _errors(snapshot)
    query = st.text_input("Search comments", placeholder="Search comments or people…", key="community-comment-search",
                          icon=":material/search:", label_visibility="collapsed").strip().casefold()
    rows = [row for row in snapshot["items"] if not query or query in
            (author(row) + " " + str(row.get("text") or row.get("message") or "") + " " + row["platform"]).casefold()]
    visible = st.session_state.get("community-comment-visible", 40)
    st.caption(f"{min(len(rows), visible)} comments shown · newest loaded first · live ads + organic posts · Sydney time")
    for row in rows[:visible]:
        with st.container(border=True, key="community-comment-card-" + row["platform"] + "-" + row["id"]):
            detail_header(author(row), row["platform"] + " · " + dated(row.get("created_time") or row.get("timestamp")),
                          "Live ad" if row["post"].get("advertising") else "Organic post", "gold")
            _comment_body(row)
            post_text = row["post"].get("message") or row["post"].get("caption")
            if post_text:
                st.caption("Post: " + " ".join(str(post_text).split())[:200])
            st.caption(f"{int(row.get('like_count') or 0)} likes")
            _comment_actions(api, row, done)
    pending = bool(snapshot["more_comments"] or any(snapshot["more_posts"].values()) or snapshot.get("more_ads"))
    if not rows and not snapshot["errors"]:
        st.info("No comments match the loaded results." if query else
                "No comments in the posts checked so far. Scroll down to check more posts." if pending else
                "No comments were returned for the posts available to this connection.")
    st.caption(f"{snapshot.get('posts_scanned', 0)} posts checked · Facebook and Instagram together")
    more = len(rows) > visible or pending
    if more:
        from social_comment_scroll import scroll_request
        token = str(st.session_state.get("community-comment-generation", 0))
        requested = scroll_request(token, not snapshot["errors"])
        manual = st.button("Load older comments", key="community-more-comments", icon=":material/arrow_downward:")
        if manual or (requested and st.session_state.get("community-comment-consumed") != token):
            st.session_state["community-comment-consumed"] = token
            if len(rows) <= visible:
                feed.more_comments(snapshot, scan_empty=False)
            st.session_state["community-comment-visible"] = visible + 40
            st.session_state["community-comment-generation"] = int(token) + 1
            st.rerun()
    elif rows:
        st.caption("You're up to date with the loaded posts.")
