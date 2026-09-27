"""Lazy Email V1 UI: mailbox reads first, optional workflow/order context second."""
from datetime import datetime, timezone
import hashlib
import html
import logging
from urllib.parse import urlencode, urlparse
from zoneinfo import ZoneInfo

import streamlit as st

import os_accounts
from ui_styles import page_header, source_status_banner, metric_strip, section_title
from support_email_provider import ImapProvider, load_configuration, MailboxError
from support_email_logic import (CACHE_TTL, STATUSES, build_threads, cached_read, is_customer,
                                 match_orders, order_numbers, workflow_for_thread)
import support_email_store as store

LOGGER = logging.getLogger(__name__)


def _date(value, user):
    if not value:
        return "—"
    if not isinstance(value, datetime):
        try:
            value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(os_accounts.timezone_for_user(user))).strftime("%d %b %Y · %I:%M %p")


def _safe_text(value, *, note=False):
    # Text may contain Markdown image syntax; escaping HTML inside a fixed div prevents
    # Streamlit Markdown from ever interpreting a tracking URL or executable HTML.
    tone = "sc-email-note" if note else "sc-email-message"
    st.html(f'<div class="{tone}">{html.escape(str(value))}</div>')


def _optional(cache, key, loader):
    entry = cached_read(cache, key, loader)
    return entry["data"], bool(entry["error"])


def _context(match, user):
    section_title("Customer context")
    order = match.get("order")
    if not order:
        st.caption(match["label"])
        if match["candidates"]:
            st.dataframe([{"Order": o["order_name"], "Date": _date(o["created_at"], user)}
                          for o in match["candidates"]], hide_index=True, use_container_width=True)
        return
    _safe_text(f"Order {order['order_name']} · {_date(order['created_at'], user)}\n"
               f"Fulfilment: {order.get('fulfillment_status') or 'Not recorded'}")
    st.caption(f"Match: {match['method'].replace('_', ' ')} · Order data synced {_date(order.get('synced_at'), user)}")
    rows = [{"Product": l.get("product_title"), "Variant": l.get("variant_title")}
            for l in order.get("lines", [])]
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    editions = order.get("editions", [])
    if editions:
        st.dataframe([{"Product": e.get("product_title"), "Edition #": e.get("edition_number"),
                       "Of": e.get("edition_total"), "Certificate": e.get("certificate_status")}
                      for e in editions], hide_index=True, use_container_width=True)
    tracking = order.get("tracking") or order.get("fulfillments") or []
    _safe_text(f"Tracking: {tracking if tracking else 'Not recorded in synced order data'}")
    admin_url = str(order.get("admin_url") or "")
    parsed = urlparse(admin_url)
    if parsed.scheme == "https" and (parsed.hostname == "admin.shopify.com" or
            (parsed.hostname or "").endswith(".myshopify.com")):
        st.link_button("Open Shopify Order", admin_url)
    st.link_button("Open Sports Cave Order", "?" + urlencode({"page": "Orders", "global_search": order["order_name"]}))
    if editions:
        # The existing Orders view owns edition rows; no invented unsupported Edition Ops deep link.
        st.link_button("Open Edition Record", "?" + urlencode({"page": "Orders", "global_search": order["order_name"]}),
                       help="Opens the existing order view containing its edition records.")
    previous = [o for o in match["previous"] if o["shopify_order_id"] != order["shopify_order_id"]]
    if previous:
        with st.expander(f"Previous orders · {len(previous)}"):
            st.dataframe([{"Order": o["order_name"], "Date": _date(o["created_at"], user)} for o in previous],
                         hide_index=True, use_container_width=True)


