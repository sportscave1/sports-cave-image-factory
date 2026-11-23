"""Synthetic migration, file ownership, token upload and rating-neutral reward contracts."""
import io
import json
import os
import unittest
from unittest.mock import Mock,patch
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient
import tests.test_reviews as original
from reviews_model import normalize,auto_mapping
from reviews_import import preview,JudgeMe
from reviews_media import media_references,validate_file,download,tick_media
from reviews_rewards import eligibility

def photo():
    buf=io.BytesIO();Image.new('RGB',(8,8),'red').save(buf,'PNG');return buf.getvalue()

REF={'provider':'dropbox','id':'id:reviewfixture','rev':'a1','size':100,'sha256':'f'*64}
OWNED={'object_key':'id:reviewfixture','sha256':'f'*64,'size_bytes':100,'mime_type':'image/jpeg',
       'storage':{'provider':'dropbox','original':REF,'variants':{'320':{**REF,'width':8,'height':8},'1280':{**REF,'width':8,'height':8}}}}

class MigrationTests(unittest.TestCase):
    def test_judgeme_export_mapping_dates_media_and_published_only(self):
        raw={'curated':'ok','rating':1,'body':'Honest feedback','review_date':'2026-01-01 12:00:00 UTC','picture_urls':'https://images.judge.me/a.jpg,https://images.judge.me/b.jpg','reply':'Thanks','reply_date':'2026-01-02','metaobject_handle':'review-one'}
        mapped={**auto_mapping(list(raw)),'status':'status'};r=normalize(raw,'judgeme',mapped)
        self.assertEqual(r['source_review_id'],'review-one');self.assertEqual(r['status'],'PUBLISHED');self.assertEqual(r['review_type'],'STORE')
        self.assertEqual(len(r['media']),2);self.assertEqual(r['merchant_reply'],'Thanks');self.assertTrue(r['created_at'].endswith('+00:00'))
        store=Mock();store.match_products.side_effect=lambda hints:[None]*len(hints);store.q.return_value=[]
        result=preview([raw,{**raw,'curated':'spam'},{**raw,'curated':'not-yet'},{**raw,'status':'Archived'}],mapped,store,'judgeme',published_only=True)
        self.assertEqual((result['ready'],result['skipped'],result['unresolved'],result['media']),(1,3,0,2))
    def test_api_curation_archive_and_nested_picture_urls(self):
        p=JudgeMe({});raw={'id':42,'rating':5,'body':'Great','hidden':False,'curated':'spam'}
        self.assertEqual(p.normalize(raw)['status'],'PENDING')
        self.assertEqual(p.normalize({**raw,'curated':'ok','hidden':True})['status'],'ARCHIVED')
        r=p.normalize({**raw,'curated':'ok','pictures':[{'urls':{'original':'https://images.judge.me/a.jpg'}}],'has_published_videos':True})
        self.assertEqual(len(r['media']),1);self.assertTrue(r['video_export_required'])
        anonymous={'rating':5,'body':'Same words','created_at':'2026-01-01'}
        self.assertIsNone(normalize(anonymous,'judgeme')['source_fingerprint'])
    def test_media_invalid_files_urls_and_unknown_hosts(self):
        body,mime,ext=validate_file(photo(),'image');self.assertEqual((mime,ext),('image/jpeg','.jpg'))
        self.assertEqual(validate_file(b'\x00\x00\x00\x18ftypmp42fixture','video')[1],'video/mp4')
        for value in ('http://images.judge.me/a.jpg','https://localhost/a.jpg','https://127.0.0.1/a.jpg'):
            with self.assertRaises(ValueError):media_references(value,'image')
        for body,kind in ((b'<svg/>','image'),(b'<html/>','video')):
            with self.assertRaises(ValueError):validate_file(body,kind)
        with patch('requests.Session') as network:
            with self.assertRaises(ValueError):download('https://example.test/private','image')
            network.assert_not_called()
    def test_rewards_ignore_rating_and_exclude_imports_unapproved_media(self):
        review={'source':'sports_cave','verified_purchase':True,'customer_id':'c','order_id':'o','rating':1}
        media=[{'kind':'image','status':'COPIED','approved':True,'consent':True},{'kind':'video','status':'COPIED','approved':True,'consent':True}]
        policy={'rewards_enabled':True,'image_percent':10,'video_percent':15}
        self.assertEqual(eligibility(review,media,policy),{'media_kind':'video','percent':15})
        self.assertIsNone(eligibility({**review,'source':'judgeme'},media,policy))
        self.assertIsNone(eligibility(review,[{**media[0],'approved':False}],policy))

    def test_import_and_collection_tabs_render_without_external_services(self):
        from streamlit.testing.v1 import AppTest
        for tab in ('Import reviews','Collect & reward'):
            script='''
import streamlit as st
from unittest.mock import Mock,patch
from reviews_page import render_page
from tests.test_crm import ADMIN
st.session_state['reviews-tabs']=TAB
store=Mock();store.connect=None
store.q.return_value=[];store.imports.return_value=[];store.products.return_value=[]
store.migration_summary.return_value={'published':0,'store_reviews':0,'unmatched':0,'media_total':0,'media_copied':0,'media_failed':0}
store.collection_settings.return_value={'rewards_enabled':False,'image_percent':10,'video_percent':15}
with patch('reviews_page.read',side_effect=lambda state,key,fn,ttl=60:(fn(),'READY')):
 render_page(ADMIN,store=store)
'''.replace('TAB',repr(tab))
            app=AppTest.from_string(script).run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(len(app.warning),0)
            if tab=='Collect & reward':self.assertEqual([x.label for x in app.number_input],['Photo reward (%)','Video reward (%)'])

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class MigrationDatabaseTests(unittest.TestCase):
    setUp=original.DatabaseTests.setUp
    def cleanup(self):
        self.store.q("UPDATE sc_review_rewards SET status='CANCELLED' WHERE review_id IN (SELECT id FROM sc_reviews WHERE source_review_id LIKE %s)",(self.prefix+'%',))
        original.DatabaseTests.cleanup(self)
    item=original.DatabaseTests.item
    insert=original.DatabaseTests.insert
    order=original.DatabaseTests.order

    def test_store_reviews_public_aggregates_and_no_product_warning(self):
        before=self.store.aggregate()['count'];attention=self.store.summary()['attention']
        r=self.insert(review_type='store',product_id='',rating=5)
        self.assertEqual(self.store.aggregate()['count'],before+1)
        self.assertEqual(self.store.summary()['attention'],attention)
        self.assertIn(r['id'],[x['id'] for x in self.store.rows(public=True,search='collector')])
    def test_media_import_idempotent_retry_and_owned_copy(self):
        r=self.insert(picture_urls='https://images.judge.me/a.jpg')
        with self.store.db() as conn:self.store.import_one(conn,self.item(source_review_id=r['source_review_id'],picture_urls='https://images.judge.me/a.jpg'),self.store.match_product({'product_id':self.pid}))
        self.assertEqual(len(self.store.media(r['id'])),1)
        with patch('reviews_media.download',return_value=(photo(),'image/png','.png')),patch('reviews_media.save_owned',return_value=OWNED):tick_media(self.store)
        m=self.store.media(r['id'])[0];self.assertEqual(m['status'],'COPIED');self.assertEqual(m['object_key'],OWNED['object_key']);self.assertFalse(m['approved'])

    def test_csv_and_api_identifiers_reconcile_then_alias_tracks_source_edits(self):
        from crm_logic import now
        from datetime import timedelta
        at=(now()-timedelta(days=2)).replace(microsecond=0).isoformat();shop='fixture.myshopify.com'
        raw={'source_review_id':self.prefix+'csv','product_id':self.pid,'rating':4,'body':'Same imported review','email':'collector@example.test','created_at':at,'status':'PUBLISHED'}
        first=normalize(raw,'judgeme',source_store=shop);self.created.append(raw['source_review_id'])
        provider=JudgeMe({'SHOPIFY_STORE_DOMAIN':shop})
        api={'id':self.prefix+'api','product_external_id':self.pid,'product_id':123,'rating':4,'body':raw['body'],'created_at':at,'hidden':False,'reviewer':{'email':raw['email']}}
        second=provider.normalize(api)
        self.assertNotEqual(first['dedupe_key'],second['dedupe_key']);self.assertEqual(first['source_fingerprint'],second['source_fingerprint'])
        product=self.store.match_product({'product_id':self.pid})
        with self.store.db() as conn:self.assertTrue(self.store.import_one(conn,first,product))
        validation=preview([{'rating':4,'body':raw['body'],'email':raw['email'],'created_at':at,'product_id':self.pid,'source_review_id':api['id'],'status':'PUBLISHED'}],{},self.store,'judgeme',shop)
        self.assertEqual((validation['ready'],validation['duplicates']),(0,1))
        with self.store.db() as conn:self.assertFalse(self.store.import_one(conn,second,product))
        edited=provider.normalize({**api,'body':'Edited in source'})
        with self.store.db() as conn:self.assertFalse(self.store.import_one(conn,edited,product))
        reviews=self.store.q('SELECT * FROM sc_reviews WHERE source_review_id=%s',(raw['source_review_id'],))
        self.assertEqual(len(reviews),1);self.assertEqual(reviews[0]['body'],'Edited in source')
        self.assertEqual(self.store.q('SELECT count(*) n FROM sc_review_identities WHERE review_id=%s',(reviews[0]['id'],),True)['n'],2)
    def test_native_multipart_upload_and_reward_once_after_approval(self):
        from reviews_submission import issue,token_row
        from reviews_http import router
        shop=Mock();shop.order.return_value=self.order()
        token=issue(self.store,shop,self.order()['id'],self.order()['customer']['id'],self.pid,{'CRM_PUBLIC_BASE_URL':'https://fixture.example','CRM_UNSUBSCRIBE_SECRET':'x'*40}).rsplit('/',1)[-1]
        self.store.save_collection_settings(original.ADMIN,{'rewards_enabled':True})
        app=FastAPI();app.include_router(router)
        with patch('reviews_http.ReviewsStore',return_value=self.store),patch('reviews_media.save_owned',return_value=OWNED) as saved,TestClient(app) as client:
            payload={'rating':'1','body':'Needs improvement','reviewer_name':'Collector','display_consent':'yes'}
            response=client.post('/reviews/request/'+token,data=payload,files={'media':('photo.png',photo(),'image/png')})
            self.assertEqual(response.status_code,200)
            response=client.post('/reviews/request/'+token,data=payload,files={'media':('photo.png',photo(),'image/png')})
            self.assertEqual(response.status_code,200);self.assertEqual(saved.call_count,1)
        identity=token_row(self.store,token)['review_id'];m=self.store.media(identity)[0]
        self.assertIsNone(self.store.q('SELECT * FROM sc_review_rewards WHERE review_id=%s',(identity,),True))
        self.store.approve_media(original.ADMIN,m['id'],True);self.store.approve_media(original.ADMIN,m['id'],True)
        reward=self.store.q('SELECT * FROM sc_review_rewards WHERE review_id=%s',(identity,),True)
        self.assertEqual(reward['status'],'ELIGIBLE');self.assertEqual(reward['percent'],10)
        self.store.approve_media(original.ADMIN,m['id'],False)
        self.assertEqual(self.store.q('SELECT status FROM sc_review_rewards WHERE review_id=%s',(identity,),True)['status'],'CANCELLED')
    def test_public_media_requires_review_publication_and_media_approval(self):
        from reviews_http import router
        r=self.insert(picture_urls='https://images.judge.me/a.jpg');m=self.store.media(r['id'])[0]
        self.store.q("UPDATE sc_review_media SET status='COPIED',object_key='id:reviewfixture',sha256=%s,size_bytes=100,storage=%s::jsonb WHERE id=%s",('f'*64,json.dumps(OWNED['storage']),m['id']))
        self.store.save_settings(original.ADMIN,{'enabled':True});app=FastAPI();app.include_router(router)
        stream=Mock();stream.iter_chunks.side_effect=lambda:iter([b'x'*100])
        with patch('reviews_http.ReviewsStore',return_value=self.store),patch('reviews_dropbox.ReviewDropboxStorage.open',return_value=stream),TestClient(app) as client:
            self.assertEqual(client.get('/reviews/media/'+str(m['id']),follow_redirects=False).status_code,404)
            self.store.approve_media(original.ADMIN,m['id'],True)
            self.assertEqual(client.get('/reviews/media/'+str(m['id']),follow_redirects=False).status_code,200)
            self.store.moderate(original.ADMIN,r['id'],status='PENDING')
            self.assertEqual(client.get('/reviews/media/'+str(m['id']),follow_redirects=False).status_code,404)

    def reward_fixture(self):
        r=self.insert(rating=1,picture_urls='https://images.judge.me/reward.jpg')
        self.store.q("UPDATE sc_reviews SET source='sports_cave',verified_purchase=true,customer_id=%s,order_id=%s WHERE id=%s",(self.order()['customer']['id'],self.order()['id'],r['id']))
        self.store.save_collection_settings(original.ADMIN,{'rewards_enabled':True})
        m=self.store.media(r['id'])[0]
        self.store.q("UPDATE sc_review_media SET status='COPIED',consent=true,object_key='reviews/reward.jpg',sha256=%s,size_bytes=100 WHERE id=%s",('f'*64,m['id']))
        self.store.approve_media(original.ADMIN,m['id'],True)
        shop=Mock();shop.order.return_value=self.order()
        customer={'id':self.order()['customer']['id'],'email':'collector@example.test','validEmailAddress':True,'emailMarketingConsent':{'marketingState':'SUBSCRIBED'},'defaultEmailAddress':{'validFormat':True,'emailAddress':'collector@example.test','marketingState':'SUBSCRIBED','marketingUnsubscribeUrl':'https://fixture.example/unsubscribe'}}
        shop.customer.return_value=customer
        from crm_logic import now
        from datetime import timedelta
        shop.query.side_effect=lambda document,*args,**kw:({'discountCodeBasicCreate':{'codeDiscountNode':{'id':'gid://shopify/DiscountCodeNode/123'},'userErrors':[]}} if document.startswith('mutation') else {'codeDiscountNodeByCode':{'id':'gid://shopify/DiscountCodeNode/123','codeDiscount':{'__typename':'DiscountCodeBasic','status':'ACTIVE','customerGets':{'value':{'percentage':.1}},'usageLimit':1,'asyncUsageCount':0,'endsAt':(now()+timedelta(days=30)).isoformat()}}})
        mailer=Mock();mailer.suppressed.return_value=False;mailer.send.return_value='fixture-message'
        env={'REVIEW_REWARDS_DELIVERY_ENABLED':'true','CRM_MARKETING_ENABLED':'true','CRM_MARKETING_SEND_ENABLED':'true','RESEND_MARKETING_API_KEY':'fixture','RESEND_FROM_NAME':'Fixture','RESEND_FROM_EMAIL':'hello@fixture.example','RESEND_REPLY_TO':'support@fixture.example'}
        return r,shop,mailer,env

    def test_reward_delivery_creates_single_customer_code_and_sends_once(self):
        from reviews_reward_delivery import tick
        r,shop,mailer,env=self.reward_fixture()
        self.assertEqual(tick(self.store,shop,mailer,env),r['id'])
        self.assertEqual(self.store.q('SELECT status FROM sc_review_rewards WHERE review_id=%s',(r['id'],),True)['status'],'ISSUED')
        discount=shop.query.call_args.args[1]['input']
        self.assertEqual(discount['usageLimit'],1);self.assertTrue(discount['appliesOncePerCustomer'])
        self.assertEqual(discount['context']['customers']['add'],[self.order()['customer']['id']]);self.assertEqual(discount['customerGets']['value']['percentage'],.1)
        tick(self.store,shop,mailer,env);tick(self.store,shop,mailer,env)
        self.assertEqual(mailer.send.call_count,1)
        self.assertEqual(self.store.q('SELECT status FROM sc_review_rewards WHERE review_id=%s',(r['id'],),True)['status'],'SENT')

    def test_reward_gate_defaults_off_and_ambiguous_provider_outcome_is_held(self):
        from reviews_reward_delivery import tick
        r,shop,mailer,env=self.reward_fixture()
        self.assertIsNone(tick(self.store,shop,mailer,{}));shop.query.assert_not_called();mailer.send.assert_not_called()
        shop.query.side_effect=TimeoutError('sensitive provider detail')
        tick(self.store,shop,mailer,env);tick(self.store,shop,mailer,env)
        self.assertEqual(shop.query.call_count,1);mailer.send.assert_not_called()
        held=self.store.q('SELECT status,error_code FROM sc_review_rewards WHERE review_id=%s',(r['id'],),True)
        self.assertEqual(held,{'status':'HELD','error_code':'verification_or_provider_failure'})

    def test_unsubscribed_reward_never_creates_code_or_sends(self):
        from reviews_reward_delivery import tick
        r,shop,mailer,env=self.reward_fixture()
        shop.customer.return_value['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
        shop.customer.return_value['defaultEmailAddress']['marketingState']='UNSUBSCRIBED'
        tick(self.store,shop,mailer,env);shop.query.assert_not_called();mailer.send.assert_not_called()

    def test_media_failures_exhaust_budget_and_staff_can_retry(self):
        r=self.insert(picture_urls='https://images.judge.me/fail.jpg')
        with patch('reviews_media.download',side_effect=ValueError('failed')) as get:
            for _ in range(4):tick_media(self.store)
        self.assertEqual(get.call_count,3)
        m=self.store.media(r['id'])[0];self.assertEqual(m['attempts'],3);self.assertEqual(m['status'],'FAILED')
        self.store.retry_media(original.ADMIN,m['id'])
        self.assertEqual(self.store.media(r['id'])[0]['status'],'QUEUED')
        # Leave no pending media in the shared disposable fixture.
        self.store.q("UPDATE sc_review_media SET attempts=3,status='FAILED' WHERE id=%s",(m['id'],))

    def test_reward_send_timeout_is_held_and_never_automatically_resent(self):
        from reviews_reward_delivery import tick
        r,shop,mailer,env=self.reward_fixture();tick(self.store,shop,mailer,env)
        mailer.send.side_effect=TimeoutError('unknown send outcome')
        tick(self.store,shop,mailer,env);tick(self.store,shop,mailer,env)
        self.assertEqual(mailer.send.call_count,1)
        self.assertEqual(self.store.q('SELECT status FROM sc_review_rewards WHERE review_id=%s',(r['id'],),True)['status'],'HELD')

if __name__=='__main__':unittest.main()
