import os,uuid,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import httpx
from starlette.applications import Starlette
from starlette.routing import Route
import wall_preview_analytics as analytics
import wall_preview_analytics_api as api
from tests import test_wall_preview_crm_v2 as fixtures


def event(name='Started',**kw):
    return dict(event='WallPreview'+name,event_id=str(uuid.uuid4()),session_id=str(uuid.uuid4()),
        client_preview_id=str(uuid.uuid4()),product_id='123',variant_id='456',product_title='Artwork',
        frame='Black',size='Medium',device_type='mobile',capture_source='camera',**kw)

class Pure(unittest.TestCase):
    def test_no_pii_photos_queries_or_credentials(self):
        row=analytics.clean(event(customer_email='private@example.test',photo='pixels',page_url='https://shop.test/products/a?email=secret#x',referrer='https://search.test/?q=secret'))
        self.assertNotIn('customer_email',row);self.assertNotIn('photo',row)
        self.assertEqual(row['page_url'],'https://shop.test/products/a');self.assertEqual(row['referrer'],'https://search.test/')
    def test_purchase_is_server_only_and_dates_bounded(self):
        with self.assertRaises(ValueError):analytics.clean(event('Purchased'))
        with self.assertRaises(ValueError):analytics.clean(event(occurred_at='2020-01-01T00:00:00Z'))
        with self.assertRaises(ValueError):analytics.filters({'start_date':'2020-01-01','end_date':'2026-01-01'})

class Api(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=Starlette(routes=[Route(p,f,methods=m) for p,f,m in api.ROUTES])),base_url='http://localhost')
        self.addAsyncCleanup(self.client.aclose)
    async def test_anonymous_ingest_outage_bounds_and_purchase_spoof(self):
        url='/api/wall-previews/analytics/events';headers={'Origin':'https://sportscaveshop.com'}
        with patch.object(analytics,'ingest',return_value=True):
            self.assertEqual((await self.client.post(url,json=event(),headers=headers)).status_code,200)
            self.assertEqual((await self.client.post(url,json=event())).status_code,403)
            self.assertEqual((await self.client.post(url,json=event('Purchased'),headers=headers)).status_code,400)
            self.assertEqual((await self.client.post(url,content=b'x'*8193,headers=headers)).status_code,413)
        with patch.object(analytics,'ingest',side_effect=RuntimeError('private database detail')):
            response=await self.client.post(url,json=event(),headers=headers)
            self.assertEqual(response.status_code,503);self.assertNotIn('private',response.text)
    async def test_read_authorization_and_filters(self):
        with patch.object(api,'authorize',side_effect=PermissionError):
            for section in ('summary','funnel','products','events'):
                self.assertEqual((await self.client.get('/api/wall-previews/analytics/'+section)).status_code,403)
        with patch.object(api,'authorize',return_value={}),patch.object(analytics,'report',return_value={'summary':{'opens':1}}) as read:
            response=await self.client.get('/api/wall-previews/analytics/summary?device_type=mobile')
            self.assertEqual(response.json(),{'opens':1});self.assertEqual(read.call_args.args[0]['device_type'],'mobile')

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Local PostgreSQL required')
class Database(unittest.TestCase):
    setUpClass=classmethod(lambda cls: fixtures.DatabaseTests.setUpClass())
    setUp=fixtures.DatabaseTests.setUp
    tearDown=fixtures.DatabaseTests.tearDown
    create=fixtures.DatabaseTests.create
    def track(self,name,**extra):
        payload=event(name);payload.update(client_preview_id=self.data['client_preview_id'],session_id=self.data['session_id']);payload.update(extra)
        analytics.ingest(payload);return payload
    def test_anonymous_journey_retry_dedupe_and_saved_link(self):
        payload=self.track('Started');self.assertFalse(analytics.ingest(payload))
        self.track('PhotoReady');self.track('ArtworkDragged');self.track('Confirmed')
        row=self.create()
        data=analytics.report()
        self.assertEqual(data['summary']['opens'],1);self.assertEqual(data['summary']['confirmed'],1)
        self.assertEqual(data['summary']['sessions'],1)
        self.assertEqual(data['funnel'][0]['next_stage_percent'],100)
        self.assertIn('WallPreviewStarted',[r['event_name'] for r in analytics.events({'preview_id':str(row['id'])})])
        payload['session_id']=str(uuid.uuid4())
        with self.assertRaises(PermissionError):analytics.ingest(payload)
    def test_purchase_retry_line_revenue_currency_and_filters(self):
        self.track('Started');self.track('AddedToCart');row=self.create()
        order={'id':99,'name':'#TEST','total_price':'300','currency':'AUD','line_items':[{'id':10,'product_id':123,'variant_id':456,'quantity':2,'price':'100','discount_allocations':[{'amount':'10'}],'properties':[{'name':'_wall_preview_id','value':str(row['id'])}]}]}
        for _ in range(2):fixtures.store.correlate_order(order)
        data=analytics.report({'device_type':'mobile','capture_source':'camera'})
        self.assertEqual(data['summary']['purchased'],1);self.assertEqual(data['summary']['purchase_percent'],100)
        self.assertEqual(float(data['summary']['revenue'][0]['revenue']),190)
        self.assertEqual(data['products'][0]['opens'],1);self.assertEqual(data['products'][0]['purchased'],1)
        with self.Adapter() as cur:
            cur.execute("SELECT count(*) n FROM wall_preview_events WHERE source='shopify'")
            self.assertEqual(cur.fetchone()['n'],1)
    def test_purchase_without_saved_preview_and_wrong_variant(self):
        self.track('Started')
        line={'id':1,'product_id':123,'variant_id':999,'price':'90','quantity':1,'properties':[{'name':'_wall_preview_client_id','value':self.data['client_preview_id']}]}
        order={'id':1234,'currency':'USD','total_price':'90','line_items':[line]}
        fixtures.store.correlate_order(order);self.assertEqual(analytics.report()['summary']['purchased'],0)
        line['variant_id']=456;fixtures.store.correlate_order(order)
        self.assertEqual(analytics.report()['summary']['purchased'],1)
    def test_no_fake_legacy_opens_or_unknown_revenue(self):
        row=self.create();data=analytics.report()
        self.assertEqual(data['summary']['opens'],0);self.assertIsNone(data['summary']['purchase_percent'])
        self.assertEqual(data['summary']['revenue'],[])
    def test_rls_and_public_grants(self):
        with self.Adapter() as cur:
            cur.execute("SELECT relrowsecurity AS enabled FROM pg_class WHERE oid='public.wall_preview_events'::regclass")
            self.assertTrue(cur.fetchone()['enabled'])
            cur.execute("SELECT has_table_privilege('anon','public.wall_preview_events','SELECT') AS allowed")
            self.assertFalse(cur.fetchone()['allowed'])

    def test_source_filter_resolves_open_before_photo_source_known(self):
        self.track('Started',capture_source='')
        self.track('PhotoReady',capture_source='upload')
        data=analytics.report({'capture_source':'upload'})
        self.assertEqual(data['summary']['opens'],1)
        self.assertEqual(data['summary']['photo_ready'],1)
