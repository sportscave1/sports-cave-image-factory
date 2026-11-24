"""Synthetic reviews in disposable PostgreSQL; no providers, uploads or email."""
import os
import asyncio
import json
import unittest
import uuid
from unittest.mock import patch, Mock
from reviews_notifications import status, mark_visible
from reviews_store import ReviewsStore
from tests.crm_db_fixture import connect


class AccessTests(unittest.TestCase):
    def test_api_requires_review_access_and_returns_no_private_rows(self):
        import top_bar_api
        for claims in (None,{'sub':'fixture','allowed_routes':['Orders']}):
            with patch('top_bar_api._claims',return_value=claims),patch('reviews_notifications.status') as query:
                response=asyncio.run(top_bar_api.top_bar_review_status(None))
                self.assertEqual(response.status_code,403);query.assert_not_called()
        with patch('top_bar_api._claims',return_value={'sub':'fixture','allowed_routes':['Reviews']}),patch('reviews_notifications.status',return_value={'unread_count':2,'checked_at':1}):
            response=asyncio.run(top_bar_api.top_bar_review_status(None))
            self.assertEqual(json.loads(response.body),{'ok':True,'unread_count':2,'checked_at':1})
            self.assertIn('no-store',response.headers['cache-control'])

    def test_no_review_access_never_reads_storage(self):
        store=Mock()
        self.assertEqual(status({'sub':'fixture','allowed_routes':[]},store)['unread_count'],0)
        store.q.assert_not_called()

    def test_receipt_requires_active_account(self):
        with patch('reviews_notifications.require',side_effect=PermissionError):
            with self.assertRaises(PermissionError):mark_visible({'id':'fixture'},[],Mock())


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.store=ReviewsStore(connect);self.actor=str(uuid.uuid4());self.ids=[]
        self.permission=patch('reviews_notifications.require');self.permission.start();self.addCleanup(self.permission.stop)
        self.addCleanup(self.clean)

    def clean(self):
        for identity in self.ids:self.store.q('DELETE FROM sc_reviews WHERE id=%s',(identity,))

    def insert(self,**extra):
        identity=str(uuid.uuid4());self.ids.append(identity)
        self.store.q("INSERT INTO sc_reviews(id,source,reviewer_name,rating,dedupe_key,created_at) VALUES(%s,'csv','Synthetic fixture',5,%s,'2020-01-01')",(identity,identity))
        for field,value in extra.items():
            assert field in ('notification_received_at','status')
            self.store.q('UPDATE sc_reviews SET '+field+'=%s WHERE id=%s',(value,identity))
        return identity

    def count(self,actor=None):return status({'sub':actor or self.actor,'allowed_routes':['Reviews']},self.store)['unread_count']
    def seen(self,ids):return mark_visible({'id':self.actor},ids,self.store)

    def test_legacy_no_backfill_and_user_receipts_are_independent(self):
        before=self.count();self.insert(notification_received_at=None)
        new=self.insert();self.assertEqual(self.count(),before+1)
        self.assertEqual(self.seen([new])['marked'],1)
        self.assertEqual(self.count(),before)
        self.assertEqual(self.count('other-'+self.actor),before+1)
        self.assertEqual(self.seen([new])['marked'],0)

    def test_arrival_after_visible_snapshot_remains_unread_and_updates_do_not_renotify(self):
        before=self.count();first=self.insert();second=self.insert()
        receipt=self.seen([first]);self.assertEqual(receipt['unread_count'],before+1)
        self.store.q("UPDATE sc_reviews SET title='Updated',status='PUBLISHED' WHERE id=%s",(first,))
        self.assertEqual(self.count(),before+1)
        self.seen([second]);self.assertEqual(self.count(),before)

    def test_archived_spam_and_oversize_receipts(self):
        before=self.count();self.insert(status='ARCHIVED');self.insert(status='SPAM')
        self.assertEqual(self.count(),before)
        with self.assertRaises(ValueError):self.seen([str(uuid.uuid4()) for _ in range(26)])

    def test_private_arrival_order_preserves_public_date_order(self):
        identity=self.insert()
        self.assertEqual(str(self.store.rows(received_first=True)[0]['id']),identity)

