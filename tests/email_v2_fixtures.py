"""Deterministic mailbox and SMTP doubles. No socket, credential or production access."""
from copy import deepcopy
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from unittest.mock import Mock

from support_email_provider import parse_headers, parse_folders
from support_email_compose import default_settings
from tests.test_support_email import MAILBOX, USER, WORKER, CONFIG, header

FOLDER_DATA = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\Sent) "/" "INBOX.Sent Items"',
               b'(\\Drafts) "/" "Drafts"', b'(\\Archive) "/" "Archive"',
               b'(\\Junk) "/" "Junk"', b'(\\Trash) "/" "Trash"', b'() "/" "Customers"']


class MailboxFixture:
    def __init__(self, count=75):
        self.folders = parse_folders(FOLDER_DATA)
        self.messages = []
        for i in range(count):
            h = header(str(i+1), f"<fixture-{i}@example.test>", subject=["Frame arrived damaged · #SC1234", "Delivery update", "Certificate question"][i % 3], hours=i)
            h.update(sender={"name": ["John Smith", "Sarah Jones", "Alex Chen"][i % 3], "email": f"customer{i}@example.test"},
                     snippet="Hello Sports Cave, could you help with my order?", has_attachments=i % 3 == 0)
            if i % 3 == 1:
                h.update(flags=("\\Seen",), unread=False)
            self.messages.append(h)
        self.calls = []
        self.appended = []
        self.fail = False

    def discover_folders(self):
        self.calls.append(("folders",))
        return {"folders": deepcopy(self.folders), "capabilities": {"MOVE", "IMAP4REV1"}}

    def list_headers(self, limit=50, folder="INBOX", **kwargs):
        self.calls.append(("headers", folder, limit, kwargs))
        if self.fail:
            raise RuntimeError("fixture-secret must never be displayed")
        items = [m for m in self.messages if m["folder"] == folder]
        query = kwargs.get("query", "")
        if query:
            items = [m for m in items if query.casefold() in str(m).casefold()]
        return {"messages": deepcopy(items[-limit:]), "total": len(items), "matched": len(items),
                "uidvalidity": "500", "refreshed_at": datetime.now(timezone.utc), "has_more": len(items) > limit}

    def related_headers(self, folder, identifiers, limit=100):
        self.calls.append(("related", folder))
        return [deepcopy(m) for m in self.messages if m["folder"] == folder and
                any(i in [m["message_id"], *m["references"], *m["in_reply_to"]] for i in identifiers)][:limit]

    def related_headers_many(self, folders, identifiers, limit=100):
        return [message for folder in folders for message in self.related_headers(folder, identifiers, limit)]

    def read_message(self, message):
        self.calls.append(("body", message["uid"]))
        return {"text": "Hi Sports Cave,\n\nMy frame arrived with a damaged corner. Could you please help me arrange a replacement?\n\nThank you,\nJohn\n\nOn Sunday, Sports Cave wrote:\n> Your order is on its way.",
                "warnings": [], "attachments": [{"section": "2", "filename": "frame-corner.jpg", "content_type": "image/jpeg", "encoded_size": 1800000}]}

    def read_attachment(self, message, section):
        self.calls.append(("attachment", message["uid"], section))
        return {"filename": "frame-corner.jpg", "data": b"mock attachment; not a real image"}

    def set_flag(self, message, flag, enabled):
        self.calls.append(("flag", message["uid"], flag, enabled))
        actual = next(m for m in self.messages if m["uid"] == message["uid"])
        flags = set(actual["flags"])
        flags.add(flag) if enabled else flags.discard(flag)
        actual.update(flags=tuple(flags), unread="\\Seen" not in flags)

    def move_message(self, message, destination):
        self.calls.append(("move", message["uid"], destination))
        next(m for m in self.messages if m["uid"] == message["uid"])["folder"] = destination
        return {"status": "moved"}

    def find_message_id(self, folder, mid):
        return [m["uid"] for m in self.messages if m["folder"] == folder and m["message_id"] == mid]

    def append_message(self, folder, raw, draft=False):
        self.calls.append(("append", folder, draft))
        self.appended.append(raw)
        h = parse_headers(raw, uid=str(len(self.messages)+1), uidvalidity="500", folder=folder)
        self.messages.append(h)
        return {"status": "appended"}

    def read_draft(self, header):
        return next(raw for raw in self.appended if BytesParser(policy=policy.default).parsebytes(raw)["Message-ID"] == header["message_id"])

    def test_connection(self):
        self.calls.append(("test",))
        return {"count": len(self.messages), "uidvalidity": "500", "folders": self.folders}


def fixture_smtp(status="accepted"):
    return Mock(submit=Mock(return_value={"status": status, "notice": {"accepted": "Mail server accepted the email.", "rejected": "Nothing was sent.", "unknown": "Delivery status is uncertain. Do not resend."}[status]}))
