"""Offline storefront feed, pagination, media visibility and form boundary tests."""
import json
import os
import unittest
import uuid
from unittest.mock import Mock,MagicMock,patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from reviews_http import router
from reviews_public_cache import CACHE
from reviews_widget import projection,FEATURED,EXCLUDED
from reviews_storefront_form import storefront_html,form_headers,SCRIPT


class WidgetBoundaryTests(unittest.TestCase):
    def setUp(self):CACHE.invalidate()
    def test_lightweight_summary_is_shared_short_cached_and_disabled_fails_closed(self):
        app=FastAPI();app.include_router(router);client=TestClient(app)
        store=Mock();store.connect='summary-fixture';store.settings.return_value={'enabled':True}
        snapshot={'summary':{'count':212,'average':4.75},'histogram':[[5,159],[4,53],[3,0],[2,0],[1,0]],'as_of':'2026-11-27T04:00:00+00:00'}
        with patch('reviews_http.ReviewsStore',return_value=store),patch('reviews_http.allow_rate',return_value=True),patch('reviews_widget.published_summary',return_value=snapshot) as summary,patch('reviews_widget.projection') as rows:
            for country in ('AU','US'):
                response=client.get('/reviews/widget?summary=1&country='+country)
                self.assertEqual(response.json(),snapshot);self.assertEqual(response.headers['cache-control'],'public,max-age=5')
            summary.assert_called_once();rows.assert_not_called()
            CACHE.invalidate();store.settings.return_value={'enabled':False}
            self.assertEqual(client.get('/reviews/widget?summary=1').status_code,404)

    def test_public_summary_reads_one_consistent_published_snapshot(self):
        from reviews_widget import published_summary
        store=Mock();store._read_query.return_value={'totals':{'published':2,'published_rating':9},'histogram':[{'rating':5,'count':1},{'rating':4,'count':1}],'as_of':'2026-11-27T04:00:00+00:00'}
        value=published_summary(store)
        self.assertEqual(value['summary'],{'count':2,'average':4.5})
        self.assertEqual(sum(n for _,n in value['histogram']),2)
        store._read_query.assert_called_once();self.assertIn("status='PUBLISHED'",store._read_query.call_args.args[1])
    def test_shop_verified_uses_standard_buyer_badge_without_changing_order_verification(self):
        row=dict(id=str(uuid.uuid4()),source='shop_app',source_review_id='synthetic-shop',reviewer_name='Synthetic buyer',
          rating=5,title='Synthetic',body='Synthetic review',product_title='Synthetic edition',product_image='',product_url='',
          review_type='PRODUCT',created_at='2026-11-27',date_known=True,verified_purchase=False,source_verified=True,shop_verified=True)
        store=Mock();store.connect='synthetic';store.db=MagicMock()
        store.db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={
          'archive':[row],'featured':[],'media':[],'histogram':[],'totals':{'published':1,'published_rating':5}}
        for country in ('AU','US'):
            result=projection(store,'https://fixture.example',country,settings={'verified':True})['reviews'][0]
            self.assertTrue(result['source_verified']);self.assertTrue(result['shop_verified'])
            self.assertFalse(result['verified_purchase'])
            self.assertFalse(projection(store,'https://fixture.example',country,settings={'verified':False})['reviews'][0]['source_verified'])
    def test_projection_is_cached_country_scoped_and_disabled_fails_closed(self):
        app=FastAPI();app.include_router(router);client=TestClient(app)
        store=Mock();store.connect='fixture';store.settings.return_value={'enabled':True}
        with patch('reviews_http.ReviewsStore',return_value=store),patch('reviews_http.allow_rate',return_value=True),patch('reviews_widget.projection',return_value={'reviews':[]}) as load:
            self.assertEqual(client.get('/reviews/widget?country=AU').status_code,200)
            client.get('/reviews/widget?country=AU');client.get('/reviews/widget?country=US')
            self.assertEqual(load.call_count,2)
            self.assertEqual(client.get('/reviews/widget?offset=-1').status_code,400)
            self.assertEqual(client.get('/reviews/widget?offset=oops').status_code,400)
            CACHE.invalidate();store.settings.return_value={'enabled':False}
            self.assertEqual(client.get('/reviews/widget').status_code,404)
    def test_collection_form_is_accessible_bounded_and_does_not_cross_to_judgeme(self):
        html=storefront_html({'title':'<script>bad</script>','image_url':'javascript:bad'},'fixture-token')
        for text in ('How does it look in your space?','Show us your setup','name="form_token"','video/mp4','name="display_consent"','role="status"','minlength="10"'):
            self.assertIn(text,html)
        self.assertEqual(html.count('type="radio"'),5)
        self.assertNotIn('<script>bad',html);self.assertNotIn('javascript:bad',html);self.assertNotIn('judgeme',html)
        policy=form_headers({'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'"})['Content-Security-Policy']
        self.assertIn("script-src 'sha256-",policy);self.assertIn("connect-src 'self'",policy)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL fixture required')
class WidgetSQLTests(unittest.TestCase):
    def test_published_snapshot_tracks_shop_publication_and_archival_without_counting_pending(self):
        from tests.crm_db_fixture import connect
        from reviews_store import ReviewsStore
        from reviews_widget import published_summary
        store=ReviewsStore(connect);identity=str(uuid.uuid4());before=published_summary(store)['summary']
        try:
            store.q("INSERT INTO sc_reviews(id,source,product_id,reviewer_name,rating,body,status,dedupe_key) VALUES(%s,'shop_app','gid://shopify/Product/123','Synthetic Shop buyer',1,'Synthetic review','PENDING',%s)",(identity,identity))
            self.assertEqual(published_summary(store)['summary'],before)
            store.q("UPDATE sc_reviews SET status='PUBLISHED' WHERE id=%s",(identity,))
            data=published_summary(store);self.assertEqual(data['summary']['count'],before['count']+1)
            expected=(before['count']*(before['average'] or 0)+1)/(before['count']+1)
            self.assertAlmostEqual(data['summary']['average'],expected)
            self.assertEqual(sum(n for _,n in data['histogram']),data['summary']['count']);self.assertIsNotNone(data['as_of'])
            store.q("UPDATE sc_reviews SET status='ARCHIVED' WHERE id=%s",(identity,))
            self.assertEqual(published_summary(store)['summary'],before)
        finally:store.q('DELETE FROM sc_reviews WHERE id=%s',(identity,))

    def test_exact_legacy_ids_pagination_country_order_and_dropbox_only_images(self):
        from tests.crm_db_fixture import connect
        from reviews_store import ReviewsStore
        store=ReviewsStore(connect)
        store.q('TRUNCATE sc_reviews CASCADE');store.q('DELETE FROM sc_review_totals');store.q('DELETE FROM sc_review_days')
        identities=[]
        for index in range(9):
            legacy=FEATURED[index] if index<7 else EXCLUDED if index==7 else str(uuid.uuid4())
            row=store.q("INSERT INTO sc_reviews(source,source_review_id,product_id,product_title,reviewer_name,rating,body,status,dedupe_key,review_type,created_at) VALUES('judgeme',%s,'gid://shopify/Product/1',%s,%s,5,'Synthetic review','PUBLISHED',%s,'PRODUCT',now()-(%s||' days')::interval) RETURNING id",('shop-fixture-'+legacy,'NBA basketball' if index==6 else 'Cricket',f'Fixture {index}',str(uuid.uuid4()),str(index)),True)
            identities.append(str(row['id']))
            if index<8:
                ref={'provider':'dropbox','variants':{'320':{'width':320},'1280':{'width':1280,'height':960}}}
                store.q("INSERT INTO sc_review_media(review_id,kind,source_url,status,approved,consent,object_key,sha256,size_bytes,storage) VALUES(%s,%s,'synthetic','COPIED',true,true,'fixture','synthetic',10,%s::jsonb)",(row['id'],'video' if index==5 else 'image',json.dumps(ref)))
        au=projection(store,'https://fixture.example','AU');us=projection(store,'https://fixture.example','US')
        self.assertEqual(len(au['reviews']),5);self.assertEqual(au['next_offset'],5)
        self.assertEqual(au['reviews'][0]['id'],identities[0]);self.assertEqual(us['reviews'][0]['id'],identities[1])
        next_page=projection(store,'https://fixture.example','AU',5)
        self.assertEqual(len(next_page['reviews']),3);self.assertIsNone(next_page['next_offset']);self.assertEqual(next_page['featured'],[])
        self.assertNotIn(identities[7],[r['id'] for r in au['featured']+au['reviews']+next_page['reviews']])
        self.assertNotIn(identities[5],[r['id'] for r in au['featured']])
        self.assertEqual(au['featured'][0]['legacy_id'],FEATURED[0])
        self.assertTrue(au['featured'][0]['media'][0]['thumbnail_url'].endswith('?size=320'))
        self.assertTrue(au['featured'][0]['media'][0]['carousel_url'].endswith('?size=640'))
        self.assertTrue(au['reviews'][0]['source_verified']);self.assertFalse(au['reviews'][0]['verified_purchase'])
        self.assertIsNotNone(au['reviews'][0]['created_at'])
        with patch.dict('reviews_widget.PUBLIC_NAMES',{identities[0]:'Public fixture name'}):
            public=projection(store,'https://fixture.example','AU')
            self.assertEqual(public['reviews'][0]['reviewer_name'],'Public fixture name')
            self.assertEqual(store.get_review(identities[0])['reviewer_name'],'Fixture 0')
        self.assertNotIn('source_review_id',au['featured'][0]);self.assertEqual(sum(c for _,c in au['histogram']),9)
        with patch.object(store,'connect',side_effect=connect) as connection:
            projection(store,'https://fixture.example','AU',settings={'verified':True})
            self.assertEqual(connection.call_count,1)
        with patch('supabase_backend.read_connection',return_value=store.db()) as pooled:
            result=projection(ReviewsStore(),'https://fixture.example','AU',settings={'verified':True})
            self.assertEqual(len(result['reviews']),5);pooled.assert_called_once_with()


if __name__=='__main__':unittest.main()
