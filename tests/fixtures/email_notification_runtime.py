"""Shared fabricated state for the local OS-shell acceptance server. No external I/O."""
from copy import deepcopy
from unittest.mock import patch
import time

import support_email_notifications as notifications
import support_email_provider as provider
from tests.test_support_email_notifications import MemoryDatabase, NotificationWire
from tests.email_v2_fixtures import MailboxFixture, CONFIG, MAILBOX
from tests.test_support_email import header

WIRE = NotificationWire()
WIRE.next_uid = 4
WIRE.unseen = 2
DATABASE = MemoryDatabase()


class Store(notifications.NotificationStore):
    def poll(self, adapter, **kwargs):
        with patch('supabase_backend.connect', DATABASE.connect):
            return super().poll(adapter, **kwargs)


class Mailbox(MailboxFixture):
    def discover_folders(self):
        result = super().discover_folders()
        next(f for f in result['folders'] if f['name']=='INBOX')['unread'] = WIRE.unseen
        return result
    def notification_target(self, validity, uid, message_id=''):
        return next((deepcopy(m) for m in self.messages if m['folder']=='INBOX' and m['uid']==uid and m['uidvalidity']==validity),None)
    def set_flag(self, message, flag, enabled):
        super().set_flag(message, flag, enabled)
        WIRE.unseen=sum(m['unread'] for m in self.messages if m['folder']=='INBOX')


MAILBOX_FIXTURE=Mailbox(3)
ADAPTER=provider.ImapProvider(CONFIG, connection_factory=lambda *args,**kwargs:WIRE)
STORE=Store()


def status():
    return notifications.status(configuration=CONFIG,provider=ADAPTER,store=STORE)


def arrive():
    uid=WIRE.next_uid
    WIRE.arrive(uid)
    message=header(str(uid),f'<mail-{uid}@example.test>',subject='Damaged frame',sender='john@example.test',hours=100+uid)
    message['sender']['name']='John Smith'
    MAILBOX_FIXTURE.messages.append(message)
    notifications.invalidate()


# Establish first-run baseline, then fabricate exactly one new arrival.
status()
arrive()
status()
