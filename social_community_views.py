"""Compact merged inbox and lazy comment rows for the Social Media page."""
import re
from datetime import datetime

import streamlit as st

from meta_social import reply_open
from social_community_feed import timestamp
from social_media import SYDNEY_TZ


def dated(value):
    if not timestamp(value):
        return "Date unavailable"
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(SYDNEY_TZ).strftime("%d %b %Y · %I:%M %p %Z")


def label_text(value, limit=110):
    text = " ".join(str(value or "").split())[:limit]
    return re.sub(r"([\\`*_[\]{}()<>!|#])", r"\\\1", text)


def author(row):
    return row.get("username") or (row.get("from") or {}).get("name") or "Customer"


def peer(thread, api):
    people = [p for p in (thread.get("participants") or {}).get("data", [])
              if str(p.get("id")) not in {api.page, api.instagram}]
    return ", ".join(p.get("name") or p.get("username") or p.get("id", "") for p in people) or thread["id"]


def _errors(snapshot):
    for error in snapshot["errors"]:
        st.warning(error)


def _select_thread(rows):
    selection = st.session_state.get("community-inbox-grid", {}).get("selection", {}).get("rows", [])
    if selection and selection[0] < len(rows):
        row = rows[selection[0]]
        st.session_state["community-selected-thread"] = (row["platform"], row["id"])


def _messages(api, feed, thread, done):
    platform, thread_id = thread["platform"], thread["id"]
    suffix = platform + "-" + thread_id
    st.markdown("**" + label_text(peer(thread, api)) + "**")
    st.caption(platform + " · " + dated(thread.get("updated_time")))
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
    with st.container(height=350, border=True):
        for message in sorted(messages.values(), key=lambda row: timestamp(row.get("created_time"))):
            outgoing = str((message.get("from") or {}).get("id")) in {api.page, api.instagram}
            with st.chat_message("assistant" if outgoing else "user"):
                st.caption(("Sports Cave" if outgoing else author(message)) + " · " + dated(message.get("created_time")))
                st.text(message.get("message") or "[Attachment]")
                if message.get("attachments"):
                    st.caption("Attachment · open in Business Suite")
    can_send = (api.writes and thread.get("is_owner") is not False
                and reply_open(messages.values(), api.owner(platform)))
    draft_key = "community-reply-" + suffix
    with st.form("community-reply-form-" + suffix):
        text = st.text_area("Reply", max_chars=1000, key=draft_key, height=80,
                            placeholder="Write a reply…", label_visibility="collapsed")
        if st.form_submit_button("Send reply", disabled=not can_send, type="primary"):
            api.send(platform, thread_id, text)
            done("Reply sent.", draft_key=draft_key)
    if not can_send:
        st.caption("Sending requires a recent customer message and control of this conversation.")


def render_inbox(api, feed, done):
    snapshot = feed.threads()
    _errors(snapshot)
    query = st.text_input("Search inbox", placeholder="Search conversations…", key="community-inbox-search",
                          label_visibility="collapsed").strip().casefold()
    rows = [row for row in snapshot["items"] if not query or query in (peer(row, api) + " " + row["platform"]).casefold()]
    unread = sum(int(row.get("unread_count") or 0) for row in snapshot["items"])
    st.caption(f"{len(rows)} conversations · {unread} unread · Facebook + Instagram")
    if rows:
        left, right = st.columns([1.15, 1.85], gap="medium")
        with left:
            st.dataframe([{"Customer": peer(row, api), "Channel": row["platform"],
                           "Updated": dated(row.get("updated_time")), "Unread": int(row.get("unread_count") or 0)}
                          for row in rows], hide_index=True, height=410, width="stretch",
                         key="community-inbox-grid", selection_mode="single-row",
                         on_select=lambda: _select_thread(rows))
            st.caption("Select a conversation to read and reply.")
        selected = st.session_state.get("community-selected-thread")
        thread = next((row for row in rows if (row["platform"], row["id"]) == selected), rows[0])
        with right:
            _messages(api, feed, thread, done)
    elif not snapshot["errors"]:
        st.info("No conversations match." if query else "Your inbox is clear.")
    if any(snapshot["more"].values()) and st.button("Load more conversations", key="community-more-threads"):
        feed.more_threads(snapshot)
        st.rerun()


