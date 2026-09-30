"""Shared Email read/parsing/workflow contract tests. All IMAP/database traffic is mocked; no real credentials."""
from contextlib import contextmanager, ExitStack
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import ast
import importlib
import inspect
from pathlib import Path
import ssl
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

import os_accounts
import support_email_provider as provider
import support_email_logic as logic
import support_email_store as store
import support_email_page as page


ROOT = Path(__file__).resolve().parents[1]
MAILBOX = "hello@sportscaveshop.com"
CONFIG = provider.Configuration(password="fixture-password")
USER = {"id": "f8fc1fb2-a1d8-4b21-8c38-8b31c21bc885", "role": "admin", "is_active": True,
        "account_status": "active", "display_name": "Nathan", "timezone": "Australia/Sydney"}
WORKER = {**USER, "id": "c66d2940-d3ad-4709-9f8a-704ddf3247ce", "role": "worker", "display_name": "Reina",
          "page_permissions": ["email"]}
HEADERS = (b'From: =?utf-8?b?Sm9zw6kgTcO8bGxlcg==?= <jose@example.test>\r\n'
           b'To: Sports Cave <hello@sportscaveshop.com>\r\nCc: Friend <friend@example.test>\r\n'
           b'Subject: =?utf-8?q?Damaged_=E2=80=94_=23SC1234?=\r\n'
           b'Date: Sun, 27 Sep 2026 10:42:00 +1000\r\nMessage-ID: <one@example.test>\r\n'
           b'In-Reply-To: <parent@example.test>\r\nReferences: <root@example.test> <parent@example.test>\r\n\r\n')
PLAIN = b'("TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "QUOTED-PRINTABLE" 22 1 NIL NIL NIL)'
HTML = b'("TEXT" "HTML" ("CHARSET" "UTF-8") NIL NIL "BASE64" 120 1 NIL NIL NIL)'
IMAGE = b'("IMAGE" "JPEG" ("NAME" "damage.jpg") NIL NIL "BASE64" 8 NIL ("ATTACHMENT" ("FILENAME" "damage.jpg")) NIL)'
MIXED = b'(' + PLAIN + IMAGE + b' "MIXED" ("BOUNDARY" "abc") NIL NIL)'
ALTERNATIVE = b'(' + PLAIN + HTML + b' "ALTERNATIVE" ("BOUNDARY" "alt") NIL NIL)'


def header(uid="1", mid="<one@example.test>", refs=(), subject="Damaged frame", sender="jose@example.test", hours=0):
    value = provider.parse_headers(HEADERS, uid=uid, uidvalidity="500", internaldate="27-Sep-2026 10:42:00 +1000")
    value.update(message_id=mid, references=refs, in_reply_to=(), subject=subject,
                 sender={"name": "José Müller", "email": sender}, cc=[], error="")
    value["received_at"] = datetime(2026, 9, 27, tzinfo=timezone.utc) + timedelta(hours=hours)
    return value


def order(oid="o1", name="#SC1234", email="jose@example.test"):
    return {"shopify_order_id": oid, "order_name": name, "customer_email": email,
            "created_at": datetime(2026, 9, 1, tzinfo=timezone.utc), "lines": [], "editions": [],
            "fulfillment_status": "fulfilled", "admin_url": "https://admin.shopify.com/store/test/orders/1"}


class FakeImap:
    def __init__(self, *, structure=MIXED, raw=HEADERS, validity=b"500", count=75):
        self.calls = []
        self.structure, self.raw, self.validity, self.count = structure, raw, validity, count
        self.parts = {"1": b"Hello Jos=C3=A9", "2": b"aW1hZ2U="}
        self.fail = False

    def login(self, address, password):
        self.calls.append(("login", address))
        if self.fail:
            raise RuntimeError("fixture-password server echoed credentials")
        return "OK", [b"Authenticated"]

    def select(self, folder, readonly=False):
        self.calls.append(("select", folder, readonly))
        return "OK", [str(self.count).encode()]

    def response(self, name):
        return name, [self.validity]

    def list(self):
        self.calls.append(("list",))
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\Sent) "/" "INBOX.Sent Items"']

    def fetch(self, sequence, query):
        self.calls.append(("fetch", sequence, query))
        return "OK", [(b'75 (UID 101 FLAGS (\\Seen) INTERNALDATE "27-Sep-2026 10:42:00 +1000" BODY[HEADER.FIELDS (FROM)] {123}', self.raw), b')']

    def uid(self, command, uid, query):
        self.calls.append(("uid", command, uid, query))
        if "BODYSTRUCTURE" in query:
            return "OK", [b'1 (UID ' + uid.encode() + b' BODYSTRUCTURE ' + self.structure + b')']
        section = query.split("BODY.PEEK[", 1)[1].split("]", 1)[0]
        return "OK", [(f'1 (UID {uid} BODY[{section}] {{20}}'.encode(), self.parts[section]), b')']

    def logout(self):
        self.calls.append(("logout",))


