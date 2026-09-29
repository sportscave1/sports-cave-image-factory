"""Same mailbox and send lifecycle for Email-authorized users; no external I/O."""
from copy import deepcopy
from email import policy
from email.parser import BytesParser
import json
import unittest
from unittest.mock import patch

from tests import test_support_email_v2 as v2
from tests import test_email_sent_lifecycle as sent
from tests.email_v2_fixtures import MailboxFixture, fixture_smtp
from support_email_workspace import Workspace
import support_email_compose as compose
import support_email_store as store
import support_email_smtp as smtp


class StaffSentLifecycleTests(sent.SentLifecycleTests):
    """Run the complete existing admin Sent safety contract as staff too."""

    def setUp(self):
        super().setUp()
        self.w.user = v2.WORKER


class RoleParityTests(unittest.TestCase):
    setUp = v2.WorkspaceTests.setUp
    event = v2.WorkspaceTests.event
    open = v2.WorkspaceTests.open
    compose = v2.WorkspaceTests.compose

    def reset_user(self, user, mailbox=None):
        self.state = {}
        self.imap = mailbox or MailboxFixture(count=3)
        self.smtp = fixture_smtp()
        self.w = Workspace(self.state, user, v2.CONFIG, v2.SMTP_CONFIG,
                           imap=self.imap, smtp=self.smtp, registry=smtp.SendRegistry())
        self.w.load()

    def test_all_compose_modes_share_transport_with_only_existing_signature_choice(self):
        for mode in ("new", "reply", "reply_all", "forward"):
            for user, signature in ((v2.USER, "nathan"), (v2.WORKER, "reina")):
                with self.subTest(mode=mode, role=user["role"]):
                    self.reset_user(user)
                    draft = self.compose(mode)
                    self.assertEqual(draft["signature"], signature)
                    compose.add_attachment(draft, compose.make_attachment("note.txt", b"local test"))
                    # Optional support metadata must never be a prerequisite to SMTP.
                    with patch.object(store, "load_metadata", side_effect=RuntimeError("private-secret")) as metadata:
                        self.event("send", operation_id=draft["operation_id"])
                        metadata.assert_not_called()
                    self.smtp.submit.assert_called_once()
                    self.assertEqual(self.smtp.submit.call_args.kwargs["mailbox"], v2.MAILBOX)
                    raw = self.smtp.submit.call_args.args[0]["bytes"]
                    self.assertEqual(self.imap.appended, [raw])
                    mime = BytesParser(policy=policy.default).parsebytes(raw)
                    expected = compose.build_mime(draft, v2.MAILBOX,
                        self.state["settings"]["sender_name"], self.state["settings"]["signatures"])
                    expected_html = BytesParser(policy=policy.default).parsebytes(expected["bytes"]).get_body(preferencelist=("html",)).get_content()
                    self.assertEqual(mime.get_body(preferencelist=("html",)).get_content(), expected_html)
                    self.assertEqual(mime["From"].addresses[0].addr_spec, v2.MAILBOX)
                    self.assertEqual(next(mime.iter_attachments()).get_payload(decode=True), b"local test")
                    self.assertEqual(self.state["send_stage"], "SENT")
                    self.assertNotIn("private-secret", json.dumps(self.w.model()))

    def test_provider_sent_copy_survives_refresh_and_new_session_for_both_users(self):
        mailbox = MailboxFixture(count=3)
        ids = []
        for user in (v2.USER, v2.WORKER):
            self.reset_user(user, mailbox)
            draft = self.compose()
            self.event("send", operation_id=draft["operation_id"])
            ids.append(self.state["send_result"]["message_id"])
            self.event("refresh")
            self.assertEqual(self.state["folder"], "INBOX.Sent Items")
        for user in (v2.USER, v2.WORKER):
            self.reset_user(user, mailbox)  # No prior session state/optimistic Sent item.
            self.event("folder", folder="INBOX.Sent Items")
            actual = {m["message_id"] for t in self.state["threads"] for m in t["messages"]}
            self.assertTrue(set(ids).issubset(actual))

    def test_receive_refresh_drafts_and_signature_preferences_share_mailbox(self):
        calls = []
        for user in (v2.USER, v2.WORKER):
            self.reset_user(user)
            self.assertTrue(self.state["selected"])
            incoming = deepcopy(self.imap.messages[-1])
            incoming.update(uid="99", message_id="<new-incoming@example.test>")
            self.imap.messages.append(incoming)
            self.event("refresh")
            self.assertTrue(any(m["uid"] == "99" for t in self.state["threads"] for m in t["messages"]))
            self.state["preference"] = "company"
            draft = self.compose()
            self.assertEqual(draft["signature"], "company")
            self.event("save_draft")
            self.assertTrue(draft["mailbox_ref"])
            self.event("folder", folder="Drafts")
            self.assertEqual(len(self.state["threads"]), 1)
            calls.append([c[0] for c in self.imap.calls])
        self.assertEqual(*calls)

    def test_email_permission_still_required_for_send_and_receive_actions(self):
        for action in ("compose", "send", "advance_send", "refresh", "folder", "open_thread"):
            self.w.user = {**v2.WORKER, "page_permissions": []}
            with self.subTest(action=action), self.assertRaises(PermissionError):
                self.event(action)
        self.smtp.submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
