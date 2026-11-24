"""Canonical account review ownership, multipart media and cross-channel dedupe."""
import os,unittest
from unittest.mock import Mock,patch
from reviews_account import submit
from reviews_submission import issue,submit as email_submit
import tests.test_reviews as original
from tests.test_reviews import ADMIN

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL only')
class NativeAccount(unittest.TestCase):
 setUp=original.DatabaseTests.setUp
 cleanup=original.DatabaseTests.cleanup
 order=original.DatabaseTests.order
 def context(self):
  shop=Mock();shop.order.return_value=self.order()
  return shop,{'shopify_order_id':self.order()['id'],'shopify_product_id':self.pid}
 def test_account_is_verified_pending_and_later_email_is_already_submitted(self):
  self.store.save_settings(ADMIN,{'enabled':True});shop,row=self.context();customer=self.order()['customer']['id']
  with patch('collector_vault._resolve_review_reference',return_value=row),patch('requests.post') as judge:
   result=submit(self.store,shop,customer,'signed',{'rating':1,'body':'An honest account review','reviewer_name':'Synthetic buyer'},[])
   again=submit(self.store,shop,customer,'signed',{'rating':1,'body':'A repeated account review','reviewer_name':'Synthetic buyer'},[])
  self.assertEqual(result,again);judge.assert_not_called()
  review=self.store.get_review(result['review_id']);self.assertTrue(review['verified_purchase']);self.assertEqual(review['status'],'PENDING');self.assertEqual(review['product_id'],self.pid)
  url=issue(self.store,shop,row['shopify_order_id'],customer,self.pid,{'CRM_PUBLIC_BASE_URL':'https://fixture.example','CRM_UNSUBSCRIBE_SECRET':'x'*40})
  self.assertEqual(email_submit(self.store,url.rsplit('/',1)[-1],{'rating':5,'body':'Duplicate email','display_consent':True}),result['review_id'])
 def test_wrong_customer_fails_before_any_upload(self):
  self.store.save_settings(ADMIN,{'enabled':True});shop,row=self.context()
  with patch('collector_vault._resolve_review_reference',return_value=row),patch('reviews_media.save_owned') as media:
   with self.assertRaises(ValueError):submit(self.store,shop,'gid://shopify/Customer/999','signed',{'rating':5,'body':'A spoofed account review'},[])
  media.assert_not_called()
 def test_multipart_account_endpoint_creates_native_queued_media(self):
  from starlette.applications import Starlette
  from starlette.routing import Route
  from starlette.testclient import TestClient
  import collector_vault_api as api
  self.store.save_settings(ADMIN,{'enabled':True});shop,row=self.context()
  owned={'object_key':'id:fixture','sha256':'a'*64,'size_bytes':10,'mime_type':'image/jpeg','storage':{'provider':'dropbox','processing':'pending','original':{'id':'id:fixture'}}}
  app=Starlette(routes=[Route('/review',api.collector_vault_review_submit,methods=['POST'])])
  with patch.object(api,'_session',return_value={'shopify_customer_id':self.order()['customer']['id']}),patch('collector_vault._resolve_review_reference',return_value=row),patch('crm_shopify.Shopify',return_value=shop),patch('reviews_store.ReviewsStore',return_value=self.store),patch('reviews_media.save_owned',return_value=owned),patch('collector_vault.submit_review') as legacy,TestClient(app) as client:
   response=client.post('/review',data={'review_reference':'signed','rating':'5','reviewer_name':'Synthetic buyer','body':'My native uploaded review','display_consent':'yes'},files=[('media',('fixture.jpg',b'fixture','image/jpeg'))],headers={'X-Sports-Cave-Request':'customer-account-extension'})
  self.assertEqual(response.status_code,200);legacy.assert_not_called();identity=response.json()['review_id'];self.assertEqual(self.store.media(identity)[0]['status'],'QUEUED')

 def test_only_approved_native_video_is_exposed_in_widget(self):
  import json
  from reviews_widget import projection
  self.store.save_settings(ADMIN,{'enabled':True});shop,row=self.context()
  with patch('collector_vault._resolve_review_reference',return_value=row):native=submit(self.store,shop,self.order()['customer']['id'],'signed',{'rating':5,'body':'Native video review','reviewer_name':'Synthetic'},[])['review_id']
  self.store.moderate(ADMIN,native,status='PUBLISHED')
  legacy=self.store.q("INSERT INTO sc_reviews(source,source_review_id,product_id,reviewer_name,rating,body,status,dedupe_key) VALUES('judgeme',%s,%s,'Legacy',5,'Hidden legacy video','PUBLISHED',%s) RETURNING id",(self.prefix+'video',self.pid,self.prefix+'video'),True)['id']
  storage={'provider':'dropbox','video_format':'mp4','original':{},'posters':{str(w):{'width':w,'height':w} for w in (320,640,1280)}}
  for identity in (native,legacy):self.store.q("INSERT INTO sc_review_media(review_id,kind,source_url,status,approved,consent,storage,object_key,sha256,size_bytes) VALUES(%s,'video',%s,'COPIED',true,true,%s::jsonb,'fixture','synthetic',10)",(identity,'native:'+str(identity),json.dumps(storage)))
  data=projection(self.store,'https://fixture.example')
  rows={str(r['id']):r for r in data['reviews']};self.assertEqual(rows[str(native)]['media'][0]['kind'],'video');self.assertTrue(rows[str(native)]['media'][0]['url'].endswith('size=original'));self.assertEqual(rows[str(legacy)]['media'],[])
  self.store.moderate(ADMIN,native,status='ARCHIVED')

