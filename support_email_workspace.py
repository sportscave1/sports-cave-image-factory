"""Event-driven mailbox controller; only explicit actions send or change mail."""
import base64
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import logging
import re
import time
from urllib.parse import urlencode
import uuid
from zoneinfo import ZoneInfo

import os_accounts
from support_email_provider import ImapProvider, MailboxError, folder_roles
from support_email_logic import build_threads, cached_read, match_orders, order_numbers, workflow_for_thread
from support_email_compose import (ComposeError, default_settings, selected_signature, new_draft, build_mime,
    sanitize_html, readable_html, split_quote, attachment_from_upload, add_attachment, make_attachment,
    edit_mailbox_draft, safe_url, sanitize_signature)
from support_email_signatures import logo_data_uri
from support_email_smtp import SMTPProvider, SEND_REGISTRY, reconcile_sent, report_progress
import support_email_store as store
from support_email_cache import DisplayLRU, BODY_LIMIT, BODY_BYTES, THREAD_LIMIT, THREAD_BYTES, ordered_folders

LOGGER = logging.getLogger(__name__)
FOLDER_TTL = 300
LIVE_INTERVAL = 55  # The existing 30-second shell heartbeat yields one check/minute.
TERMINAL_CONNECTION_ERRORS = {"configuration", "authentication", "tls", "select"}


def reference_key(header):
    return hashlib.sha256(f"{header['folder']}\n{header['uidvalidity']}\n{header['uid']}".encode()).hexdigest()


def formatted_date(value, user):
    if not value:
        return ""
    if not isinstance(value, datetime):
        try:
            value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(os_accounts.timezone_for_user(user))).strftime("%d %b · %I:%M %p")


