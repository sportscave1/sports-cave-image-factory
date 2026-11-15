"""Offline controller benchmark: python -m tests.profile_email_interactions.

Provider methods are fabricated, not a measurement of VentraIP or browser latency.
All persistence and network entry points are replaced; no customer data is used.
"""
import json
from time import perf_counter
from uuid import uuid4
from unittest.mock import patch

from tests.email_v2_fixtures import MailboxFixture, fixture_smtp, USER, CONFIG
from support_email_workspace import Workspace
import support_email_workspace as workspace
import support_email_compose as compose
import support_email_provider as provider
import support_email_smtp as smtp
from support_email_logic import match_orders
from tests.test_support_email import HEADERS, FakeImap, order


def profile():
    results = {}
    with (patch.object(workspace.store, "load_email_settings", return_value=(compose.default_settings(), None)),
          patch.object(workspace.store, "audit"),
          patch.object(workspace.store, "load_orders", return_value=[]) as orders,
          patch.object(workspace.store, "load_metadata", return_value={}),
          patch.object(workspace.store, "load_assignees", return_value=[]),
          patch.object(provider.imaplib, "IMAP4_SSL", side_effect=AssertionError("No real IMAP")),
          patch.object(smtp.smtplib, "SMTP_SSL", side_effect=AssertionError("No real SMTP")),
          patch.object(workspace, "readable_html", wraps=workspace.readable_html) as html):
        imap = MailboxFixture()
        w = Workspace({}, USER, CONFIG, smtp.SMTPConfiguration(), imap=imap, smtp=fixture_smtp())

        def measure(label, operation):
            imap.calls.clear(); html.reset_mock(); orders.reset_mock()
            start = perf_counter(); operation(); operation_ms = (perf_counter()-start)*1000
            start = perf_counter(); model = w.model(); model_ms = (perf_counter()-start)*1000
            results[label] = dict(operation_ms=round(operation_ms, 3), model_ms=round(model_ms, 3),
                                  payload_bytes=len(json.dumps(model, default=str).encode()),
                                  provider_calls=[c[0] for c in imap.calls],
                                  html_conversions=html.call_count, order_loads=orders.call_count)

        def event(action, **values):
            w.handle(dict(id=str(uuid4()), action=action, **values))

        measure("initial_mailbox", w.load)
        key = w.state["threads"][0]["thread_key"]
        measure("uncached_open", lambda: w.open_thread(key))
        measure("thread_history", lambda: w.resolve_thread(key, w.state["mailbox_version"]))
        measure("cached_open", lambda: w.open_thread(key))
        measure("reply", lambda: event("compose", mode="reply", message_key=w.state["active_message"]))
        event("close_composer")
        measure("new_mail", lambda: event("compose", mode="new"))
        event("close_composer")
        measure("mark_unread", lambda: event("mark_unread", message_key=w.state["active_message"]))
        measure("mark_read", lambda: event("mark_read", message_key=w.state["active_message"]))
        measure("flag", lambda: event("star", message_key=w.state["active_message"]))
        measure("folder_switch", lambda: event("folder", folder="Archive"))
        measure("folder_return", lambda: event("folder", folder="INBOX"))
        measure("cached_folder", lambda: event("folder", folder="Archive"))
        event("folder", folder="INBOX")
        measure("search", lambda: event("search", query="certificate"))
        event("search", query="")
        w.state["live_checked_at"] = 0
        measure("live_check", w.live_check)
        # Independent CPU-only costs, including the actual MIME/BODYSTRUCTURE path.
        def cpu(label, operation, repeats=100):
            start = perf_counter()
            for _ in range(repeats):
                operation()
            results[label] = {"mean_ms": round((perf_counter()-start)*1000/repeats, 3), "repeats": repeats}
        cpu("header_parse", lambda: provider.parse_headers(HEADERS, uid="1", uidvalidity="500"))
        cpu("html_sanitize", lambda: compose.sanitize_html('<p>Hello <b>Sports Cave</b></p>'*100))
        wire = FakeImap()
        adapter = provider.ImapProvider(CONFIG, connection_factory=lambda *a, **k: wire)
        cpu("mime_read_parse", lambda: adapter.read_message(imap.messages[0]))
        dataset = [order(oid=str(i), email=f"customer{i}@example.test") for i in range(1000)]
        cpu("order_match_1000", lambda: match_orders(w.state["threads"][0], dataset))
        assert not w.state.get("error"), w.state.get("error")
    return results


if __name__ == "__main__":
    print(json.dumps(profile(), indent=2))