def _workflow(thread, metadata, assignees, available, config, user, cache):
    existing = workflow_for_thread(thread, metadata)
    if existing.get("conflict"):
        st.warning("Multiple saved workflows now belong to this thread. Workflow editing needs administrator review.")
        return
    key = existing.get("thread_key") or thread["thread_key"]
    section_title("Support workflow")
    if not available:
        st.caption("Workflow metadata unavailable. Inbox access does not require it.")
        return
    labels = {"": "Unassigned", **{str(u["id"]): os_accounts.safe_account_label(u) for u in assignees}}
    assigned = str(existing.get("assigned_user_id") or "")
    if assigned not in labels:
        labels[assigned] = "Previously assigned account (unavailable)"
    version = hashlib.sha256(str(existing.get("updated_at", "new")).encode()).hexdigest()[:12]
    with st.form(f"email-workflow-{key}-{version}"):
        columns = st.columns(2)
        status = columns[0].selectbox("Support status", STATUSES,
                                     index=STATUSES.index(existing.get("support_status") or "Needs Reply"))
        assignment = columns[1].selectbox("Assigned to", list(labels), format_func=labels.get,
                                          index=list(labels).index(assigned))
        approval = st.checkbox("Approval required", value=bool(existing.get("needs_approval")))
        notes = st.text_area("Internal Sports Cave notes", value=existing.get("internal_notes") or "",
                             max_chars=8000, height=90, help="Internal workflow notes only. Never sent to the customer.")
        save = st.form_submit_button("Save workflow")
    if existing.get("internal_notes"):
        _safe_text("INTERNAL NOTE\n" + existing["internal_notes"], note=True)
    if save:
        try:
            store.save_workflow(config.address, key, actor=user, support_status=status,
                                assigned_user_id=assignment or None, internal_notes=notes,
                                needs_approval=approval, previous=existing)
            for cache_key in list(cache):
                if cache_key[0] == "metadata":
                    del cache[cache_key]
            st.rerun()
        except store.SupportStorageError as error:
            st.warning(str(error))


def _conversation(thread, match, metadata, assignees, workflow_available, provider, config, user, cache):
    st.divider()
    customer = thread["customer"]
    _safe_text(f"{customer['name'] or customer['email']}\n{customer['email']}\n{thread['subject']}")
    _workflow(thread, metadata, assignees, workflow_available, config, user, cache)
    # Load only the selected message. This bounds slow server reads even in a long conversation.
    messages = thread["messages"]
    st.caption("Messages are listed oldest to newest. Select a message to read its text.")
    labels = {m["uid"]: f"{'CUSTOMER' if is_customer(m, config.address) else 'SPORTS CAVE'} · "
              f"{_date(m['received_at'], user)} · {m['subject']}" for m in messages}
    selected_uid = st.selectbox("Message", list(labels), index=len(messages)-1, format_func=labels.get,
                                key=f"email-message-choice-{thread['thread_key']}")
    message = next(m for m in messages if m["uid"] == selected_uid)
    if message.get("error"):
        st.caption(message["error"])
    body_key = ("body", message["folder"], message["uidvalidity"], message["uid"])
    detail = cached_read(cache, body_key, lambda: provider.read_message(message))
    body = detail["data"]
    if body and match["method"] != "manual":
        numbers = order_numbers(body["text"])
        if numbers:
            orders, error = _optional(cache, ("body-orders", tuple(sorted(numbers)), thread["customer"]["email"]),
                                     lambda: store.load_orders([thread["customer"]["email"]], sorted(numbers)))
            if not error:
                match = match_orders(thread, orders, body=body["text"])
    _context(match, user)
    section_title("Message")
    _safe_text(labels[selected_uid])
    with st.expander("Original message headers"):
        _safe_text(f"From: {message['sender']['name']} <{message['sender']['email']}>\n"
                   f"To: {', '.join(p['email'] for p in message['to'])}\n"
                   f"CC: {', '.join(p['email'] for p in message['cc'])}\n"
                   f"Subject: {message['subject']}\nDate: {_date(message['date'], user)}\n"
                   f"Message-ID: {message['message_id']}\nIn-Reply-To: {' '.join(message['in_reply_to'])}\n"
                   f"References: {' '.join(message['references'])}\nIMAP UID: {message['uid']}\n"
                   f"UIDVALIDITY: {message['uidvalidity']}\nFlags: {' '.join(message['flags'])}")
    if detail["error"]:
        st.warning(detail["error"])
        return
    for warning in body["warnings"]:
        st.caption(warning)
    _safe_text(body["text"] or "No readable text in this message. Use your existing mail client for other formats.")
    if body["attachments"]:
        section_title("Attachments")
    for part in body["attachments"]:
        section = part["section"]
        _safe_text(f"{part['filename']} · {part['content_type']} · {part['encoded_size'] / 1024:.1f} KB encoded")
        attachment_key = ("attachment", message["uidvalidity"], message["uid"], section)
        if st.button("Retrieve attachment", key=f"email-fetch-{message['uid']}-{section}"):
            result = cached_read(cache, attachment_key, lambda: provider.read_attachment(message, section))
            if result["error"]:
                st.warning(result["error"])
        result = cache.get(attachment_key, {})
        if result.get("data"):
            file = result["data"]
            st.download_button("Download", file["data"], file_name=file["filename"],
                               mime="application/octet-stream", key=f"email-download-{message['uid']}-{section}")


