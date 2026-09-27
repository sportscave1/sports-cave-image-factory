"""V2.2 real-command contracts against fabricated IMAP only."""
from copy import deepcopy
import imaplib
import time
import unittest
from unittest.mock import Mock, patch

import support_email_provider as provider
from tests import test_support_email_v2 as v2
from tests.test_support_email import CONFIG, HEADERS, FakeImap, header


class LiveWire(FakeImap):
    capabilities = (b"IMAP4rev1", b"MOVE")

    def __init__(self):
        super().__init__(count=3)
        self.messages = {"1": (), "2": ("\\Seen",), "3": ("\\Flagged",)}

    def status(self, folder, fields):
        self.calls.append(("status", folder, fields))
        return "OK", [f'INBOX (UNSEEN {sum("\\Seen" not in flags for flags in self.messages.values())} MESSAGES {len(self.messages)} UIDNEXT 4 UIDVALIDITY 500)'.encode()]

    def uid(self, command, *args):
        self.calls.append(("uid", command, *args))
        if command == "SEARCH":
            criteria = args[-1].decode()
            ids = list(self.messages)
            if criteria == "UNSEEN":
                ids = [uid for uid in ids if "\\Seen" not in self.messages[uid]]
            elif criteria.startswith("UID "):
                low, high = map(int, criteria.split()[1].split(":"))
                ids = [uid for uid in ids if low <= int(uid) <= high]
            return "OK", [" ".join(ids).encode()]
        ids = args[0].split(",")
        if command == "FETCH":
            flags = [f'1 (UID {uid} FLAGS ('.encode()+" ".join(self.messages[uid]).encode()+b'))' for uid in ids if uid in self.messages]
            return "OK", ([(raw, HEADERS) for raw in flags] if "HEADER.FIELDS" in args[1] else flags)
        if command == "STORE":
            for uid in ids:
                self.messages[uid] = tuple({*self.messages[uid], "\\Seen"})
        return "OK", []


class LiveProviderTests(unittest.TestCase):
    def setUp(self):
        self.wire = LiveWire()
        self.factory = Mock(return_value=self.wire)
        self.adapter = provider.ImapProvider(CONFIG, connection_factory=self.factory)

    def test_unchanged_poll_fetches_flags_but_no_body_or_headers(self):
        snap = {"messages": [header(str(i)) for i in (1,2,3)], "uidvalidity": "500"}
        result = self.adapter.live_changes("INBOX", snap)
        self.assertEqual(result["added"], [])
        self.assertEqual(result["unread"], 2)
        self.assertEqual(result["flags"]["2"], ("\\Seen",))
        commands = str(self.wire.calls)
        self.assertIn('(UID FLAGS)', commands)
        for forbidden in ('BODY', 'BODYSTRUCTURE', 'SEARCH', 'LIST'):
            self.assertNotIn(forbidden, commands)
        self.factory.assert_called_once()
        self.assertEqual(self.wire.calls[-1], ('logout',))

    def test_new_uid_fetches_only_new_headers_and_no_content(self):
        result = self.adapter.live_changes("INBOX", {"messages": [header("1"),header("2")], "uidvalidity":"500"})
        self.assertEqual([m['uid'] for m in result['added']], ['3'])
        fetches = [c for c in self.wire.calls if c[:2] == ('uid','FETCH')]
        self.assertEqual(fetches[-1][2], '3')
        self.assertIn('BODY.PEEK[HEADER.FIELDS', fetches[-1][-1])
        for forbidden in ('BODY.PEEK[]','BODY.PEEK[1]','BODYSTRUCTURE'):
            self.assertNotIn(forbidden,str(self.wire.calls))

    def test_live_stale_socket_defers_retry_to_next_bounded_check(self):
        bad = LiveWire();bad.status = Mock(side_effect=imaplib.IMAP4.abort('fixture-secret'))
        self.factory.side_effect = [bad,self.wire]
        with self.assertRaises(provider.MailboxError):
            self.adapter.live_changes('INBOX', {'messages':[], 'uidvalidity':'500'})
        self.assertEqual(self.factory.call_count,1)
        result = self.adapter.live_changes('INBOX', {'messages':[], 'uidvalidity':'500'})
        self.assertEqual(result['unread'], 2)
        self.assertEqual(self.factory.call_count,2)
        self.assertEqual(bad.calls[-1],('logout',))

    def test_search_baseline_skips_old_nonmatching_uids(self):
        self.adapter.live_changes('INBOX', {'messages':[header('1')], 'uidvalidity':'500', 'live_uid':3}, query='frame')
        self.assertNotIn('SEARCH',str(self.wire.calls))
        self.assertNotIn('BODY',str(self.wire.calls))

    def test_bulk_read_search_store_status_no_body(self):
        result = self.adapter.mark_folder_read('INBOX')
        self.assertEqual(result['uids'],['1','3'])
        self.assertEqual(result['unread'],0)
        self.assertIn(('uid','STORE','1,3','+FLAGS.SILENT','(\\Seen)'),self.wire.calls)
        self.assertNotIn('BODY',str(self.wire.calls))
        self.assertIn(('select','INBOX',False),self.wire.calls)

    def test_copy_preserves_source_and_move_uses_same_safe_connection_boundary(self):
        before = deepcopy(self.wire.messages)
        self.adapter.copy_message(header('1'),'Archive')
        self.assertIn(('uid','COPY','1','"Archive"'),self.wire.calls)
        self.assertEqual(self.wire.messages,before)
        self.adapter.move_message(header('1'),'Archive')
        self.assertIn(('uid','MOVE','1','"Archive"'),self.wire.calls)
        self.assertEqual(self.factory.call_count,2)


