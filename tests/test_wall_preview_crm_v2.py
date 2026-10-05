"""No real provider delivery. Local PostgreSQL plus mocked Dropbox/Resend boundaries."""
import asyncio
import hashlib
import io
import os
import unittest
import uuid
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from PIL import Image
from starlette.applications import Starlette
from starlette.routing import Route

import wall_preview_api as api
import wall_preview_crm_api as web
import wall_preview_crm_store as store
import wall_preview_email as delivery
import wall_preview_store as legacy


def jpeg(color='red', exif=False):
    stream=io.BytesIO(); image=Image.new('RGB',(640,480),color)
    tags=Image.Exif();tags[270]='private source metadata' if exif else ''
    image.save(stream,'JPEG',exif=tags if exif else b'')
    return stream.getvalue()


def payload():
    return {'client_preview_id':str(uuid.uuid4()),'session_id':str(uuid.uuid4()),
        'image_sha256':hashlib.sha256(jpeg()).hexdigest(),'width':640,'height':480,'bytes':1000,
        'identity':{'customer_email':'','customer_name':'','shopify_customer_id':'','identity_source':'anonymous','email_marketing_state':'UNKNOWN'},
        'product_id':'123','variant_id':'456','product_handle':'collector-edition','product_title':'Real collector edition',
        'product_url':'https://sportscaveshop.com/products/collector-edition?variant=456',
        'frame_label':'Black','size_label':'Large','measurement_unit':'cm','attribution':{'utm_source':'test'}}


class PureTests(unittest.TestCase):
    def test_clean_image_removes_metadata_preserves_aspect_and_bounds_size(self):
        data,w,h=web.clean_image(jpeg(exif=True),'image/jpeg')
        with Image.open(io.BytesIO(data)) as image:
            self.assertFalse(image.getexif());self.assertEqual(image.size,(640,480))
        self.assertEqual((w,h),(640,480))
    def test_invalid_and_truncated_jpeg_rejected(self):
        for data in (b'not jpeg',jpeg()[:100],b'\xff\xd8\xfffake'):
            with self.assertRaises(ValueError):web.clean_image(data,'image/jpeg')
    def test_exact_product_variant_url_no_arbitrary_host(self):
        self.assertEqual(web.product_url('https://sportscaveshop.com/products/edition?utm_x=secret','gid://shopify/ProductVariant/456'),
            'https://sportscaveshop.com/products/edition?variant=456')
        for url in ('javascript:alert(1)','https://evil.example/products/a','https://sportscaveshop.com@evil.example/products/a'):
            with self.assertRaises(ValueError):web.product_url(url)
    def test_attribution_strips_referrer_query_and_fragment(self):
        self.assertEqual(web.attribution({'landing_url':'https://sportscaveshop.com/products/a?email=private#x','utm_source':'news'}),
                         {'landing_url':'https://sportscaveshop.com/products/a','utm_source':'news'})
    def test_message_escaped_exact_image_and_variant_no_marketing_optin(self):
        row=dict(payload(),share_token='a'*43,product_title='<script>alert(1)</script>')
        mail=delivery.message(row)
        self.assertIn('&lt;script&gt;',mail['html']);self.assertNotIn('<script>',mail['html'])
        self.assertIn('/wall-preview/'+'a'*43+'/image',mail['html']);self.assertIn('?variant=456',mail['html'])
        self.assertEqual(mail['subject'],'Your Sports Cave wall preview is ready')
        self.assertNotIn('Unsubscribe',mail['html'])
    def test_claimed_customer_id_never_used_as_auth(self):
        with self.assertRaises(ValueError):store.identifier('123')
        with self.assertRaises(ValueError):store.identifier(str(uuid.uuid1()))
    def test_frontend_has_no_identity_gate_no_pixel_and_no_drag_upload(self):
        source=Path('docs/storefront/wall-preview-crm-v2.js').read_text()
        self.assertIn('crypto.randomUUID()',source);self.assertIn('compositeBlob(false)',source)
        changed=source.split('function placementChanged()')[1].split('function confirm()')[0]
        self.assertNotIn('fetch(',changed);self.assertNotIn('upload(',changed)
        self.assertNotIn('fbq(',source);self.assertNotIn('marketing_permission',source)
        self.assertIn('_wall_preview_client_id',source);self.assertIn('_wall_preview_id',source)
    def test_migration_reviewed_and_additive_metadata_preserved(self):
        import run_migrations
        path=Path('migrations/20261005_wall_preview_crm_v2.sql')
        self.assertTrue(run_migrations.reviewed_migration_sql(path,path.read_text()))
        self.assertIn(path.name,run_migrations.DEPLOYMENT_MIGRATIONS)
        self.assertNotIn('DELETE FROM',path.read_text());self.assertNotIn('DROP TABLE',path.read_text())
    def test_followups_require_existing_marketing_gate(self):
        config=Mock(enabled=False)
        with patch('wall_preview_identity.resolve') as resolve:
            self.assertEqual(delivery.followup_eligibility({},config),(None,'marketing_disabled'))
            resolve.assert_not_called()
    def test_followups_use_fresh_existing_consent_and_suppress_unknown(self):
        from datetime import datetime,timezone
        row={'customer_email':'collector@example.com','confirmed_at':datetime.now(timezone.utc)}
        customer={'id':'gid://shopify/Customer/42','email':'collector@example.com',
                  'emailMarketingConsent':{'marketingState':'UNSUBSCRIBED'}}
        with patch('wall_preview_identity.resolve',return_value={'shopify_customer_id':customer['id']}),patch('crm_shopify.Shopify') as shop,patch('crm_store.Store') as records,patch.object(delivery,'Resend') as resend:
            shop.return_value.customer.return_value=customer
            records.return_value.suppressed.return_value=False
            result=delivery.followup_eligibility(row,Mock(enabled=True))
            self.assertIsNone(result[0]);shop.return_value.customer.assert_called_once_with(customer['id'],fresh=True)
            resend.assert_not_called()
    def test_verified_order_hook_runs_correlation_even_on_receipt_duplicate(self):
        import webhook_server
        order={'id':789,'line_items':[{'variant_id':456,'properties':[{'name':'_wall_preview_id','value':str(uuid.uuid4())}]}]}
        calls=[]
        with patch('supabase_backend.is_configured',return_value=True),patch('supabase_backend.claim_order_paid_webhook_receipt',side_effect=lambda *a,**k: calls.append('receipt') or {'duplicate':True}),patch.object(store,'correlate_order',side_effect=lambda *a:calls.append('correlation')):
            result=webhook_server._process_paid_order_durably(order,'event','orders/paid','shop')
            self.assertEqual(result['state'],'duplicate');self.assertEqual(calls,['correlation','receipt'])


class HttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        api._RATE_BUCKETS.clear()
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=Starlette(routes=[
            Route(api.WALL_PREVIEW_PATH,api.wall_preview_ingest,methods=['POST','OPTIONS']),
            *[Route(path,fn,methods=list(methods)) for path,fn,methods in web.ROUTES]])),base_url='https://fixture')
        self.headers={'Origin':'https://sportscaveshop.com','Content-Type':'image/jpeg'}
        self.pid=str(uuid.uuid4());self.sid=str(uuid.uuid4())
    async def asyncTearDown(self):await self.client.aclose()
    async def test_anonymous_blank_identity_confirm_uses_stable_private_root(self):
        def confirm(data,upload):
            storage=upload({},self.pid)
            self.assertIn('/03_ASSETS/11 Wall Preview Inbox/Anonymous/',storage['path'])
            self.assertEqual(data['identity']['identity_source'],'anonymous')
            self.assertEqual(data['identity']['customer_email'],'')
            return {'id':self.pid,'version':1,'share_token':'a'*43},False
        with patch.object(store,'confirm',side_effect=confirm),patch.object(api,'_dropbox_connection',return_value=('token','/Sportscave Team Folder')),patch('dropbox_integration.ensure_folder_path'),patch('dropbox_integration.upload_stream',return_value={'id':'id:file'}) as upload,patch('wall_preview_identity.crm_shopify.Shopify') as shop:
            response=await self.client.post(api.WALL_PREVIEW_PATH,params={'client_preview_id':str(uuid.uuid4()),'session_id':self.sid,'customer_email':'','customer_name':'','product_url':'https://sportscaveshop.com/products/edition'},content=jpeg(),headers=self.headers)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['preview_id'],self.pid)
            self.assertEqual(response.json()['preview_token'],self.sid)
            self.assertEqual(upload.call_args.kwargs['conflict'],'replace');shop.assert_not_called()
            self.assertNotIn('dropbox',response.text);self.assertNotIn('customer_email',response.text)
    async def test_events_whitelist_arbitrary_metadata_and_purchase_spoof_rejected(self):
        headers={**self.headers,'X-Wall-Preview-Token':self.sid}
        with patch.object(store,'add_event',side_effect=ValueError('No')):
            for body in ({'event_name':'WallPreviewPurchased','event_id':str(uuid.uuid4())},
                         {'event_name':'WallPreviewShared','event_id':str(uuid.uuid4()),'email':'private@example.com'}):
                response=await self.client.post(f'/api/wall-previews/{self.pid}/events',json=body,headers=headers)
                self.assertEqual(response.status_code,400)
        with patch.object(store,'add_event') as add:
            response=await self.client.post(f'/api/wall-previews/{self.pid}/events',json={'event_name':'WallPreviewShared','event_id':str(uuid.uuid4())},headers=headers)
            self.assertEqual(response.json(),{'ok':True});self.assertEqual(add.call_args.args[0],self.pid)
    async def test_actions_missing_capability_rejected(self):
        with patch.object(store,'add_event',side_effect=PermissionError()):
            response=await self.client.post(f'/api/wall-previews/{self.pid}/events',json={'event_name':'WallPreviewShared','event_id':str(uuid.uuid4())},headers=self.headers)
            self.assertEqual(response.status_code,403)
    async def test_email_validates_reserved_domains_no_fake_sent_or_consent(self):
        headers={**self.headers,'X-Wall-Preview-Token':self.sid}
        with patch.object(store,'request_email') as request:
            for email in ('not email','fixture@example.invalid'):
                response=await self.client.post(f'/api/wall-previews/{self.pid}/email',json={'email':email},headers=headers)
                self.assertEqual(response.status_code,400)
            request.assert_not_called()
        with patch.object(delivery,'configured',return_value=True),patch.object(store,'request_email',return_value='queued'):
            response=await self.client.post(f'/api/wall-previews/{self.pid}/email',json={'email':'collector@example.com'},headers=headers)
            self.assertEqual(response.json()['email_status'],'queued');self.assertFalse(response.json()['marketing_subscribed'])
        with patch.object(delivery,'configured',return_value=False),patch.object(store,'request_email') as request:
            response=await self.client.post(f'/api/wall-previews/{self.pid}/email',json={'email':'collector@example.com'},headers=headers)
            self.assertEqual(response.status_code,503);request.assert_not_called()
    async def test_cors_preflight_denied_origin_and_malformed_size(self):
        for suffix in ('events','email'):
            url=f'/api/wall-previews/{self.pid}/{suffix}'
            response=await self.client.options(url,headers=self.headers)
            self.assertEqual(response.status_code,204);self.assertIn('X-Wall-Preview-Token',response.headers['access-control-allow-headers'])
            response=await self.client.post(url,json={},headers={'Origin':'https://evil.example'})
            self.assertEqual(response.status_code,403)
            response=await self.client.post(url,content=b'x'*4097,headers=self.headers)
            self.assertEqual(response.status_code,413)
    async def test_share_page_noindex_minimum_payload_and_missing_file(self):
        row={'id':self.pid,'product_title':'Edition <script>','product_url':'https://sportscaveshop.com/products/a','variant_id':'456',
             'frame_label':'Black','size_label':'Large','dropbox_path':'/secret/archive','dropbox_file_id':'id:secret','customer_email':'private@example.com','session_id':self.sid}
        with patch.object(store,'public_preview',return_value=row):
            response=await self.client.get('/wall-preview/'+'a'*43)
            self.assertEqual(response.status_code,200);self.assertIn('noindex',response.headers['x-robots-tag'])
            for secret in ('private@example.com',self.sid,self.pid,'/secret/archive','id:secret'):
                self.assertNotIn(secret,response.text)
            self.assertIn('&lt;script&gt;',response.text)
            with patch.object(web,'archive_bytes',side_effect=RuntimeError()):
                response=await self.client.get('/wall-preview/'+'a'*43+'/image')
                self.assertEqual(response.status_code,404)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_wall_preview_feature import WallPreviewDatabaseTests
        WallPreviewDatabaseTests.setUpClass()
    def setUp(self):
        from tests.crm_db_fixture import Connection
        class Adapter(Connection):
            def cursor(self):return nullcontext(self)
            def execute(self,sql,args=()):self.result=super().execute(sql,args);return self.result
            def fetchone(self):return self.result.fetchone()
            def fetchall(self):return self.result.fetchall()
            def commit(self):pass
            def rollback(self):pass
        self.Adapter=Adapter
        self.backend=patch.object(legacy,'_backend');self.backend.start().return_value.connect.side_effect=Adapter
        with Adapter() as cur:cur.execute('TRUNCATE public.wall_previews CASCADE')
        self.upload=Mock(return_value={'path':'/Sportscave Team Folder/03_ASSETS/11 Wall Preview Inbox/Anonymous/test.jpg','folder':'/Sportscave Team Folder/03_ASSETS/11 Wall Preview Inbox/Anonymous','file_id':'id:fixture'})
        self.data=payload()
    def tearDown(self):self.backend.stop()
    def create(self):return store.confirm(self.data,self.upload)[0]
    def test_confirm_retry_and_reconfirm_one_row_one_file(self):
        first=self.create();second,duplicate=store.confirm(self.data,self.upload)
        self.assertTrue(duplicate);self.assertEqual(first['id'],second['id']);self.upload.assert_called_once()
        self.data['image_sha256']='b'*64;self.data['size_label']='Medium'
        third,duplicate=store.confirm(self.data,self.upload)
        self.assertFalse(duplicate);self.assertEqual(third['version'],2);self.assertEqual(third['id'],first['id'])
        self.assertEqual(self.upload.call_count,2)
        with self.Adapter() as cur:
            cur.execute('SELECT count(*) AS n FROM public.wall_previews');self.assertEqual(cur.fetchone()['n'],1)
        self.assertEqual([e['event_name'] for e in store.timeline(str(first['id']))].count('WallPreviewConfirmed'),2)
    def test_wrong_session_or_claimed_preview_id_cannot_replace(self):
        self.create();self.data['session_id']=str(uuid.uuid4())
        with self.assertRaises(PermissionError):store.confirm(self.data,self.upload)
        self.upload.assert_called_once()
    def test_same_composite_different_anonymous_clients_remain_independent(self):
        first=self.create()
        other=payload();second,_=store.confirm(other,self.upload)
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(first['archive_sha256'],second['archive_sha256'])
        self.assertNotEqual(first['image_sha256'],second['image_sha256'])
    def test_capture_same_record_jobs_idempotent_no_consent_write(self):
        row=self.create();pid=str(row['id']);sid=str(row['session_id'])
        self.assertEqual(store.request_email(pid,sid,'collector@example.com'),'queued')
        self.assertEqual(store.request_email(pid,sid,'collector@example.com'),'queued')
        with self.Adapter() as cur:
            cur.execute('SELECT * FROM public.wall_previews WHERE id=%s',(pid,));updated=cur.fetchone()
            self.assertEqual(updated['id'],row['id']);self.assertEqual(updated['identity_source'],'email_capture')
            self.assertEqual(updated['email_marketing_state'],'UNKNOWN');self.assertFalse(updated['marketing_permission'])
            cur.execute('SELECT count(*) AS n FROM public.wall_preview_email_jobs');self.assertEqual(cur.fetchone()['n'],3)
        with self.assertRaises(ValueError):store.request_email(pid,sid,'other@example.com')
    def test_event_dedup_and_only_authoritative_purchase(self):
        row=self.create();pid=str(row['id']);sid=str(row['session_id']);eid=str(uuid.uuid4())
        for _ in range(2):store.add_event(pid,sid,'WallPreviewAddedToCart',eid)
        self.assertEqual(len(store.timeline(pid)),3)
        with self.assertRaises(ValueError):store.add_event(pid,sid,'WallPreviewPurchased',eid)
        with self.assertRaises(PermissionError):store.add_event(pid,str(uuid.uuid4()),'WallPreviewShared',eid)
    def test_verified_purchase_matching_variant_suppresses_followups_and_deduplicates(self):
        row=self.create();pid=str(row['id']);store.request_email(pid,str(row['session_id']),'collector@example.com')
        order={'id':789,'name':'#789','line_items':[{'variant_id':456,'properties':[{'name':'_wall_preview_id','value':pid}]}]}
        for _ in range(2):self.assertEqual(store.correlate_order(order),1)
        with self.Adapter() as cur:
            cur.execute('SELECT kind,state FROM public.wall_preview_email_jobs ORDER BY kind');jobs=cur.fetchall()
            self.assertEqual({j['kind']:j['state'] for j in jobs},{'requested':'queued','4h':'suppressed','24h':'suppressed'})
        self.assertEqual([e['event_name'] for e in store.timeline(pid)].count('WallPreviewPurchased'),1)
    def test_client_id_fallback_and_wrong_variant_not_attributed(self):
        row=self.create()
        order={'id':789,'line_items':[{'variant_id':999,'properties':[{'name':'_wall_preview_client_id','value':self.data['client_preview_id']}]}]}
        self.assertEqual(store.correlate_order(order),0)
        order['line_items'][0]['variant_id']=456;self.assertEqual(store.correlate_order(order),1)
    def test_private_counts_filters_and_revoke(self):
        row=self.create();pid=str(row['id'])
        store.add_event(pid,str(row['session_id']),'WallPreviewAddedToCart',str(uuid.uuid4()))
        self.assertEqual(legacy.summary(include_private=True)['confirmed'],1)
        self.assertEqual(legacy.summary(include_private=True)['added_to_cart'],1)
        self.assertEqual(len(legacy.list_previews(status='all',intent='added_to_cart',include_private=True)),1)
        self.assertEqual(legacy.list_previews(status='all'),[])
        self.assertIsNotNone(store.public_preview(row['share_token']));store.revoke_share(pid)
        self.assertIsNone(store.public_preview(row['share_token']))
    def test_rls_no_public_read_and_repeat_migration_preserves_rows(self):
        self.create()
        with self.Adapter() as cur:
            for statement in Path('migrations/20261005_wall_preview_crm_v2.sql').read_text().split(';'):
                if statement.strip():cur.execute(statement)
            for table in ('wall_previews','wall_preview_events','wall_preview_email_jobs'):
                cur.execute('SELECT has_table_privilege(%s,%s,%s) AS allowed',('anon','public.'+table,'SELECT'))
                self.assertFalse(cur.fetchone()['allowed'])
            cur.execute('SELECT count(*) AS n FROM public.wall_previews');self.assertEqual(cur.fetchone()['n'],1)
            self.assertEqual(legacy.schema_issues(cur),[])
    def test_requested_worker_uses_existing_resend_and_never_resends(self):
        row=self.create();store.request_email(str(row['id']),str(row['session_id']),'collector@example.com')
        provider=Mock();provider.send.return_value.provider_message_id='provider-fixture'
        with patch.object(delivery,'configured',return_value=True),patch.object(delivery,'ResendEmailProvider',return_value=provider),patch.object(delivery,'pace'):
            self.assertTrue(delivery.tick());self.assertFalse(delivery.tick())
        provider.send.assert_called_once()
        self.assertTrue(legacy.list_previews(status='all',include_private=True)[0]['email_sent_at'])
    def test_unknown_provider_outcome_not_replayed(self):
        from email_service import EmailDeliveryError
        row=self.create();store.request_email(str(row['id']),str(row['session_id']),'collector@example.com')
        provider=Mock();provider.send.side_effect=EmailDeliveryError('timeout',retryable=True)
        with patch.object(delivery,'configured',return_value=True),patch.object(delivery,'ResendEmailProvider',return_value=provider),patch.object(delivery,'pace'):
            delivery.tick();self.assertFalse(delivery.tick())
        with self.Adapter() as cur:
            cur.execute("SELECT state FROM public.wall_preview_email_jobs WHERE kind='requested'");self.assertEqual(cur.fetchone()['state'],'uncertain')


if __name__=='__main__':unittest.main()