class Workspace:
    def __init__(self, state, user, imap_config, smtp_config, *, imap=None, smtp=None, registry=None, progress=None):
        self.state, self.user, self.config, self.smtp_config = state, user, imap_config, smtp_config
        if imap is None:
            imap = ImapProvider(imap_config)
            if type(imap).__module__ == 'support_email_provider':
                from support_email_reads import AsyncInbox
                imap = AsyncInbox(imap_config)
        self.imap, self.smtp = imap, smtp or SMTPProvider(smtp_config)
        self.registry = registry or SEND_REGISTRY
        self.progress = progress
        for key, default in {"cache": {}, "processed": set(), "limit": 50, "query": "", "field": "TEXT",
                             "settings": default_settings(), "expanded": set(), "notice": "", "view": "mail",
                             "mailbox_version": 0, "history_pending": False}.items():
            state.setdefault(key, default)
        # Content lives separately from short-lived mailbox/header snapshots and selection.
        self.bodies = DisplayLRU(state, "opened_content", limit=BODY_LIMIT, byte_limit=BODY_BYTES)
        self.resolved_threads = DisplayLRU(state, "resolved_threads", limit=THREAD_LIMIT, byte_limit=THREAD_BYTES)

    @property
    def cache(self):
        return self.state["cache"]

    @property
    def roles(self):
        return folder_roles(self.state.get("folders", []), self.state["settings"].get("folder_mapping"))

    def audit(self, action, identity=""):
        try:
            store.audit(action, hashlib.sha256(str(identity).encode()).hexdigest() if identity else "",
                        actor=os_accounts.safe_account_label(self.user))
        except Exception as error:
            LOGGER.info("Email audit unavailable (%s)", type(error).__name__)

    def load(self, *, force=False, previews=True, defer_body=False):
        self.state.update(initial_load_pending=False, initial_load_attempted=True)
        if not force and (self.state.get("recovery_state") == "stopped" or
                          time.monotonic() < self.state.get("load_retry_at", 0)):
            if self.state.get("snapshot_view") != (self.state.get("folder"), self.state["query"], self.state["field"]):
                self.state["error"] = self.state.get("connection_message") or "Mailbox connection unavailable."
            return
        recovering = bool(self.state.get("recovery_state"))
        if force:
            self.state.update(recovery_attempts=0, recovery_state="", load_failures=0, load_retry_at=0)
        refresh = getattr(self.imap, "interactive_refresh", None)
        with refresh() if force and refresh else nullcontext():
            self._load(force=force, previews=previews, recovering=recovering, defer_body=defer_body)

    def _unavailable(self, message, *, code="temporary", retry_after=0):
        s = self.state
        if code == 'pending':
            s.update(read_pending=True, recovery_state='waiting',load_retry_at=time.monotonic()+1,
                     connection_message='Syncing…', connection_code='pending')
            return
        s['read_pending'] = False
        s["load_failures"] = min(4, s.get("load_failures", 0) + 1)
        s["load_retry_at"] = time.monotonic() + max(retry_after, min(120, 15 * 2 ** (s["load_failures"] - 1)))
        stopped = code in TERMINAL_CONNECTION_ERRORS
        s.update(recovery_state="stopped" if stopped else "waiting", connection_code=code)
        s["connection_message"] = (message if code in TERMINAL_CONNECTION_ERRORS else
                                  "Mailbox connection unavailable." if stopped else "Reconnecting mailbox…")
        same_view = s.get("snapshot_view") == (s.get("folder"), s["query"], s["field"])
        if s.get("snapshot") and same_view:
            s.update(error="", live_error=s["connection_message"] + " Showing last successful mailbox view.")
        else:
            s["error"] = message

    def _recovered(self):
        s = self.state
        if s.get("recovery_state"):
            LOGGER.info("email_workspace_reconnect_succeeded attempts=%d", s.get("recovery_attempts", 0))
        if s.get("notice") == s.pop("connection_notice", None):
            s["notice"] = ""
        s.update(error="", live_error="", recovery_state="", recovery_attempts=0,
                 connection_code="", connection_message="", load_failures=0, load_retry_at=0, read_pending=False)

    def reconnect(self):
        """Bounded UI recovery. Only authoritative reads; never replay an action."""
        s = self.state
        if s.get("recovery_state") != "waiting" or time.monotonic() < s.get("load_retry_at", 0):
            return
        s["recovery_attempts"] = s.get("recovery_attempts", 0) + 1
        LOGGER.info("email_workspace_reconnect_started attempt=%d", s["recovery_attempts"])
        # Preserve folder mapping, cached bodies, compose state and selected UID.
        # Refresh only header membership and a failed discovery result.
        for key in list(self.cache):
            if key[0] == "headers":
                self.cache.pop(key, None)
        s.pop("folder_failure", None)
        self.load(previews=False, defer_body=hasattr(self.imap,'reads'))
        if s.get("recovery_state"):
            LOGGER.warning("email_workspace_reconnect_failed code=%s stopped=%s",
                           s.get("connection_code"), s["recovery_state"] == "stopped")

    def _load(self, *, force=False, previews=True, recovering=False, defer_body=False):
        if not self.config.configured:
            self.state.update(error="Mailbox is not configured.", folders=[], threads=[])
            return
        if force:
            from support_email_notifications import invalidate
            invalidate()
            self.cache.clear()
            self.state.pop("folder_failure", None)
            self.state["history_pending"] = False
        if "settings_available" not in self.state or force:
            try:
                settings, preference = store.load_email_settings(self.config.address, self.user["id"])
                self.state.update(settings=settings, preference=preference, settings_available=True)
            except Exception:
                self.state["settings_available"] = False
        folders = None if force or hasattr(self.imap,'reads') else self.state.get("folder_cache")
        failure = self.state.get("folder_failure", {})
        if failure.get("expires", 0) > time.monotonic():
            return
        if not folders or folders["expires"] <= time.monotonic():
            folders = cached_read({}, "folders", self.imap.discover_folders)
            if not folders["error"]:
                folders["expires"] = time.monotonic() + FOLDER_TTL
                self.state["folder_cache"] = folders
                self.state.pop("folder_failure", None)
                inbox = next((f for f in folders["data"]["folders"] if f["name"].upper() == "INBOX"), {})
                if isinstance(inbox.get("unread"), int):
                    self.state["inbox_status"] = {"unread_count": inbox["unread"], "checked_at": time.time()}
        if folders["error"]:
            # Throttle failed reruns separately; never cache an empty successful mailbox.
            self._unavailable(folders["error"], code=folders.get("error_code", "temporary"), retry_after=folders.get("retry_after", 0))
            self.state["folder_failure"] = {"error": folders["error"], "expires": self.state["load_retry_at"]}
            return
        self.state["folders"] = folders["data"]["folders"]
        self.state["capabilities"] = list(folders["data"]["capabilities"])
        names = [f["name"] for f in self.state["folders"]]
        if not names:
            self._unavailable("No selectable mailbox folders were returned.")
            return
        if self.state.get("folder") not in names:
            self.state["folder"] = self.roles.get("inbox", names[0])
        key = ("headers", self.state["folder"], self.state["limit"], self.state["query"], self.state["field"])
        list_started = time.monotonic()
        entry = cached_read(self.cache, key, lambda: self.imap.list_headers(self.state["limit"], self.state["folder"],
                            query=self.state["query"], field=self.state["field"], previews=previews))
        LOGGER.info("Email list ready duration_ms=%.1f", (time.monotonic()-list_started)*1000)
        if entry["error"]:
            self.cache.pop(key, None)  # Retry timing belongs to backoff, never a failed data cache.
            self._unavailable(entry["error"], code=entry.get("error_code", "temporary"), retry_after=entry.get("retry_after", 0))
            return
        snapshot = entry["data"]
        # Two refreshes can share a wall-clock tick. Fresh snapshots must still
        # invalidate membership/flags and UIDVALIDITY-dependent caches.
        signature = (key, entry.get("revision", entry["refreshed_at"]))
        changed = self.state.get("snapshot_signature") != signature
        self.state.update(error="",
                          snapshot_view=(self.state["folder"], self.state["query"], self.state["field"]),
                          refreshed_at=entry["refreshed_at"], snapshot=snapshot)
        if changed:
            self.state["mailbox_version"] += 1
            self.state["snapshot_signature"] = signature
            self.state["threads"] = sorted(build_threads(snapshot["messages"], self.config.address), key=lambda t: t["last_activity"], reverse=True)
            self.state["thread_index"] = {t["thread_key"]: t for t in self.state["threads"]}
            self.state.pop("list_model", None)
            self.resolved_threads.clear()
            folder, validity = self.state["folder"], str(snapshot["uidvalidity"])
            self.bodies.remove_where(lambda k: k[1] == folder and k[2] != validity)
        if self.state.get("selected") and not any(t["thread_key"] == self.state["selected"] for t in self.state["threads"]):
            self.state.update(selected=None, conversation=[], history_pending=False)
        elif changed and self.state.get("selected"):
            # Refresh header flags/membership without re-fetching immutable, identity-matched MIME.
            view, context = self.state["view"], self.state.get("context", {})
            self._select_thread(self._thread())
            self.state.update(view=view, context=context)
        selected_first = False
        if (not self.state.get("selected") and self.state["threads"]
                and self.state["folder"] == self.roles.get("inbox")
                and not self.state["query"] and self.state["view"] == "mail"):
            # Initial Inbox paint only: preserve ordering and do not mutate read flags.
            self._select_thread(self.state["threads"][0])
            selected_first = True
        if (self.state["view"] == "mail" and self.state.get("selected")
                and (selected_first or recovering or self.state.get("recovery_state"))):
            message = next((m for m in self.state.get("conversation", [])
                            if reference_key(m) == self.state.get("active_message")), None)
            try:
                if message and reference_key(message) in self.state["expanded"]:
                    if defer_body:
                        self.state["body_pending"] = reference_key(message)
                    else:
                        self._body(message, defer=True)
            except MailboxError as error:
                connection_failure = error.retryable or error.code in TERMINAL_CONNECTION_ERRORS | {"deferred", "busy", "limit"}
                if not connection_failure:
                    self._recovered()  # Headers recovered; a missing/malformed body is a separate error.
                self.state["notice"] = str(error)
                if connection_failure:
                    self.state["connection_notice"] = str(error)
                self.state["loaded"] = True
                return
        self._recovered()
        self.state["loaded"] = True
        self.state["live_checked_at"] = time.monotonic()

    def _thread(self):
        return self.state.get("thread_index", {}).get(self.state.get("selected"))

    def _header(self, key):
        if self.state.get("error"):
            raise MailboxError("Refresh the mailbox before taking this action.")
        for message in [*self.state.get("conversation", []), *self.state.get("snapshot", {}).get("messages", [])]:
            if reference_key(message) == key:
                return message
        raise MailboxError("Message is no longer selected. Refresh the mailbox.")

    def _content_key(self, message):
        return (self.config.address.casefold(), message["folder"], str(message["uidvalidity"]),
                str(message["uid"]), message["message_id"])

    def _content(self, message):
        return self.bodies.get(self._content_key(message))

    def _body(self, message, *, defer=False):
        key = self._content_key(message)
        existing = self.bodies.get(key)
        if existing is not None:
            return existing["body"]
        try:
            started = time.monotonic()
            loader = self.imap.read_body_for_action if not defer and hasattr(self.imap,'reads') else self.imap.read_message
            body = loader(message)
            LOGGER.info("Email selected body fetched duration_ms=%.1f", (time.monotonic()-started)*1000)
        except Exception as error:
            LOGGER.info("Email body read unavailable (%s)", type(error).__name__)
            if isinstance(error, MailboxError) and error.code == 'pending':
                self.state.update(body_pending=reference_key(message), body_loading=True)
                return None
            if isinstance(error, MailboxError) and (error.retryable or error.code in
                    TERMINAL_CONNECTION_ERRORS | {"deferred", "busy", "limit"}):
                self._unavailable(str(error), code=error.code, retry_after=error.retry_after)
                raise
            raise MailboxError("Could not open this message. Refresh and try again.")
        text, quote = split_quote(body["text"])
        content = {"body": body, "html": readable_html(text), "quote": readable_html(quote)}
        if body.get("html"):
            from support_email_render import sanitize_received_html, reader_document
            try:
                render_started = time.monotonic()
                content["reader_document"] = reader_document(sanitize_received_html(body["html"],body.get("inline_images")))
                LOGGER.info("Email HTML sanitized duration_ms=%.1f", (time.monotonic()-render_started)*1000)
            except (ValueError, TypeError, RecursionError):
                LOGGER.info("Email HTML fallback used")
        if not self.bodies.put(key, content):
            raise MailboxError("This message exceeds the display cache limit. Open it in your mail client.")
        self.state['body_loading'] = False
        return body

    def _select_thread(self, thread):
        self.state.pop("body_pending", None)
        self.state.update(selected=thread["thread_key"], expanded=set(), view="mail", context={})
        resolved = self.resolved_threads.get((self.state["mailbox_version"], thread["thread_key"]))
        messages = resolved if resolved is not None else thread["messages"]
        self.state["conversation"] = messages
        active = next((m for m in reversed(messages) if m["folder"] == self.state["folder"]), messages[-1])
        self.state["active_message"] = reference_key(active)
        self.state["expanded"].add(reference_key(active))
        self.state["history_pending"] = resolved is None and any(m["message_id"] or m["references"] or m["in_reply_to"] for m in messages)
        return active

    def open_thread(self, thread_key):
        if self.state.get("error"):
            raise MailboxError("Refresh the mailbox before opening a conversation.")
        thread = self.state.get("thread_index", {}).get(thread_key)
        if not thread:
            raise MailboxError("This conversation is no longer in the current list.")
        # First paint needs only the requested MIME, never historical searches.
        message = self._select_thread(thread)
        if self._body(message, defer=True) is not None:
            self._read_visible(message)
        else:
            self.state['body_mark_read'] = reference_key(message)

    def _read_visible(self, message):
        if message.get("unread"):
            try:
                self.message_action("mark_read", message)
            except MailboxError:
                self.state["notice"] = "Could not update message. Try again."

    def _folder_count(self, folder, count, *, checked_at=None):
        if not isinstance(count, int):
            return
        count = max(0, count)
        for f in self.state.get("folders", []):
            if f["name"] == folder:
                f["unread"] = count
        if folder.upper() == "INBOX":
            self.state["inbox_status"] = {"unread_count": count, "checked_at": checked_at or time.time()}

    def _refresh_rows(self, *, membership_changed=True):
        for thread in self.state.get("threads", []):
            thread["unread"] = sum(m["unread"] for m in thread["messages"])
        self.state.pop("list_model", None)
        self.state["mailbox_version"] += 1
        # Flag-only changes invalidate rendered rows, not expensive thread membership.
        retained = [] if membership_changed else [
            (key[1], entry["value"]) for key, entry in self.resolved_threads.data["entries"].items()]
        self.resolved_threads.clear()
        for thread_key, messages in retained:
            self.resolved_threads.put((self.state["mailbox_version"], thread_key), messages)
        self.cache.clear()

    def _apply_flag(self, message, flag, enabled):
        key = reference_key(message)
        all_rows = [message, *self.state.get("snapshot", {}).get("messages", []), *self.state.get("conversation", [])]
        all_rows += [m for t in self.state.get("threads", []) for m in t["messages"]]
        all_rows += [m for entry in self.resolved_threads.data["entries"].values() for m in entry["value"]]
        for row in all_rows:
            if reference_key(row) == key:
                flags = set(row["flags"])
                flags.add(flag) if enabled else flags.discard(flag)
                row.update(flags=tuple(sorted(flags)), unread="\\Seen" not in flags)

    def live_check(self, signal_version=None):
        """Heartbeat or validated push invokes this; selections/reruns do not."""
        if (hasattr(self.imap, 'reads') and self.state.get('folder', 'INBOX') == 'INBOX'
                and self.state['limit'] == 50 and not self.state['query']):
            # The index worker owns Inbox refresh. Heartbeats consume it, never
            # start a competing remote delta read for every browser session.
            for key in list(self.cache):
                if key[0] == 'headers':self.cache.pop(key, None)
            self._load(previews=False, defer_body=True)
            return
        if self.state.get("recovery_state"):
            self.reconnect()
            return
        now = time.monotonic()
        pushed = False
        if signal_version and signal_version != self.state.get('idle_version'):
            from support_email_idle import HUB
            signal = HUB.snapshot()
            pushed = (signal.get('version') == signal_version and signal.get('mailbox') == self.config.address.casefold()
                      and time.time() - signal.get('checked_at', 0) < 120)
        if now < self.state.get("load_retry_at", 0) or (not pushed and now - self.state.get("live_checked_at", 0) < LIVE_INTERVAL):
            return
        self.state["live_checked_at"] = now  # Failures are bounded too.
        if not self.state.get("loaded") or self.state.get("error"):
            self.load(previews=False)
            return
        try:
            s = self.state
            s['live_pending'] = False
            old = s["snapshot"]
            delta = self.imap.live_changes(s["folder"], {**old, "visible_messages": s.get("conversation", [])},
                                          limit=s["limit"], query=s["query"], field=s["field"])
            rows = [] if delta["reset"] else [m for m in old["messages"] if m["uid"] in delta["flags"]]
            membership_changed = delta["reset"] or len(rows) != len(old["messages"]) or bool(delta["added"])
            changed = membership_changed
            cached_headers = {}
            if not membership_changed:
                for entry in self.resolved_threads.data["entries"].values():
                    for cached in entry["value"]:
                        cached_headers.setdefault(reference_key(cached), []).append(cached)
            for m in rows:
                flags = delta["flags"][m["uid"]]
                if set(flags) != set(m["flags"]):
                    changed = True
                m.update(flags=flags, unread="\\Seen" not in flags)
                for cached in cached_headers.get(reference_key(m), []):
                    cached.update(flags=flags, unread=m["unread"])
            checked = set(delta.get("checked_uids", [m["uid"] for m in old["messages"]]))
            for m in s.get("conversation", []):
                if m["folder"] == s["folder"] and not delta["reset"] and m["uid"] in delta["flags"]:
                    flags = delta["flags"][m["uid"]]
                    changed = changed or set(flags) != set(m["flags"])
                    m.update(flags=flags, unread="\\Seen" not in flags)
                elif m["folder"] == s["folder"] and m["uid"] in checked:
                    changed = True
                    membership_changed = True
            removed = len(old["messages"]) - len(rows)
            unique = {reference_key(m): m for m in [*rows, *delta["added"]]}
            matched = max(0, old.get("matched", len(old["messages"])) - removed + len(delta["added"]))
            rows = sorted(unique.values(), key=lambda m: int(m["uid"]))[-s["limit"]:]
            self._folder_count(s["folder"], delta["unread"], checked_at=delta["checked_at"])
            s["snapshot"] = {**old, "messages": rows, "uidvalidity": delta["uidvalidity"], "live_uid": delta["live_uid"],
                "total": delta["total"], "matched": matched,
                "has_more": (matched if s["query"] else delta["total"]) > len(rows),
                "refreshed_at": datetime.fromtimestamp(delta["checked_at"], timezone.utc)}
            s["refreshed_at"] = s["snapshot"]["refreshed_at"]
            s["live_error"] = ""
            if pushed:
                s['idle_version'] = signal_version
            s.update(load_failures=0, load_retry_at=0)
            if changed:
                s["threads"] = sorted(build_threads(rows, self.config.address), key=lambda t: t["last_activity"], reverse=True)
                s["thread_index"] = {t["thread_key"]: t for t in s["threads"]}
                # Keep opened bodies and compose state. Update only known displayed flags.
                by_key = {reference_key(m): m for m in rows}
                s["conversation"] = [by_key.get(reference_key(m), m) for m in s.get("conversation", [])
                    if m["folder"] != s["folder"] or (not delta["reset"] and
                        (m["uid"] not in checked or m["uid"] in delta["flags"])) or reference_key(m) in by_key]
                active = s.get("active_message")
                for thread in s["threads"]:
                    if any(reference_key(m) == active for m in thread["messages"]):
                        s["selected"] = thread["thread_key"]
                self._refresh_rows(membership_changed=membership_changed)
                s["history_pending"] = False  # Polling never launches history searches.
        except Exception as error:
            if isinstance(error, MailboxError) and error.code == 'pending':
                self.state.update(live_pending=True,live_checked_at=0)
                return
            if isinstance(error, MailboxError) and error.code == "busy":
                return  # A skipped/coalesced poll says nothing about connection health.
            LOGGER.info("Email live check unavailable (%s)", type(error).__name__)
            self._unavailable(str(error) if isinstance(error, MailboxError) else "Mailbox is temporarily unavailable.",
                              code=getattr(error, "code", "temporary"), retry_after=getattr(error, "retry_after", 0))

    def folder_action(self, action, folder, *, confirmed=False):
        if folder not in {f["name"] for f in self.state.get("folders", [])}:
            raise MailboxError("Choose a discovered mailbox folder.")
        if action == "mark_folder_read":
            if not confirmed:
                raise MailboxError("Confirm Mark folder read first.")
            result = self.imap.mark_folder_read(folder)
            marked = set(result["uids"])
            for m in [*self.state.get("snapshot", {}).get("messages", []), *self.state.get("conversation", [])]:
                if m["folder"] == folder and m["uidvalidity"] == result["uidvalidity"] and m["uid"] in marked:
                    self._apply_flag(m, "\\Seen", True)
            self._folder_count(folder, result["unread"])
            self._refresh_rows(membership_changed=False)
            from support_email_notifications import invalidate
            invalidate()
            self.audit("email_folder_marked_read", folder)
        else:
            if action == "search_folder" and folder == self.state.get("folder"):
                return  # Focus the existing search control without another mailbox read.
            if folder != self.state.get("folder"):
                self.state.update(folder=folder, selected=None, conversation=[], query="")
            self.cache.clear()
            self.load()  # Keeps discovered folders and opened bodies cached.

    def open_notification(self, target):
        """Deep link resolution belongs exclusively to the authorised Email page."""
        if not str(target.get("uid", "")).isdigit() or not str(target.get("uidvalidity", "")).isdigit():
            return
        self.state.update(folder="INBOX", query="", selected=None, conversation=[])
        self.load()
        if self.state.get("error"):
            return
        try:
            message = self.imap.notification_target(target["uidvalidity"], target["uid"], target.get("message_id", ""))
            if not message:
                self.state["notice"] = "This email is no longer in Inbox. The current Inbox is shown."
                return
            threads = self.state["threads"]
            thread = next((t for t in threads if any(reference_key(m) == reference_key(message) for m in t["messages"])), None)
            if thread is None:
                thread = build_threads([message], self.config.address)[0]
                threads.insert(0, thread)
                self.state["thread_index"][thread["thread_key"]] = thread
                self.state.pop("list_model", None)
            self._select_thread(thread)
            self.state.update(active_message=reference_key(message), expanded={reference_key(message)})
            self._body(message)
            self._read_visible(message)
        except Exception as error:
            LOGGER.info("Email notification target unavailable (%s)", type(error).__name__)
            self.state["notice"] = "Could not open that email. The current Inbox is shown."

    def resolve_thread(self, thread_key, version):
        if self.state.get("error") or thread_key != self.state.get("selected") or version != self.state["mailbox_version"]:
            return
        thread = self._thread()
        cache_key = (version, thread_key)
        self.state["history_pending"] = False
        if not thread or self.resolved_threads.get(cache_key) is not None:
            return
        identifiers = list(dict.fromkeys(i for m in thread["messages"]
                          for i in [*m["references"], *m["in_reply_to"], m["message_id"]] if i))
        all_messages = list(thread["messages"])
        folders = list(dict.fromkeys(f for f in [self.state["folder"], self.roles.get("inbox"), self.roles.get("sent")] if f))
        try:
            if identifiers:
                all_messages.extend(self.imap.related_headers_many(folders, identifiers))
        except Exception as error:
            LOGGER.info("Email history unavailable (%s)", type(error).__name__)
            if isinstance(error, MailboxError) and error.code == 'pending':
                self.state['history_pending'] = True
                return
            self.state["notice"] = "Message loaded. Older conversation history is temporarily unavailable."
            return
        unique = {}
        for message in all_messages:
            unique.setdefault(message["message_id"] or reference_key(message), message)
        groups = build_threads(list(unique.values()), self.config.address)
        group = next((t for t in groups if set(t["aliases"]).intersection(thread["aliases"])), thread)
        self.state["conversation"] = group["messages"]
        self.resolved_threads.put(cache_key, group["messages"])

    def _sync_draft(self, payload):
        draft = self.state.get("draft")
        if not draft or not payload or payload.get("id") != draft["id"]:
            return
        if self.state.get("send_result", {}).get("status") in {"accepted", "unknown", "in_progress"} or self.state.get("draft_pending"):
            return
        for key in ("to", "cc", "bcc", "subject"):
            value = str(payload.get(key, draft[key]))
            if len(value) > 4000:
                raise ComposeError("A compose field is too long.")
            draft[key] = value
        markup = payload.get("html", draft["html"])
        if markup != draft["html"]:
            draft["html"] = sanitize_html(markup)
        if payload.get("signature") in {"company", "nathan", "reina", "none"}:
            draft["signature"] = payload["signature"]
        draft["include_quote"] = bool(payload.get("include_quote", draft["include_quote"]))

    def handle(self, event):
        if not os_accounts.can_access_page(self.user, "Email"):
            raise PermissionError("Email permission required.")
        if not isinstance(event, dict) or not event.get("id"):
            return False
        try:
            event_id = str(uuid.UUID(str(event["id"])))
        except ValueError:
            return False
        if event_id == self.state.get("ack") or event_id in self.state["processed"]:
            return False
        if len(self.state["processed"]) > 10000:
            raise MailboxError("Session action limit reached. Reopen Email.")
        # Heartbeats are idempotent and TTL guarded; do not consume the action ledger forever.
        if event.get("action") != "live_check":
            self.state["processed"].add(event_id)
        self.state["ack"] = event_id
        if event.get("action") != "live_check" and not (event.get("action") in {"confirm_delete_forever", "cancel_delete_forever"}
                and event.get("token") != self.state.get("delete_confirmation", {}).get("token")):
            self.state["notice"] = ""
        self.state.pop("download", None)
        try:
            self._sync_draft(event.get("draft"))
            action = event.get("action")
            if action not in {"request_delete_forever", "confirm_delete_forever", "cancel_delete_forever", "live_check", "resolve_thread"}:
                self.state.pop("delete_confirmation", None)
            if action == "load_initial_mailbox":
                if self.state.pop("initial_load_pending", False):
                    self.load(defer_body=True)
            elif action == 'sync_index':
                for key in list(self.cache):
                    if key[0] == 'headers':self.cache.pop(key,None)
                self.load(previews=False,defer_body=True)
            elif action == "load_visible_body":
                key = self.state.get("body_pending")
                if key and key == self.state.get("active_message") and key == event.get("message_key"):
                    self.state.pop('body_pending',None)
                    message = self._header(key)
                    if self._body(message, defer=True) is not None and self.state.pop('body_mark_read',None) == key:
                        self._read_visible(message)  # Only the prior explicit Open action permits this.
            elif action == "reconnect":
                self.reconnect()
            elif action == "retry_connection":
                self.load(force=True)
            elif action == "live_check":
                self.live_check(event.get('signal_version'))
            elif action == "request_delete_forever":
                self.request_delete_forever(event.get("thread_key"))
            elif action == "cancel_delete_forever":
                if event.get("token") == self.state.get("delete_confirmation", {}).get("token"):
                    self.state.pop("delete_confirmation", None)
            elif action == "confirm_delete_forever":
                self.confirm_delete_forever(event.get("token"))
            elif action in {"refresh_folder", "search_folder", "mark_folder_read"}:
                self.folder_action(action, event.get("folder"), confirmed=event.get("confirmed") is True)
            elif action in {"refresh", "folder", "search", "load_more"}:
                if action == "folder":
                    if event.get("folder") not in {f["name"] for f in self.state.get("folders", [])}:
                        raise MailboxError("Choose a discovered mailbox folder.")
                    self.state.update(folder=event["folder"], query="", limit=50, selected=None, conversation=[], history_pending=False)
                elif action == "search":
                    query, field = str(event.get("query") or "").strip()[:256], "TEXT"
                    match = re.match(r"^(from|to|subject|text):\s*(.*)", query, re.I)
                    if match:
                        field, query = match[1].upper(), match[2]
                    self.state.update(query=query, field=field, limit=50, selected=None, conversation=[], history_pending=False)
                elif action == "load_more":
                    self.state["limit"] = min(1000, self.state["limit"] + 50)
                self.load(force=action == "refresh")
                if action == "refresh" and not self.state.get("error"):
                    self.audit("email_inbox_refreshed")
            elif action == "open_thread":
                self.open_thread(event.get("thread_key"))
            elif action == "resolve_thread":
                self.resolve_thread(event.get("thread_key"), event.get("mailbox_version"))
            elif action == "open_message":
                message = self._header(event.get("message_key"))
                self.state["active_message"] = reference_key(message)
                self.state["expanded"].add(reference_key(message))
                if self._body(message, defer=True) is not None:
                    self._read_visible(message)
                else:
                    self.state['body_mark_read'] = reference_key(message)
            elif action in {"mark_read", "mark_unread", "star", "unstar", "archive", "trash", "junk", "move", "copy"}:
                self.message_action(action, self._header(event.get("message_key")), event.get("destination"))
            elif action == "download":
                message = self._header(event.get("message_key"))
                self._validate_part(message, event.get("section"))
                file = self.imap.read_attachment(message, event["section"])
                self.state["download"] = {"id": event_id, "filename": file["filename"], "base64": base64.b64encode(file["data"]).decode()}
            elif action == "compose":
                if self.state.get("send_stage") in {"SENDING", "SAVING_SENT_COPY"}:
                    raise ComposeError("Wait for the current send to finish.")
                mode = event.get("mode", "new")
                if mode not in {"new", "reply", "reply_all", "forward"}:
                    raise ComposeError("Unknown compose action.")
                message, text = None, ""
                if mode != "new":
                    message = self._header(event.get("message_key"))
                    text = self._body(message)["text"]
                    thread = next((t for t in self.state["threads"] if any(reference_key(m) == reference_key(message) for m in t["messages"])), self._thread())
                    if thread:
                        self._select_thread(thread)
                    self._read_visible(message)
                self.state["draft"] = new_draft(self.config.address, mode=mode, header=message, text=text,
                    signature=selected_signature(self.state["settings"], self.user, self.state.get("preference")))
                if mode != "new":
                    thread = self._thread()
                    self.state["draft"]["source_thread"] = {"thread_key": thread["thread_key"], "aliases": thread["aliases"]}
                self.state.update(view="compose", send_result={}, sent_result={}, send_progress={}, sent_checks=0, draft_pending=None, send_stage="")
            elif action in {"attach", "remove_attachment", "forward_attachment"}:
                draft = self._editable_draft()
                if action == "attach":
                    add_attachment(draft, attachment_from_upload(event.get("filename"), event.get("base64")))
                elif action == "remove_attachment":
                    draft["attachments"] = [a for a in draft["attachments"] if a["id"] != event.get("attachment_id")]
                else:
                    if draft["mode"] != "forward":
                        raise ComposeError("Open a forward before adding an original attachment.")
                    message = self._header(event.get("message_key"))
                    self._validate_part(message, event.get("section"))
                    file = self.imap.read_attachment(message, event["section"])
                    add_attachment(draft, make_attachment(file["filename"], file["data"]))
            elif action == "send":
                self.send(event.get("operation_id"))
            elif action == "advance_send":
                self.advance_send(event.get("operation_id"))
            elif action == "retry_rejected":
                if self.state.get("send_result", {}).get("status") != "rejected":
                    raise ComposeError("Only a known rejected send can be prepared again.")
                self.state["draft"]["operation_id"] = str(uuid.uuid4())
                self.state["send_result"] = {}
            elif action == "check_sent":
                self.check_sent(operation_id=event.get("operation_id"))
            elif action == "retry_sent_copy":
                self.check_sent(retry=True, operation_id=event.get("operation_id"))
            elif action == "auto_check_sent":
                self.check_sent(automatic=True, operation_id=event.get("operation_id"))
            elif action == "save_draft":
                self.save_draft()
            elif action == "edit_draft":
                if self.state.get("send_stage") in {"SENDING", "SAVING_SENT_COPY"}:
                    raise ComposeError("Wait for the current send to finish.")
                message = self._header(event.get("message_key"))
                if message["folder"] != self.roles.get("drafts"):
                    raise ComposeError("Only messages in the mapped Drafts folder can be edited.")
                self.state["draft"] = edit_mailbox_draft(self.imap.read_draft(message), self.config.address, message)
                thread = self._thread()
                self.state["draft"]["source_thread"] = {"thread_key": thread["thread_key"], "aliases": thread["aliases"]}
                self.state.update(view="compose", send_result={}, sent_result={}, send_progress={}, sent_checks=0, draft_pending=None, send_stage="")
            elif action == "discard_draft":
                draft = self._editable_draft()
                if draft and draft.get("mailbox_ref"):
                    self._trash_draft(draft["mailbox_ref"])
                self.state.update(draft=None, draft_pending=None, view="mail", send_result={})
            elif action in {"close_composer", "close_panel", "resume_composer", "settings", "context"}:
                if action == "context":
                    self.load_context()
                self.state["view"] = {"close_composer": "mail", "close_panel": "mail", "resume_composer": "compose"}.get(action, action)
            elif action == "workflow":
                self.save_workflow(event)
            elif action == "test_connection":
                self.state.pop("folder_cache", None)
                result = self.imap.test_connection()
                self.state["notice"] = f"Connected securely. INBOX accessible · {result['count']} messages."
            elif action == "save_settings":
                if not self.state.get("settings_available"):
                    raise store.SupportStorageError("Apply the Email settings migration before saving settings.")
                values = event.get("settings", {})
                store.save_email_settings(self.config.address, actor=self.user, sender_name=values.get("sender_name", ""),
                    signatures=values.get("signatures", {}), folder_mapping=values.get("folder_mapping", {}),
                    sent_policy=values.get("sent_policy", "verify"), discovered_names={f["name"] for f in self.state["folders"]})
                self.load(force=True)
                self.state["notice"] = "Email settings saved."
            elif action == "save_preference":
                store.save_email_preference(self.config.address, actor=self.user, signature_key=event.get("signature"))
                self.state["preference"] = event["signature"]
                self.state["notice"] = "Your signature preference was saved."
            else:
                raise ComposeError("Unknown Email action.")
        except (MailboxError, ComposeError, store.SupportStorageError) as error:
            if self.state.get("send_stage") == "VALIDATING":
                self.state.update(send_stage="VALIDATION_FAILED", send_progress={})
            self.state["notice"] = "Could not update message. Try again." if event.get("action") in {
                "mark_read", "mark_unread", "star", "unstar", "move", "copy", "archive", "trash", "junk"} else str(error)
            if event.get("action") in {"open_thread", "open_message"} and self.state.get("recovery_state"):
                self.state["connection_notice"] = self.state["notice"]
            if event.get("action") == "test_connection":
                self.state["error"] = "Connection unavailable. Refresh to reconnect."
        except Exception as error:
            LOGGER.warning("Email action failed (%s)", type(error).__name__)
            self.state["notice"] = "Could not complete this Email action. Refresh and try again."
            if self.state.get("send_stage") == "VALIDATING":
                self.state.update(send_stage="VALIDATION_FAILED", send_progress={})
        return True

    def request_delete_forever(self, thread_key):
        """Freeze the exact visible Trash row membership for explicit confirmation."""
        if self.state.get("delete_confirmation"):
            return
        folder = self.roles.get("trash")
        thread = self.state.get("thread_index", {}).get(thread_key)
        if (not folder or self.state.get("folder") != folder or self.state["view"] != "mail" or
                self.state.get("error") or not thread):
            raise MailboxError("Select a conversation in Trash before deleting permanently.")
        # Never use the expanded cross-folder reading-pane conversation as a delete target.
        messages = [dict(m) for m in thread["messages"] if m["folder"] == folder]
        if not messages or len(messages) != len(thread["messages"]):
            raise MailboxError("Refresh Trash before deleting this conversation.")
        self.state["delete_confirmation"] = {"token": str(uuid.uuid4()), "folder": folder,
            "thread_key": thread_key, "subject": thread["subject"], "messages": messages}

    def confirm_delete_forever(self, token):
        pending = self.state.get("delete_confirmation")
        if not pending or not token or token != pending["token"]:
            return
        # Consume before I/O: replayed confirmations/reruns cannot issue another command.
        self.state.pop("delete_confirmation", None)
        if (self.state["view"] != "mail" or self.state.get("folder") != pending["folder"] or
                self.roles.get("trash") != pending["folder"]):
            raise MailboxError("Return to Trash and confirm this deletion again.")
        try:
            result = self.imap.delete_trash_messages(pending["messages"], trash_folder=pending["folder"],
                folder_mapping=self.state["settings"].get("folder_mapping"))
            if result.get("status") != "deleted":
                raise MailboxError("Deletion was not confirmed.")
        except Exception as error:
            LOGGER.warning("Email permanent deletion unconfirmed type=%s", type(error).__name__)
            self.state["notice"] = (str(error) if isinstance(error, MailboxError) else
                "Could not permanently delete this email. Please try again.")
            return
        keys = {reference_key(m) for m in pending["messages"]}
        snapshot = self.state.get("snapshot", {})
        removed = [m for m in snapshot.get("messages", []) if reference_key(m) in keys]
        snapshot["messages"] = [m for m in snapshot.get("messages", []) if reference_key(m) not in keys]
        for count in ("total", "matched"):
            if isinstance(snapshot.get(count), int):
                snapshot[count] = max(0, snapshot[count] - len(removed))
        self.state["threads"] = sorted(build_threads(snapshot["messages"], self.config.address), key=lambda t: t["last_activity"], reverse=True)
        self.state["thread_index"] = {t["thread_key"]: t for t in self.state["threads"]}
        if self.state.get("selected") == pending["thread_key"]:
            self.state.update(selected=None, active_message=None, conversation=[], expanded=set(), history_pending=False, context={})
        self.bodies.remove_where(lambda k: any(k == self._content_key(m) for m in pending["messages"]))
        self._refresh_rows()
        self.audit("email_permanently_deleted", "|".join(sorted(keys)))
        self.load(force=True, previews=False)
        self.state["notice"] = "Permanently deleted from Trash."
        if self.state.get("live_error") or self.state.get("error"):
            self.state["notice"] += " Trash refresh is temporarily unavailable."

    def message_action(self, action, message, destination=None):
        if action in {"mark_read", "mark_unread", "star", "unstar"}:
            flag, enabled = ("\\Seen" if action.startswith("mark_") else "\\Flagged"), action in {"mark_read", "star"}
            if (flag in message["flags"]) == enabled:
                return
            was_unread = message["unread"]
            self.imap.set_flag(message, flag, enabled)
            self._apply_flag(message, flag, enabled)
            if flag == "\\Seen":
                folder = next((f for f in self.state["folders"] if f["name"] == message["folder"]), {})
                if isinstance(folder.get("unread"), int):
                    self._folder_count(message["folder"], folder["unread"] + (-1 if was_unread else 1))
            self.audit("email_" + action if action.startswith("mark_") else "email_flag_changed", reference_key(message))
        else:
            destination = destination if action in {"move", "copy"} else self.roles.get(action)
            if destination not in {f["name"] for f in self.state["folders"]} or destination == message["folder"]:
                raise MailboxError("Map this folder in Email settings first.")
            result = self.imap.copy_message(message, destination) if action == "copy" else self.imap.move_message(message, destination)
            self.state["notice"] = result.get("notice", "Message copied." if result["status"] == "copied" else "Message moved.")
            if result["status"] == "moved":
                key = reference_key(message)
                snapshot = self.state.get("snapshot", {})
                snapshot["messages"] = [m for m in snapshot.get("messages", []) if reference_key(m) != key]
                if message["folder"] == self.state["folder"]:
                    for count in ("total", "matched"):
                        if isinstance(snapshot.get(count), int):
                            snapshot[count] = max(0, snapshot[count] - 1)
                self.state["conversation"] = [m for m in self.state.get("conversation", []) if reference_key(m) != key]
                self.state["threads"] = build_threads(snapshot["messages"], self.config.address)
                self.state["threads"].sort(key=lambda t: t["last_activity"], reverse=True)
                self.state["thread_index"] = {t["thread_key"]: t for t in self.state["threads"]}
            if message["unread"]:
                for folder in self.state["folders"]:
                    if isinstance(folder.get("unread"), int):
                        if folder["name"] == destination:
                            self._folder_count(destination, folder["unread"] + 1)
                        elif folder["name"] == message["folder"] and result["status"] == "moved":
                            self._folder_count(message["folder"], folder["unread"] - 1)
            self.audit({"archive": "email_archived", "trash": "email_trashed", "junk": "email_junked"}.get(action, "email_moved")
                       if result["status"] == "moved" else "email_copied", reference_key(message))
        self._refresh_rows(membership_changed=action not in {"mark_read", "mark_unread", "star", "unstar"})
        from support_email_notifications import invalidate
        invalidate()

    def _editable_draft(self):
        draft = self.state.get("draft")
        if not draft or self.state.get("send_result", {}).get("status") in {"accepted", "unknown", "in_progress"}:
            raise ComposeError("This compose session cannot be changed. Open New mail for another message.")
        if self.state.get("draft_pending"):
            raise ComposeError("Resolve the previous draft save before editing it.")
        return draft

    def _validate_part(self, header, section):
        if section not in {a["section"] for a in self._body(header)["attachments"]}:
            raise MailboxError("Attachment is not available in this message.")

    def _send_progress(self, percent, label):
        # Pure state update: never call Streamlit from inside SMTP/IMAP I/O.
        self.state["send_stage"] = "SAVING_SENT_COPY" if percent == 100 else "SENDING"
        report_progress(self.progress, percent, label)

    def send(self, operation_id):
        """An explicit Send click validates and freezes the exact outgoing MIME once."""
        old = self.state.get("send_result", {})
        if old.get("operation_id") == operation_id and old.get("status"):
            return
        draft = self.state.get("draft")
        if not draft or operation_id != draft["operation_id"]:
            raise ComposeError("Send session changed. Review the current draft before sending.")
        if old.get("status") in {"accepted", "unknown", "in_progress", "rejected"}:
            self.state["notice"] = old["notice"]
            return
        if self.state.get("draft_pending"):
            raise ComposeError("Resolve the pending draft save before sending.")
        if len(self.state.get("pending_sent", {})) >= 5:
            raise ComposeError("Save the pending Sent copies before sending more messages. No email was sent.")
        # handle() enforces Email access for every action. Optional support-workflow
        # metadata is not transport authorization: all permitted users share this
        # send path, even when that metadata is unavailable or marked for review.
        self.state["send_stage"] = "VALIDATING"
        mime = build_mime(draft, self.config.address, self.state["settings"]["sender_name"], self.state["settings"]["signatures"])
        self.state["outgoing_mime"] = mime
        self.state.update(send_result={"status": "in_progress", "operation_id": operation_id, "notice": "Sending…"},
                          send_stage="SENDING", send_progress={}, send_finalized=False)

    def recover_send(self):
        """Reconcile an interrupted run from metadata only; rendering cannot send mail."""
        result = self.state.get("send_result", {})
        if result.get("status") == "in_progress":
            receipt = self.registry.get(result.get("operation_id"), self.config.address)
            if receipt and receipt.get("status") != "in_progress":
                self.state["send_result"] = receipt
                self.state["send_stage"] = "SAVING_SENT_COPY" if receipt["status"] == "accepted" else receipt["status"].upper()

    def advance_send(self, operation_id):
        """Continue only a previously confirmed send, using its frozen bytes and receipt."""
        self.recover_send()
        result = self.state.get("send_result", {})
        if not operation_id or operation_id != result.get("operation_id") or self.state.get("send_finalized"):
            return
        if result.get("status") == "in_progress" and self.state.get("outgoing_mime"):
            result = self.registry.submit(operation_id, self.config.address, self.state["outgoing_mime"], self.smtp,
                                          progress=self._send_progress)
            self.state.update(send_result=result, send_progress={},
                              send_stage="SAVING_SENT_COPY" if result["status"] == "accepted" else result["status"].upper())
            # Complete accepted delivery even if the browser disconnects now. No Streamlit
            # calls occur between SMTP acceptance and saving its mailbox copy.
        if result.get("status") == "accepted":
            self._finish_send()

    def _finish_send(self):
        s, result, draft = self.state, self.state["send_result"], self.state.get("draft") or {}
        if s.get("last_sent", {}).get("operation_id") != result["operation_id"]:
            s["last_sent"] = {"operation_id": result["operation_id"], "mime": s["outgoing_mime"],
                              "result": dict(result), "subject": draft.get("subject", ""), "checks": 0}
        delivery = s["last_sent"]
        if not delivery.get("audited"):
            delivery["audited"] = True
            action = "email_reply_sent" if draft.get("mode") in {"reply", "reply_all"} else "email_forward_sent" if draft.get("mode") == "forward" else "email_sent"
            self.audit(action, result["message_id"])
        self.check_sent()
        if draft.get("mailbox_ref") and not delivery.get("draft_cleanup_attempted"):
            delivery["draft_cleanup_attempted"] = True
            try:
                self._trash_draft(draft["mailbox_ref"])
            except Exception:
                delivery["draft_warning"] = "The saved draft remains in Drafts; do not send it again."
        try:
            self._show_sent(delivery)
        except Exception as error:
            LOGGER.warning("Email Sent view unavailable (%s)", type(error).__name__)
            self.state["notice"] = "Email sent. Sent-folder refresh is temporarily unavailable; refresh Sent to view it."
        s.update(send_stage="SENT", send_progress={}, send_finalized=True, draft=None, draft_pending=None, view="mail")

    def _show_sent(self, delivery):
        folder = self.roles.get("sent")
        if not folder:
            return
        self.state.update(folder=folder, query="", field="TEXT", limit=50, selected=None,
                          conversation=[], history_pending=False, view="mail", load_retry_at=0)
        self._mailbox_changed()
        self.load()  # Reload real IMAP headers, including mail sent by other clients.
        thread = next((t for t in self.state.get("threads", []) if any(
            m["message_id"] == delivery["mime"]["message_id"] for m in t["messages"])), None)
        if thread:
            try:
                self.open_thread(thread["thread_key"])
            except MailboxError:
                self.state["notice"] = "Sent. The message body is temporarily unavailable; reopen it in Sent."

    def check_sent(self, *, automatic=False, operation_id=None, retry=False):
        result = self.state.get("send_result", {})
        delivery = self.state.get("pending_sent", {}).get(operation_id) or self.state.get("last_sent", {})
        # Uncertain transport outcomes can only be searched, never appended.
        if result.get("status") == "unknown" and not operation_id:
            self.state["sent_result"] = reconcile_sent(self.imap, self.state["outgoing_mime"], self.roles.get("sent"))
            return
        if not delivery or (operation_id and operation_id != delivery["operation_id"]):
            return
        retry = retry and delivery.get("copy", {}).get("retryable") is True
        if automatic:
            if (delivery.get("checks", 0) >= 3 or delivery.get("copy", {}).get("status") in {"present", "appended"}
                    or time.monotonic() - self.state.get("sent_check_at", 0) < 5):
                return
            delivery["checks"] = delivery.get("checks", 0) + 1
        self.state["sent_check_at"] = time.monotonic()
        # Legacy verify default now ensures a copy. Explicit confirmed server-saving is respected.
        policy = "verify" if automatic or self.state["settings"]["sent_policy"] == "server" else "append"
        if retry:
            policy = "append"
        previous = delivery.get("copy", {}).get("status")
        delivery["copy"] = self.registry.save_sent(delivery["operation_id"], self.config.address, self.imap,
            delivery["mime"], self.roles.get("sent"), policy, retry=retry)
        pending = self.state.setdefault("pending_sent", {})
        if delivery["copy"]["status"] in {"present", "appended"}:
            pending.pop(delivery["operation_id"], None)
        else:
            pending[delivery["operation_id"]] = delivery
        if result.get("operation_id") == delivery["operation_id"]:
            self.state.update(sent_result=delivery["copy"], sent_checks=delivery.get("checks", 0))
        if (self.state.get("send_finalized") and delivery["copy"]["status"] in {"present", "appended"}
                and (retry or previous not in {"present", "appended"}) and self.state["view"] != "compose"):
            self._show_sent(delivery)

    def save_draft(self):
        draft = self.state.get("draft")
        if not draft or self.state.get("send_result", {}).get("status") in {"accepted", "unknown", "in_progress"}:
            raise ComposeError("This compose session cannot be saved again.")
        folder = self.roles.get("drafts")
        if not folder:
            raise ComposeError("Map the real Drafts folder in Email settings first.")
        pending = self.state.get("draft_pending")
        if not pending:
            draft["revision"] += 1
            mime = build_mime(draft, self.config.address, self.state["settings"]["sender_name"], self.state["settings"]["signatures"], as_draft=True)
            pending = {"mime": mime, "attempted": False}
            self.state["draft_pending"] = pending
        found = self.imap.find_message_id(folder, pending["mime"]["message_id"])
        if not found and not pending["attempted"]:
            pending["attempted"] = True
            self.imap.append_message(folder, pending["mime"]["bytes"], draft=True)
        matches = self.imap.related_headers(folder, [pending["mime"]["message_id"]])
        saved = next((m for m in matches if m["message_id"] == pending["mime"]["message_id"]), None)
        if not saved:
            raise ComposeError("Draft save needs verification. Click Save draft to check again; no duplicate will be appended.")
        old = draft.get("mailbox_ref")
        draft["mailbox_ref"], self.state["draft_pending"] = saved, None
        self.state["notice"] = "Draft saved in the real mailbox."
        if old and reference_key(old) != reference_key(saved):
            try:
                self._trash_draft(old)
            except MailboxError:
                self.state["notice"] += " Previous draft version remains; remove it in your mail client."
        self.audit("email_draft_saved", pending["mime"]["message_id"])
        self._mailbox_changed()

    def _mailbox_changed(self):
        """Known writes invalidate membership, not immutable MIME display content."""
        self.cache.clear()
        self.resolved_threads.clear()
        self.state["mailbox_version"] += 1
        self.state["history_pending"] = bool(self.state.get("selected"))

    def _trash_draft(self, header):
        destination = self.roles.get("trash")
        if not destination:
            raise MailboxError("Map Trash before discarding a saved draft.")
        result = self.imap.move_message(header, destination)
        self._mailbox_changed()
        self.state["notice"] = result.get("notice", self.state["notice"])
        self.audit("email_draft_discarded" if result["status"] == "moved" else "email_copied", reference_key(header))

    def load_context(self):
        thread = self._thread()
        if not thread:
            raise MailboxError("Open a conversation first.")
        context = {"workflow_available": False, "workflow": {}, "assignees": [], "order_error": ""}
        try:
            metadata = store.load_metadata(self.config.address, thread["aliases"])
            context.update(workflow=workflow_for_thread(thread, metadata), assignees=store.load_assignees(), workflow_available=True)
        except Exception:
            pass
        body = "\n".join(content["body"]["text"] for m in self.state.get("conversation", [])
                         if reference_key(m) in self.state["expanded"] and (content := self._content(m)))
        numbers = set().union(*(order_numbers(m["subject"]) for m in thread["messages"])) | order_numbers(body)
        try:
            override = context["workflow"].get("matched_order_id")
            orders = store.load_orders([thread["customer"]["email"]], sorted(numbers), [override] if override else [])
            context["match"] = match_orders(thread, orders, body=body, override=override)
        except Exception:
            context["order_error"] = "Synced order context is unavailable."
        self.state["context"] = context

    def save_workflow(self, event):
        context, thread = self.state.get("context", {}), self._thread()
        if not thread or not context.get("workflow_available") or context["workflow"].get("conflict"):
            raise store.SupportStorageError("Workflow editing is unavailable for this conversation.")
        previous = context["workflow"]
        store.save_workflow(self.config.address, previous.get("thread_key") or thread["thread_key"], actor=self.user,
            support_status=event.get("status"), assigned_user_id=event.get("assigned") or None,
            internal_notes=event.get("notes", ""), needs_approval=bool(event.get("approval")), previous=previous)
        self.load_context()
        self.state["notice"] = "Support workflow saved."

    def model(self):
        """Whitelisted browser payload: no credentials, raw MIME or unsolicited attachment bytes."""
        self.recover_send()
        s, user = self.state, self.user
        if "list_model" not in s:
            s["list_model"] = self._list_model()
        threads = s["list_model"] if not s.get("error") else []
        conversation = []
        reply_prompts = []
        prompt_source = None
        if not s.get("error"):
            for m in s.get("conversation", []):
                key = reference_key(m)
                content = self._content(m) if key in s["expanded"] else None
                body = content["body"] if content else None
                row = {"key": key, "sender": m["sender"], "subject": m["subject"], "to": m["to"], "cc": m["cc"],
                    "time": formatted_date(m["date"] or m["received_at"], user), "folder": m["folder"],
                    "own": m["sender"]["email"].casefold() == self.config.address.casefold(), "unread": m["unread"],
                    "starred": "\\Flagged" in m["flags"], "expanded": bool(body), "attachments": [], "draft": m["folder"] == self.roles.get("drafts")}
                if body:
                    row.update(html=content["html"], reader_document=content.get("reader_document", ""), quote=content["quote"], warnings=body.get("warnings", []),
                        attachments=[{k: a[k] for k in ("section", "filename", "content_type", "encoded_size")} for a in body["attachments"]])
                if body and key == s.get("active_message") and s.get("view") == "compose" and (s.get("draft") or {}).get("mode") == "reply":
                    from support_email_reply_prompts import build_reply_prompts
                    prompt_source = (m, {"html": content["html"], "review": body.get("review")})
                conversation.append(row)
        if prompt_source:
            from support_email_reply_prompts import clean_text
            # Only reuse already-rendered messages and an existing, unambiguous match.
            # No extra body reads, order queries, or provider calls for the menu.
            history = [{'sender_name': row['sender'].get('name', ''), 'own': row['own'],
                        'message': clean_text(row['html'])} for row in conversation
                       if row.get('html') and row['key'] != s.get('active_message')]
            match = s.get('context', {}).get('match', {})
            order = match.get('order') if match.get('state') == 'matched' else None
            safe_order = {k: order[k] for k in ('order_name', 'customer_name', 'created_at', 'fulfillment_status')
                          if k in order} if order else {}
            if order:
                safe_order['lines'] = [{k: line[k] for k in ('product_title', 'variant_title') if k in line}
                                       for line in order.get('lines', [])]
            reply_prompts = build_reply_prompts(*prompt_source, thread_context=history, order_context=safe_order)
        draft = s.get("draft")
        public_draft = None
        if draft:
            public_draft = {k: draft[k] for k in ("id", "operation_id", "mode", "to", "cc", "bcc", "subject", "html", "signature", "include_quote", "quote_html")}
            public_draft.update(attachments=[{"id": a["id"], "filename": a["filename"], "size": len(a["data"])} for a in draft["attachments"]], saved=bool(draft.get("mailbox_ref")))
        settings = s["settings"]
        signature_source = tuple((key, value.get("label", key), value.get("html", ""))
                                 for key, value in settings["signatures"].items() if key in {"company", "nathan", "reina"})
        if s.get("signature_source") != signature_source:
            s["signature_model"] = {key: {"label": label, "html": sanitize_signature(markup)} for key, label, markup in signature_source}
            s["signature_source"] = signature_source
        signatures = s["signature_model"]
        return {"mailbox": self.config.address, "configured": self.config.configured,
            "inbox_status": s.get("inbox_status", {}),
            "smtp_configured": self.smtp_config.configured and self.smtp_config.address.casefold() == self.config.address.casefold(),
            "error": s.get("error", ""), "live_error": s.get("live_error", ""), "notice": s["notice"] or s.get("live_error", ""), "ack": s.get("ack", ""),
            "recovery": {"state": s.get("recovery_state", ""), "message": s.get("connection_message", ""),
                         "delay_ms": max(0, int((s.get("load_retry_at", 0) - time.monotonic()) * 1000))},
            "mailbox_version": s["mailbox_version"], "history_pending": s["history_pending"],
            "idle_version": s.get("idle_version", ""),
            "refreshed": formatted_date((s.get("snapshot", {}).get("refreshed_at") if hasattr(self.imap, 'reads') else s.get("refreshed_at")), user), "folders": ordered_folders(s.get("folders", []), self.roles), "roles": self.roles,
            "folder": s.get("folder", ""), "query": s["query"], "field": s["field"], "threads": threads,
            "selected": s.get("selected"), "messages": conversation, "active_message": s.get("active_message"),
            "delete_confirmation": ({"token": s["delete_confirmation"]["token"], "subject": s["delete_confirmation"]["subject"],
                "count": len(s["delete_confirmation"]["messages"])} if s.get("delete_confirmation") else None),
            "initial_load_pending": bool(s.get("initial_load_pending")),
            "read_pending": bool(s.get('read_pending')), "body_loading": bool(s.get('body_loading')),
            "live_pending": bool(s.get('live_pending')),
            "sync_health": (dict(self.imap.reads.health) if hasattr(self.imap,'reads') else {}),
            "body_pending": s.get("body_pending"), "view": s["view"], "reply_prompts": reply_prompts, "draft": public_draft, "has_more": s.get("snapshot", {}).get("has_more", False) and s["limit"] < 1000,
            "signature_logo": logo_data_uri() if s["view"] in {"compose", "settings"} else "",
            "matched": s.get("snapshot", {}).get("matched", 0), "limit": s["limit"], "send_result": s.get("send_result", {}),
            "send_stage": s.get("send_stage", ""), "send_progress": s.get("send_progress", {}), "sent_result": s.get("sent_result", {}), "sent_checks": s.get("sent_checks", 0),
            "last_sent": {k: s.get("last_sent", {}).get(k) for k in ("operation_id", "subject", "result", "copy", "checks", "draft_warning")},
            "pending_sent": [{k: d.get(k) for k in ("operation_id", "subject", "copy", "checks", "draft_warning")}
                             for d in s.get("pending_sent", {}).values() if d["operation_id"] != s.get("last_sent", {}).get("operation_id")],
            "download": s.get("download"), "settings": {"sender_name": settings["sender_name"], "sent_policy": settings["sent_policy"],
            "folder_mapping": settings["folder_mapping"], "signatures": signatures}, "settings_available": s.get("settings_available", False),
            "admin": os_accounts.is_admin(user), "signature_preference": selected_signature(settings, user, s.get("preference")),
            "context": self.context_model(), "draft_pending": bool(s.get("draft_pending"))}

    def _list_model(self):
        return [{"key": t["thread_key"], "customer": t["customer"]["name"] or t["customer"]["email"],
            "email": t["customer"]["email"], "subject": t["subject"], "time": formatted_date(t["last_activity_at"], self.user),
            "unread": bool(t["unread"]), "count": len(t["messages"]), "snippet": t["messages"][-1].get("snippet", ""),
            "attachment": any(m.get("has_attachments") for m in t["messages"]),
            "starred": any("\\Flagged" in m["flags"] for m in t["messages"]),
            "message_key": reference_key(t["messages"][-1]), "message_unread": t["messages"][-1]["unread"],
            "message_starred": "\\Flagged" in t["messages"][-1]["flags"]} for t in self.state.get("threads", [])]
    def context_model(self):
        context = self.state.get("context", {})
        match, order = context.get("match", {}), context.get("match", {}).get("order")
        result = {"label": match.get("label", context.get("order_error", "")), "method": match.get("method", ""),
            "candidates": [{"name": o.get("order_name"), "date": formatted_date(o.get("created_at"), self.user)} for o in match.get("candidates", [])],
            "workflow_available": context.get("workflow_available", False),
            "workflow": {k: str(v) if k in {"assigned_user_id", "updated_at"} and v is not None else v for k, v in context.get("workflow", {}).items()
                         if k in {"support_status", "assigned_user_id", "internal_notes", "needs_approval", "conflict", "updated_at"}},
            "assignees": [{"id": str(u["id"]), "name": os_accounts.safe_account_label(u)} for u in context.get("assignees", [])]}
        if order:
            tracking = []
            for fulfillment in order.get("fulfillments") or []:
                if isinstance(fulfillment, dict):
                    tracking.extend(safe_url(u) for u in [fulfillment.get("tracking_url"), *(fulfillment.get("tracking_urls") or [])] if safe_url(u))
            result["order"] = {"name": order.get("order_name"), "date": formatted_date(order.get("created_at"), self.user),
                "fulfilment": order.get("fulfillment_status") or "Not recorded", "lines": order.get("lines", []),
                "editions": [{k: str(v) if k == "id" else v for k, v in e.items()} for e in order.get("editions", [])],
                "edition_url": "?" + urlencode({"page": os_accounts.page_key_for_route("Edition Ops"), "global_search": order.get("order_name") or ""}),
                "tracking": list(dict.fromkeys(tracking)), "shopify_url": safe_url(order.get("admin_url")),
                "os_url": "?" + urlencode({"page": "Orders", "global_search": order.get("order_name") or ""}),
                "previous": [{"name": o.get("order_name"), "date": formatted_date(o.get("created_at"), self.user)}
                             for o in match.get("previous", []) if o["shopify_order_id"] != order["shopify_order_id"]]}
        return result
