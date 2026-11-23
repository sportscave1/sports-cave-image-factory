"""Synthetic-only review journey, storefront form and draft isolation checks."""
from copy import deepcopy
from datetime import timedelta
import json
import os
import unittest
from unittest.mock import Mock,patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from crm_logic import now
from crm_automation_definition import validate
from crm_lifecycle_definition import expanded_flow
from crm_lifecycle_policy import preview
from reviews_journey import products,order_products
from reviews_public_submission import issue,verify,submit
from reviews_submission import prepare_email,MARKER
from scripts.prepare_native_review_emails import prepare

SECRET={'CRM_UNSUBSCRIBE_SECRET':'synthetic-review-secret-for-tests-only-12345'}
P='gid://shopify/Product/'

def baseline():
    flow=expanded_flow('post_purchase')
    flow['emails'].append(deepcopy(flow['emails'][-1]))
    return flow

def line(identity,price):return {'product':{'id':P+str(identity)},'originalTotalSet':{'shopMoney':{'amount':str(price),'currencyCode':'AUD'}}}

class JourneyTests(unittest.TestCase):
    def test_exact_online_and_pos_timing_and_no_missing_product_emails(self):
        flow=prepare(baseline());at=now();customer={'id':'fixture','emailMarketingConsent':{'marketingState':'SUBSCRIBED'}}
        order={'id':'order','paid_at':at,'fullyPaid':True,'displayFinancialStatus':'PAID','fulfilled_at':at,'review_products':[P+'1',P+'2']}
        online=preview(flow,customer,[order],at)
        slots=online['stages'][1:4]
        self.assertEqual([(s['due_at']-at).days for s in slots],[14,19,24]);self.assertEqual(slots[-1]['state'],'DISABLED')
        pos=preview(flow,customer,[{**order,'sourceName':'pos'}],at)
        self.assertEqual([(s['due_at']-at).days for s in pos['stages'][1:4]],[7,12,17])
        held=preview(flow,customer,[{**order,'fulfilled_at':None}],at)
        self.assertEqual(held['stages'][1]['state'],'HELD')
        validate(flow,draft=True)

    def test_price_ordering_and_pagination(self):
        lines=[line(1,5),line(2,20),line(1,10),line(3,15),line(4,1)]
        self.assertEqual(products(lines),[P+'2',P+'3',P+'1'])
        shop=Mock();shop.line_page.return_value={'nodes':lines[2:],'pageInfo':{}}
        self.assertEqual(order_products(shop,{'id':'order','lineItems':{'nodes':lines[:2],'pageInfo':{'hasNextPage':True,'endCursor':'next'}}}),[P+'2',P+'3',P+'1'])
        shop.line_page.assert_called_once_with('order','next',fresh=True)

    def test_draft_preserves_thank_you_and_upsell(self):
        old=baseline();new=prepare(old)
        self.assertEqual(new['emails'][0],old['emails'][0]);self.assertEqual(new['emails'][-1],old['emails'][3])
        self.assertEqual(len(new['emails']),5)
        for step in new['emails'][1:4]:
            self.assertIn(MARKER,json.dumps(step['document']));self.assertIn('Every star rating qualifies',json.dumps(step['document']))
        self.assertNotIn('review_request',old['emails'][1])

    def test_native_link_uses_verified_order_product_and_safe_title(self):
        request=prepare(baseline())['emails'][1]
        content={'trigger':'post_purchase','review_request':request['review_request'],'document':request['document']}
        shop=Mock();shop.order.return_value={'id':'order','displayFulfillmentStatus':'FULFILLED','lineItems':{'nodes':[line(1,50)],'pageInfo':{}}}
        store=Mock();store.match_product.return_value={'title':'A "great" \\ edition'}
        with patch('reviews_submission.issue',return_value=request['review_request']['base_url']+'/reviews/request/'+'a'*64) as issuer:
            result=prepare_email(content,{},dict(trigger_shopify_id='order',shopify_customer_id='buyer'),shop,store)
        self.assertNotIn(MARKER,json.dumps(result));self.assertIn('&quot;great&quot;',json.dumps(result));self.assertIn('SC_REVIEW_PRODUCT_TITLE',json.dumps(content))
        issuer.assert_called_once_with(store,shop,'order','buyer',P+'1')

    @patch.dict(os.environ,SECRET)
    def test_public_nonce_cannot_change_product_or_be_replayed_after_expiry(self):
        token=issue(P+'123');self.assertEqual(verify(token),P+'123')
        with self.assertRaises(ValueError):verify(token.replace('.123.','.124.'))
        with patch('reviews_public_submission.time.time',return_value=0):
            old=issue()
        with self.assertRaises(ValueError):verify(old)

    @patch.dict(os.environ,SECRET)
    def test_public_form_and_post_boundary(self):
        from reviews_http import router
        app=FastAPI();app.include_router(router);client=TestClient(app)
        store=Mock();store.settings.return_value={'enabled':True}
        with patch('reviews_http.ReviewsStore',return_value=store),patch('reviews_http.allow_rate',return_value=True):
            response=client.get('/reviews/write')
            self.assertEqual(response.status_code,200);self.assertIn('form_token',response.text)
            self.assertIn('video/mp4',response.text);self.assertIn('frame-ancestors https://www.sportscaveshop.com',response.headers['content-security-policy'])
            self.assertNotIn('judge.me',response.text)
            self.assertEqual(client.post('/reviews/write',data={'rating':'1'},headers={'origin':'https://evil.test'}).status_code,403)
            with patch('reviews_public_submission.submit') as writer:
                data={'rating':'1','body':'Room to improve','reviewer_name':'Fixture','display_consent':'yes','form_token':issue()}
                result=client.post('/reviews/write',data=data)
                self.assertEqual(result.status_code,200);self.assertEqual(writer.call_args.args[2]['rating'],'1')
            self.assertEqual(client.post('/reviews/write',data={'form_token':'invalid'}).status_code,400)

    def test_reward_policy_is_rating_neutral_but_requires_published_media(self):
        from reviews_rewards import eligibility
        settings={'rewards_enabled':True,'image_percent':30,'video_percent':30}
        review={'source':'sports_cave','verified_purchase':True,'customer_id':'c','order_id':'o','rating':1,'status':'PUBLISHED'}
        media=[{'status':'COPIED','approved':True,'consent':True,'kind':'video'}]
        self.assertEqual(eligibility(review,media,settings)['percent'],30)
        self.assertIsNone(eligibility({**review,'status':'PENDING'},media,settings))
        self.assertIsNone(eligibility({**review,'verified_purchase':False},media,settings))

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL fixture required')
class DatabaseJourneyTests(unittest.TestCase):
    def test_one_reward_for_two_reviews_of_the_same_order(self):
        import uuid
        from tests.crm_db_fixture import connect
        from reviews_store import ReviewsStore
        from reviews_rewards import register
        store=ReviewsStore(connect);order='gid://shopify/Order/'+str(uuid.uuid4().int%10**12)
        identities=[]
        for index in range(2):
            key='synthetic-reward:'+uuid.uuid4().hex
            row=store.q("""INSERT INTO sc_reviews(source,source_review_id,product_id,customer_id,order_id,reviewer_name,rating,body,status,verified_purchase,dedupe_key)
              VALUES('sports_cave',%s,%s,'gid://shopify/Customer/99999',%s,'Fixture',1,'Honest feedback','PUBLISHED',true,%s) RETURNING id""",(key,P+str(index+1),order,key),True)
            identities.append(row['id'])
            store.q("INSERT INTO sc_review_media(review_id,kind,source_url,status,approved,consent,object_key,sha256,size_bytes) VALUES(%s,'image',%s,'COPIED',true,true,'fixture','synthetic',10)",(row['id'],'native:'+key))
        with patch.object(store,'collection_settings',return_value={'rewards_enabled':True,'image_percent':30,'video_percent':30}):
            self.assertIsNotNone(register(store,identities[0]));self.assertIsNone(register(store,identities[1]))
            register(store,identities[0])
        self.assertEqual(store.q('SELECT count(*) n FROM sc_review_rewards WHERE order_id=%s',(order,),True)['n'],1)
        store.q("UPDATE sc_review_rewards SET status='CANCELLED' WHERE order_id=%s",(order,))

    def test_anonymous_submission_is_pending_unverified_and_media_owned_first(self):
        from tests.crm_db_fixture import connect
        from reviews_store import ReviewsStore
        store=ReviewsStore(connect)
        with patch.dict(os.environ,SECRET):
            token=issue();payload={'rating':1,'title':'Honest','body':'Useful feedback','reviewer_name':'Synthetic buyer','display_consent':True}
            saved={'object_key':'owned','sha256':'a'*64,'size_bytes':10,'mime_type':'image/webp','storage':{'provider':'dropbox','variants':{}}}
            with patch('reviews_media.save_owned',return_value=saved) as owned:
                identity=submit(store,token,payload,[{'kind':'image','data':b'fixture'}])
                self.assertEqual(submit(store,token,payload,[]),identity);owned.assert_called_once()
        row=store.get_review(identity);self.assertEqual(row['status'],'PENDING');self.assertFalse(row['verified_purchase']);self.assertEqual(row['review_type'],'STORE')
        media=store.media(identity);self.assertEqual(media[0]['storage']['provider'],'dropbox');self.assertFalse(media[0]['approved'])
        self.assertIsNone(store.q('SELECT * FROM sc_review_rewards WHERE review_id=%s',(identity,),True))

