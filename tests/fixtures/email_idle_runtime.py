"""Real watcher/SSE lifecycle with a fabricated IMAP wire and in-memory lease."""
import queue
import time

from support_email_idle import MailboxWatcher, HUB
from tests.test_support_email_idle import MemorySignals
from tests.fixtures import email_notification_runtime as fixture
from tests.email_v2_fixtures import CONFIG

EVENTS = queue.Queue()


class IdleWire:
    def login(self, *args): pass
    def capabilities(self): return (b'IMAP4rev1', b'IDLE')
    def select_folder(self, folder, readonly=True): assert folder == 'INBOX' and readonly
    def folder_status(self, folder, fields):
        rows=[m for m in fixture.MAILBOX_FIXTURE.messages if m['folder']=='INBOX']
        return {b'UIDVALIDITY':500,b'UIDNEXT':fixture.WIRE.next_uid,
                b'UNSEEN':sum(m['unread'] for m in rows),b'MESSAGES':len(rows)}
    def idle(self): pass
    def idle_check(self, timeout):
        if time.monotonic() < fixture.MAILBOX_FIXTURE.outage_until:
            raise ConnectionResetError('Fabricated outage')
        try: return [EVENTS.get(timeout=timeout)]
        except queue.Empty: return []
    def idle_done(self): pass
    def noop(self): pass
    def shutdown(self): pass


def watcher():
    fixture.IDLE_EVENT = lambda: EVENTS.put((1,b'EXISTS'))
    return MailboxWatcher(CONFIG,store=MemorySignals(time.monotonic),hub=HUB,factory=lambda cfg:IdleWire())
