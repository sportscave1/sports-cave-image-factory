"""Event-driven mailbox controller; only explicit actions send or change mail."""
import base64
from datetime import datetime, timezone
import hashlib
import logging
import re
from urllib.parse import urlencode
import uuid
from zoneinfo import ZoneInfo

import os_accounts
from support_email_provider import ImapProvider, MailboxError, folder_roles
from support_email_logic import build_threads, cached_read, match_orders, order_numbers, workflow_for_thread
from support_email_compose import (ComposeError, default_settings, selected_signature, new_draft, build_mime,
    sanitize_html, readable_html, split_quote, attachment_from_upload, add_attachment, make_attachment,
    edit_mailbox_draft, safe_url)
from support_email_smtp import SMTPProvider, SEND_REGISTRY, reconcile_sent
import support_email_store as store

LOGGER = logging.getLogger(__name__)


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
    def __init__(self, state, user, imap_config, smtp_config, *, imap=None, smtp=None, registry=None):
        self.state, self.user, self.config, self.smtp_config = state, user, imap_config, smtp_config
        self.imap, self.smtp = imap or ImapProvider(imap_config), smtp or SMTPProvider(smtp_config)
        self.registry = registry or SEND_REGISTRY
        for key, default in {"cache": {}, "processed": set(), "limit": 50, "query": "", "field": "TEXT",
                             "settings": default_settings(), "expanded": set(), "notice": "", "view": "mail"}.items():
            state.setdefault(key, default)

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

    def load(self, *, force=False):
        if not self.config.configured:
            self.state.update(error="Mailbox is not configured.", folders=[], threads=[])
            return
        if force:
            self.cache.clear()
        if "settings_available" not in self.state or force:
            try:
                settings, preference = store.load_email_settings(self.config.address, self.user["id"])
                self.state.update(settings=settings, preference=preference, settings_available=True)
            except Exception:
                self.state["settings_available"] = False
        folders = cached_read(self.cache, ("folders",), self.imap.discover_folders)
        if folders["error"]:
            self.state.update(error="Could not load folders. Check the mailbox connection.", threads=[])
            return
        self.state["folders"] = folders["data"]["folders"]
        self.state["capabilities"] = list(folders["data"]["capabilities"])
        names = [f["name"] for f in self.state["folders"]]
        if not names:
            self.state.update(error="No selectable mailbox folders were returned.", threads=[])
            return
        if self.state.get("folder") not in names:
            self.state["folder"] = self.roles.get("inbox", names[0])
        key = ("headers", self.state["folder"], self.state["limit"], self.state["query"], self.state["field"])
        entry = cached_read(self.cache, key, lambda: self.imap.list_headers(self.state["limit"], self.state["folder"],
                            query=self.state["query"], field=self.state["field"], previews=True))
        if entry["error"]:
            self.state.update(error="Could not load folder. Refresh to reconnect.", threads=[])
            return
        snapshot = entry["data"]
        self.state.update(error="", refreshed_at=entry["refreshed_at"], snapshot=snapshot,
            threads=sorted(build_threads(snapshot["messages"], self.config.address), key=lambda t: t["last_activity"], reverse=True))
        if self.state.get("selected") and not any(t["thread_key"] == self.state["selected"] for t in self.state["threads"]):
            self.state.update(selected=None, conversation=[])
        self.state["loaded"] = True

    def _thread(self):
        return next((t for t in self.state.get("threads", []) if t["thread_key"] == self.state.get("selected")), None)

    def _header(self, key):
        if self.state.get("error"):
            raise MailboxError("Refresh the mailbox before taking this action.")
        for message in self.state.get("conversation", []):
            if reference_key(message) == key:
                return message
        raise MailboxError("Message is no longer selected. Refresh the mailbox.")

    def _body(self, message):
        result = cached_read(self.cache, ("body", reference_key(message)), lambda: self.imap.read_message(message))
        if result["error"]:
            raise MailboxError("Could not open this message. Refresh and try again.")
        return result["data"]

    def open_thread(self, thread_key):
        if self.state.get("error"):
            raise MailboxError("Refresh the mailbox before opening a conversation.")
        thread = next((t for t in self.state.get("threads", []) if t["thread_key"] == thread_key), None)
        if not thread:
            raise MailboxError("This conversation is no longer in the current list.")
        self.state.update(selected=thread_key, expanded=set(), view="mail", context={})
        identifiers = list(dict.fromkeys(i for m in thread["messages"]
                          for i in [*m["references"], *m["in_reply_to"], m["message_id"]] if i))
        all_messages = list(thread["messages"])
        for folder in dict.fromkeys([self.state["folder"], self.roles.get("inbox"), self.roles.get("sent")]):
            if folder and identifiers:
                related = cached_read(self.cache, ("related", folder, tuple(identifiers[:8])),
                                      lambda f=folder: self.imap.related_headers(f, identifiers))
                all_messages.extend(related["data"] or [])
        unique = {}
        for message in all_messages:
            unique.setdefault(message["message_id"] or reference_key(message), message)
        groups = build_threads(list(unique.values()), self.config.address)
        group = next((t for t in groups if set(t["aliases"]).intersection(thread["aliases"])), thread)
        self.state["conversation"] = group["messages"]
        active = next((m for m in reversed(group["messages"]) if m["folder"] == self.state["folder"]), group["messages"][-1])
        self.state["active_message"] = reference_key(active)
        self.state["expanded"].add(self.state["active_message"])
        self._body(active)

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
        draft["html"] = sanitize_html(payload.get("html", draft["html"]))
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
        if event_id in self.state["processed"]:
            return False
        if len(self.state["processed"]) > 10000:
            raise MailboxError("Session action limit reached. Reopen Email.")
        self.state["processed"].add(event_id)
        self.state.update(ack=event_id, notice="")
        self.state.pop("download", None)
        try:
            self._sync_draft(event.get("draft"))
            action = event.get("action")
            if action in {"refresh", "folder", "search", "load_more"}:
                if action == "folder":
                    if event.get("folder") not in {f["name"] for f in self.state.get("folders", [])}:
                        raise MailboxError("Choose a discovered mailbox folder.")
                    self.state.update(folder=event["folder"], query="", limit=50, selected=None, conversation=[])
                elif action == "search":
                    query, field = str(event.get("query") or "").strip()[:256], "TEXT"
                    match = re.match(r"^(from|to|subject|text):\s*(.*)", query, re.I)
                    if match:
                        field, query = match[1].upper(), match[2]
                    self.state.update(query=query, field=field, limit=50, selected=None, conversation=[])
                elif action == "load_more":
                    self.state["limit"] = min(1000, self.state["limit"] + 50)
                self.load(force=action == "refresh")
                if action == "refresh" and not self.state.get("error"):
                    self.audit("email_inbox_refreshed")
            elif action == "open_thread":
                self.open_thread(event.get("thread_key"))
            elif action == "open_message":
                message = self._header(event.get("message_key"))
                self.state["active_message"] = reference_key(message)
                self.state["expanded"].add(reference_key(message))
                self._body(message)
            elif action in {"mark_read", "mark_unread", "star", "unstar", "archive", "trash", "junk"}:
                self.message_action(action, self._header(event.get("message_key")))
            elif action == "download":
                message = self._header(event.get("message_key"))
                self._validate_part(message, event.get("section"))
                file = self.imap.read_attachment(message, event["section"])
                self.state["download"] = {"id": event_id, "filename": file["filename"], "base64": base64.b64encode(file["data"]).decode()}
            elif action == "compose":
                mode = event.get("mode", "new")
                if mode not in {"new", "reply", "reply_all", "forward"}:
                    raise ComposeError("Unknown compose action.")
                message, text = None, ""
                if mode != "new":
                    message = self._header(event.get("message_key"))
                    text = self._body(message)["text"]
                self.state["draft"] = new_draft(self.config.address, mode=mode, header=message, text=text,
                    signature=selected_signature(self.state["settings"], self.user, self.state.get("preference")))
                if mode != "new":
                    thread = self._thread()
                    self.state["draft"]["source_thread"] = {"thread_key": thread["thread_key"], "aliases": thread["aliases"]}
                self.state.update(view="compose", send_result={}, draft_pending=None)
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
            elif action == "retry_rejected":
                if self.state.get("send_result", {}).get("status") != "rejected":
                    raise ComposeError("Only a known rejected send can be prepared again.")
                self.state["draft"]["operation_id"] = str(uuid.uuid4())
                self.state["send_result"] = {}
            elif action == "check_sent":
                self.check_sent()
            elif action == "save_draft":
                self.save_draft()
            elif action == "edit_draft":
                message = self._header(event.get("message_key"))
                if message["folder"] != self.roles.get("drafts"):
                    raise ComposeError("Only messages in the mapped Drafts folder can be edited.")
                self.state["draft"] = edit_mailbox_draft(self.imap.read_draft(message), self.config.address, message)
                thread = self._thread()
                self.state["draft"]["source_thread"] = {"thread_key": thread["thread_key"], "aliases": thread["aliases"]}
                self.state.update(view="compose", send_result={}, draft_pending=None)
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
            self.state["notice"] = str(error)
            if event.get("action") == "test_connection":
                self.state["error"] = "Connection unavailable. Refresh to reconnect."
        except Exception as error:
            LOGGER.warning("Email action failed (%s)", type(error).__name__)
            self.state["notice"] = "Could not complete this Email action. Refresh and try again."
        return True

    def message_action(self, action, message):
        if action in {"mark_read", "mark_unread", "star", "unstar"}:
            self.imap.set_flag(message, "\\Seen" if action.startswith("mark_") else "\\Flagged", action in {"mark_read", "star"})
            self.audit("email_" + action if action.startswith("mark_") else "email_flag_changed", reference_key(message))
        else:
            destination = self.roles.get(action)
            if not destination:
                raise MailboxError("Map this folder in Email settings first.")
            result = self.imap.move_message(message, destination)
            self.state["notice"] = result.get("notice", "Message moved.")
            self.audit({"archive": "email_archived", "trash": "email_trashed", "junk": "email_junked"}[action]
                       if result["status"] == "moved" else "email_copied", reference_key(message))
        self.state.update(selected=None, conversation=[])
        self.load(force=True)

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

    def send(self, operation_id):
        draft = self.state.get("draft")
        if not draft or operation_id != draft["operation_id"]:
            raise ComposeError("Send session changed. Review the current draft before sending.")
        old = self.state.get("send_result", {})
        if old.get("status") in {"accepted", "unknown", "in_progress", "rejected"}:
            self.state["notice"] = old["notice"]
            return
        if self.state.get("draft_pending"):
            raise ComposeError("Resolve the pending draft save before sending.")
        # Always re-read a known workflow before sending a reply, rather than trusting a drawer visit.
        thread = draft.get("source_thread")
        if thread and draft["mode"] in {"reply", "reply_all", "forward"}:
            try:
                workflow = workflow_for_thread(thread, store.load_metadata(self.config.address, thread["aliases"]))
            except Exception:
                if not os_accounts.is_admin(self.user):
                    raise ComposeError("Approval metadata is unavailable. Nathan can review and send, or try again later.") from None
                workflow = {}
            if (workflow.get("needs_approval") or workflow.get("conflict")) and not os_accounts.is_admin(self.user):
                raise ComposeError("This conversation requires Nathan's approval. Save a mailbox draft for review.")
        mime = build_mime(draft, self.config.address, self.state["settings"]["sender_name"], self.state["settings"]["signatures"])
        self.state["outgoing_mime"] = mime
        self.state["send_result"] = {"status": "in_progress", "notice": "Sending…"}
        result = self.registry.submit(operation_id, self.config.address, mime, self.smtp)
        self.state["send_result"], self.state["notice"] = result, result["notice"]
        if result["status"] == "accepted":
            action = "email_reply_sent" if draft["mode"] in {"reply", "reply_all"} else "email_forward_sent" if draft["mode"] == "forward" else "email_sent"
            self.audit(action, mime["message_id"])
            self.state["sent_receipt"] = {}
            self.check_sent()
            if draft.get("mailbox_ref"):
                try:
                    self._trash_draft(draft["mailbox_ref"])
                    draft["mailbox_ref"] = None
                except MailboxError:
                    self.state["notice"] += " The saved draft remains in Drafts; do not send it again."
            self.cache.clear()

    def check_sent(self):
        mime = self.state.get("outgoing_mime")
        if not mime:
            return
        result = self.state.get("send_result", {})
        policy = self.state["settings"]["sent_policy"] if result.get("status") == "accepted" else "verify"
        sent = reconcile_sent(self.imap, mime, self.roles.get("sent"), policy, receipt=self.state.setdefault("sent_receipt", {}))
        self.state["sent_result"] = sent
        self.state["notice"] = result.get("notice", "") + " " + sent["notice"]

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
        self.cache.clear()

    def _trash_draft(self, header):
        destination = self.roles.get("trash")
        if not destination:
            raise MailboxError("Map Trash before discarding a saved draft.")
        result = self.imap.move_message(header, destination)
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
        body = "\n".join(self.cache[("body", k)]["data"]["text"] for k in self.state["expanded"]
                         if self.cache.get(("body", k), {}).get("data"))
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
        s, user = self.state, self.user
        threads = [{"key": t["thread_key"], "customer": t["customer"]["name"] or t["customer"]["email"],
            "email": t["customer"]["email"], "subject": t["subject"], "time": formatted_date(t["last_activity_at"], user),
            "unread": bool(t["unread"]), "count": len(t["messages"]), "snippet": t["messages"][-1].get("snippet", ""),
            "attachment": any(m.get("has_attachments") for m in t["messages"]),
            "starred": any("\\Flagged" in m["flags"] for m in t["messages"])} for t in s.get("threads", [])]
        conversation = []
        if not s.get("error"):
            for m in s.get("conversation", []):
                key = reference_key(m)
                body = self.cache.get(("body", key), {}).get("data") if key in s["expanded"] else None
                row = {"key": key, "sender": m["sender"], "subject": m["subject"], "to": m["to"], "cc": m["cc"],
                    "time": formatted_date(m["date"] or m["received_at"], user), "folder": m["folder"],
                    "own": m["sender"]["email"].casefold() == self.config.address.casefold(), "unread": m["unread"],
                    "starred": "\\Flagged" in m["flags"], "expanded": bool(body), "attachments": [], "draft": m["folder"] == self.roles.get("drafts")}
                if body:
                    text, quote = split_quote(body["text"])
                    row.update(html=readable_html(text), quote=readable_html(quote), warnings=body.get("warnings", []),
                        attachments=[{k: a[k] for k in ("section", "filename", "content_type", "encoded_size")} for a in body["attachments"]])
                conversation.append(row)
        draft = s.get("draft")
        public_draft = None
        if draft:
            public_draft = {k: draft[k] for k in ("id", "operation_id", "mode", "to", "cc", "bcc", "subject", "html", "signature", "include_quote", "quote_html")}
            public_draft.update(attachments=[{"id": a["id"], "filename": a["filename"], "size": len(a["data"])} for a in draft["attachments"]], saved=bool(draft.get("mailbox_ref")))
        settings = s["settings"]
        signatures = {key: {"label": value.get("label", key), "html": sanitize_html(value.get("html", ""))}
                      for key, value in settings["signatures"].items() if key in {"company", "nathan", "reina"}}
        return {"mailbox": self.config.address, "configured": self.config.configured,
            "smtp_configured": self.smtp_config.configured and self.smtp_config.address.casefold() == self.config.address.casefold(),
            "error": s.get("error", ""), "notice": s["notice"], "ack": s.get("ack", ""),
            "refreshed": formatted_date(s.get("refreshed_at"), user), "folders": s.get("folders", []), "roles": self.roles,
            "folder": s.get("folder", ""), "query": s["query"], "field": s["field"], "threads": threads,
            "selected": s.get("selected"), "messages": conversation, "active_message": s.get("active_message"),
            "view": s["view"], "draft": public_draft, "has_more": s.get("snapshot", {}).get("has_more", False) and s["limit"] < 1000,
            "matched": s.get("snapshot", {}).get("matched", 0), "limit": s["limit"], "send_result": s.get("send_result", {}),
            "download": s.get("download"), "settings": {"sender_name": settings["sender_name"], "sent_policy": settings["sent_policy"],
            "folder_mapping": settings["folder_mapping"], "signatures": signatures}, "settings_available": s.get("settings_available", False),
            "admin": os_accounts.is_admin(user), "signature_preference": selected_signature(settings, user, s.get("preference")),
            "context": self.context_model(), "draft_pending": bool(s.get("draft_pending"))}

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
