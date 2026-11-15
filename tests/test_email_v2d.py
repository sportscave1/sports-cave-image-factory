"""V2D local contracts: validated searches and bounded, identity-fenced triage."""
from copy import deepcopy
from contextlib import nullcontext
import os
import unittest
import uuid
from unittest.mock import Mock, patch

from tests.test_email_outlook_v2a import Reliability
from tests.test_support_email_v2 import FolderTests
from support_email_tools import filters, criteria, contacts
from support_email_provider import MailboxError
from support_email_workspace import reference_key


adapter=FolderTests.adapter


class Search(unittest.TestCase):
    def test_combined_criteria_and_dates(self):
        value=criteria(dict(unread=True,flagged=True,sender='test@example.test',subject='A "quoted" item',since='2026-01-01',before='2026-02-01'))
        self.assertIn('UNSEEN FLAGGED FROM "test@example.test"',value)
        self.assertIn('SINCE 01-Jan-2026 BEFORE 01-Feb-2026',value)
        self.assertIn(r'SUBJECT "A \"quoted\" item"',value)

    def test_rejects_raw_criteria_invalid_booleans_dates_and_scope(self):
        for value in [{'raw':'ALL'},{'unread':'UNSEEN'},{'sender':'x\r\nUID STORE'},{'before':'yesterday'},{'since':'2026-02-01','before':'2026-01-01'},{'scope':'anything'},[]]:
            with self.subTest(value=value),self.assertRaises(MailboxError):filters(value)

    def test_provider_combined_filters_only_fetch_headers(self):
        p,wire=adapter(self)
        p.list_headers(query='invoice',filters={'unread':True,'flagged':True,'sender':'a@example.test'})
        search=next(c for c in wire.calls if c[:2]==('uid','SEARCH'))
        self.assertEqual(search[3],b'TEXT "invoice" UNSEEN FLAGGED FROM "a@example.test"')
        self.assertFalse(any('BODY[]' in str(c) for c in wire.calls))

    def test_attachment_filter_structure_only_and_cursor_survives_empty_page(self):
        p,wire=adapter(self)
        with patch.object(p,'_structure',return_value=[{'attachment':False}]) as structure:
            page=p.list_headers(limit=2,filters={'attachments':True})
        self.assertEqual(page['messages'],[])
        self.assertTrue(page['has_more']);self.assertGreater(page['next_before_uid'],0)
        self.assertEqual(structure.call_count,1)  # Wire fixture returns one header for this bounded UID fetch.
        fetch=next(c for c in wire.calls if c[:2]==('uid','FETCH'))
        self.assertEqual(fetch[2],'2,101')

    def test_all_folder_search_is_bounded_and_partial(self):
        p,_=adapter(self)
        with patch.object(p,'list_headers',return_value={'messages':[],'has_more':False}) as call:
            result=p.search_folders([f'Folder {i}' for i in range(20)],filters={'unread':True})
        self.assertEqual(call.call_count,12);self.assertTrue(result['search_partial']);self.assertFalse(result['has_more'])

    def test_failed_folder_is_explicit_partial(self):
        p,_=adapter(self)
        with patch.object(p,'list_headers',side_effect=[{'messages':[],'has_more':False},MailboxError('failed')]):
            result=p.search_folders(['INBOX','Archive'])
        self.assertEqual(result['search_failures'],['Archive']);self.assertTrue(result['search_partial'])


