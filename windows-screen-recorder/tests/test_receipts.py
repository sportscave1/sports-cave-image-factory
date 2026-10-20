import sqlite3
import tempfile
from pathlib import Path
from uuid import uuid4
from unittest import TestCase
from desktop_recorder.receipts import Receipts
from desktop_recorder.contract import Invalid


class ReceiptTests(TestCase):
    def test_completed_receipt_survives_restart_and_rejects_changed_content(self):
        with tempfile.TemporaryDirectory() as root:
            first = Receipts(root)
            key = str(uuid4())
            first.begin(key, "fingerprint")
            first.complete(key, {"last_saved": {"id": "saved"}})
            second = Receipts(root)
            self.assertEqual(second.lookup(key, "fingerprint")["last_saved"]["id"], "saved")
            with self.assertRaisesRegex(Invalid, "changed content"):
                second.lookup(key, "different")

    def test_pending_desktop_receipt_is_uncertain_without_touching_relay_rows(self):
        with tempfile.TemporaryDirectory() as root:
            first = Receipts(root)
            key = str(uuid4())
            first.begin(key, "fingerprint")
            with first.connection() as db:
                db.execute("INSERT INTO commands VALUES('relay-original','h','accepted','{}')")
            second = Receipts(root)
            with self.assertRaisesRegex(Invalid, "will not be repeated"):
                second.lookup(key, "fingerprint")
            with second.connection() as db:
                self.assertEqual(db.execute("SELECT status FROM commands WHERE id='relay-original'").fetchone()[0], "accepted")