class LiveWorkspaceTests(unittest.TestCase):
    setUp = v2.WorkspaceTests.setUp
    event = v2.WorkspaceTests.event
    open = v2.WorkspaceTests.open
    compose = v2.WorkspaceTests.compose

    def tick(self):
        self.state['live_checked_at']=0
        self.event('live_check')

    def arrive(self):
        message = header('76','<new-76@example.test>',subject='New live arrival',hours=1000)
        self.imap.messages.append(message)
        return message

    def test_new_mail_updates_list_and_count_without_full_load(self):
        before = self.w.model()['inbox_status']['unread_count']
        self.arrive();self.imap.calls.clear()
        with patch.object(v2.store,'load_orders',side_effect=AssertionError('Orders forbidden')):
            self.tick()
        self.assertEqual(self.imap.calls,[('live','INBOX')])
        self.assertEqual(self.w.model()['threads'][0]['subject'],'New live arrival')
        self.assertEqual(self.w.model()['inbox_status']['unread_count'],before+1)

    def test_selection_composer_query_and_opened_content_survive_live_check(self):
        self.open();selected=self.state['selected'];active=self.state['active_message']
        self.compose('reply');draft=self.state['draft'];draft['html']='<p>Unsent edits</p>'
        self.arrive();self.imap.calls.clear();self.tick()
        self.assertEqual(self.state['selected'],selected)
        self.assertEqual(self.state['active_message'],active)
        self.assertIs(self.state['draft'],draft)
        self.assertEqual(self.state['view'],'compose')
        self.assertEqual(self.imap.calls,[('live','INBOX')])
        self.assertTrue(self.w.bodies.data['entries'])

    def test_notification_target_outside_latest_page_survives_arrival(self):
        message=self.imap.messages[0]
        self.imap.notification_target=Mock(return_value=deepcopy(message))
        self.w.open_notification(message)
        active=self.state['active_message']
        self.arrive();self.tick()
        self.assertEqual(self.state['active_message'],active)
        self.assertTrue(any(m['key']==active for m in self.w.model()['messages']))

    def test_live_does_not_switch_folders_or_repeat_historical_search(self):
        self.event('folder',folder='Archive');self.arrive();self.imap.calls.clear()
        self.state['query']='frame';self.tick()
        self.assertEqual(self.state['folder'],'Archive')
        self.assertEqual(self.state['query'],'frame')
        self.assertEqual(self.imap.calls,[('live','Archive')])

    def test_live_ttl_and_failure_recovery_are_bounded(self):
        self.imap.calls.clear()
        recorded=len(self.state['processed'])
        for _ in range(4):self.event('live_check')
        self.assertEqual(self.imap.calls,[])
        self.assertEqual(len(self.state['processed']),recorded)
        self.imap.fail=True;self.tick()
        self.assertIn('Reconnecting',self.state['live_error'])
        self.imap.fail=False;self.tick();self.assertTrue(self.state['live_error'])
        self.state['load_retry_at']=0
        self.tick();self.assertEqual(self.state['live_error'],'')

    def test_only_visible_message_marks_read_and_reopen_does_not_store_again(self):
        before=self.w.model()['inbox_status']['unread_count']
        self.imap.calls.clear();self.open()
        self.assertEqual([c[0] for c in self.imap.calls],['body','flag'])
        self.assertFalse(self.w.model()['messages'][0]['unread'])
        self.assertEqual(self.w.model()['inbox_status']['unread_count'],before-1)
        self.imap.calls.clear();self.open();self.assertEqual(self.imap.calls,[])

    def test_flag_changes_preserve_cached_thread_membership(self):
        key=self.open()
        self.event('resolve_thread',thread_key=self.state['selected'],mailbox_version=self.state['mailbox_version'])
        self.assertTrue(self.w.resolved_threads.data['entries'])
        self.event('mark_unread',message_key=key)
        self.imap.calls.clear();self.open()
        self.assertEqual([c[0] for c in self.imap.calls],['flag'])
        self.assertFalse(self.state['history_pending'])
        self.tick();self.imap.calls.clear();self.open()
        self.assertEqual(self.imap.calls,[])

    def test_initial_load_and_poll_never_mark_messages_read(self):
        self.imap.calls.clear();before=self.w.model()['inbox_status']['unread_count']
        self.tick()
        self.assertEqual(self.w.model()['inbox_status']['unread_count'],before)
        self.assertFalse(any(c[0]=='flag' for c in self.imap.calls))

    def test_empty_search_does_not_gain_false_load_more_after_poll(self):
        self.event('search',query='no-matching-message')
        self.tick()
        self.assertEqual(self.state['snapshot']['messages'],[])
        self.assertFalse(self.state['snapshot']['has_more'])

    def test_failed_body_never_marks_read_and_failed_store_never_lies(self):
        before=self.w.model()['inbox_status']['unread_count']
        with patch.object(self.imap,'read_message',side_effect=RuntimeError('fixture')):
            self.open()
        self.assertFalse(any(c[0]=='flag' for c in self.imap.calls))
        with patch.object(self.imap,'set_flag',side_effect=provider.MailboxError('fixture')):
            self.open()
        self.assertEqual(self.w.model()['inbox_status']['unread_count'],before)
        self.assertTrue(self.w.model()['messages'][0]['unread'])

    def test_mark_unread_and_external_thunderbird_flags(self):
        key=self.open();self.event('mark_unread',message_key=key)
        self.assertTrue(self.w.model()['messages'][0]['unread'])
        message=next(m for m in self.imap.messages if v2.reference_key(m)==key)
        message.update(flags=('\\Seen','\\Flagged'),unread=False)
        self.tick()
        self.assertFalse(self.w.model()['messages'][0]['unread'])
        self.assertTrue(self.w.model()['messages'][0]['starred'])

    def test_context_nonselected_target_no_body_and_shared_actions(self):
        target=self.w.model()['threads'][2];self.imap.calls.clear()
        self.event('star',message_key=target['message_key'])
        self.assertEqual([c[0] for c in self.imap.calls],['flag'])
        self.assertIsNone(self.state.get('selected'))
        self.event('unstar',message_key=target['message_key'])
        self.assertFalse(next(t for t in self.w.model()['threads'] if t['key']==target['key'])['starred'])

    def test_move_copy_archive_junk_trash_discovered_destinations_only(self):
        target=self.w.model()['threads'][0];key=target['message_key']
        self.event('copy',message_key=key,destination='Customers')
        self.assertTrue(any(v2.reference_key(m)==key for m in self.imap.messages))
        self.assertTrue(any(m['folder']=='Customers' for m in self.imap.messages))
        self.imap.calls.clear();self.event('move',message_key=key,destination='Not discovered')
        self.assertEqual(self.imap.calls,[])
        for action,dest in [('archive','Archive'),('junk','Junk'),('trash','Trash'),('move','Customers')]:
            key=self.w.model()['threads'][0]['message_key']
            self.event(action,message_key=key,destination=dest)
            self.assertTrue(any(c[0]=='move' and c[2]==dest for c in self.imap.calls))

    def test_folder_bulk_requires_confirmation_then_updates_all_loaded_flags(self):
        self.imap.calls.clear();self.event('mark_folder_read',folder='INBOX')
        self.assertEqual(self.imap.calls,[])
        self.event('mark_folder_read',folder='INBOX',confirmed=True)
        self.assertEqual(self.imap.calls,[('folder_read','INBOX')])
        self.assertFalse(any(t['unread'] for t in self.w.model()['threads']))
        self.assertEqual(self.w.model()['inbox_status']['unread_count'],0)

    def test_folder_refresh_keeps_folder_cache_and_search_uses_existing_route(self):
        self.imap.calls.clear();self.event('refresh_folder',folder='INBOX')
        self.assertEqual([c[0] for c in self.imap.calls],['headers'])
        self.imap.calls.clear();self.event('search_folder',folder='INBOX')
        self.assertEqual(self.imap.calls,[])
        self.event('search_folder',folder='Archive')
        self.assertEqual(self.state['folder'],'Archive')


if __name__=='__main__':unittest.main()

