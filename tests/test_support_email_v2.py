"""V2 mailbox, MIME, SMTP, controller and storage contracts. All external I/O blocked."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from copy import deepcopy
from email import policy
from email.parser import BytesParser
import inspect
import json
from pathlib import Path
import smtplib
import ssl
import unittest
from unittest.mock import Mock, patch
import uuid

import support_email_compose as compose
import support_email_provider as provider
import support_email_smtp as smtp
import support_email_store as store
from support_email_workspace import Workspace, reference_key
from tests.test_support_email import CONFIG, MAILBOX, USER, WORKER, HEADERS, PLAIN, IMAGE, MIXED, FakeImap, header, order
from tests.email_v2_fixtures import FOLDER_DATA, MailboxFixture, fixture_smtp

ROOT = Path(__file__).resolve().parents[1]
SMTP_CONFIG = smtp.SMTPConfiguration(password="smtp-fixture-secret")


class ComposeTests(unittest.TestCase):
    def draft(self, **values):
        d = compose.new_draft(MAILBOX)
        d.update(to="Customer <customer@example.test>", subject="Your order", html="<p>Hello <b>there</b>.</p>", **values)
        return d

    def mime(self, d=None, **kw):
        return compose.build_mime(d or self.draft(), MAILBOX, "Sports Cave", compose.default_settings()["signatures"], **kw)

    def test_new_mime_plain_html_headers_and_stable_message_id(self):
        d = self.draft()
        mime = self.mime(d)
        msg = BytesParser(policy=policy.default).parsebytes(mime["bytes"])
        self.assertEqual(msg.get_content_type(), "multipart/alternative")
        self.assertEqual(msg["From"].addresses[0].addr_spec, MAILBOX)
        self.assertTrue(msg["Date"])
        self.assertEqual(mime["message_id"], self.mime(d)["message_id"])
        self.assertIn("Hello there.", msg.get_body(preferencelist=("plain",)).get_content())
        self.assertIn("<b>there</b>", msg.get_body(preferencelist=("html",)).get_content())

    def test_bcc_envelope_only_and_deduplicated(self):
        d = self.draft()
        d.update(cc="CUSTOMER@example.test, friend@example.test", bcc="hidden@example.test, friend@example.test")
        mime = self.mime(d)
        msg = BytesParser(policy=policy.default).parsebytes(mime["bytes"])
        self.assertNotIn("Bcc", msg)
        self.assertEqual(mime["recipients"], ["customer@example.test", "friend@example.test", "hidden@example.test"])
        self.assertNotIn(b"hidden@example.test", mime["bytes"])
        self.assertIn(b"Bcc: hidden@example.test", self.mime(d, as_draft=True)["bytes"])

    def test_reply_headers_and_reply_all_exclusion(self):
        h = header(refs=("<root@example.test>",))
        h.update(to=[{"name": "", "email": MAILBOX}, {"name": "Colleague", "email": "colleague@example.test"}],
                 cc=[{"name": "", "email": MAILBOX.upper()}, {"name": "", "email": "colleague@example.test"}, {"name": "", "email": "other@example.test"}])
        d = compose.new_draft(MAILBOX, mode="reply_all", header=h, text="Original message")
        mime = self.mime(d)
        self.assertEqual(mime["recipients"], ["jose@example.test", "colleague@example.test", "other@example.test"])
        msg = BytesParser(policy=policy.default).parsebytes(mime["bytes"])
        self.assertEqual(msg["In-Reply-To"], h["message_id"])
        self.assertIn("<root@example.test>", msg["References"])
        self.assertEqual(msg["Subject"], "Re: Damaged frame")

    def test_reply_to_and_own_sent_reply(self):
        h = header()
        h["reply_to"] = [{"name": "Support", "email": "reply@example.test"}]
        self.assertIn("reply@example.test", compose.reply_recipients(h, MAILBOX)[0])
        h["sender"]["email"] = MAILBOX
        h["to"] = [{"name": "Customer", "email": "customer@example.test"}]
        self.assertIn("customer@example.test", compose.reply_recipients(h, MAILBOX)[0])

    def test_forward_contains_metadata_without_reply_headers(self):
        d = compose.new_draft(MAILBOX, mode="forward", header=header(), text="Customer original")
        d["to"] = "recipient@example.test"
        msg = BytesParser(policy=policy.default).parsebytes(self.mime(d)["bytes"])
        self.assertNotIn("In-Reply-To", msg)
        self.assertEqual(msg["Subject"], "Fwd: Damaged frame")
        plain = msg.get_body(preferencelist=("plain",)).get_content()
        for value in ("From:", "To:", "Date:", "Subject:", "Customer original"):
            self.assertIn(value, plain)

    def test_signatures_once_and_user_preferences(self):
        d = self.draft()
        for _ in range(3):
            msg = BytesParser(policy=policy.default).parsebytes(self.mime(d)["bytes"])
            self.assertEqual(msg.get_body(preferencelist=("html",)).get_content().count("Kind regards"), 1)
        settings = compose.default_settings()
        self.assertEqual(compose.selected_signature(settings, USER), "nathan")
        self.assertEqual(compose.selected_signature(settings, WORKER), "reina")
        self.assertEqual(compose.selected_signature(settings, WORKER, "company"), "company")
        self.assertEqual(compose.selected_signature(settings, WORKER, "none"), "none")

    def test_outgoing_attachment_mime_and_removal(self):
        d = self.draft()
        a = compose.attachment_from_upload("photo.jpg", "aW1hZ2U=")
        compose.add_attachment(d, a)
        msg = BytesParser(policy=policy.default).parsebytes(self.mime(d)["bytes"])
        part = list(msg.iter_attachments())[0]
        self.assertEqual((part.get_filename(), part.get_payload(decode=True)), ("photo.jpg", b"image"))
        d["attachments"] = []
        self.assertEqual(list(BytesParser(policy=policy.default).parsebytes(self.mime(d)["bytes"]).iter_attachments()), [])

    def test_attachment_limits_and_invalid_base64(self):
        for value in ("invalid !", "X"*(compose.MAX_FILE_BYTES*4//3+17)):
            with self.assertRaises(compose.ComposeError):
                compose.attachment_from_upload("x", value)
        with self.assertRaises(compose.ComposeError):
            compose.make_attachment("x", b"x"*(compose.MAX_FILE_BYTES+1))
        d = self.draft()
        d["attachments"] = [compose.make_attachment("x", b"x"*8*1024*1024)]
        with self.assertRaises(compose.ComposeError):
            compose.add_attachment(d, compose.make_attachment("y", b"x"*8*1024*1024))

    def test_unsafe_html_and_tracking_removed(self):
        malicious = '<p onclick="alert(1)">Hi</p><script>secret()</script><img src="https://tracker.test/pixel"><iframe src="x"></iframe><svg onload="x"></svg><a href="javascript:alert(1)">bad</a><a href="https://example.test">link</a>'
        safe = compose.sanitize_html(malicious)
        for forbidden in ("onclick", "script", "secret", "img", "tracker", "iframe", "svg", "javascript"):
            self.assertNotIn(forbidden, safe)
        self.assertIn('rel="noopener noreferrer"', safe)
        self.assertIn('&lt;img', compose.readable_html('<img src=x>'))
        self.assertEqual(compose.safe_url('https://[broken'), '')

    def test_header_injection_and_invalid_recipients(self):
        for recipient in ("no-address", "a@example.test\r\nBcc: x@example.test", "@example.test"):
            d = self.draft(); d["to"] = recipient
            with self.assertRaises(compose.ComposeError): self.mime(d)
        d = self.draft(); d["subject"] = "Hi\r\nBcc: x"
        with self.assertRaises(compose.ComposeError): self.mime(d)

    def test_html_links_survive_as_visible_safe_destinations_only(self):
        text=provider.html_to_text('<a href="https://example.test/tracking">Track order</a><a href="javascript:bad()">Bad</a><img src="https://tracker.test/pixel">')
        self.assertIn('Track order (https://example.test/tracking)',text)
        rendered=compose.readable_html(text)
        self.assertIn('href="https://example.test/tracking"',rendered)
        self.assertNotIn('javascript',rendered);self.assertNotIn('tracker.test',rendered)

    def test_quote_collapsed_without_modifying_original(self):
        original = "My message\n\nOn Sunday, Alex wrote:\n> old"
        text, quote = compose.split_quote(original)
        self.assertEqual(text, "My message")
        self.assertIn("> old", quote)

    def test_mailbox_draft_roundtrip_preserves_bcc_attachment_and_reply_headers(self):
        d = compose.new_draft(MAILBOX, mode="reply", header=header(), text="old")
        d.update(bcc="hidden@example.test", html="<p>My response</p>")
        compose.add_attachment(d, compose.make_attachment("proof.txt", b"proof"))
        parsed = compose.edit_mailbox_draft(self.mime(d, as_draft=True)["bytes"], MAILBOX, header())
        self.assertEqual(parsed["signature"], "company")
        self.assertEqual(parsed["bcc"], "hidden@example.test")
        self.assertEqual(parsed["in_reply_to"], "<one@example.test>")
        self.assertEqual(parsed["attachments"][0]["data"], b"proof")
        self.assertEqual(parsed["html"].count("Kind regards"), 0)
        rebuilt = BytesParser(policy=policy.default).parsebytes(self.mime(parsed)["bytes"])
        self.assertEqual(rebuilt.get_body(preferencelist=("html",)).get_content().count("Kind regards"), 1)


class SMTPTests(unittest.TestCase):
    def setup_smtp(self):
        conn = Mock(esmtp_features={"size": "20971520"})
        conn.ehlo.return_value = (250, b"ok")
        conn.mail.return_value = (250, b"ok")
        conn.rcpt.return_value = (250, b"ok")
        conn.data.return_value = (250, b"accepted")
        factory = Mock(return_value=conn)
        return smtp.SMTPProvider(SMTP_CONFIG, connection_factory=factory), conn, factory

    def mime(self): return {"bytes": b"Subject: fixture\r\n\r\nbody", "recipients": ["customer@example.test"], "message_id": "<id@example.test>"}

    def test_ssl_configuration_and_only_accept_after_data(self):
        p, c, f = self.setup_smtp()
        self.assertEqual(p.submit(self.mime(), mailbox=MAILBOX)["status"], "accepted")
        self.assertEqual(f.call_args.args, ("ventraip.email", 465))
        self.assertTrue(f.call_args.kwargs["context"].check_hostname)
        self.assertEqual(f.call_args.kwargs["context"].verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(f.call_args.kwargs["timeout"], 12)
        c.login.assert_called_once_with(MAILBOX, SMTP_CONFIG.password)
        c.set_debuglevel.assert_called_once_with(0)
        c.data.assert_called_once_with(self.mime()["bytes"])

    def test_no_insecure_connection_or_wrong_mailbox(self):
        for env in ({}, {"SPORTSCAVE_EMAIL_SMTP_PASSWORD": "x", "SPORTSCAVE_EMAIL_SMTP_SSL": "false"},
                    {"SPORTSCAVE_EMAIL_SMTP_PASSWORD": "x", "SPORTSCAVE_EMAIL_SMTP_PORT": "587"}):
            f = Mock()
            result = smtp.SMTPProvider(smtp.load_smtp_configuration(env), connection_factory=f).submit(self.mime(), mailbox=MAILBOX)
            self.assertEqual(result["status"], "rejected"); f.assert_not_called()
        p, _, f = self.setup_smtp()
        self.assertEqual(p.submit(self.mime(), mailbox="another@example.test")["status"], "rejected")
        f.assert_not_called()
        self.assertNotIn(SMTP_CONFIG.password, repr(SMTP_CONFIG))

    def test_recipient_rejection_never_sends_partial(self):
        p, c, _ = self.setup_smtp(); c.rcpt.side_effect = [(250,b"ok"),(550,b"no")]
        mime = self.mime(); mime["recipients"].append("bad@example.test")
        self.assertEqual(p.submit(mime, mailbox=MAILBOX)["status"], "rejected")
        c.data.assert_not_called(); c.rset.assert_called_once()

    def test_disconnect_after_data_is_unknown_no_retry_no_secrets(self):
        p, c, _ = self.setup_smtp(); c.data.side_effect = TimeoutError(SMTP_CONFIG.password)
        with self.assertLogs(smtp.LOGGER) as logs:
            result = p.submit(self.mime(), mailbox=MAILBOX)
        self.assertEqual(result["status"], "unknown")
        self.assertNotIn(SMTP_CONFIG.password, str(result)+str(logs.output))
        c.data.assert_called_once()

    def test_explicit_data_rejection_and_auth_failure(self):
        p, c, _ = self.setup_smtp(); c.data.side_effect = smtplib.SMTPDataError(550, b"reject")
        self.assertEqual(p.submit(self.mime(), mailbox=MAILBOX)["status"], "rejected")
        p, c, _ = self.setup_smtp(); c.login.side_effect = smtplib.SMTPAuthenticationError(535, b"secret")
        self.assertEqual(p.submit(self.mime(), mailbox=MAILBOX)["status"], "rejected")
        c.data.assert_not_called()

    def test_server_size_limit_and_quit_failure(self):
        p, c, _ = self.setup_smtp(); c.esmtp_features = {"size": "1"}
        self.assertEqual(p.submit(self.mime(), mailbox=MAILBOX)["status"], "rejected"); c.data.assert_not_called()
        p, c, _ = self.setup_smtp(); c.quit.side_effect = TimeoutError()
        self.assertEqual(p.submit(self.mime(), mailbox=MAILBOX)["status"], "accepted")

    def test_duplicate_operation_during_concurrent_reruns(self):
        registry, fake, op = smtp.SendRegistry(), fixture_smtp(), str(uuid.uuid4())
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(lambda _: registry.submit(op, MAILBOX, self.mime(), fake), range(20)))
        fake.submit.assert_called_once()
        receipt = str(registry.receipts)
        self.assertNotIn("Subject: fixture", receipt)

    def test_interrupted_claim_cannot_resubmit(self):
        registry, fake, op = smtp.SendRegistry(), fixture_smtp(), str(uuid.uuid4())
        fake.submit.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt): registry.submit(op, MAILBOX, self.mime(), fake)
        self.assertEqual(registry.submit(op, MAILBOX, self.mime(), fake)["status"], "unknown")
        fake.submit.assert_called_once()

    def test_sent_existing_copy_does_not_append(self):
        imap = Mock(); imap.find_message_id.return_value = ["55"]
        self.assertEqual(smtp.reconcile_sent(imap, self.mime(), "Real Sent", "append")["status"], "present")
        imap.append_message.assert_not_called()

    def test_sent_append_policy_explicit_and_idempotent(self):
        imap = Mock(); imap.find_message_id.return_value = []
        smtp.reconcile_sent(imap, self.mime(), "Real Sent")
        imap.append_message.assert_not_called()
        receipt = {}
        smtp.reconcile_sent(imap, self.mime(), "Real Sent", "append", receipt=receipt)
        smtp.reconcile_sent(imap, self.mime(), "Real Sent", "append", receipt=receipt)
        imap.append_message.assert_called_once_with("Real Sent", self.mime()["bytes"])

    def test_sent_uncertain_append_cannot_retry(self):
        imap = Mock(); imap.find_message_id.return_value = []; imap.append_message.side_effect = provider.MailboxError("Safe error")
        receipt = {}
        self.assertEqual(smtp.reconcile_sent(imap, self.mime(), "Real Sent", "append", receipt=receipt)["status"], "unknown")
        smtp.reconcile_sent(imap, self.mime(), "Real Sent", "append", receipt=receipt)
        imap.append_message.assert_called_once()


class WireImap(FakeImap):
    capabilities = (b"IMAP4REV1", b"MOVE")
    def list(self): return "OK", FOLDER_DATA
    def status(self, folder, query): return "OK", [b'"INBOX" (UNSEEN 7)']
    def uid(self, command, *args):
        self.calls.append(("uid", command, *args))
        if command == "SEARCH": return "OK", [b"1 2 101"]
        if command in {"STORE", "MOVE", "COPY"}: return "OK", [b"ok"]
        uid, query = args
        if "HEADER.FIELDS" in query:
            return "OK", [(b'75 (UID 101 FLAGS (\\Seen) BODY[HEADER.FIELDS (FROM)] {123}', self.raw), b')']
        if "RFC822.SIZE" in query: return "OK", [b'1 (UID 1 RFC822.SIZE 300)']
        if "BODY.PEEK[]" in query: return "OK", [(b'1 (UID 1 BODY[] {300}', self.raw), b')']
        return super().uid(command, uid, query)
    def append(self, *args):
        self.calls.append(("append", *args)); return "OK", [b"[APPENDUID 500 102]"]


class FolderTests(unittest.TestCase):
    def adapter(self):
        wire = WireImap()
        return provider.ImapProvider(CONFIG, connection_factory=Mock(return_value=wire)), wire

    def test_discover_special_folders_and_optional_real_unread(self):
        p, wire = self.adapter(); result = p.discover_folders()
        roles = provider.folder_roles(result["folders"])
        self.assertEqual(roles["sent"], "INBOX.Sent Items")
        for key in ("inbox","sent","drafts","archive","junk","trash"): self.assertIn(key, roles)
        self.assertEqual(result["folders"][0]["unread"], 7)
        self.assertFalse(any(c[0] == "select" for c in wire.calls))

    def test_folder_literal_utf7_quoting_and_no_guessed_names(self):
        folders = provider.parse_folders([b'(\\Noselect) "/" "Parent"', b'() "/" "Sent"', (b'(\\Sent) "/" {10}', b'Sent Items'), b'() "/" "&ZeVnLIqe-"'])
        self.assertEqual(provider.folder_roles(folders)["sent"], "Sent Items")
        self.assertNotIn("Parent", [f["name"] for f in folders])
        self.assertEqual(folders[-1]["label"], "日本語")
        self.assertEqual(provider.folder_argument('Sent "Items"'), '"Sent \\"Items\\""')
        self.assertNotIn("sent", provider.folder_roles(provider.parse_folders([b'() "/" "Sent"'])))
        with self.assertRaises(provider.MailboxError): provider.folder_argument("x\r\nSTORE")

    def test_ambiguous_special_folder_requires_mapping(self):
        folders = provider.parse_folders([b'(\\Sent) "/" "A"',b'(\\Sent) "/" "B"'])
        self.assertNotIn("sent", provider.folder_roles(folders))
        self.assertEqual(provider.folder_roles(folders, {"sent":"B"})["sent"], "B")

    def test_historical_search_fetches_uid_headers_not_entire_bodies(self):
        p, wire = self.adapter()
        result = p.list_headers(query="old order SC3148", field="TEXT")
        search = next(c for c in wire.calls if c[:2] == ("uid", "SEARCH"))
        self.assertEqual(search[3], b'TEXT "old order SC3148"')
        fetch = next(c for c in wire.calls if c[:2] == ("uid", "FETCH"))
        self.assertEqual(fetch[2], "1,2,101")
        self.assertIn("BODY.PEEK[HEADER.FIELDS", fetch[3])
        self.assertEqual(result["matched"], 3)

    def test_search_sender_subject_unicode_and_escaping(self):
        p, wire = self.adapter()
        for field in ("FROM", "SUBJECT"):
            p.list_headers(query='José "order"', field=field)
            call = [c for c in wire.calls if c[:2] == ("uid", "SEARCH")][-1]
            self.assertEqual(call[2:4], ("CHARSET", "UTF-8")); self.assertIn(b'\\"order\\"', call[4])
        self.assertIn("SINCE 01-Jan-2026 BEFORE 01-Feb-2026", provider.search_criteria("x", since="2026-01-01", before="2026-02-01"))
        with self.assertRaises(provider.MailboxError): provider.search_criteria("x\r\nALL")

    def test_explicit_seen_and_star_store_only_allowlisted_flags(self):
        p, wire = self.adapter()
        for flag, enabled in (("\\Seen",True),("\\Seen",False),("\\Flagged",True)):
            p.set_flag(header(), flag, enabled)
        self.assertIn(("select", "INBOX", False), wire.calls)
        self.assertIn(("uid", "STORE", "1", "-FLAGS.SILENT", "(\\Seen)"), wire.calls)
        with self.assertRaises(provider.MailboxError): p.set_flag(header(), "\\Deleted", True)

    def test_move_archive_trash_junk_no_expunge(self):
        p, wire = self.adapter()
        for folder in ("Archive", "Trash", "Junk"):
            self.assertEqual(p.move_message(header(), folder)["status"], "moved")
            self.assertIn(("uid", "MOVE", "1", '"'+folder+'"'), wire.calls)
        self.assertNotIn("expunge", str(wire.calls).lower())

    def test_copy_fallback_explicit_original_retained(self):
        p, wire = self.adapter(); wire.capabilities = ()
        result = p.move_message(header(), "Trash")
        self.assertEqual(result["status"], "copied")
        self.assertIn("original retained", result["notice"])
        self.assertIn(("uid", "COPY", "1", '"Trash"'), wire.calls)
        self.assertFalse(any(c[1] == "STORE" for c in wire.calls if c[0] == "uid"))

    def test_uidvalidity_change_prevents_writes(self):
        p, wire = self.adapter(); wire.validity = b"501"
        with self.assertRaises(provider.MailboxError): p.move_message(header(), "Trash")
        self.assertFalse(any(c[:2] == ("uid", "MOVE") for c in wire.calls))

    def test_folder_role_collision_disables_ambiguous_actions(self):
        folders=provider.parse_folders(FOLDER_DATA)
        roles=provider.folder_roles(folders,{"trash":"INBOX.Sent Items"})
        self.assertNotIn("sent",roles);self.assertNotIn("trash",roles)

    def test_bounded_preview_uses_only_non_attachment_peek_section(self):
        p,wire=self.adapter()
        wire.uid=Mock(side_effect=[("OK",[b'1 (UID 101 BODYSTRUCTURE '+MIXED+b')']),
            ("OK",[(b'1 (UID 101 BODY[1]<0> {20}',b'Hello Jos=C3=A9')])])
        result=p.list_headers(previews=True)
        self.assertEqual(result['messages'][0]['snippet'],'Hello Jos\u00e9')
        self.assertTrue(result['messages'][0]['has_attachments'])
        self.assertIn('BODY.PEEK[1]<0.1024>',wire.uid.call_args.args[2])
        self.assertNotIn('BODY.PEEK[2]',str(wire.uid.call_args_list))

    def test_sent_message_id_requires_exact_match(self):
        p, _ = self.adapter()
        self.assertEqual(p.find_message_id("INBOX.Sent Items", "<one@example.test>"), ["101"])
        self.assertEqual(p.find_message_id("INBOX.Sent Items", "<other@example.test>"), [])

    def test_draft_append_and_explicit_read_remain_mailbox_only(self):
        p, wire = self.adapter(); p.append_message("Drafts", b"MIME", draft=True)
        self.assertIn("(\\Draft)", next(c for c in wire.calls if c[0] == "append"))
        self.assertEqual(p.read_draft(header()), HEADERS)
        self.assertTrue(any("BODY.PEEK[]" in str(c) for c in wire.calls))


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(provider.imaplib,"IMAP4_SSL",side_effect=AssertionError("Real IMAP forbidden")))
        self.stack.enter_context(patch.object(smtp.smtplib,"SMTP_SSL",side_effect=AssertionError("Real SMTP forbidden")))
        self.stack.enter_context(patch.object(store,"load_email_settings",return_value=(compose.default_settings(),None)))
        self.stack.enter_context(patch.object(store,"load_metadata",return_value={}))
        self.stack.enter_context(patch.object(store,"load_orders",return_value=[order()]))
        self.stack.enter_context(patch.object(store,"load_assignees",return_value=[USER,WORKER]))
        self.audit=self.stack.enter_context(patch.object(store,"audit"))
        self.imap=MailboxFixture();self.smtp=fixture_smtp();self.state={}
        self.w=Workspace(self.state,USER,CONFIG,SMTP_CONFIG,imap=self.imap,smtp=self.smtp,registry=smtp.SendRegistry())
        self.w.load()

    def event(self,action,**kwargs):
        event={"id":str(uuid.uuid4()),"action":action,**kwargs};self.w.handle(event);return event

    def open(self):
        self.event("open_thread",thread_key=self.state["threads"][0]["thread_key"])
        return self.state["active_message"]

    def compose(self,mode="new"):
        key=self.open() if mode!="new" else None
        self.event("compose",mode=mode,message_key=key)
        d=self.state["draft"]; d.update(to="customer@example.test",subject="Fixture subject",html="<p>Fixture body</p>")
        return d

    def test_initial_50_lazy_body_and_refresh_bypasses_cache(self):
        self.assertEqual(len(self.w.model()["threads"]),50)
        self.assertFalse(any(c[0]=="body" for c in self.imap.calls))
        self.event("refresh"); self.assertEqual(len([c for c in self.imap.calls if c[0]=="headers"]),2)
        self.event("load_more");self.assertEqual(len(self.w.model()["threads"]),75)

    def test_folder_switch_and_server_search_older_than_initial_page(self):
        self.event("search",query="from: customer0@example.test")
        self.assertEqual(len(self.w.model()["threads"]),1)
        call=[c for c in self.imap.calls if c[0]=="headers"][-1]
        self.assertEqual(call[3]["field"],"FROM")
        self.event("folder",folder="INBOX.Sent Items")
        self.assertEqual(self.state["folder"],"INBOX.Sent Items")
        self.event("folder",folder="Invented")
        self.assertEqual(self.state["folder"],"INBOX.Sent Items")

    def test_message_open_marks_read_without_refreshing_inbox(self):
        self.open()
        self.assertEqual(len([c for c in self.imap.calls if c[0]=="headers"]),1)
        self.assertEqual(len([c for c in self.imap.calls if c[0]=="flag"]),1)
        self.assertEqual(len([c for c in self.imap.calls if c[0]=="body"]),1)

    def test_cross_folder_thread_historical_sent_reply(self):
        original=self.state["threads"][0]["messages"][0]
        reply=header("900","<sent-reply@example.test>",(original["message_id"],),"Re: "+original["subject"],sender=MAILBOX,hours=100)
        reply["folder"]="INBOX.Sent Items";self.imap.messages.append(reply)
        self.open()
        self.event("resolve_thread",thread_key=self.state["selected"],mailbox_version=self.state["mailbox_version"])
        self.assertEqual(len(self.w.model()["messages"]),2)
        self.assertTrue(self.w.model()["messages"][-1]["own"])
        self.assertTrue(self.w.model()["messages"][0]["expanded"])
        self.assertFalse(self.w.model()["messages"][1]["expanded"])
        self.assertEqual(self.state['active_message'],reference_key(original))

    def test_failure_labels_cached_inbox_and_preserves_compose(self):
        d=self.compose();self.imap.fail=True;self.event("refresh")
        self.assertTrue(self.w.model()["threads"])
        self.assertIn("last successful", self.w.model()["live_error"])
        self.assertEqual(self.state["draft"]["id"],d["id"])
        self.assertNotIn("fixture-secret",json.dumps(self.w.model()))

    def test_optional_database_unavailable_does_not_block_mailbox(self):
        with patch.object(store,"load_email_settings",side_effect=RuntimeError("secret")):
            self.event("refresh")
        self.assertEqual(len(self.w.model()["threads"]),50)
        self.assertFalse(self.w.model()["settings_available"])

    def test_safe_model_no_secrets_or_attachment_binary(self):
        self.open();d=self.compose();compose.add_attachment(d,compose.make_attachment("x.txt",b"PRIVATE-ATTACHMENT"))
        serialized=json.dumps(self.w.model())
        for value in (CONFIG.password,SMTP_CONFIG.password,"PRIVATE-ATTACHMENT"):
            self.assertNotIn(value,serialized)

    def test_attachment_explicit_download_and_forward_only(self):
        key=self.open();self.assertFalse(any(c[0]=="attachment" for c in self.imap.calls))
        self.event("download",message_key=key,section="2")
        self.assertTrue(self.w.model()["download"]["base64"])
        self.event("compose",mode="forward",message_key=key)
        self.event("forward_attachment",message_key=key,section="2")
        self.assertEqual(len(self.state["draft"]["attachments"]),1)
        aid=self.state["draft"]["attachments"][0]["id"]
        self.event("remove_attachment",attachment_id=aid)
        self.assertEqual(self.state["draft"]["attachments"],[])

    def test_send_duplicate_events_and_distinct_reruns_once(self):
        d=self.compose();event=self.event("send",operation_id=d["operation_id"])
        self.w.handle(event);self.event("send",operation_id=d["operation_id"])
        self.smtp.submit.assert_called_once()
        self.assertEqual(self.state["send_result"]["status"],"accepted")
        self.assertNotIn("Fixture body",str(self.audit.call_args_list))

    def test_unknown_send_never_appends_or_retries(self):
        self.smtp.submit.return_value={"status":"unknown","notice":"Uncertain. Do not resend."}
        d=self.compose();self.state["settings"]["sent_policy"]="append"
        self.event("send",operation_id=d["operation_id"]);self.event("check_sent");self.event("retry_rejected")
        self.event("send",operation_id=d["operation_id"])
        self.smtp.submit.assert_called_once();self.assertFalse(self.imap.appended)
        self.assertNotIn("accepted",self.state["notice"].lower())

    def test_rejected_requires_explicit_new_operation(self):
        self.smtp.submit.return_value={"status":"rejected","notice":"Rejected."}
        d=self.compose();old=d["operation_id"];self.event("send",operation_id=old)
        self.event("send",operation_id=old);self.smtp.submit.assert_called_once()
        self.event("retry_rejected");self.assertNotEqual(d["operation_id"],old)
        self.event("send",operation_id=d["operation_id"]);self.assertEqual(self.smtp.submit.call_count,2)

    def test_saved_drafts_edit_revision_discard(self):
        d=self.compose();self.event("save_draft")
        self.assertTrue(d["mailbox_ref"]);self.assertEqual(len(self.imap.appended),1)
        old=d["mailbox_ref"];d["html"]="<p>Changed</p>";self.event("save_draft")
        self.assertNotEqual(d["mailbox_ref"]["uid"],old["uid"])
        self.assertTrue(any(c[:3]==("move",old["uid"],"Trash") for c in self.imap.calls))
        self.event("discard_draft");self.assertIsNone(self.state["draft"])

    def test_uncertain_draft_append_blocked_until_verified_no_repeat(self):
        self.compose()
        with patch.object(self.imap,"append_message",side_effect=provider.MailboxError("Safe error")) as append:
            self.event("save_draft");self.event("save_draft");self.event("discard_draft")
            append.assert_called_once()
        self.assertTrue(self.state["draft_pending"]);self.assertIsNotNone(self.state["draft"])

    def test_manual_flags_archive_trash_and_test_connection(self):
        for action,expected in (("mark_read",("\\Seen",True)),("mark_unread",("\\Seen",False)),("star",("\\Flagged",True))):
            key=self.open();self.event(action,message_key=key)
            self.assertTrue(any(c[0]=="flag" and c[2:]==expected for c in self.imap.calls))
        key=self.open();self.event("archive",message_key=key)
        self.assertTrue(any(c[0]=="move" and c[2]=="Archive" for c in self.imap.calls))
        self.event("test_connection");self.assertIn(("test",),self.imap.calls)

    def test_approval_source_survives_folder_switch_and_database_outage(self):
        d=self.compose("reply");self.w.user=WORKER
        self.event("folder",folder="Archive")
        with patch.object(store,"load_metadata",side_effect=RuntimeError("unavailable")):
            self.event("send",operation_id=d["operation_id"])
        self.smtp.submit.assert_not_called();self.assertIn("Approval",self.state["notice"])

    def test_required_approval_blocks_worker_send_and_worker_cannot_clear_it(self):
        d=self.compose('reply');self.w.user=WORKER
        key=d['source_thread']['thread_key']
        with patch.object(store,'load_metadata',return_value={key:{'thread_key':key,'needs_approval':True}}):
            self.event('send',operation_id=d['operation_id'])
        self.smtp.submit.assert_not_called()
        with self.assertRaises(store.SupportStorageError):
            store.save_workflow(MAILBOX,key,actor=WORKER,support_status='Needs Reply',needs_approval=False,previous={'needs_approval':True})

    def test_customer_context_only_on_demand_workflow_writes_no_body(self):
        key=self.open()
        with patch.object(store,"load_orders",return_value=[order()]) as orders:
            self.w.model();orders.assert_not_called();self.event("context");orders.assert_called_once()
        with patch.object(store,"save_workflow") as save:
            self.event("workflow",status="Waiting on Customer",assigned=WORKER["id"],notes="Approved internally",approval=False)
            self.assertNotIn("damaged corner",str(save.call_args))
            self.assertNotIn("attachments",str(save.call_args))

    def test_unauthorized_user_cannot_trigger_action(self):
        self.w.user={**WORKER,"page_permissions":[]}
        with self.assertRaises(PermissionError): self.event("send",operation_id=str(uuid.uuid4()))
        self.smtp.submit.assert_not_called()


class SettingsTests(unittest.TestCase):
    def test_settings_migration_has_only_configuration_and_rls(self):
        import pglast
        sql=(ROOT/'migrations/20260927025319_customer_support_email_settings.sql').read_text()
        self.assertTrue(pglast.parse_sql(sql));self.assertIn('ENABLE ROW LEVEL SECURITY',sql)
        for value in ('email_body','attachment','bytea','smtp_password','imap_password'):
            self.assertNotIn(value,sql.split('BEGIN;',1)[1].lower())

    def test_settings_sanitized_admin_only_and_own_preference(self):
        signatures=compose.default_settings()['signatures'];signatures['company']['html']='<b>Sports Cave</b><img src="https://tracker">'
        kwargs=dict(sender_name='Sports Cave',signatures=signatures,folder_mapping={'sent':'Real Sent'},sent_policy='verify',discovered_names={'Real Sent'})
        with self.assertRaises(store.SupportStorageError): store.save_email_settings(MAILBOX,actor=WORKER,**kwargs)
        with patch.object(store,'cursor') as factory,patch.object(store,'audit'):
            cur=factory.return_value.__enter__.return_value
            store.save_email_settings(MAILBOX,actor=USER,**kwargs)
            self.assertNotIn('tracker',str(cur.execute.call_args))
            store.save_email_preference(MAILBOX,actor=WORKER,signature_key='reina')
            self.assertIn(WORKER['id'],cur.execute.call_args.args[1])
        kwargs['folder_mapping']={'trash':'INBOX'};kwargs['discovered_names']={'INBOX'}
        with self.assertRaises(store.SupportStorageError): store.save_email_settings(MAILBOX,actor=USER,**kwargs)


if __name__=='__main__': unittest.main()