def _comment_actions(api, row, done):
    platform, post_id, comment_id = row["platform"], row["post"]["id"], row["id"]
    suffix = platform + "-" + comment_id
    st.text(row.get("text") or row.get("message") or "[Comment]")
    post_text = row["post"].get("message") or row["post"].get("caption") or "Sports Cave post"
    st.caption("Post: " + post_text[:200])
    st.caption(dated(row.get("created_time") or row.get("timestamp")) +
               f" · {int(row.get('like_count') or 0)} likes")
    actions = st.columns([1, 1, 1, 1, 1.5])
    if platform == "Facebook":
        if actions[0].button("Like", icon=":material/thumb_up:", key="like-" + suffix, disabled=not api.writes):
            api.moderate(platform, post_id, comment_id, "like")
            done("Comment liked.")
        if actions[1].button("Unlike", key="unlike-" + suffix, disabled=not api.writes):
            api.moderate(platform, post_id, comment_id, "unlike")
            done("Like removed.")
    else:
        link = row["post"].get("permalink")
        if str(link or "").startswith("https://"):
            actions[0].link_button("Like on Instagram", link)
    for column, action in zip(actions[2:4], ("hide", "unhide")):
        if column.button(action.title(), key=action + "-" + suffix, disabled=not api.writes):
            api.moderate(platform, post_id, comment_id, action)
            done("Comment updated.")
    link = row["post"].get("permalink") or row["post"].get("permalink_url")
    if str(link or "").startswith("https://"):
        actions[4].link_button("Open post", link)
    draft_key = "community-comment-reply-" + suffix
    with st.form("community-comment-form-" + suffix):
        text = st.text_area("Public reply", max_chars=1000, key=draft_key, height=80,
                            placeholder="Reply to this comment…", label_visibility="collapsed")
        if st.form_submit_button("Reply", icon=":material/reply:", type="primary", disabled=not api.writes):
            api.moderate(platform, post_id, comment_id, "reply", text)
            done("Reply sent.", draft_key=draft_key)
    with st.popover("More", icon=":material/more_horiz:"):
        confirm = st.checkbox("Confirm permanent deletion", key="community-delete-confirm-" + suffix)
        if st.button("Delete comment", key="delete-" + suffix, disabled=not (api.writes and confirm)):
            api.moderate(platform, post_id, comment_id, "delete")
            done("Comment deleted.")


def render_comments(api, feed, done):
    snapshot = feed.comments()
    _errors(snapshot)
    query = st.text_input("Search comments", placeholder="Search comments or people…", key="community-comment-search",
                          label_visibility="collapsed").strip().casefold()
    rows = [row for row in snapshot["items"] if not query or query in
            (author(row) + " " + str(row.get("text") or row.get("message") or "") + " " + row["platform"]).casefold()]
    visible = st.session_state.get("community-comment-visible", 40)
    st.caption(f"{min(len(rows), visible)} of {len(rows)} loaded comments · newest first · dates in Sydney time")
    for row in rows[:visible]:
        platform, comment_id = row["platform"], row["id"]
        date = dated(row.get("created_time") or row.get("timestamp"))
        summary = (date + " · " + platform + " · " + label_text(author(row), 45) +
                   " — " + label_text(row.get("text") or row.get("message") or "[Comment]"))
        panel = st.expander(summary, key="community-comment-open-" + platform + "-" + comment_id, on_change="rerun")
        # Closed rows send only summaries; forms/actions are constructed on demand.
        if panel.open:
            with panel:
                _comment_actions(api, row, done)
    if not rows and not snapshot["errors"]:
        st.info("No comments match." if query else "No comments yet.")
    more = len(rows) > visible or snapshot["more_comments"] or any(snapshot["more_posts"].values())
    if more and st.button("Show more comments", icon=":material/expand_more:", key="community-more-comments"):
        if len(rows) <= visible:
            feed.more_comments(snapshot)
        st.session_state["community-comment-visible"] = visible + 40
        st.rerun()
