"""Email V2.1 read-path and cache contracts. No live mailbox or database traffic."""
from unittest.mock import Mock, patch
import unittest

import support_email_workspace as workspace
import support_email_provider as provider
from support_email_cache import DisplayLRU, ordered_folders
from tests.test_support_email import CONFIG, header
from tests import test_support_email_v2 as v2_tests


class SelectionPerformanceTests(unittest.TestCase):
    setUp = v2_tests.WorkspaceTests.setUp
    event = v2_tests.WorkspaceTests.event
    open = v2_tests.WorkspaceTests.open
    compose = v2_tests.WorkspaceTests.compose

    def resolve(self):
        self.event("resolve_thread",thread_key=self.state["selected"],mailbox_version=self.state["mailbox_version"])

    def test_cold_selection_only_fetches_requested_body(self):
        self.w.bodies.clear()  # Initial Inbox selection now preloads one body.
        self.imap.calls.clear()
        with patch.object(workspace.store,"load_orders") as orders,patch.object(workspace.store,"load_metadata") as metadata:
            self.open()
            self.assertEqual([c[0] for c in self.imap.calls],["body","flag"])
            orders.assert_not_called();metadata.assert_not_called()
        self.assertTrue(self.w.model()["messages"][0]["expanded"])
        self.assertTrue(self.state["history_pending"])

    def test_reopen_after_header_expiry_does_not_fetch_body_or_resolve_history(self):
        self.open();self.resolve()
        for item in self.w.cache.values():item['expires']=0
        self.imap.calls.clear()
        self.open();self.resolve()
        self.assertEqual(self.imap.calls,[])

    def test_selection_never_discovers_folders_headers_previews_or_orders(self):
        self.w.bodies.clear()
        self.imap.calls.clear()
        with patch.object(workspace.store,'load_orders') as orders:
            for t in self.state['threads'][:5]:
                self.event('open_thread',thread_key=t['thread_key'])
                self.w.model()
            self.assertEqual([c[0] for c in self.imap.calls if c[0]!='flag'],['body']*5)
            orders.assert_not_called()

    def test_safe_html_prepared_once_and_model_list_reused(self):
        self.w.bodies.clear()
        with patch.object(workspace,'readable_html',wraps=workspace.readable_html) as html,patch.object(workspace,'build_threads',wraps=workspace.build_threads) as threads:
            self.open()
            rows=self.w.model()['threads']
            for _ in range(5):
                self.open();self.assertIs(self.w.model()['threads'],rows)
            self.assertEqual(html.call_count,2)
            threads.assert_not_called()

    def test_refresh_invalidates_history_headers_but_preserves_identity_matched_body(self):
        self.open();self.resolve()
        version=self.state['mailbox_version'];key=self.state['selected']
        self.imap.calls.clear();self.event('refresh')
        self.assertGreater(self.state['mailbox_version'],version)
        self.assertEqual([c[0] for c in self.imap.calls],['folders','headers'])
        self.assertIsNone(self.w.resolved_threads.get((version,key)))
        self.open();self.assertFalse(any(c[0]=='body' for c in self.imap.calls))
        self.resolve();self.assertEqual(len([c for c in self.imap.calls if c[0]=='related']),2)

    def test_refresh_preserves_open_composer_and_context(self):
        self.open();self.compose()
        draft=self.state['draft']['id'];self.state['context']={'label':'Existing context'}
        self.event('refresh')
        self.assertEqual(self.state['view'],'compose')
        self.assertEqual(self.state['draft']['id'],draft)
        self.assertEqual(self.state['context']['label'],'Existing context')

    def test_mailbox_write_invalidates_history_but_keeps_opened_mime(self):
        self.open();self.resolve()
        version=self.state['mailbox_version'];self.w._mailbox_changed()
        self.assertGreater(self.state['mailbox_version'],version)
        self.assertEqual(len(self.w.resolved_threads.data['entries']),0)
        self.imap.calls.clear();self.open()
        self.assertEqual(self.imap.calls,[])

    def test_uidvalidity_change_does_not_reuse_old_body(self):
        self.open()
        for m in self.imap.messages:m['uidvalidity']='new-uidvalidity'
        original=self.imap.list_headers
        def headers(*args,**kwargs):
            result=original(*args,**kwargs);result['uidvalidity']='new-uidvalidity';return result
        with patch.object(self.imap,'list_headers',side_effect=headers):self.event('refresh')
        self.imap.calls.clear();self.open()
        self.assertEqual([c[0] for c in self.imap.calls],['body'])
        self.assertTrue(all(k[2]=='new-uidvalidity' for k in self.w.bodies.data['entries']))

    def test_changed_message_id_cannot_reuse_old_content(self):
        self.open();self.imap.messages[-1]['message_id']='<different@example.test>'
        self.imap.calls.clear();self.event('refresh')
        self.assertEqual([c[0] for c in self.imap.calls if c[0]=='body'],['body'])
        self.imap.calls.clear();self.open()
        self.assertEqual(self.imap.calls,[])  # Fallback selection fetched the new identity.

    def test_delayed_history_for_old_selection_or_version_is_ignored(self):
        self.open();old=self.state['selected'];version=self.state['mailbox_version']
        other=self.state['threads'][1]['thread_key'];self.event('open_thread',thread_key=other)
        self.imap.calls.clear()
        self.event('resolve_thread',thread_key=old,mailbox_version=version)
        self.event('resolve_thread',thread_key=other,mailbox_version=version-1)
        self.assertEqual(self.imap.calls,[])
        self.assertEqual(self.state['selected'],other)

    def test_history_failure_does_not_hide_loaded_body(self):
        self.open()
        with patch.object(self.imap,'related_headers_many',side_effect=provider.MailboxError('Safe connection error')):
            self.resolve()
        model=self.w.model()
        self.assertTrue(model['messages'][0]['expanded'])
        self.assertFalse(model['error']);self.assertIn('Older conversation',model['notice'])

    def test_body_failure_not_cached_and_no_attachment_fetch_on_open(self):
        self.w.bodies.clear()
        with patch.object(self.imap,'read_message',side_effect=RuntimeError('fixture-secret')):
            self.open()
        self.assertEqual(len(self.w.bodies.data['entries']),0)
        self.open();self.assertEqual([c[0] for c in self.imap.calls].count('attachment'),0)
        self.assertNotIn('fixture-secret',self.state['notice'])

    def test_folder_cache_survives_header_expiry_and_expires_independently(self):
        self.imap.calls.clear()
        for item in self.w.cache.values():item['expires']=0
        self.w.load()
        self.assertEqual([c[0] for c in self.imap.calls],['headers'])
        self.state['folder_cache']['expires']=0;self.imap.calls.clear();self.w.load()
        self.assertEqual([c[0] for c in self.imap.calls],['folders'])

    def test_order_drawer_still_reads_on_demand_only(self):
        with patch.object(workspace.store,'load_orders',return_value=[]) as orders:
            self.open();self.resolve();self.w.model();orders.assert_not_called()
            self.event('context');orders.assert_called_once()

    def test_search_still_queries_live_provider_and_paginates(self):
        self.event('search',query='subject: Delivery update')
        request=[c for c in self.imap.calls if c[0]=='headers'][-1]
        self.assertEqual(request[-1]['field'],'SUBJECT')
        self.assertEqual(request[-1]['query'],'Delivery update')
        self.event('load_more');self.assertEqual(self.state['limit'],100)

    def test_model_orders_discovered_inbox_first(self):
        self.state['folders']=list(reversed(self.state['folders']))
        self.assertEqual([f['name'] for f in self.w.model()['folders']],['INBOX','Drafts','INBOX.Sent Items','Archive','Junk','Trash','Customers'])


