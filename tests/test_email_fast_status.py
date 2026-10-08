"""Local-only regression checks: counts, read recovery and durable confirmation."""
import asyncio
import threading
import time
import unittest
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch
from starlette.requests import Request
import support_email_notifications as notifications
from support_email_reads import ReadService
from support_email_provider import MailboxError
from support_email_durable import receipt
from support_email_workspace import Workspace
from tests.test_email_inbox_reliability import Provider
from tests.email_v2_fixtures import CONFIG


class FastStatusTests(unittest.TestCase):
    def setUp(self):
        if notifications._REFRESH:notifications._REFRESH.result(timeout=3)
        self.saved=deepcopy(notifications._CACHE)
        notifications._CACHE.update(scope=None,value={},expires=0,success=0)
        self.addCleanup(notifications._CACHE.update,self.saved)

    def test_immediate_deduplicated_count_and_account_isolation(self):
        gate=threading.Event()
        def refresh(**kwargs):gate.wait(2)
        with patch.object(notifications,'load_configuration',return_value=CONFIG),patch.object(notifications,'status',side_effect=refresh) as call:
            start=time.perf_counter()
            try:
                for _ in range(10):
                    result=notifications.fast_status()
                    self.assertTrue(result['refreshing']);self.assertIsNone(result['unread_count'])
                self.assertLess(time.perf_counter()-start,.2)
            finally:gate.set();notifications._REFRESH.result(timeout=3)
            self.assertEqual(call.call_count,1)
        notifications._CACHE.update(scope=CONFIG.scope,value={'unread_count':7,'checked_at':1,'available':False})
        self.assertEqual(notifications.cached_status(CONFIG.scope)['unread_count'],7)
        self.assertIsNone(notifications.cached_status('other-account')['unread_count'])

    def test_busy_refresh_preserves_count_without_connecting(self):
        notifications._CACHE.update(scope=CONFIG.scope,value={'unread_count':3,'available':True})
        with notifications._LOCK:
            result=notifications.status(configuration=CONFIG)
        self.assertEqual(result['unread_count'],3);self.assertTrue(result['stale'])

    def test_wall_count_request_does_not_load_activity(self):
        import top_bar_api
        request=Request({'type':'http','method':'GET','path':'/','headers':[], 'query_string':b'counts_only=1'})
        with patch.object(top_bar_api,'_claims',return_value={'sub':'fixture'}),patch.object(top_bar_api,'load_notification_sources') as history,patch('wall_preview_notifications.status',return_value={'unread_count':4,'notifications':[]}) as count:
            response=asyncio.run(top_bar_api.top_bar_notifications(request))
        history.assert_not_called();count.assert_called_once_with({'sub':'fixture'},count_only=True)
        self.assertIn(b'"wall_unread_count":4',response.body)

    def test_orders_unavailable_is_not_zero(self):
        import top_bar_api
        with patch('supabase_backend.is_configured',return_value=True),patch.object(top_bar_api,'_cached_order_action_summary',side_effect=RuntimeError()),patch('supabase_backend.consume_new_order_notifications',return_value=[]),patch('order_allocator.load_orders_snapshot',return_value=None):
            self.assertIsNone(top_bar_api.load_order_status({'sub':'fixture','allowed_routes':['Orders']})['action_required_count'])

    def test_failed_read_can_recover_without_twenty_second_negative_cache(self):
        reads=ReadService(Provider(1),Mock());self.addCleanup(reads.close)
        loader=Mock(side_effect=[MailboxError('offline',code='timeout'),{'ok':True}])
        with self.assertRaises(MailboxError):reads.request(('body',),loader,wait=True)
        self.assertEqual(reads.request(('body',),loader,wait=True),{'ok':True})
        self.assertEqual(loader.call_count,2)

    def test_deferred_sync_does_not_invent_connection_failure(self):
        provider=Provider(1);provider.list_headers=Mock(side_effect=MailboxError('backoff',code='deferred',retry_after=45))
        reads=ReadService(provider,Mock());self.addCleanup(reads.close)
        reads.health.update(state='CONNECTED',last_success_at=time.time())
        reads.sync()
        self.assertEqual(reads.health['state'],'CONNECTED');self.assertEqual(reads.health['attempts'],0)
        self.assertGreater(reads.health['retry_at'],reads.clock()+40)

    def test_unknown_receipt_stops_spinner_without_inventing_success_or_retry(self):
        value=receipt({'operation_id':'fixture','status':'unknown','message_id':'id','fingerprint':'fp',
            'created_at':datetime.now(timezone.utc)-timedelta(minutes=20),'reconcile_attempts':2})
        self.assertTrue(value['verification_overdue']);self.assertEqual(value['status'],'unknown')
        fake=Mock();fake.state={'send_result':{'status':'unknown'}};fake.durable=True
        Workspace.check_sent(fake,automatic=True)
        fake.recover_send.assert_called_once();fake.registry.reconcile.assert_not_called();fake._finish_send.assert_not_called()

    def test_recent_peer_snapshot_restores_health_but_old_snapshot_does_not(self):
        store=Mock();reads=ReadService(Provider(1),store);self.addCleanup(reads.close)
        store.read_index.return_value={'snapshot':{'messages':[]},'observed_at':time.time(),'synced_at':time.time()}
        from support_email_db_guard import SNAPSHOT_DB
        with patch.object(SNAPSHOT_DB,'ready',return_value=True):reads.restore()
        self.assertEqual(reads.health_snapshot()['state'],'CONNECTED')
        reads.health['last_success_at']=time.time()-600
        self.assertEqual(reads.health_snapshot()['state'],'RECONNECTING')


if __name__=='__main__':unittest.main()