class ProviderTests(unittest.TestCase):
    def adapter(self, **kwargs):
        server = FakeImap(**kwargs)
        factory = Mock(return_value=server)
        return provider.ImapProvider(CONFIG, connection_factory=factory), server, factory

    def test_configuration_defaults_and_no_password_repr(self):
        cfg = provider.load_configuration({"SPORTSCAVE_EMAIL_PASSWORD": "secret-value"})
        self.assertTrue(cfg.configured)
        self.assertEqual((cfg.host, cfg.port, cfg.address), ("ventraip.email", 993, MAILBOX))
        self.assertNotIn("secret-value", repr(cfg))
        self.assertNotIn("secret-value", str(cfg.scope))

    def test_insecure_or_missing_config_rejected_before_connection(self):
        for env in ({}, {"SPORTSCAVE_EMAIL_PASSWORD": "x", "SPORTSCAVE_EMAIL_IMAP_SSL": "false"},
                    {"SPORTSCAVE_EMAIL_PASSWORD": "x", "SPORTSCAVE_EMAIL_IMAP_PORT": "143"},
                    {"SPORTSCAVE_EMAIL_PASSWORD": "x", "SPORTSCAVE_EMAIL_IMAP_PORT": "bad"}):
            factory = Mock()
            with self.assertRaises(provider.MailboxError):
                provider.ImapProvider(provider.load_configuration(env), connection_factory=factory).test_connection()
            factory.assert_not_called()

    def test_ssl_verifies_hostname_and_uses_timeout_readonly_and_full_username(self):
        adapter, server, factory = self.adapter()
        result = adapter.test_connection()
        self.assertEqual(result["count"], 75)
        self.assertIn("Sent Items", result["folders"][1])
        context = factory.call_args.kwargs["ssl_context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(factory.call_args.args, ("ventraip.email", 993))
        self.assertEqual(factory.call_args.kwargs["timeout"], 8)
        self.assertIn(("login", MAILBOX), server.calls)
        self.assertIn(("select", "INBOX", True), server.calls)
        self.assertEqual(server.calls[-1], ("logout",))

    def test_headers_are_bounded_peek_not_bodies(self):
        adapter, server, _ = self.adapter()
        result = adapter.list_headers()
        self.assertTrue(result["has_more"])
        query = next(c for c in server.calls if c[0] == "fetch")
        self.assertEqual(query[1], "26:75")
        self.assertIn("BODY.PEEK[HEADER.FIELDS", query[2])
        self.assertFalse(any(c[0] == "uid" for c in server.calls))
        self.assertEqual(result["messages"][0]["uid"], "101")
        self.assertFalse(result["messages"][0]["unread"])
        server.calls.clear()
        adapter.list_headers(100)
        self.assertEqual(next(c for c in server.calls if c[0] == "fetch")[1], "1:75")

    def test_empty_mailbox_no_fetch(self):
        adapter, server, _ = self.adapter(count=0)
        self.assertEqual(adapter.list_headers()["messages"], [])
        self.assertFalse(any(c[0] == "fetch" for c in server.calls))

    def test_encoded_subject_unicode_sender_recipients_and_thread_headers(self):
        parsed = provider.parse_headers(HEADERS, uid=1, uidvalidity=500)
        self.assertEqual(parsed["subject"], "Damaged — #SC1234")
        self.assertEqual(parsed["sender"], {"name": "José Müller", "email": "jose@example.test"})
        self.assertEqual(parsed["to"][0]["email"], MAILBOX)
        self.assertEqual(parsed["cc"][0]["email"], "friend@example.test")
        self.assertEqual(parsed["message_id"], "<one@example.test>")
        self.assertEqual(parsed["in_reply_to"], ("<parent@example.test>",))
        self.assertEqual(parsed["references"], ("<root@example.test>", "<parent@example.test>"))
        self.assertTrue(parsed["unread"])

    def test_malformed_header_is_isolated(self):
        value = provider.parse_headers(b"Not a header\x00\xff", uid=1, uidvalidity=500)
        self.assertTrue(value["error"])
        self.assertEqual(value["uid"], "1")

    def test_body_fetch_keeps_attachments_remote(self):
        adapter, server, _ = self.adapter()
        detail = adapter.read_message(header())
        self.assertEqual(detail["text"], "Hello José")
        self.assertEqual(detail["attachments"][0]["filename"], "damage.jpg")
        self.assertEqual(detail["attachments"][0]["encoded_size"], 8)
        self.assertFalse(any("PEEK[2]" in str(c) for c in server.calls))
        self.assertTrue(any("PEEK[1]" in str(c) for c in server.calls))
        self.assertTrue(all(c[2] is True for c in server.calls if c[0] == "select"))

    def test_attachment_is_downloaded_only_on_explicit_request(self):
        adapter, server, _ = self.adapter()
        file = adapter.read_attachment(header(), "2")
        self.assertEqual(file, {"data": b"image", "filename": "damage.jpg"})
        self.assertTrue(any("BODY.PEEK[2]" in str(c) for c in server.calls))
        self.assertFalse(any("BODY.PEEK[1]" in str(c) for c in server.calls))

    def test_alternative_prefers_html_and_mixed_uses_one_body(self):
        adapter, server, _ = self.adapter(structure=ALTERNATIVE)
        import base64
        server.parts["2"] = base64.b64encode(b'<p><b>Hello</b></p>')
        self.assertEqual(adapter.read_message(header())["html"], '<p><b>Hello</b></p>')
        self.assertFalse(any("PEEK[1]" in str(c) for c in server.calls))
        adapter, server, _ = self.adapter(structure=b'(' + PLAIN + HTML + b' "MIXED" NIL NIL)')
        import base64
        server.parts["2"] = base64.b64encode(b"<p>Additional text</p><img src='https://tracker.invalid/pixel'>")
        self.assertIn("Additional text", adapter.read_message(header())["text"])

    def test_nested_multipart_attachment_and_rfc2231_filename(self):
        struct = b'(' + ALTERNATIVE + IMAGE + b' "MIXED" NIL NIL)'
        parts = provider.mime_parts(provider._imap_tree(struct))
        self.assertEqual([p["section"] for p in parts], ["1.1", "1.2", "2"])
        self.assertEqual(parts[-1]["content_type"], "image/jpeg")
        self.assertEqual(provider._filename({"filename*": "utf-8''caf%C3%A9.jpg"}), "café.jpg")

    def test_html_is_inert_text_and_remote_images_never_fetched(self):
        value = '<html><head><style>hide</style></head><body><script>bad()</script><p>Hello José</p><img src="https://tracker/pixel"><iframe>bad</iframe></body></html>'
        text = provider.html_to_text(value)
        self.assertEqual(text, "Hello José")
        self.assertNotIn("tracker", text)
        with patch.object(page.st, "html") as output:
            page._safe_text('<img src="https://tracker">\n\n![pixel](https://tracker)')
        self.assertNotIn('<img src=', output.call_args.args[0])
        self.assertIn('&lt;img', output.call_args.args[0])

    def test_single_plain_and_html_base64_parts(self):
        import base64
        adapter, server, _ = self.adapter(structure=PLAIN)
        self.assertEqual(adapter.read_message(header())["text"], "Hello José")
        adapter, server, _ = self.adapter(structure=HTML)
        server.parts["1"] = base64.b64encode("<p>日本語</p>".encode())
        self.assertEqual(adapter.read_message(header())["text"], "日本語")

    def test_message_rfc822_is_attachment_not_auto_fetched(self):
        struct = b'("MESSAGE" "RFC822" NIL NIL NIL "7BIT" 100 NIL ' + PLAIN + b' 3 NIL ("ATTACHMENT" ("FILENAME" "forward.eml")))'
        adapter, server, _ = self.adapter(structure=struct)
        self.assertEqual(adapter.read_message(header())["text"], "")
        self.assertFalse(any("PEEK" in str(c) for c in server.calls))

    def test_uidvalidity_change_never_reads_wrong_message(self):
        adapter, server, _ = self.adapter(validity=b"999")
        with self.assertRaisesRegex(provider.MailboxError, "identifiers changed"):
            adapter.read_message(header())
        self.assertFalse(any(c[0] == "uid" for c in server.calls))

    def test_failures_redact_secrets_and_cleanup(self):
        adapter, server, _ = self.adapter()
        server.fail = True
        with self.assertLogs(provider.LOGGER, level="WARNING") as log:
            with self.assertRaises(provider.MailboxError) as caught:
                adapter.test_connection()
        self.assertNotIn("fixture-password", str(caught.exception) + str(log.output))
        self.assertEqual(server.calls[-1], ("logout",))

    def test_bad_structure_and_oversized_attachment_are_safe(self):
        adapter, _, _ = self.adapter(structure=b'(BROKEN)')
        with self.assertRaises(provider.MailboxError):
            adapter.read_message(header())
        adapter, server, _ = self.adapter(structure=MIXED.replace(b'"BASE64" 8', b'"BASE64" 99999999'))
        with self.assertRaisesRegex(provider.MailboxError, "too large"):
            adapter.read_attachment(header(), "2")
        self.assertFalse(any("PEEK[2]" in str(c) for c in server.calls))

    def test_timeout_and_no_response_are_safe(self):
        factory = Mock(side_effect=TimeoutError("fixture-password"))
        with self.assertRaisesRegex(provider.MailboxError, "timed out"):
            provider.ImapProvider(CONFIG, connection_factory=factory).test_connection()
        adapter, server, _ = self.adapter()
        server.select = Mock(return_value=("NO", [b"fixture-password"]))
        with self.assertRaises(provider.MailboxError) as caught:
            adapter.list_headers()
        self.assertNotIn("fixture-password", str(caught.exception))

    def test_deleted_message_between_list_and_detail(self):
        adapter, server, _ = self.adapter()
        server.uid = Mock(return_value=("OK", [None]))
        with self.assertRaisesRegex(provider.MailboxError, "no longer available"):
            adapter.read_message(header())

    def test_unknown_charset_falls_back_without_losing_other_messages(self):
        adapter, _, _ = self.adapter(structure=PLAIN.replace(b'"UTF-8"', b'"X-UNKNOWN"'))
        self.assertEqual(adapter.read_message(header())["text"], "Hello José")

    def test_imap_provider_has_no_smtp_resend_or_permanent_deletion(self):
        source = inspect.getsource(provider)
        tree = ast.parse(source)
        calls = {n.func.attr.lower() for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and isinstance(n.func.value, ast.Name) and n.func.value.id == "conn"}
        self.assertFalse(calls.intersection({"expunge", "close", "sendmail", "send_message"}))
        self.assertNotIn("smtplib", source)
        self.assertNotIn("email_service", inspect.getsource(page))


class LogicTests(unittest.TestCase):
    def test_header_threads_and_keys_stay_stable_across_load_more(self):
        reply = header("2", "<reply>", ("<root>",), "Re: Damaged frame", hours=1)
        alone = logic.build_threads([reply], MAILBOX)[0]
        complete = logic.build_threads([header(mid="<root>"), reply], MAILBOX)[0]
        self.assertEqual(alone["thread_key"], complete["thread_key"])
        self.assertEqual(len(complete["messages"]), 2)
        self.assertEqual([m["uid"] for m in complete["messages"]], ["1", "2"])

    def test_in_reply_to_links_and_missing_parent_alias_preserves_workflow(self):
        a, b = header(mid="<root>"), header("2", "<reply>", hours=1)
        b["in_reply_to"] = ("<root>",)
        thread = logic.build_threads([a, b], MAILBOX)[0]
        old_key = logic.thread_hash(MAILBOX, "<reply>")
        saved = {"thread_key": old_key, "support_status": "Resolved"}
        self.assertEqual(logic.workflow_for_thread(thread, {old_key: saved}), saved)

    def test_subject_normalization_and_conservative_fallback(self):
        self.assertEqual(logic.normalize_subject("RE: Fw: Fwd: Frame"), "frame")
        a, b = header(mid=""), header("2", "", subject="RE: Damaged frame", hours=1)
        self.assertEqual(len(logic.build_threads([a, b], MAILBOX)), 1)
        c = header("3", "", hours=0.5)
        self.assertEqual(len(logic.build_threads([a, b, c], MAILBOX)), 3)
        b["to"] = [{"name": "", "email": "someone@example.test"}]
        self.assertEqual(len(logic.build_threads([a, b], MAILBOX)), 2)

    def test_same_sender_and_subject_with_separate_roots_does_not_merge(self):
        self.assertEqual(len(logic.build_threads([header(), header("2", "<other>")], MAILBOX)), 2)

    def test_uid_fallback_includes_uidvalidity(self):
        a, b = header(mid=""), header(mid="")
        b["uidvalidity"] = "999"
        self.assertNotEqual(logic.build_threads([a], MAILBOX)[0]["thread_key"], logic.build_threads([b], MAILBOX)[0]["thread_key"])

    def test_sender_label_uses_address_not_name(self):
        a = header()
        a["sender"]["name"] = "Sports Cave"
        self.assertTrue(logic.is_customer(a, MAILBOX))
        a["sender"]["email"] = MAILBOX.upper()
        self.assertFalse(logic.is_customer(a, MAILBOX))

    def test_workflow_conflicts_do_not_silently_choose_a_status(self):
        a, b = header(mid="<root>"), header("2", "<reply>", ("<root>",))
        thread = logic.build_threads([a, b], MAILBOX)[0]
        saved = {key: {"thread_key": key, "support_status": status}
                 for key, status in zip(thread["aliases"], ["Resolved", "Needs Reply"])}
        self.assertTrue(logic.workflow_for_thread(thread, saved)["conflict"])

    def test_newest_customer_activity_not_internal_display_name_orders_threads(self):
        customer = header(mid="<root>")
        internal = header("2", "<reply>", ("<root>",), sender=MAILBOX, hours=3)
        other = header("3", "<other>", subject="Another question", hours=2)
        threads = logic.build_threads([customer, internal, other], MAILBOX)
        self.assertEqual(threads[0]["subject"], "Another question")

    def test_exact_email_match_and_ambiguity(self):
        thread = logic.build_threads([header()], MAILBOX)[0]
        self.assertEqual(logic.match_orders(thread, [order()])["state"], "matched")
        result = logic.match_orders(thread, [order(), order("o2", "#SC2222")])
        self.assertEqual(result["state"], "ambiguous")
        self.assertIsNone(result["order"])

    def test_subject_body_different_email_and_conflicting_orders(self):
        thread = logic.build_threads([header(subject="Damage #SC1234")], MAILBOX)[0]
        result = logic.match_orders(thread, [order(email="different@example.test")])
        self.assertEqual(result["method"], "subject_order_number")
        thread = logic.build_threads([header()], MAILBOX)[0]
        result = logic.match_orders(thread, [order(), order("o2", "#SC2222")], body="Order #SC2222")
        self.assertEqual(result["order"]["shopify_order_id"], "o2")
        self.assertEqual(result["method"], "body_order_number")
        result = logic.match_orders(thread, [order(), order("o2", "#SC2222")], body="SC1234 SC2222")
        self.assertEqual(result["state"], "ambiguous")

    def test_no_substring_or_bare_number_guess(self):
        self.assertEqual(logic.order_numbers("SC1234x date 2026 postal 1234 XSC567"), set())
        thread = logic.build_threads([header()], MAILBOX)[0]
        self.assertEqual(logic.match_orders(thread, [order(email="other@example.test")])["state"], "unmatched")

    def test_cache_refresh_ttl_and_failure_no_stale_body(self):
        cache, loader = {}, Mock(return_value={"text": "customer body"})
        logic.cached_read(cache, "headers", loader, clock=lambda: 0)
        logic.cached_read(cache, "headers", loader, clock=lambda: 19)
        self.assertEqual(loader.call_count, 1)
        logic.cached_read(cache, "headers", loader, clock=lambda: 21)
        self.assertEqual(loader.call_count, 2)
        loader.side_effect = RuntimeError("fixture-password")
        failed = logic.cached_read(cache, "headers", loader, clock=lambda: 42)
        self.assertIsNone(failed["data"])
        self.assertNotIn("customer body", str(cache))
        self.assertNotIn("fixture-password", failed["error"])
        cache.clear()
        loader.side_effect = None
        logic.cached_read(cache, "headers", loader, clock=lambda: 43)
        self.assertEqual(loader.call_count, 4)


class StorageTests(unittest.TestCase):
    @contextmanager
    def fake_cursor(self, cur):
        with patch.object(store, "cursor") as factory:
            factory.return_value.__enter__.return_value = cur
            yield factory

    def test_metadata_retrieval_never_requires_email_content(self):
        cur = Mock()
        cur.fetchall.return_value = [{"thread_key": "abc", "support_status": "Resolved"}]
        with self.fake_cursor(cur):
            self.assertEqual(store.load_metadata(MAILBOX, ["abc"])["abc"]["support_status"], "Resolved")
        self.assertIn("customer_support_threads", cur.execute.call_args.args[0])

    def test_manual_status_assignment_notes_and_audit_contain_no_email_payload(self):
        cur = Mock()
        cur.fetchone.return_value = {"thread_key": "a" * 64, "support_status": "Waiting on Customer"}
        with self.fake_cursor(cur), patch.object(store, "load_assignees", return_value=[WORKER]), patch.object(store, "audit") as audit:
            store.save_workflow(MAILBOX, "a"*64, actor=USER, support_status="Waiting on Customer",
                                assigned_user_id=WORKER["id"], internal_notes="Replacement approved by Nathan.")
        sql, values = cur.execute.call_args.args
        self.assertIn("assigned_user_id", sql)
        self.assertIn("Waiting on Customer", values)
        self.assertNotIn("Replacement approved", str(audit.call_args_list))
        self.assertTrue(any(c.args[0] == "support_assignment_changed" for c in audit.call_args_list))
        for forbidden in ("body", "html", "attachments", "message", "subject", "raw"):
            with self.assertRaises(TypeError):
                store.save_workflow(MAILBOX, "a"*64, actor=USER, support_status="Resolved", **{forbidden: b"customer-data"})

    def test_access_and_assignment_enforced_server_side(self):
        with self.assertRaises(store.SupportStorageError):
            store.save_workflow(MAILBOX, "a"*64, actor={**WORKER, "page_permissions": []}, support_status="Resolved")
        with patch.object(store, "load_assignees", return_value=[]):
            with self.assertRaises(store.SupportStorageError):
                store.save_workflow(MAILBOX, "a"*64, actor=USER, support_status="Resolved", assigned_user_id="unknown")

    def test_optimistic_concurrency_failure_does_not_overwrite(self):
        cur = Mock()
        cur.fetchone.return_value = None
        with self.fake_cursor(cur), self.assertRaisesRegex(store.SupportStorageError, "Another user"):
            store.save_workflow(MAILBOX, "a"*64, actor=USER, support_status="Resolved")

    def test_bounded_read_only_synced_order_queries(self):
        cur = Mock()
        cur.fetchall.side_effect = [[order()], [], []]
        with self.fake_cursor(cur):
            result = store.load_orders(["jose@example.test"], ["SC1234"])
        self.assertEqual(result[0]["shopify_order_id"], "o1")
        for call in cur.execute.call_args_list:
            self.assertTrue(call.args[0].strip().startswith("SELECT"))
        self.assertNotIn("shopify_sync", inspect.getsource(store))

    def test_migration_is_metadata_only_rls_no_public_grants(self):
        import pglast
        sql = (ROOT / "migrations/20260927020406_customer_support_workflow.sql").read_text()
        self.assertTrue(pglast.parse_sql(sql))
        self.assertIn("ENABLE ROW LEVEL SECURITY", sql)
        self.assertIn("FROM PUBLIC, anon, authenticated", sql)
        create = sql.split("CREATE TABLE", 1)[1].split("ALTER TABLE", 1)[0].lower()
        for forbidden in ("email_body", "html", "attachment", "subject", "jsonb", "bytea", "message_id"):
            self.assertNotIn(forbidden, create)


class PageTests(unittest.TestCase):
    def setUp(self):
        from tests.email_v2_fixtures import MailboxFixture
        import support_email_workspace as workspace
        import support_email_smtp as smtp
        from support_email_compose import default_settings
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.imap = self.stack.enter_context(patch.object(provider.imaplib, "IMAP4_SSL", side_effect=AssertionError("Real mailbox forbidden")))
        self.stack.enter_context(patch.object(smtp.smtplib, "SMTP_SSL", side_effect=AssertionError("Real SMTP forbidden")))
        self.stack.enter_context(patch.object(page, "load_configuration", return_value=CONFIG))
        self.stack.enter_context(patch.object(page, "load_smtp_configuration", return_value=smtp.SMTPConfiguration()))
        fixture = MailboxFixture()
        self.fake = Mock(wraps=fixture)
        self.stack.enter_context(patch.object(workspace, "ImapProvider", return_value=self.fake))
        self.component = Mock(return_value=None)
        self.stack.enter_context(patch.object(page, "get_component", return_value=self.component))
        self.stack.enter_context(patch.object(store, "load_email_settings", return_value=(default_settings(), None)))
        self.stack.enter_context(patch.object(store, "audit"))

    def app(self, user=USER):
        return AppTest.from_string(f"import support_email_page\nsupport_email_page.render_page({user!r})").run()

    def test_desktop_page_initial_load_defers_first_body_until_shell_visible(self):
        app = self.app()
        self.assertFalse(app.exception)
        self.fake.list_headers.assert_called_once_with(50, "INBOX", query="", field="TEXT", previews=True)
        self.fake.read_message.assert_not_called()
        model = self.component.call_args.kwargs["model"]
        self.assertEqual(len(model["threads"]), 50)
        self.assertEqual(model["selected"], model["threads"][0]["key"])
        self.assertFalse(model["messages"][0]["expanded"])
        self.assertEqual(model["body_pending"],model["active_message"])
        self.assertNotIn(CONFIG.password, str(model))

    def test_not_configured_and_not_authorized_do_not_connect(self):
        with patch.object(page, "load_configuration", return_value=provider.Configuration()):
            app = self.app()
            self.assertFalse(app.exception)
            self.assertFalse(self.component.call_args.kwargs["model"]["configured"])
            self.fake.list_headers.assert_not_called()
        self.app({**WORKER, "page_permissions": []})
        self.fake.list_headers.assert_not_called()

    def test_database_failure_does_not_block_inbox(self):
        with patch.object(store, "load_email_settings", side_effect=RuntimeError("db failure")):
            app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual(len(self.component.call_args.kwargs["model"]["threads"]), 50)

    def test_changed_navigation_epoch_rereads_real_provider(self):
        app = self.app()
        app.session_state["navigation_epoch"] = 9
        app.run()
        self.assertEqual(self.fake.list_headers.call_count, 2)

    def test_full_app_boot_home_orders_and_email_keep_imap_route_local(self):
        import time
        import supabase_backend
        with (patch.object(supabase_backend, "connect", side_effect=RuntimeError("Test database offline")),
              patch.object(os_accounts.DEFAULT_STORE, "get_user", return_value=USER)):
            for route in ("Dashboard", "Orders", "Email"):
                app = AppTest.from_file(str(ROOT / "app.py"))
                app.session_state["sports_cave_authenticated"] = True
                app.session_state["sports_cave_current_user"] = USER
                app.session_state["sports_cave_auth_checked_at"] = time.monotonic()
                app.session_state["startup_shell_loaded"] = True
                app.query_params["page"] = os_accounts.page_key_for_route(route)
                app.run(timeout=20)
                self.assertFalse(app.exception, route)
                self.assertEqual(app.session_state["current_page"], route)
                if route != "Email":
                    self.fake.list_headers.assert_not_called()
            self.fake.list_headers.assert_called_once_with(50, "INBOX", query="", field="TEXT", previews=True)
        self.imap.assert_not_called()

    def test_module_imports_are_lazy_and_unrelated_routes_do_not_connect(self):
        # Extract the actual dispatch function without running app.py's module-level main().
        app_tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        dispatch = next(n for n in app_tree.body if isinstance(n, ast.FunctionDef) and n.name == "render_selected_page")
        import ads_navigation, analytics_navigation, seo_navigation, social_media
        home, orders, email = Mock(), Mock(), Mock()
        namespace = {"render_lightweight_dashboard_page": home, "get_orders_page": orders,
                     "get_support_email_page": email, "os_accounts": os_accounts, "social_media": social_media,
                     "analytics_nav": analytics_navigation, "seo_nav": seo_navigation, "ads_nav": ads_navigation}
        exec(compile(ast.Module(body=[dispatch], type_ignores=[]), "app.py", "exec"), namespace)
        namespace["render_selected_page"]("Dashboard")
        namespace["render_selected_page"]("Orders")
        home.assert_called_once()
        orders.return_value.render_page.assert_called_once()
        email.assert_not_called()
        self.imap.assert_not_called()
        for module in (provider, logic, store, page):
            tree = ast.parse(inspect.getsource(module))
            # Connection construction can only live under a function/class definition.
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    continue
                self.assertNotIn("IMAP4_SSL(", ast.unparse(node))
        self.assertTrue(os_accounts.can_access_page(WORKER, "Email"))


if __name__ == "__main__":
    unittest.main()