class ProductThumbnail(unittest.TestCase):
 def test_small_first_product_image_uses_shopify_cdn_only(self):
  from reviews_widget import product_thumbnail
  from urllib.parse import urlsplit,parse_qs
  row={'review_type':'PRODUCT','product_image':'https://cdn.shopify.com/s/files/black-frame.jpg?v=2&width=2000'}
  result=product_thumbnail(row);query=parse_qs(urlsplit(result).query)
  self.assertEqual(query['width'],['136']);self.assertEqual(query['format'],['webp']);self.assertEqual(query['v'],['2'])
  self.assertEqual(product_thumbnail({**row,'review_type':'STORE'}),'')
  self.assertEqual(product_thumbnail({**row,'product_image':'https://images.judge.me/old.jpg'}),'')

class AlreadyReviewedEmail(unittest.TestCase):
 def test_existing_native_review_does_not_issue_another_request(self):
  from reviews_submission import prepare_email,ReviewAlreadyReceived
  from scripts.prepare_native_review_emails import prepare
  from tests.test_reviews_journey import baseline
  step=prepare(baseline())['emails'][1];store=Mock();store.q.return_value={'id':'already-received'}
  shop=Mock();shop.order.return_value={'id':'order','displayFulfillmentStatus':'FULFILLED','lineItems':{'nodes':[{'product':{'id':'gid://shopify/Product/1'},'originalTotalSet':{'shopMoney':{'amount':'5'}}}],'pageInfo':{}}}
  with patch('reviews_submission.issue') as issue:
   with self.assertRaises(ReviewAlreadyReceived):prepare_email({'trigger':'post_purchase','review_request':step['review_request'],'document':step['document']},{},{'trigger_shopify_id':'order','shopify_customer_id':'buyer'},shop,store)
  issue.assert_not_called()

class ReviewJourneySkip(unittest.TestCase):
 def test_received_review_skips_only_its_email_and_keeps_later_steps(self):
  from crm_lifecycle_runtime import advance
  from crm_logic import now
  engine=Mock();engine.clock.return_value=now()
  steps=[{'step_id':'review','template_id':'one','template_version':1},{'step_id':'collection','template_id':'two','template_version':1}]
  row={'id':'automation','status':'ACTIVE','steps':steps,'config':{'draft':{'emails':[{'review_request':{'product_index':0}}]}}}
  engine.store.get.return_value=row
  receipt={'step_index':0,'status':'BLOCKED','error_code':'review_already_received'}
  engine.store.q.side_effect=lambda sql,*a,**k:[receipt] if sql.startswith('SELECT * FROM crm_marketing_sends') else None
  engine.validate.return_value=({'id':'customer','email':'fixture@example.test'},None,'')
  enrollment={'id':'journey','automation_id':'automation','status':'ACTIVE','steps':steps,'shopify_customer_id':'customer','trigger_shopify_id':'order','trigger_at':now()}
  with patch('crm_lifecycle_runtime.locked',return_value=False),patch('crm_lifecycle_runtime.verified_plan',return_value={'stages':[]}):advance(engine,enrollment)
  engine.stop.assert_not_called();self.assertEqual(engine.store.enqueue.call_args.kwargs['step_index'],1)
