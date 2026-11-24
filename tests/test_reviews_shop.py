"""Shop inbox tests use synthetic records and a disposable localhost database."""
from copy import deepcopy
from datetime import timedelta
import json
import os
import unittest
import uuid
from unittest.mock import Mock

from crm_logic import now
from reviews_shop import decode, import_entry, tick, KEY
from reviews_store import ReviewsStore
from reviews_rewards import eligibility
from tests.crm_db_fixture import connect


def entry(seed='1', **changes):
    values={'body':'A genuine fixture review','rating':'4.0',
      'product_id':'gid://shopify/Product/'+seed,'order_id':'gid://shopify/Order/'+seed,
      'variant_id':'gid://shopify/ProductVariant/'+seed,'line_item_id':'gid://shopify/LineItem/'+seed,
      'display_name':'Fixture '+seed,'submitted_at':(now()-timedelta(days=1)).isoformat(),**changes}
    return {'id':'gid://shopify/Metaobject/'+seed,'handle':'shop-'+seed+'-'+seed,
      'updatedAt':now().isoformat(),'fields':[{'key':k,'value':v} for k,v in values.items()]}


class DecodeTests(unittest.TestCase):
    def test_verified_provenance_has_no_native_reward_identity(self):
        item=decode(entry(),'fixture.myshopify.com')
        self.assertEqual(item['source'],'shop_app');self.assertEqual(item['rating'],4)
        self.assertTrue(item['source_verified']);self.assertFalse(item['verified_purchase'])
        self.assertIsNone(eligibility(item,[{'kind':'image','status':'COPIED','approved':True,'consent':True}],{'rewards_enabled':True}))

    def test_invalid_ids_dates_and_ratings_fail_closed(self):
        for value in (entry(rating='6'),entry(rating='4.5'),entry(submitted_at=''),entry(submitted_at='2100-01-01'),entry(product_id='elsewhere'),{**entry(),'handle':'wrong'}):
            with self.assertRaises(ValueError):decode(value,'fixture.myshopify.com')

    def test_rating_only_stays_in_inbox_and_text_is_sanitized(self):
        self.assertIsNone(decode(entry(body=''),'fixture.myshopify.com'))
        item=decode(entry(body='<script>bad()</script><b>Excellent</b>'),'fixture.myshopify.com')
        self.assertEqual(item['body'],'Excellent')


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class InboxTests(unittest.TestCase):
    def setUp(self):
        self.store=ReviewsStore(connect);self.seed=str(uuid.uuid4().int%10**12);self.value=entry(self.seed)
        self.item=decode(self.value,'fixture.myshopify.com');self.shop=Mock()
        self.product={'id':self.item['product_id'],'title':'Fixture product','handle':'fixture',
          'onlineStoreUrl':'https://www.sportscaveshop.com/products/fixture',
          'media':{'nodes':[{'image':{'url':'https://cdn.shopify.com/fixture.jpg'}}]}}
        self.order={'id':self.item['order_id'],'lineItems':{'nodes':[{'id':self.item['line_item_id'],
          'product':{'id':self.item['product_id']},'variant':{'id':self.item['variant_id']}}]}}
        def query(doc,variables,*args,**kwargs):
            if 'ShopReviewProduct' in doc:return {'product':self.product}
            if 'ShopReviewOrder' in doc:return {'order':self.order}
            return self.page
        self.shop.query.side_effect=query
        self.page={'metaobjects':{'nodes':[self.value],'pageInfo':{'hasNextPage':False,'endCursor':'last'}}}
        self.store.q('DELETE FROM sc_review_settings WHERE key=%s',(KEY,))
        self.addCleanup(lambda:self.store.q("UPDATE sc_reviews SET status='ARCHIVED' WHERE source_review_id=%s",(self.item['source_review_id'],)))

    def review(self):return self.store.q('SELECT * FROM sc_reviews WHERE source_review_id=%s',(self.item['source_review_id'],),one=True)

    def test_import_publication_totals_product_thumbnail_and_idempotency(self):
        before=self.store.aggregate()['count']
        self.assertEqual(import_entry(self.store,self.shop,self.value,'fixture.myshopify.com'),'imported')
        row=self.review();self.assertEqual(row['status'],'PUBLISHED');self.assertEqual(row['product_image'],self.product['media']['nodes'][0]['image']['url'])
        self.assertEqual(self.store.aggregate()['count'],before+1)
        self.shop.query.reset_mock()
        self.assertEqual(import_entry(self.store,self.shop,self.value,'fixture.myshopify.com'),'unchanged')
        self.shop.query.assert_not_called();self.assertEqual(self.store.aggregate()['count'],before+1)
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM sc_review_rewards WHERE review_id=%s',(row['id'],),one=True)['n'],0)
        self.assertTrue(self.store.rows(product=self.item['product_id'],public=True)[0]['shop_verified'])

    def test_mismatched_purchase_never_publishes(self):
        self.order['lineItems']['nodes'][0]['product']['id']='gid://shopify/Product/0'
        with self.assertRaises(ValueError):import_entry(self.store,self.shop,self.value,'fixture.myshopify.com')
        self.assertIsNone(self.review())

    def test_deleted_product_and_rating_only_skip(self):
        self.product=None
        self.assertEqual(import_entry(self.store,self.shop,self.value,'fixture.myshopify.com'),'deleted_product')
        self.assertEqual(import_entry(self.store,self.shop,entry(self.seed,body=''),'fixture.myshopify.com'),'rating_only')
        self.assertIsNone(self.review())

    def test_repeat_update_preserves_local_moderation_and_does_not_add_count(self):
        import_entry(self.store,self.shop,self.value,'fixture.myshopify.com')
        self.store.q("UPDATE sc_reviews SET status='ARCHIVED',moderated_at=now() WHERE id=%s",(self.review()['id'],))
        revised=deepcopy(self.value)
        next(f for f in revised['fields'] if f['key']=='body')['value']='Updated fixture review'
        self.assertEqual(import_entry(self.store,self.shop,revised,'fixture.myshopify.com'),'updated')
        row=self.review();self.assertEqual(row['status'],'ARCHIVED');self.assertEqual(row['body'],'Updated fixture review')

    def test_legacy_exact_match_gains_shop_identity_without_duplicate_or_republishing(self):
        from reviews_model import normalize
        legacy=normalize({'source_review_id':self.item['source_review_id'],'product_id':self.item['product_id'],
          'rating':4,'body':self.item['body'],'reviewer_name':self.item['reviewer_name'],
          'created_at':self.item['created_at'],'status':'archived'},source='judgeme')
        with self.store.db() as conn:self.store.import_one(conn,legacy,{'shopify_product_id':self.product['id'],'title':'Fixture'})
        self.assertEqual(import_entry(self.store,self.shop,self.value,'fixture.myshopify.com'),'updated')
        rows=self.store.q('SELECT * FROM sc_reviews WHERE source_review_id=%s',(self.item['source_review_id'],))
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['source'],'judgeme');self.assertEqual(rows[0]['status'],'ARCHIVED')

    def configure(self,**extra):
        state={'enabled':True,'shop_domain':'fixture.myshopify.com','watermark':'2020-01-01T00:00:00+00:00',**extra}
        self.store.q('INSERT INTO sc_review_settings(key,value) VALUES(%s,%s::jsonb)',(KEY,json.dumps(state)))

    def test_disabled_inbox_has_no_network_and_failed_sync_retains_watermark(self):
        self.assertIsNone(tick(self.store,self.shop));self.shop.query.assert_not_called()
        self.configure();self.shop.query.side_effect=RuntimeError('synthetic network failure')
        state=tick(self.store,self.shop)
        self.assertEqual(state['watermark'],'2020-01-01T00:00:00+00:00');self.assertEqual(state['last_error'],'shop_sync_unavailable')
        calls=self.shop.query.call_count;self.assertIsNone(tick(self.store,self.shop));self.assertEqual(self.shop.query.call_count,calls)

    def test_pagination_keeps_scan_boundary_until_final_page(self):
        self.configure();self.page['metaobjects']['pageInfo']={'hasNextPage':True,'endCursor':'page2'}
        clock=now();state=tick(self.store,self.shop,clock)
        self.assertEqual(state['watermark'],'2020-01-01T00:00:00+00:00');self.assertEqual(state['cursor'],'page2')
        upper=state['scan_until'];self.page['metaobjects']['nodes']=[];self.page['metaobjects']['pageInfo']={'hasNextPage':False,'endCursor':None}
        state=tick(self.store,self.shop,clock+timedelta(seconds=3))
        self.assertEqual(state['watermark'],upper);self.assertIsNone(state['cursor']);self.assertIsNone(state['scan_until'])


if __name__=='__main__':unittest.main()