class InboxTools(unittest.TestCase):
    setUp=Reliability.setUp
    event=Reliability.event

    def items(self,n=2):
        return [dict(key=t['message_key'],identity=t['identity']) for t in self.w.model()['threads'][:n]]

    def test_bulk_flags_confirm_individually_and_survive_sync(self):
        items=self.items();self.event('bulk_action',operation='star',items=items)
        self.assertEqual([r['status'] for r in self.w.state['bulk_result']['items']],['confirmed']*2)
        self.w.live_check()
        self.assertTrue(all('\\Flagged' in self.w._header(i['key'])['flags'] for i in items))

    def test_bulk_moves_do_not_resurrect(self):
        items=self.items();self.event('bulk_action',operation='archive',items=items);self.w.live_check()
        keys=[reference_key(m) for m in self.w.state['snapshot']['messages']]
        self.assertTrue(all(i['key'] not in keys for i in items))

    def test_bulk_duplicate_event_never_replays(self):
        event=dict(id=str(uuid.uuid4()),action='bulk_action',operation='star',items=self.items())
        self.w.handle(event);calls=len(self.provider.calls);self.assertFalse(self.w.handle(event));self.assertEqual(calls,len(self.provider.calls))

    def test_bulk_wrong_actor_identity_never_writes(self):
        items=self.items();items[0]['identity']='foreign-session'
        self.event('bulk_action',operation='star',items=items)
        self.assertEqual([r['status'] for r in self.w.state['bulk_result']['items']],['not_attempted','confirmed'])

    def test_bulk_unchanged_flags_do_not_claim_a_new_provider_write(self):
        items=self.items()
        self.event('bulk_action',operation='star',items=items)
        with patch.object(self.w,'message_action') as mutate:
            self.event('bulk_action',operation='star',items=self.items())
        mutate.assert_not_called()
        self.assertEqual([r['status'] for r in self.w.state['bulk_result']['items']],['unchanged','unchanged'])

    def test_bulk_message_id_reuse_rejected(self):
        items=self.items(1);self.w._header(items[0]['key'])['message_id']='<reused@example.test>'
        self.event('bulk_action',operation='trash',items=items)
        self.assertEqual(self.w.state['bulk_result']['items'][0]['status'],'not_attempted')

    def test_bulk_ambiguous_error_not_replayed(self):
        with patch.object(self.w,'message_action',side_effect=[MailboxError('timeout'),None]) as action:
            self.event('bulk_action',operation='archive',items=self.items())
        self.assertEqual(action.call_count,2)
        self.assertEqual([r['status'] for r in self.w.state['bulk_result']['items']],['unconfirmed','confirmed'])

    def test_bulk_duplicate_oversize_and_unsafe_action_rejected(self):
        for operation,items in [('star',self.items(1)*2),('star',[{'key':str(i)} for i in range(51)]),('expunge',self.items())]:
            self.event('bulk_action',operation=operation,items=items)
            self.assertNotIn('bulk_result',self.w.state)

    def test_restore_requires_trash_and_valid_destination(self):
        self.event('restore',message_key=self.items(1)[0]['key'],destination='INBOX')
        self.assertIn('Restore',self.w.state['notice'])
        self.assertFalse(any(c[0]=='move' for c in self.provider.calls))

    def test_collapse_never_fetches_bodies_or_retains_grants(self):
        self.w.state.update(expanded={'one'},image_grants={'grant'})
        calls=len(self.provider.calls);self.event('collapse_conversation')
        self.assertEqual(self.w.state['expanded'],set());self.assertEqual(self.w.state['image_grants'],set());self.assertEqual(calls,len(self.provider.calls))

    def test_contacts_permission_blocks_crm_but_allows_own_recent(self):
        self.w.state['local_drafts']=[{'recipients':'Own Person <own@example.test>'}]
        with patch('os_accounts.can_access_page',side_effect=lambda user,route:route=='Email'),patch('support_email_store.search_contacts') as db:
            result=contacts(self.w,'own')
        db.assert_not_called();self.assertEqual(result[0]['email'],'own@example.test')

    def test_contacts_no_empty_enumeration_and_limit(self):
        with patch('support_email_store.search_contacts',return_value=[dict(name='A',email=f'a{i}@example.test',source='Synced customer record') for i in range(20)]) as db:
            self.assertEqual(contacts(self.w,''),[]);db.assert_not_called()
            self.assertLessEqual(len(contacts(self.w,'ab')),8)

    def test_contact_event_preserves_draft_and_has_no_send(self):
        self.event('compose',mode='new');draft=self.w.state['draft'];draft['html']='<p>Keep my edits</p>'
        with patch('support_email_store.search_contacts',return_value=[]):self.event('contact_search',query='test')
        self.assertEqual(self.w.state['draft']['html'],'<p>Keep my edits</p>')
        self.assertEqual(self.w.state['draft']['id'],draft['id']);self.assertEqual(self.w.state['view'],'compose')

    def test_contact_database_has_separate_permission_check(self):
        from support_email_store import search_contacts
        with patch('os_accounts.can_access_page',return_value=False),patch('support_email_store.cursor') as db:
            with self.assertRaises(PermissionError):search_contacts(self.w.user,'ab')
        db.assert_not_called()

    def test_changed_filters_do_not_show_previous_snapshot(self):
        self.w.state['filters']={'unread':True}
        self.assertFalse(self.w.model()['threads'])

    def test_confirmed_flag_removes_row_from_active_filter_without_losing_reader(self):
        self.w.state['filters']={'unread':True}
        self.w.state['snapshot_filters']={'unread':True}
        message=next(m for m in self.w.state['snapshot']['messages'] if m['unread'])
        key=reference_key(message)
        self.w.message_action('mark_read',message)
        self.assertNotIn(key,[reference_key(m) for m in self.w.state['snapshot']['messages']])
        self.assertTrue(self.w.model()['threads'])
        self.assertTrue(all(t['unread'] for t in self.w.model()['threads']))


del Reliability, FolderTests


@unittest.skipUnless(os.environ.get('EMAIL_TEST_POSTGRES')=='1','Disposable Email PostgreSQL fixture required')
class ContactSQL(unittest.TestCase):
    def test_recent_recipient_actor_mailbox_and_accepted_scope(self):
        from tests.test_email_durable_delivery import Connection
        from support_email_durable import MailStore
        store=MailStore(connect=Connection);actor=str(uuid.uuid4());mailbox=str(uuid.uuid4())+'@example.test'
        for owner,box,address,status in [(actor,mailbox,'own@example.test','accepted'),('someone-else',mailbox,'other@example.test','accepted'),(actor,'other-'+mailbox,'other-mailbox@example.test','accepted'),(actor,mailbox,'uncertain@example.test','unknown')]:
            operation=str(uuid.uuid4());store.prepare(box,operation,dict(bytes=b'Synthetic',message_id='<'+operation+'>',recipients=[address]),actor=owner)
            with Connection() as connection:
                connection.execute('UPDATE support_email_outbox SET status=%s WHERE mailbox=%s AND operation_id=%s',(status,box,operation))
        self.assertEqual(store.recent_recipients(mailbox,actor),['own@example.test'])

    def test_synced_contact_literal_query_and_bounded_result(self):
        from tests.test_email_durable_delivery import Connection
        from support_email_store import search_contacts
        from tests.email_v2_fixtures import USER
        token=uuid.uuid4().hex
        first_id=uuid.uuid4().int % (2**62)
        with Connection() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS shopify_orders (shopify_order_id bigint, customer_name text,customer_email text,email text,created_at timestamptz)')
            for i in range(10):connection.execute('INSERT INTO shopify_orders (shopify_order_id,customer_name,customer_email,email,created_at) VALUES (%s,%s,%s,%s,now())',(first_id+i,token+' Customer',f'{token}{i}@example.test',''))
            with patch('support_email_store.cursor',return_value=nullcontext(connection)):
                rows=search_contacts(USER,token)
                self.assertEqual(len(rows),8)
                self.assertTrue(all(token in r['email'] for r in rows))
                self.assertEqual(search_contacts(USER,"' OR 1=1 --"),[])
