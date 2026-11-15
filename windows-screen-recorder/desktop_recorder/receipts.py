"""Desktop IPC receipts in the existing DeviceAgent commands.sqlite schema.

The prefix scopes startup recovery to this coordinator. It must never rewrite
DeviceAgent's unrelated accepted commands. Authenticated relay receipts remain
DeviceAgent's responsibility.
"""
import json
from pathlib import Path
import sqlite3
from contextlib import contextmanager
from .contract import Invalid


class Receipts:
    def __init__(self, root):
        self.path = Path(root) / "commands.sqlite"
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY,hash TEXT,status TEXT,receipt TEXT)")
            db.execute("UPDATE commands SET status='uncertain' WHERE id LIKE 'desktop:%' AND status='accepted'")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def lookup(self, command_id, fingerprint):
        with self.connection() as db:
            row = db.execute("SELECT hash,status,receipt FROM commands WHERE id=?", ("desktop:" + command_id,)).fetchone()
        if row is None:
            return None
        if row[0] != fingerprint:
            raise Invalid("Command identity reused with changed content.")
        if row[1] != "completed":
            raise Invalid("Previous command outcome is uncertain. Review preserved state; it will not be repeated.")
        return json.loads(row[2])

    def begin(self, command_id, fingerprint):
        with self.connection() as db:
            db.execute("INSERT INTO commands VALUES(?,?,?,?)",
                       ("desktop:" + command_id, fingerprint, "accepted", "{}"))

    def complete(self, command_id, receipt):
        with self.connection() as db:
            db.execute("UPDATE commands SET status='completed',receipt=? WHERE id=?",
                       (json.dumps(receipt), "desktop:" + command_id))
