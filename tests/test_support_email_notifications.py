"""All notification I/O is fabricated; no configured mailbox or database is used."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import asyncio
import json
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, patch

from starlette.requests import Request
import support_email_notifications as notifications
import support_email_provider as provider
import top_bar_api
from tests.email_v2_fixtures import CONFIG, MAILBOX
from tests.test_support_email import header
from tests import test_support_email_v2 as v2


class NotificationWire:
    capabilities = (b"IMAP4REV1",)
    def __init__(self):
        self.calls = []
        self.next_uid, self.unseen, self.validity = 101, 3, "500"
        self.headers = {}
        self.fail = False
    def login(self, *args):
        self.calls.append(("LOGIN",))
        if self.fail:
            raise RuntimeError("fixture-secret must not escape")
        return "OK", []
    def logout(self): self.calls.append(("LOGOUT",))
    def status(self, folder, fields):
        self.calls.append(("STATUS", folder, fields))
        return "OK", [f'"INBOX" (UNSEEN {self.unseen} MESSAGES 90 UIDNEXT {self.next_uid} UIDVALIDITY {self.validity})'.encode()]
    def select(self, folder, readonly=False):
        self.calls.append(("SELECT", folder, readonly));return "OK", [b"90"]
    def response(self, name):return name, [self.validity.encode()]
    def uid(self, command, sequence, fields):
        self.calls.append((command, sequence, fields))
        if command == "SEARCH":return "OK", [b"101"]
        lo, _, hi = str(sequence).partition(":")
        return "OK", [(f'1 (UID {uid})'.encode(), raw) for uid,raw in self.headers.items()
                      if int(lo) <= uid <= int(hi or lo)]
    def arrive(self, uid, subject="Damaged frame"):
        self.next_uid=max(self.next_uid,uid+1);self.unseen+=1
        self.headers[uid]=(f'From: John Smith <john@example.test>\r\nSubject: {subject}\r\n'
            f'Message-ID: <mail-{uid}@example.test>\r\nDate: Sun, 27 Sep 2026 10:00:00 +1000\r\n\r\n').encode()


class MemoryDatabase:
    """Transactional SQL recorder for the existing cursor/audit table contract."""
    def __init__(self):
        self.states, self.events, self.queries = {}, [], []
        self.lock_available=True;self.fail_state_write=False
    @contextmanager
    def connect(self):
        transaction=deepcopy((self.states,self.events))
        try:yield self
        except Exception:
            self.states,self.events=transaction
            raise
    def cursor(self):return self
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def commit(self):pass
    def execute(self, sql, args=()):
        self.queries.append((sql,args));self.row=None
        if "pg_try_advisory" in sql:self.row={"acquired":self.lock_available}
        elif "SELECT value FROM app_sync_state" in sql:self.row={"value":deepcopy(self.states.get(args[0],{}))}
        elif "INSERT INTO audit_logs" in sql:
            if not any(e['entity_id']==args[1] for e in self.events):
                self.events.append({"event_type":args[0],"entity_type":"email_notification","entity_id":args[1],
                    "new_value":json.loads(args[2]),"created_at":datetime.now(timezone.utc).isoformat(),"source":"Email"})
        elif "INSERT INTO app_sync_state" in sql:
            if self.fail_state_write:raise RuntimeError('fixture database unavailable')
            self.states[args[0]]=json.loads(args[1])
    def fetchone(self):return self.row


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.wire=NotificationWire()
        self.adapter=provider.ImapProvider(CONFIG,connection_factory=Mock(return_value=self.wire))
        self.db=MemoryDatabase();self.store=notifications.NotificationStore()
        self.connection=patch('supabase_backend.connect',self.db.connect);self.connection.start();self.addCleanup(self.connection.stop)
        notifications._CACHE.update(scope=None,expires=0,success=0,value={},dirty=False)
    def poll(self, now=1000):return notifications.status(configuration=CONFIG,provider=self.adapter,store=self.store,now=now)

    def test_count_zero_one_many_uses_status_only(self):
        for count in (0,1,37):
            self.wire.unseen=count;self.wire.calls.clear()
            self.assertEqual(self.adapter.get_unread_count(),count)
            self.assertEqual([c[0] for c in self.wire.calls],['LOGIN','STATUS','LOGOUT'])
    def test_first_run_only_baselines_historical_unread(self):
        result=self.poll();self.assertEqual(result['unread_count'],3)
        self.assertEqual(self.db.events,[])
        self.assertEqual(self.db.states[notifications.state_key(MAILBOX)]['last_uid'],100)
        self.assertEqual([c[0] for c in self.wire.calls],['LOGIN','STATUS','LOGOUT'])
    def test_new_uid_exactly_once_after_restart(self):
        self.poll();self.wire.arrive(101);self.poll(1031)
        self.assertEqual(len(self.db.events),1)
        notifications._CACHE.update(scope=None,expires=0,value={})
        self.poll(1062);self.assertEqual(len(self.db.events),1)
    def test_multiple_arrivals_minimal_fields_and_no_content(self):
        self.poll();self.wire.arrive(101);self.wire.arrive(102);self.poll(1031)
        self.assertEqual(len(self.db.events),2)
        fetch=[c for c in self.wire.calls if c[0]=='FETCH']
        self.assertEqual(fetch,[('FETCH','101:102','(UID BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])')])
        self.assertIn(('SELECT','"INBOX"',True),self.wire.calls)
        for forbidden in ('BODYSTRUCTURE','BODY.PEEK[]','BODY.PEEK[TEXT]','attachment','password'):
            self.assertNotIn(forbidden,str(self.db.events)+str(self.wire.calls))
    def test_uidvalidity_reset_baselines_without_history(self):
        self.poll();self.wire.validity='600';self.wire.arrive(101);self.poll(1031)
        self.assertEqual(self.db.events,[])
        self.wire.arrive(102);self.poll(1062);self.assertEqual(len(self.db.events),1)
    def test_catchup_is_bounded_and_does_not_skip_next_window(self):
        self.poll()
        for uid in range(101,164):self.wire.arrive(uid)
        self.poll(1031);self.assertEqual(len(self.db.events),50)
        self.poll(1062);self.assertEqual(len(self.db.events),63)
    def test_ttl_avoids_reconnecting_on_streamlit_reruns(self):
        self.poll();before=list(self.wire.calls)
        for now in range(1001,1030):self.poll(now)
        self.assertEqual(self.wire.calls,before)
    def test_durable_ttl_coalesces_a_second_process(self):
        self.poll();self.wire.calls.clear()
        self.assertEqual(self.store.poll(self.adapter,now=1001)['unread_count'],3)
        self.assertEqual(self.wire.calls,[])
    def test_transaction_rollback_prevents_lost_events(self):
        self.store.poll(self.adapter,now=1000);self.wire.arrive(101);self.db.fail_state_write=True
        with self.assertRaises(RuntimeError):self.store.poll(self.adapter,now=1031)
        self.assertEqual(self.db.events,[])
        self.db.fail_state_write=False;self.store.poll(self.adapter,now=1032)
        self.assertEqual(len(self.db.events),1)
    def test_busy_mailbox_lock_never_duplicates_or_blocks(self):
        self.db.lock_available=False
        self.assertIsNone(self.store.poll(self.adapter,now=1000));self.assertEqual(self.wire.calls,[])
    def test_invalidation_refreshes_real_read_count(self):
        self.poll();self.wire.unseen=2;notifications.invalidate()
        self.assertEqual(self.poll(1001)['unread_count'],2)
        self.wire.unseen=3;notifications.invalidate()
        self.assertEqual(self.poll(1002)['unread_count'],3)
    def test_imap_failure_is_quiet_bounded_and_not_fake_zero(self):
        self.poll();self.wire.fail=True;self.wire.calls.clear()
        with self.assertLogs(level='WARNING') as logs:result=self.poll(1031)
        self.assertEqual(result['unread_count'],3);self.assertFalse(result['available'])
        self.assertNotIn('fixture-secret',str(logs.output)+str(result))
        self.assertEqual(sum(c[0]=='LOGIN' for c in self.wire.calls),1)
        self.poll(1032);self.assertEqual(sum(c[0]=='LOGIN' for c in self.wire.calls),1)
        self.assertIsNone(self.poll(1152)['unread_count'])
    def test_missing_storage_can_show_count_but_never_announces_old_mail(self):
        with patch.object(self.store,'poll',side_effect=RuntimeError('DB unavailable')):
            self.assertEqual(self.poll()['unread_count'],3)
        self.assertEqual(self.db.events,[])
        self.poll(1031);self.assertEqual(self.db.events,[])
    def test_unconfigured_does_not_connect(self):
        result=notifications.status(configuration=provider.Configuration(),provider=self.adapter)
        self.assertIsNone(result['unread_count']);self.assertEqual(self.wire.calls,[])
    def test_persistence_allowlist_strips_bodies_attachments_and_flags(self):
        message=header();message.update(body='private',html='<p>private</p>',attachments=[b'binary'],password='secret')
        data=notifications.event_metadata(MAILBOX,message)
        self.assertEqual(set(data),{'mailbox','folder','uidvalidity','uid','message_id','sender_name','sender_email','subject','received_at'})
        self.assertNotIn('private',str(data));self.assertNotIn('binary',str(data))
    def test_bell_permission_and_exact_target_with_no_actor_guessing(self):
        self.poll();self.wire.arrive(101);self.poll(1031)
        for who in ('nathan','reina'):
            result=top_bar_api.build_notifications({'sub':who,'allowed_routes':['Email']},activity_rows=self.db.events)
            self.assertEqual(len(result),1);self.assertEqual(result[0]['title'],'New email')
            self.assertEqual(result[0]['email_target'],{'uid':'101','uidvalidity':'500','message_id':'<mail-101@example.test>'})
        self.assertEqual(top_bar_api.build_notifications({'allowed_routes':['Orders']},activity_rows=self.db.events),[])
    def test_status_endpoint_requires_email_permission_before_io(self):
        request=Request({'type':'http','method':'GET','path':top_bar_api.EMAIL_STATUS_PATH,'headers':[]})
        with patch.object(top_bar_api,'_claims',return_value={'allowed_routes':['Orders']}),patch.object(notifications,'status') as status:
            response=asyncio.run(top_bar_api.top_bar_email_status(request))
        self.assertEqual(response.status_code,403);status.assert_not_called()
    def test_notification_poll_has_no_order_or_workspace_dependency(self):
        with (patch('support_email_store.load_orders',side_effect=AssertionError('orders forbidden')),
              patch('support_email_workspace.Workspace.load',side_effect=AssertionError('workspace forbidden'))):
            self.poll();self.wire.arrive(101);self.poll(1031)
    def test_target_exact_uid_safe_missing_and_message_id_fallback(self):
        self.wire.arrive(101)
        self.assertEqual(self.adapter.notification_target('500','101')['uid'],'101')
        self.assertIsNone(self.adapter.notification_target('500','999'))
        self.assertEqual(self.adapter.notification_target('499','50','<mail-101@example.test>')['uid'],'101')
        self.assertFalse(any(c[0] in ('STORE','MOVE') for c in self.wire.calls))


class WorkspaceNotificationTests(unittest.TestCase):
    setUp=v2.WorkspaceTests.setUp
    event=v2.WorkspaceTests.event
    open=v2.WorkspaceTests.open
    def test_notification_selects_exact_message_even_outside_latest_headers(self):
        message=self.imap.messages[0]
        self.imap.notification_target=Mock(return_value=message)
        self.w.open_notification(message)
        self.assertEqual(self.state['folder'],'INBOX')
        self.assertEqual(self.state['active_message'],v2.reference_key(message))
        self.assertIn(('body','1'),self.imap.calls)
        self.assertEqual([c for c in self.imap.calls if c[0]=='flag'],[('flag','1','\\Seen',True)])
    def test_missing_notification_opens_inbox_safely(self):
        self.imap.notification_target=Mock(return_value=None)
        self.w.open_notification({'uid':'999','uidvalidity':'500'})
        self.assertIsNone(self.state['selected']);self.assertIn('no longer in Inbox',self.state['notice'])
    def test_mark_read_and_unread_invalidate_shared_notification_count(self):
        key=self.open()
        for action in ('mark_unread','mark_read'):
            with patch.object(notifications,'invalidate') as invalidate:
                self.event(action,message_key=key)
                invalidate.assert_called_once()


if __name__=='__main__':unittest.main()
