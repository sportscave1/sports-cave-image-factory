"""Reviews tests: local SQL, synthetic identities, mocked providers; no live data."""
from concurrent.futures import Future
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import unittest
import uuid
from unittest.mock import Mock,patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from crm_logic import now
from reviews_model import normalize,auto_mapping,display_settings,product_gid
from reviews_import import read_csv,preview,JudgeMe
from reviews_store import ReviewsStore
from reviews_worker import tick
from reviews_submission import issue,submit,token_row,prepare_email,MARKER
from reviews_cache import read,invalidate
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN

ROOT=Path(__file__).resolve().parents[1]

class ModelTests(unittest.TestCase):
    def test_utf8_csv_mapping_and_plain_text(self):
        headers,rows=read_csv('review_id;stars;review_body;customer;handle\n42;5;<b>Great</b> café;Nathan;fox\n'.encode())
        item=normalize(rows[0],mapping=auto_mapping(headers))
        self.assertEqual(item['rating'],5);self.assertEqual(item['body'],'Great café');self.assertEqual(item['reviewer_name'],'Nathan')
        self.assertEqual(item['product_hints']['product_handle'],'fox');self.assertEqual(item['source_review_id'],'42')
    def test_manual_mapping_and_duplicate_missing_date_stability(self):
        r={'score':'4','comment':'Wonderful','who':'Collector'};mapping={'rating':'score','body':'comment','reviewer_name':'who'}
        a=normalize(r,mapping=mapping);b=normalize(r,mapping=mapping)
        self.assertEqual(a['dedupe_key'],b['dedupe_key']);self.assertEqual(a['status'],'PENDING')
    def test_invalid_rating_text_date_and_file_limits(self):
        for raw in ({'rating':6,'body':'yes'},{'rating':3.5,'body':'yes'},{'rating':5},{'rating':4,'body':'yes','created_at':'no-date'},{'rating':4,'body':'yes','created_at':'2100-01-01'}):
            with self.assertRaises(ValueError):normalize(raw)
        for data in (b'\xff',b'a,a\n1,2',b'a,b\n1,2,3',b'a\x00'):
            with self.assertRaises(ValueError):read_csv(data)
    def test_verification_hash_and_no_email_storage(self):
        item=normalize({'rating':5,'body':'<script>secret()</script>Excellent','email':'Person@example.test','source_verified':True})
        self.assertTrue(item['source_verified']);self.assertFalse(item['verified_purchase']);self.assertEqual(item['body'],'Excellent')
        self.assertNotIn('Person@example.test',json.dumps(item));self.assertEqual(len(item['reviewer_email_hash']),64)
    def test_dedupe_source_ids_and_distinct_reviews(self):
        a=normalize({'rating':5,'body':'A','source_review_id':'42'});b=normalize({'rating':4,'body':'Updated','source_review_id':'42'})
        self.assertEqual(a['dedupe_key'],b['dedupe_key'])
        self.assertNotEqual(normalize({'rating':5,'body':'A','reviewer_name':'One'})['dedupe_key'],normalize({'rating':5,'body':'A','reviewer_name':'Two'})['dedupe_key'])
    def test_display_policy_is_rating_neutral_and_validated(self):
        self.assertEqual(display_settings({})['moderation'],'manual')
        for value in ({'per_page':100},{'accent':'javascript:x'},{'moderation':'publish_high'},{'enabled':'yes'}):
            with self.assertRaises(ValueError):display_settings(value)
    def test_review_date_without_zone_uses_utc(self):
        item=normalize({'rating':5,'body':'Dated','created_at':'2026-01-01'})
        self.assertEqual(item['created_at'],'2026-01-01T00:00:00+00:00')
    def test_judgeme_normalization_never_uses_internal_product_id_as_shopify(self):
        p=JudgeMe({'JUDGEME_PRIVATE_API_TOKEN':'secret','SHOPIFY_STORE_DOMAIN':'fixture.myshopify.com'})
        item=p.normalize({'id':42,'product_id':999,'rating':5,'body':'Nice','reviewer':{'name':'Fixture','email':'test@example.test'},'verified':True,'hidden':False})
        self.assertIsNone(item['product_id']);self.assertFalse(item['verified_purchase']);self.assertEqual(item['status'],'PUBLISHED')
        self.assertEqual(p.normalize({'id':43,'product_external_id':55,'rating':4,'body':'Good','hidden':False})['product_id'],'gid://shopify/Product/55')
    def test_provider_is_official_read_only_bounded_and_redacts_errors(self):
        session=Mock();session.get.return_value=Mock(status_code=200,json=lambda:{'reviews':[]})
        p=JudgeMe({'JUDGEME_PRIVATE_API_TOKEN':'private-secret','SHOPIFY_STORE_DOMAIN':'fixture.myshopify.com'},session)
        self.assertEqual(p.page(1),[]);kw=session.get.call_args.kwargs;self.assertEqual(kw['params']['per_page'],100);self.assertFalse(kw['allow_redirects'])
        session.get.side_effect=RuntimeError('https://token/private-secret')
        with self.assertRaises(RuntimeError) as err:p.page(2)
        self.assertNotIn('private-secret',str(err.exception));self.assertEqual(session.post.call_count,0)
    def test_cache_retains_values_on_refresh_failure_and_invalidates_only_groups(self):
        state={};f=Future();f.set_result({'total':4,'average':4.5,'recent':4,'five_rate':50,'attention':0})
        state['reviews_cache']={('summary',):{'future':f,'completed':None},('table',):{'future':f,'completed':None}}
        self.assertEqual(read(state,('summary',),lambda:None)[0]['total'],4)
        invalidate(state,'table');self.assertIn(('summary',),state['reviews_cache'])
        pending=Future();state['reviews_cache'][('summary',)]={'future':pending,'completed':None}
        self.assertEqual(read(state,('summary',),lambda:None)[1],'REFRESHING');self.assertEqual(read(state,('summary',),lambda:None)[0]['total'],4)
        pending.set_exception(ValueError('failed'));self.assertEqual(read(state,('summary',),lambda:None)[0]['total'],4)
        empty=Future();empty.set_result({});state['reviews_cache'][('summary',)]={'future':empty,'completed':None}
        self.assertEqual(read(state,('summary',),lambda:None),({'total':4,'average':4.5,'recent':4,'five_rate':50,'attention':0},'ERROR'))
    def test_ui_escapes_and_no_unverified_badge(self):
        from reviews_page import row_html,kpi_html
        r={'id':'1','created_at':now(),'source':'csv','status':'PUBLISHED','product_title':'<b>Product</b>','reviewer_name':'<img onerror=x>','rating':5,'title':'<script>x</script>','body':'<b>body</b>','verified_purchase':False}
        html=row_html(r);self.assertNotIn('<script>',html);self.assertNotIn('Verified purchase',html);self.assertIn('&lt;',html)
        self.assertIn('—',kpi_html());self.assertNotIn('iframe',html)
    def test_navigation_is_single_top_level_and_page_three_areas(self):
        import os_accounts
        self.assertEqual(len([p for p in os_accounts.PAGE_REGISTRY if p['route']=='Reviews']),1)
        self.assertFalse(os_accounts.PAGE_BY_KEY['reviews'].get('navigation_child'))
        text=(ROOT/'reviews_page.py').read_text();self.assertIn("['Overview','Import reviews','Display']",text)
        self.assertNotIn('Judge.me admin',text)
    def test_page_shell_is_emitted_without_waiting_for_reads_and_hidden_tabs(self):
        from streamlit.testing.v1 import AppTest
        script='''
import streamlit as st
from unittest.mock import Mock,patch
from reviews_page import render_page
from tests.test_crm import ADMIN
store=Mock();store.connect=None
with patch('reviews_page.read',return_value=(None,'LOADING')) as read:
 render_page(ADMIN,store=store)
 st.session_state['read_groups']=[c.args[1][0] for c in read.call_args_list]
store.summary.assert_not_called();store.imports.assert_not_called();store.settings.assert_not_called()
'''
        app=AppTest.from_string(script).run()
        self.assertEqual(len(app.exception),0);self.assertEqual(app.title[0].value,'Reviews')
        self.assertEqual(app.session_state['read_groups'],['summary','table'])

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.store=ReviewsStore(connect);self.prefix=uuid.uuid4().hex;self.created=[];self.jobs=[]
        self.pid='gid://shopify/Product/'+str(uuid.uuid4().int%10**12);self.handle='fixture-'+self.prefix
        self.store.q('''CREATE TABLE IF NOT EXISTS shopify_products(shopify_product_id text PRIMARY KEY,title text,handle text,status text,image_url text,online_store_url text)''')
        self.store.q('CREATE TABLE IF NOT EXISTS shopify_variants(shopify_variant_id text PRIMARY KEY,shopify_product_id text,sku text)')
        self.store.q('INSERT INTO shopify_products VALUES(%s,%s,%s,%s,%s,%s)',(self.pid,'Collector '+self.prefix,self.handle,'ACTIVE','https://cdn.shopify.com/fixture.png','https://fixture.example/products/'+self.handle))
        self.guard=patch('requests.sessions.Session.request',side_effect=AssertionError('External network forbidden'));self.guard.start();self.addCleanup(self.guard.stop)
        self.addCleanup(self.cleanup)
    def cleanup(self):
        # Archive instead of delete: aggregate trigger and provenance stay intact.
        self.store.q("UPDATE sc_reviews SET status='ARCHIVED' WHERE source_review_id LIKE %s",(self.prefix+'%',))
        for job in self.jobs:self.store.q("UPDATE sc_review_imports SET status='COMPLETED' WHERE id=%s",(job,))
    def item(self,**updates):
        raw={'source_review_id':self.prefix+str(len(self.created)),'product_id':self.pid,'rating':5,'body':'A collector review','reviewer_name':'Fixture','created_at':(now()-timedelta(days=2)).isoformat(),'status':'PUBLISHED',**updates}
        item=normalize(raw);self.created.append(item['source_review_id']);return item
    def insert(self,**updates):
        item=self.item(**updates)
        with self.store.db() as conn:self.store.import_one(conn,item,self.store.match_product(item['product_hints']))
        return self.store.q('SELECT * FROM sc_reviews WHERE dedupe_key=%s',(item['dedupe_key'],),True)
    def test_kpis_incremental_archive_reply_and_empty_product(self):
        before=self.store.summary();r=self.insert(rating=2);self.insert(rating=5)
        after=self.store.summary();self.assertEqual(after['total'],before['total']+2);self.assertEqual(after['recent'],before['recent']+2);self.assertEqual(after['attention'],before['attention']+1)
        self.assertEqual(self.store.aggregate(self.pid),{'count':2,'average':3.5})
        self.store.moderate(ADMIN,r['id'],reply='Thank you');self.assertEqual(self.store.summary()['attention'],before['attention'])
        self.store.moderate(ADMIN,r['id'],status='ARCHIVED');self.assertEqual(self.store.aggregate(self.pid)['count'],1)
        self.assertEqual(self.store.aggregate('gid://shopify/Product/0'),{'count':0,'average':None})
    def test_server_pagination_and_filters(self):
        for i in range(28):self.insert(rating=4 if i%2 else 5,body='Distinct text '+str(i))
        rows=self.store.rows(product=self.pid,limit=25);self.assertEqual(len(rows),26)
        page=self.store.rows(product=self.pid,limit=25,offset=25);self.assertEqual(len(page),3)
        self.assertEqual(len(self.store.rows(product=self.pid,rating=4)),14)
        self.assertEqual(len(self.store.rows(product=self.pid,search='Distinct',source='csv')),26)
        self.store.moderate(ADMIN,page[0]['id'],status='PENDING');self.assertEqual(len(self.store.rows(product=self.pid,status='PENDING')),1)
    def test_exact_mapping_priority_and_ambiguous_title_unresolved(self):
        self.assertEqual(self.store.match_product({'product_id':self.pid})['shopify_product_id'],self.pid)
        self.assertEqual(self.store.match_product({'product_handle':self.handle})['shopify_product_id'],self.pid)
        self.assertEqual(self.store.match_product({'product_url':'https://fixture.example/products/'+self.handle})['shopify_product_id'],self.pid)
        self.assertIsNone(self.store.match_product({'product_url':'https://evil.example/products/'+self.handle}))
        self.store.q('INSERT INTO shopify_products VALUES(%s,%s,%s,%s,%s,%s)',('gid://shopify/Product/'+str(uuid.uuid4().int%10**12),'Collector '+self.prefix,'other-'+self.prefix,'ACTIVE','',''))
        self.assertIsNone(self.store.match_product({'product_title':'Collector '+self.prefix}))
    def test_import_file_twice_atomic_progress_and_unresolved(self):
        items=[self.item(),self.item(product_id='gid://shopify/Product/0')]
        for _ in range(2):
            job=self.store.enqueue_import(ADMIN,'csv','Fixture',items);self.jobs.append(job['id']);tick(self.store)
        first=self.store.q('SELECT * FROM sc_review_imports WHERE id=%s',(self.jobs[0],),True);second=self.store.q('SELECT * FROM sc_review_imports WHERE id=%s',(self.jobs[1],),True)
        self.assertEqual(first['imported'],2);self.assertEqual(first['unresolved'],1);self.assertEqual(first['status'],'COMPLETED');self.assertEqual(second['duplicates'],2)
        self.assertEqual(len(self.store.rows(product=self.pid)),1)
    def test_import_chunks_and_no_provider_email_transport(self):
        items=[self.item(body='Row '+str(i)) for i in range(205)]
        job=self.store.enqueue_import(ADMIN,'csv','Chunk fixture',items);self.jobs.append(job['id'])
        tick(self.store);r=self.store.q('SELECT cursor,status FROM sc_review_imports WHERE id=%s',(job['id'],),True)
        self.assertEqual(r,{'cursor':100,'status':'PENDING'});tick(self.store);tick(self.store)
        self.assertEqual(self.store.q('SELECT imported FROM sc_review_imports WHERE id=%s',(job['id'],),True)['imported'],205)
    def test_provider_sync_idempotent_preserves_local_reply_and_moderation(self):
        provider=Mock();provider.page.return_value=[{}];provider.normalize.return_value=self.item()
        for i in range(2):
            job=self.store.enqueue_sync(ADMIN);self.jobs.append(job['id']);tick(self.store,provider)
            if i==0:
                r=self.store.q('SELECT * FROM sc_reviews WHERE source_review_id=%s',(provider.normalize.return_value['source_review_id'],),True)
                self.store.moderate(ADMIN,r['id'],reply='Local reply',status='ARCHIVED')
        r=self.store.get_review(r['id']);self.assertEqual(r['merchant_reply'],'Local reply');self.assertEqual(r['status'],'ARCHIVED')
    def test_csv_preview_invalid_duplicates_unresolved_no_raw_email(self):
        rows=[{'rating':'5','body':'Excellent','product_id':self.pid,'email':'test@example.test'}, {'rating':'5','body':'Excellent','product_id':self.pid,'email':'test@example.test'}, {'rating':'9','body':'Invalid'}, {'rating':'2','body':'Unknown product'}]
        result=preview(rows,{},self.store);self.assertEqual((result['ready'],result['duplicates'],result['unresolved'],len(result['invalid'])),(2,1,1,1))
        self.assertNotIn('test@example.test',json.dumps(result))
    def test_moderation_permissions_audit_and_source_verified_not_native(self):
        r=self.insert(source_verified=True);self.assertFalse(r['verified_purchase'])
        with self.assertRaises(PermissionError):self.store.moderate({'is_active':False},r['id'],status='ARCHIVED')
        self.store.moderate(ADMIN,r['id'],reply='<b>Thanks</b>');self.assertEqual(self.store.get_review(r['id'])['merchant_reply'],'Thanks')
        self.assertEqual(self.store.q('SELECT count(*) n FROM sc_review_audit WHERE review_id=%s',(r['id'],),True)['n'],1)
    def order(self):
        return {'id':'gid://shopify/Order/123','customer':{'id':'gid://shopify/Customer/456'},'cancelledAt':None,'lineItems':{'nodes':[{'product':{'id':self.pid}}],'pageInfo':{'hasNextPage':False}}}
    def test_native_token_context_expiry_submission_dedupe_and_verified(self):
        order=self.order();shop=Mock();shop.order.return_value=order
        env={'CRM_PUBLIC_BASE_URL':'https://fixture.example','CRM_UNSUBSCRIBE_SECRET':'fixture-signing-key-'+self.prefix}
        url=issue(self.store,shop,order['id'],order['customer']['id'],self.pid,env);token=url.rsplit('/',1)[-1]
        self.assertEqual(issue(self.store,shop,order['id'],order['customer']['id'],self.pid,env),url)
        payload={'rating':'5','body':'Beautiful','reviewer_name':'Collector','display_consent':True}
        a=submit(self.store,token,payload);self.assertEqual(a,submit(self.store,token,payload));r=self.store.get_review(a)
        self.assertTrue(r['verified_purchase']);self.assertEqual(r['status'],'PENDING');self.assertEqual(r['order_id'],order['id'])
        self.store.q("UPDATE sc_reviews SET status='ARCHIVED' WHERE id=%s",(a,))
        self.store.q('UPDATE sc_review_tokens SET expires_at=%s WHERE token_hash=%s',(now()-timedelta(days=1),hashlib.sha256(token.encode()).hexdigest()))
        with self.assertRaises(ValueError):token_row(self.store,token)
        with self.assertRaises(ValueError):token_row(self.store,'forged')
    def test_spoofed_customer_product_and_bot_rejected(self):
        shop=Mock();shop.order.return_value=self.order();env={'CRM_PUBLIC_BASE_URL':'https://fixture.example','CRM_UNSUBSCRIBE_SECRET':'x'*40}
        for customer,product in (('gid://shopify/Customer/999',self.pid),('gid://shopify/Customer/456','gid://shopify/Product/999')):
            with self.assertRaises(ValueError):issue(self.store,shop,'gid://shopify/Order/123',customer,product,env)
        with self.assertRaises(ValueError):submit(self.store,'a'*64,{'rating':5,'body':'Bot','website':'trap','display_consent':True})
    def test_public_projection_only_published_no_sensitive_fields(self):
        a=self.insert();self.insert(status='PENDING');self.store.save_settings(ADMIN,{'enabled':True})
        from reviews_http import router
        app=FastAPI();app.include_router(router)
        with patch('reviews_http.ReviewsStore',return_value=self.store),TestClient(app) as client:
            response=client.get('/reviews/public',params={'product':self.pid})
            self.assertEqual(response.status_code,200);data=response.json();self.assertEqual(len(data['reviews']),1)
            self.assertEqual(data['summary']['count'],1)
            numeric=client.get('/reviews/public',params={'product':self.pid.rsplit('/',1)[-1],'summary':'1'})
            self.assertEqual(numeric.json()['summary'],data['summary'])
            for field in ('reviewer_email_hash','customer_id','order_id','source_metadata','reply_actor'):self.assertNotIn(field,data['reviews'][0])
            self.assertEqual(client.get('/reviews/public?product=invalid').status_code,400)
    def test_submission_http_no_email_and_honeypot(self):
        shop=Mock();shop.order.return_value=self.order();env={'CRM_PUBLIC_BASE_URL':'https://fixture.example','CRM_UNSUBSCRIBE_SECRET':'token-key-'+self.prefix}
        url=issue(self.store,shop,'gid://shopify/Order/123','gid://shopify/Customer/456',self.pid,env);token=url.rsplit('/',1)[-1]
        from reviews_http import router
        app=FastAPI();app.include_router(router)
        with patch('reviews_http.ReviewsStore',return_value=self.store),TestClient(app) as client:
            self.assertEqual(client.get('/reviews/request/'+token).status_code,200)
            payload={'rating':'4','body':'Good','reviewer_name':'Fixture','display_consent':'yes'}
            self.assertEqual(client.post('/reviews/request/'+token,data=payload,headers={'Origin':'https://evil.example'}).status_code,403)
            self.assertEqual(client.post('/reviews/request/'+token,data={**payload,'website':'bot'}).status_code,400)
            self.assertEqual(client.post('/reviews/request/'+token,data=payload).status_code,200)
            r=token_row(self.store,token);self.store.q("UPDATE sc_reviews SET status='ARCHIVED' WHERE id=%s",(r['review_id'],))
    def test_schema_and_reviewed_migration_security(self):
        import reviews_schema
        class Adapter:
            def __init__(self,conn):self.conn=conn
            def execute(self,*args):self.result=self.conn.execute(*args)
            def fetchall(self):return self.result.fetchall()
        with connect() as conn:self.assertEqual(reviews_schema.schema_issues(Adapter(conn)),[])
        from run_migrations import reviewed_migration_sql,DEPLOYMENT_MIGRATIONS
        p=ROOT/'migrations/20261002152512_reviews_v1.sql';reviewed_migration_sql(p,p.read_text());self.assertIn(p.name,DEPLOYMENT_MIGRATIONS)
    def test_unknown_date_not_counted_as_a_new_review(self):
        before=self.store.summary()['recent'];self.insert(created_at='')
        self.assertEqual(self.store.summary()['recent'],before)
    def test_sku_and_manual_mapping_are_exact_and_reset_verification(self):
        sku='sku-'+self.prefix;self.store.q('INSERT INTO shopify_variants VALUES(%s,%s,%s)',('variant-'+self.prefix,self.pid,sku))
        self.assertEqual(self.store.match_product({'product_sku':sku})['shopify_product_id'],self.pid)
        r=self.insert(product_id='gid://shopify/Product/0');self.assertIsNone(r['product_id'])
        self.store.moderate(ADMIN,r['id'],product=self.pid);r=self.store.get_review(r['id'])
        self.assertEqual(r['product_id'],self.pid);self.assertFalse(r['verified_purchase']);self.assertIsNone(r['order_id'])
    def test_background_failure_is_bounded_retry_and_never_exposes_provider_details(self):
        job=self.store.enqueue_sync(ADMIN);self.jobs.append(job['id']);provider=Mock();provider.page.side_effect=RuntimeError('PRIVATE TOKEN OR EMAIL')
        with self.assertLogs('reviews_worker',level='WARNING') as logs:
            for _ in range(3):tick(self.store,provider)
        r=self.store.q('SELECT status,attempts,error_code FROM sc_review_imports WHERE id=%s',(job['id'],),True)
        self.assertEqual(r,{'status':'FAILED','attempts':3,'error_code':'source_unavailable'});self.assertNotIn('PRIVATE',str(logs.output))
    def test_public_stars_read_does_not_load_review_bodies_and_cache_is_scoped(self):
        self.insert();self.store.save_settings(ADMIN,{'enabled':True})
        from reviews_http import router
        from reviews_public_cache import CACHE
        CACHE.invalidate();app=FastAPI();app.include_router(router)
        with patch('reviews_http.ReviewsStore',return_value=self.store),patch.object(self.store,'rows',wraps=self.store.rows) as rows,patch.object(self.store,'aggregate',wraps=self.store.aggregate) as aggregate,TestClient(app) as client:
            for _ in range(2):self.assertEqual(client.get('/reviews/public',params={'product':self.pid,'summary':'1'}).status_code,200)
            rows.assert_not_called();aggregate.assert_called_once()
    def test_review_request_handoff_reuses_automation_editor_and_freezes_link(self):
        from reviews_submission import create_automation
        from crm_automation_store import AutomationStore
        from crm_automation_definition import validate
        from tests.test_crm_send_flow import CFG,LIVE
        with patch.dict(os.environ,{**LIVE,'CRM_PUBLIC_BASE_URL':'https://example.test'}),patch.object(AutomationStore,'render_settings',return_value=deepcopy(CFG)):
            row=create_automation(ADMIN,self.store,self.pid,7)
        flow=row['config']['draft'];validate(flow)
        self.assertEqual(flow['trigger'],'fulfilled');self.assertEqual(flow['emails'][0]['delay_seconds'],7*86400)
        self.assertEqual(row['status'],'DRAFT');self.assertEqual(len(flow['emails']),1)
        self.assertIn(MARKER,flow['emails'][0]['document']['custom_html'])
        content={'format':'automation_delivery_v1','trigger':'fulfilled','review_request':flow['review_request'],'document':flow['emails'][0]['document']}
        shop=Mock();shop.order.return_value=self.order();enrollment={'trigger_shopify_id':self.order()['id'],'shopify_customer_id':self.order()['customer']['id']}
        with patch.dict(os.environ,LIVE):prepared=prepare_email(content,{},enrollment,shop,self.store)
        self.assertNotIn(MARKER,json.dumps(prepared['document']));self.assertIn(MARKER,json.dumps(content['document']))
        with patch('reviews_submission.issue') as issued:self.assertIs(prepare_email({'document':{}},{},None,shop,self.store)['document'].get('body'),None);issued.assert_not_called()
        self.store.q("UPDATE crm_automations SET status='PAUSED' WHERE id=%s",(row['id'],))
    def test_import_product_matching_is_batched_not_n_plus_one(self):
        with patch.object(self.store,'q',wraps=self.store.q) as reads:
            matches=self.store.match_products([{'product_id':self.pid} for _ in range(100)])
        self.assertEqual(len(matches),100);self.assertTrue(all(m['shopify_product_id']==self.pid for m in matches));self.assertEqual(reads.call_count,1)
    def test_thirty_day_boundary_and_needs_attention_are_not_double_counted(self):
        before=self.store.summary();self.insert(created_at=(now()-timedelta(days=31)).isoformat())
        self.insert(created_at=(now()-timedelta(days=29,hours=23)).isoformat(),status='PENDING',rating=1,product_id='gid://shopify/Product/0')
        after=self.store.summary();self.assertEqual(after['recent'],before['recent']+1);self.assertEqual(after['attention'],before['attention']+1)

if __name__=='__main__':unittest.main()