class CacheAndProviderTests(unittest.TestCase):
    def test_email_rerun_stays_fragment_local_except_full_run_reconnect(self):
        import support_email_page as page
        with patch.object(page.st,'rerun') as rerun:
            page.rerun_email();rerun.assert_called_once_with(scope='fragment')
        with patch.object(page.st,'rerun',side_effect=[page.StreamlitAPIException('Full run'),None]) as rerun:
            page.rerun_email()
            self.assertEqual(rerun.call_args_list,[unittest.mock.call(scope='fragment'),unittest.mock.call()])

    def test_lru_bounds_entry_count_and_byte_budget(self):
        cache=DisplayLRU({},'test',limit=2,byte_limit=100)
        cache.put('a','one');cache.put('b','two');cache.get('a');cache.put('c','three')
        self.assertIsNone(cache.get('b'));self.assertEqual(cache.get('a'),'one')
        self.assertFalse(cache.put('large','x'*101))
        cache.put('big','x'*95)
        self.assertLessEqual(cache.data['bytes'],100)
        self.assertEqual(len(cache.data['entries']),1)
        cache.clear();self.assertEqual(cache.data['bytes'],0)

    def test_system_order_then_custom_alphabetical_without_changing_names(self):
        names=['Zulu','Trash','Sent','INBOX','Archive','Drafts','Alpha','Junk','Flagged']
        folders=[{'name':name,'label':name,'role':''} for name in names]
        roles={name.lower():name for name in names if name not in {'Zulu','Alpha'}}
        result=ordered_folders(folders,roles)
        self.assertEqual([f['name'] for f in result],['INBOX','Flagged','Drafts','Sent','Archive','Junk','Trash','Alpha','Zulu'])
        self.assertEqual([f['name'] for f in folders],names)

    def test_history_reuses_one_connection_and_readonly_selects_each_folder(self):
        wire=v2_tests.WireImap();factory=Mock(return_value=wire)
        p=provider.ImapProvider(CONFIG,connection_factory=factory)
        result=p.related_headers_many(['INBOX','INBOX.Sent Items'],['<one@example.test>'])
        factory.assert_called_once()
        self.assertEqual([c for c in wire.calls if c[0]=='select'],[('select','INBOX',True),('select','"INBOX.Sent Items"',True)])
        self.assertEqual([m['folder'] for m in result],['INBOX','INBOX.Sent Items'])
        self.assertEqual(len([c for c in wire.calls if c[0]=='logout']),1)
        self.assertFalse(any('BODY.PEEK[]' in str(c) for c in wire.calls))

    def test_failed_history_socket_is_closed_and_next_operation_reconnects(self):
        bad,good=v2_tests.WireImap(),v2_tests.WireImap();bad.select=Mock(side_effect=TimeoutError('fixture-password'))
        factory=Mock(side_effect=[bad,good]);p=provider.ImapProvider(CONFIG,connection_factory=factory)
        with self.assertRaises(provider.MailboxError):p.related_headers_many(['INBOX'],['<one@example.test>'])
        self.assertIn(('logout',),bad.calls)
        p.related_headers_many(['INBOX'],['<one@example.test>']);self.assertEqual(factory.call_count,2)

    def test_uncached_body_uses_one_connection_and_safe_peek_no_attachment(self):
        wire=v2_tests.WireImap();factory=Mock(return_value=wire)
        p=provider.ImapProvider(CONFIG,connection_factory=factory)
        p.read_message(header());factory.assert_called_once()
        self.assertIn(('select','INBOX',True),wire.calls)
        self.assertTrue(any('BODY.PEEK[1]' in str(c) for c in wire.calls))
        self.assertFalse(any('BODY.PEEK[2]' in str(c) for c in wire.calls))


if __name__=='__main__':unittest.main()