def render_page(user):
    if not os_accounts.can_access_page(user, "Email"):
        st.info("Your OS account does not have Email access.")
        return
    try:
        _render_page(user)
    except Exception as error:
        # Streamlit control-flow exceptions derive from BaseException and are not swallowed.
        LOGGER.warning("Support email page unavailable (%s)", type(error).__name__)
        st.warning("Email is temporarily unavailable. Other Sports Cave OS pages remain available.")


def _render_page(user):
    config = load_configuration()
    provider = ImapProvider(config)
    page_header("EMAIL", "Customer Support")
    st.markdown("""<style>
      .sc-email-message {white-space:pre-wrap;overflow-wrap:anywhere;font-size:.88rem;color:#181818;
          border:1px solid #e5e1d8;background:#fffdf8;padding:12px 14px;border-radius:6px;margin:6px 0;}
      .sc-email-note {white-space:pre-wrap;overflow-wrap:anywhere;background:#f5edda;
          border-left:3px solid #b7954c;padding:10px 14px;font-size:.86rem;margin:6px 0;}
    </style>""", unsafe_allow_html=True)
    st.text(config.address)
    scope = (config.scope, str(user.get("id")), st.session_state.get("navigation_epoch", 0))
    if st.session_state.get("support_email_scope") != scope:
        previous_scope = st.session_state.get("support_email_scope")
        if not previous_scope or previous_scope[:2] != scope[:2]:
            st.session_state.pop("support_email_last_refresh", None)
        st.session_state["support_email_scope"] = scope
        st.session_state["support_email_cache"] = {}
        st.session_state["support_email_limit"] = 50
    cache = st.session_state.setdefault("support_email_cache", {})
    columns = st.columns([1, 1, 3])
    refresh = columns[0].button("Refresh Inbox", disabled=not config.configured)
    test = columns[1].button("Test Connection", disabled=not config.configured)
    if not config.configured:
        st.caption("● Not configured")
        st.info("Add the secure IMAP environment variables in Render to connect this mailbox.")
        return
    if refresh:
        cache.clear()
    if test:
        try:
            result = provider.test_connection()
            st.success(f"Connected to {config.address}. INBOX accessible · {result['count']} messages available.")
            with st.expander("Discovered mailbox folders"):
                _safe_text("\n".join(result["folders"]))
        except MailboxError as error:
            cache.clear()
            st.caption("● Connection error")
            st.warning(str(error))
            st.caption("Last refreshed: " + _date(st.session_state.get("support_email_last_refresh"), user))
            return
    limit = st.session_state["support_email_limit"]
    entry = cached_read(cache, ("headers", limit), lambda: provider.list_headers(limit))
    if entry["refreshed_at"]:
        st.session_state["support_email_last_refresh"] = entry["refreshed_at"]
    source_status_banner([
        ("Mail source", "VentraIP IMAP"), ("Mailbox", config.address),
        ("Last refreshed", _date(st.session_state.get("support_email_last_refresh"), user)),
    ])
    if entry["error"]:
        # No stale message display or database fallback, even if bodies remain cached.
        st.caption("● Connection error")
        st.warning(entry["error"])
        return
    st.caption(f"● Live mailbox · INBOX · {CACHE_TTL}-second display cache · Read-only")
    if refresh:
        store.audit("email_inbox_refreshed", actor=os_accounts.safe_account_label(user))
    snapshot = entry["data"]
    threads = build_threads(snapshot["messages"], config.address)
    st.caption(f"{len(snapshot['messages'])} of {snapshot['total']} mailbox messages · {len(threads)} conversations in this window. "
               "Sent history is not included. Load More may reveal earlier messages in a thread.")
    if not threads:
        st.info("INBOX is empty.")
        return
    keys = tuple(sorted({k for t in threads for k in t["aliases"]}))
    metadata, workflow_error = _optional(cache, ("metadata", keys), lambda: store.load_metadata(config.address, keys))
    metadata = metadata or {}
    assignees, assignee_error = _optional(cache, ("assignees",), store.load_assignees)
    assignees = assignees or []
    emails = tuple(sorted({t["customer"]["email"] for t in threads if "@" in t["customer"]["email"]}))
    numbers = tuple(sorted(set().union(*(order_numbers(m["subject"]) for m in snapshot["messages"]))))
    overrides = tuple(sorted({m["matched_order_id"] for m in metadata.values() if m.get("matched_order_id")}))
    orders, order_error = _optional(cache, ("orders", emails, numbers, overrides), lambda: store.load_orders(emails, numbers, overrides))
    if workflow_error:
        st.caption("Workflow metadata unavailable. Unsaved conversations show Needs Reply as a triage default.")
    else:
        counts = {status: sum(workflow_for_thread(t, metadata).get("support_status") == status for t in threads) for status in STATUSES}
        metric_strip(counts.items())
        st.caption("Status totals count saved workflow decisions in this window. Needs Reply is the default for unsaved conversations, not historical status.")
    if order_error:
        st.caption("Synced order context is unavailable. Mailbox messages are still live.")
    query = st.text_input("Search inbox", placeholder="Customer, email, subject or matched order").strip().casefold()
    filtered, rows, matches = [], [], {}
    names = {str(u["id"]): os_accounts.safe_account_label(u) for u in assignees}
    for thread in threads:
        workflow = workflow_for_thread(thread, metadata)
        match = match_orders(thread, orders or [], override=workflow.get("matched_order_id"))
        if order_error:
            match["label"] = "Order matching unavailable"
        matches[thread["thread_key"]] = match
        searchable = " ".join([thread["customer"]["name"], thread["customer"]["email"],
                                *(m["subject"] for m in thread["messages"]), match["label"]]).casefold()
        if query and query not in searchable:
            continue
        filtered.append(thread)
        order = match.get("order") or {}
        rows.append({"Customer": thread["customer"]["name"] or thread["customer"]["email"],
                     "Subject": thread["subject"], "Received": _date(thread["last_customer_at"], user),
                     "Order": match["label"], "Product": ", ".join(l["product_title"] or "" for l in order.get("lines", [])),
                     "Status": "Workflow conflict" if workflow.get("conflict") else workflow.get("support_status") or "Needs Reply · default",
                     "Messages": len(thread["messages"]), "Unread": thread["unread"],
                     "Assigned": names.get(str(workflow.get("assigned_user_id")), "Unassigned"),
                     "Last activity": _date(thread["last_activity_at"], user)})
    # Key includes row identity/order to prevent an old selected index opening a different customer after refresh/search.
    table_version = hashlib.sha256("|".join(t["thread_key"] for t in filtered).encode()).hexdigest()[:16]
    selection = st.dataframe(rows, hide_index=True, use_container_width=True, row_height=34,
                             on_select="rerun", selection_mode="single-row", key=f"email-inbox-{table_version}")
    if snapshot["has_more"] and limit < 1000:
        if st.button("Load More"):
            st.session_state["support_email_limit"] = min(limit + 50, 1000)
            cache.clear()
            st.rerun()
    elif snapshot["has_more"]:
        st.caption("Showing the newest 1,000 messages. Use your existing mail client for older history.")
    chosen = selection.selection.rows
    if chosen and chosen[0] < len(filtered):
        thread = filtered[chosen[0]]
        _conversation(thread, matches[thread["thread_key"]], metadata, assignees,
                      not workflow_error and not assignee_error, provider, config, user, cache)
