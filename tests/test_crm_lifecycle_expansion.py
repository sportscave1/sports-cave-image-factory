"""Deterministic lifecycle tests; external services are never used."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json,os,unittest,uuid
from pathlib import Path
from unittest.mock import Mock,patch
from crm_lifecycle_definition import expanded_flow
from crm_lifecycle_policy import preview,order_from_ledger,latest_paid
from crm_automation_definition import validate,new_flow
from crm_logic import date

AT=datetime(2026,10,10,12,tzinfo=timezone.utc)
CUSTOMER={'id':'gid://shopify/Customer/999999','email':'fixture@example.test','firstName':'Fixture','lastName':'Collector',
 'createdAt':AT.isoformat(),'updatedAt':AT.isoformat(),'emailMarketingConsent':{'marketingState':'SUBSCRIBED','consentUpdatedAt':AT.isoformat()}}
def order(days=0,identity='gid://shopify/Order/99',**overrides):
    return dict(id=identity,createdAt=AT-timedelta(days=days),paid_at=AT-timedelta(days=days),fullyPaid=True,
                displayFinancialStatus='PAID',**overrides)

class PolicyTests(unittest.TestCase):
    def test_all_ten_drafts_render_through_existing_test_preview_without_network(self):
        from crm_flow_tests import prepare
        from tests.test_crm_send_flow import CFG
        count=0
        with patch('requests.sessions.Session.request',side_effect=AssertionError('External request forbidden')):
            for kind in ('welcome','post_purchase','win_back'):
                flow=expanded_flow(kind)
                # Exercise the optional draft too, only in this detached test copy.
                for step in flow['emails']:step['enabled']=True
                messages=prepare(flow,{**CFG,'test_unsubscribe_url':'https://example.test/crm/unsubscribe/test'})
                count+=len(messages)
                for _,_,message in messages:
                    self.assertIn('TEST sequence',message['html'])
                    self.assertIn('Sports Cave',message['text'])
        self.assertEqual(count,10)
    def test_recommendations_use_real_published_available_products_and_exclude_purchases(self):
        from crm_lifecycle_products import recommend,hydrate
        from crm_lifecycle_shopify import PRODUCT_AVAILABILITY
        from tests.test_crm_modular_catalogue import node
        doc=expanded_flow('win_back')['emails'][0]['document'];store=Mock();store.connect=None
        store.q.return_value=[{'shopify_product_id':str(i)} for i in (1,2,3)]
        shop=Mock()
        def query(q,v,*args):
            if q==PRODUCT_AVAILABILITY:return {'nodes':[dict(id=i,totalInventory=2 if i.endswith('/2') else 0,tracksInventory=True,createdAt=AT.isoformat()) for i in v['ids']]}
            return {'nodes':[node(int(i.rsplit('/',1)[-1])) for i in v['ids']]}
        shop.query.side_effect=query
        products=recommend(store,shop,doc,[{'products':[{'product':{'id':'gid://shopify/Product/1'},'title':'Basketball artwork'}]}],AT,new_since=AT-timedelta(days=100))
        self.assertEqual([p['id'] for p in products],['gid://shopify/Product/2'])
        self.assertIsNone(products[0]['edition'])
        rendered=hydrate(doc,products)
        self.assertTrue(rendered['middle_sections'][-1]['products'])
        self.assertFalse(rendered['middle_sections'][-1]['settings']['display']['price'])
        self.assertEqual(doc['middle_sections'][-1]['products'],[])
        with self.assertRaises(ValueError):recommend(store,shop,doc,[],AT,new_since=AT+timedelta(days=1))
    def test_ten_editable_drafts_and_optional_fourth(self):
        flows=[validate(expanded_flow(k),draft=True) for k in ('welcome','post_purchase','win_back')]
        self.assertEqual([len(f['emails']) for f in flows],[3,3,4])
        self.assertFalse(flows[2]['emails'][3]['enabled'])
        self.assertEqual(len({s['document']['content']['subject'] for f in flows for s in f['emails']}),10)
        self.assertTrue(all(s['document']['content_mode']=='HTML' for f in flows for s in f['emails']))
    def test_welcome_dates_and_purchase_exit(self):
        flow=expanded_flow('welcome');r=preview(flow,CUSTOMER,[],AT,subscribed_at=AT)
        self.assertEqual([s['due_at'] for s in r['stages']],[AT+timedelta(days=d) for d in (0,3,7)])
        self.assertEqual(preview(flow,CUSTOMER,[order()],AT,subscribed_at=AT)['reason'],'purchased')
    def test_pending_opt_in_unsubscribe_and_missing_consent(self):
        for state in ('PENDING','UNSUBSCRIBED','NOT_SUBSCRIBED',None):
            c=deepcopy(CUSTOMER);c['emailMarketingConsent']['marketingState']=state
            self.assertFalse(preview(expanded_flow('welcome'),c,[],AT,subscribed_at=AT)['eligible'])
    def test_paid_only_and_latest_order(self):
        flow=expanded_flow('post_purchase')
        for state in ('PENDING','PARTIALLY_PAID','AUTHORIZED','REFUNDED','VOIDED'):
            o=order();o['displayFinancialStatus']=state
            self.assertFalse(preview(flow,CUSTOMER,[o],AT)['eligible'])
        old=order(4);latest=order(1,'gid://shopify/Order/100')
        self.assertEqual(preview(flow,CUSTOMER,[old,latest],AT,order_id=old['id'])['reason'],'superseded_by_latest_order')
    def test_delivery_and_fallback_are_distinct_and_configurable(self):
        flow=expanded_flow('post_purchase');o=order(2,fulfilled_at=AT-timedelta(days=1))
        r=preview(flow,CUSTOMER,[o],AT)
        self.assertEqual(r['stages'][1]['due_at'],AT+timedelta(days=13))
        self.assertEqual(r['stages'][1]['anchor'],'verified_fulfilment_fallback')
        o['delivered_at']=AT
        self.assertEqual(preview(flow,CUSTOMER,[o],AT)['stages'][1]['due_at'],AT+timedelta(days=7))
        del o['delivered_at'];flow['fulfilment_fallback_days']=None
        self.assertEqual(preview(flow,CUSTOMER,[o],AT)['stages'][1]['state'],'HELD')
    def test_unfulfilled_cross_sell_and_issues_hold(self):
        flow=expanded_flow('post_purchase')
        r=preview(flow,CUSTOMER,[order(50)],AT)
        self.assertEqual([s['state'] for s in r['stages']],['DRAFT','HELD','HELD'])
        for issue in ('cancelledAt','fraudulent','disputed'):
            self.assertFalse(preview(flow,CUSTOMER,[order(**{issue:True})],AT)['eligible'])
    def test_winback_latest_paid_clock_and_historical_no_replay(self):
        flow=expanded_flow('win_back');o=order(160)
        r=preview(flow,CUSTOMER,[o],AT)
        self.assertEqual([s['due_at'] for s in r['stages']],[o['paid_at']+timedelta(days=d) for d in (90,105,120,150)])
        self.assertEqual([s['state'] for s in r['stages']],['DRAFT','DRAFT','DRAFT','DISABLED'])
        self.assertFalse(preview(flow,CUSTOMER,[o,order(1,'new')],AT)['eligible'])
        self.assertTrue(preview(flow,CUSTOMER,[order(90)],AT)['eligible'])
        self.assertFalse(preview(flow,CUSTOMER,[order(89)],AT)['eligible'])
    def test_ledger_never_infers_delivery_or_payment_timestamp(self):
        r=order_from_ledger(dict(shopify_order_id='99',financial_status='PAID',fulfillment_status='FULFILLED',created_at=AT))
        self.assertIsNone(r['paid_at']);self.assertIsNone(r['delivered_at']);self.assertIsNone(r['fulfilled_at'])
    def test_partial_delivery_does_not_start_delivery_clock(self):
        from crm_lifecycle_shopify import operational_facts
        n=dict(risk={'recommendation':'ACCEPT'},disputes=[],fulfillments=[{'status':'SUCCESS','createdAt':AT.isoformat(),'deliveredAt':AT.isoformat()}, {'status':'SUCCESS','createdAt':AT.isoformat(),'deliveredAt':None}])
        self.assertIsNone(operational_facts(n,True)['delivered_at'])
        self.assertEqual(operational_facts(n,True)['fulfilled_at'],AT)
        self.assertIsNone(operational_facts(n,False)['fulfilled_at'])
        legacy=order_from_ledger(dict(shopify_order_id='99',financial_status='PAID',fulfillment_status='FULFILLED',created_at=AT,raw_json=n))
        self.assertIsNone(legacy['delivered_at'])
    def test_editing_cross_sell_delay_does_not_remove_fulfilment_guard(self):
        flow=expanded_flow('post_purchase');flow['emails'][2]['delay_seconds']=0
        self.assertEqual(preview(flow,CUSTOMER,[order(50)],AT)['stages'][2]['state'],'HELD')
    def test_publication_and_entry_lock_even_with_active_row(self):
        from crm_automation_publication import preflight
        from crm_automation_runtime import enter
        from crm_automation_definition import FORMAT
        a=dict(status='ACTIVE',config=dict(format=FORMAT,revision=1,published_version=0,draft=expanded_flow('welcome')))
        self.assertEqual(preflight(a,1)['trigger'],'welcome')
        engine=Mock()
        self.assertIsNone(enter(engine,a,'id','id','id',AT));engine.shop.customer.assert_not_called()
    def test_abandoned_contract_is_unmodified(self):
        f=new_flow('abandoned')
        self.assertNotIn('lifecycle_version',f);self.assertNotIn('anchor',f['emails'][0])

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.crm_db_fixture import connect
        cls.connect=staticmethod(connect)
        # Use the actual operational ledger DDL, not a guessed schema.
        source=Path('migrations/20260625_stage1_supabase_operational_ledger.sql').read_text()
        table=source[source.index('CREATE TABLE IF NOT EXISTS shopify_orders ('):source.index('CREATE TABLE IF NOT EXISTS shopify_order_lines (')]
        with connect() as c:
            c.execute(table)
            for _ in range(2):
                for statement in Path('migrations/20261010112655_crm_lifecycle_draft_expansion.sql').read_text().split(';'):
                    if statement.strip():c.execute(statement)
    def setUp(self):
        from crm_automation_store import AutomationStore
        from tests.test_crm import ADMIN
        from tests.test_crm_send_flow import CFG
        from crm_lifecycle_audience import cache_customer
        self.store=AutomationStore(self.connect);self.user=ADMIN
        self.patch=patch.object(self.store,'render_settings',return_value=CFG);self.patch.start();self.addCleanup(self.patch.stop)
        self.customer=deepcopy(CUSTOMER);self.customer['id']='gid://shopify/Customer/'+str(uuid.uuid4().int%10**12)
        cache_customer(self.store,self.customer,AT)
        self.flow=self.store.create(ADMIN,'welcome',lifecycle=True)
    def test_real_sql_listing_filter_sort_pagination_and_draft_roundtrip(self):
        from crm_lifecycle_audience import listing
        for sort in ('Newest','Oldest','Longest inactivity','Last purchase','Customer value','Sequence stage'):
            rows=listing(self.store,self.flow,search=self.customer['id'],sort=sort,at=AT)
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['customer_id'],self.customer['id'])
        self.assertEqual(listing(self.store,self.flow,search=self.customer['id'],page=1),[])
        f=deepcopy(self.flow['config']['draft']);f['emails'][0]['document']['content']['subject']='Saved lifecycle draft'
        saved=self.store.save_flow(self.user,self.flow['id'],self.flow['name'],f,1)
        self.assertEqual(saved['status'],'DRAFT');self.assertEqual(saved['config']['revision'],2)
        self.assertEqual(self.store.flow(self.flow['id'])['config']['draft'],f)
    def test_stage_idempotent_and_no_delivery_or_enrollment(self):
        from crm_lifecycle_audience import stage
        for _ in range(2):stage(self.store,self.user,self.flow,self.customer['id'])
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_lifecycle_staged WHERE automation_id=%s',(self.flow['id'],),True)['n'],1)
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(self.flow['id'],),True)['n'],0)
        with self.assertRaisesRegex(ValueError,'not ready'):self.store.request_publish(self.user,self.flow['id'],1)
    def test_upgrade_preserves_identity_original_revision_content_and_repeat(self):
        old=self.store.create(self.user,'post_purchase')
        upgraded=self.store.prepare_lifecycle(self.user,old['id'])
        self.assertEqual(upgraded['id'],old['id'])
        self.assertEqual(upgraded['config']['lifecycle_previous']['config'],old['config'])
        self.assertEqual(upgraded['config']['lifecycle_previous']['steps'],old['steps'])
        self.assertEqual(upgraded['config']['lifecycle_previous']['emails'],old['config']['draft']['emails'])
        self.assertEqual(upgraded['config']['revision'],2)
        self.assertEqual(self.store.prepare_lifecycle(self.user,old['id'])['config'],upgraded['config'])
    def test_out_of_order_sync_does_not_restore_old_consent(self):
        from crm_lifecycle_audience import cache_customer
        newer=deepcopy(self.customer);newer['updatedAt']=(AT+timedelta(days=1)).isoformat();newer['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
        cache_customer(self.store,newer,AT);cache_customer(self.store,self.customer,AT)
        self.assertEqual(self.store.q('SELECT consent FROM crm_lifecycle_customers WHERE customer_id=%s',(self.customer['id'],),True)['consent'],'UNSUBSCRIBED')
    def test_draft_lock_cannot_be_removed_and_revisions_retained(self):
        f=deepcopy(self.flow['config']['draft']);del f['lifecycle_version']
        for s in f['emails']:s.pop('anchor',None)
        with self.assertRaises(ValueError):self.store.save_flow(self.user,self.flow['id'],self.flow['name'],f,1)
        f=deepcopy(self.flow['config']['draft']);f['emails'][0]['name']='Revised internal name'
        self.store.save_flow(self.user,self.flow['id'],self.flow['name'],f,1)
        original=self.store.q('SELECT definition FROM crm_lifecycle_revisions WHERE automation_id=%s AND revision=1',(self.flow['id'],),True)
        self.assertEqual(original['definition'],self.flow['config']['draft'])
    def test_post_purchase_fulfilment_safety_cannot_be_removed(self):
        a=self.store.create(self.user,'post_purchase',lifecycle=True)
        flow=deepcopy(a['config']['draft']);flow['emails'][2]['requires_fulfilment']=False
        with self.assertRaisesRegex(ValueError,'Successful fulfilment'):
            self.store.save_flow(self.user,a['id'],a['name'],flow,1)
    def test_post_purchase_winback_use_local_history_with_no_shopify_reads(self):
        from crm_lifecycle_audience import listing
        self.store.q("UPDATE crm_lifecycle_customers SET profile=profile||%s::jsonb WHERE customer_id=%s",(json.dumps({'amountSpent':{'amount':'110.50','currencyCode':'AUD'}}),self.customer['id']))
        oid='gid://shopify/Order/'+str(uuid.uuid4().int%10**12)
        self.store.q("INSERT INTO shopify_orders(shopify_order_id,shopify_customer_id,order_name,financial_status,created_at,total_price,currency) VALUES(%s,%s,'#Fixture','PAID',%s,'125','AUD')",(oid,self.customer['id'],AT-timedelta(days=100)))
        for kind in ('post_purchase','win_back'):
            a=self.store.create(self.user,kind,lifecycle=True)
            rows=listing(self.store,a,search=self.customer['id'],at=AT)
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['order_count'],1)
            self.assertEqual(float(rows[0]['lifetime_value']),110.50)
        self.store.q("UPDATE shopify_orders SET cancelled_at=%s WHERE shopify_order_id=%s",(AT,oid))
        self.assertEqual(listing(self.store,a,search=self.customer['id'],at=AT),[])
    def test_public_data_roles_have_no_access(self):
        for role in ('anon','authenticated'):
            for table in ('crm_lifecycle_customers','crm_lifecycle_staged','crm_lifecycle_revisions'):
                row=self.store.q('SELECT has_table_privilege(%s,%s,%s) AS allowed',(role,table,'SELECT'),True)
                self.assertFalse(row['allowed'])

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class RuntimeTests(unittest.TestCase):
    def setUp(self):
        from tests.test_crm_native_automations import NativeAutomationTests
        NativeAutomationTests.setUp(self)
        self.shop.orders.return_value={'nodes':[],'pageInfo':{'hasNextPage':False}}
        self.shop.query.side_effect=lambda query,variables,*args: {'nodes':[dict(id=i,risk={'recommendation':'ACCEPT'},disputes=[],returnStatus='NO_RETURN',fulfillments=[]) for i in variables.get('ids',[])]}
        self.store.set_state('shopify_automation_capabilities',{'scopes':['read_customers','read_orders','read_all_orders','read_products'],'checked_at':self.clock.isoformat(),'triggers':{k:'AVAILABLE' for k in ('welcome','post_purchase','win_back','abandoned','fulfilled')},'webhooks':{'ORDERS_PAID':True,'ORDERS_FULFILLED':True,'CUSTOMERS_EMAIL_MARKETING_CONSENT_UPDATE':True}})
    def test_incomplete_shopify_history_access_fails_closed(self):
        from crm_lifecycle_runtime import verified_plan
        self.store.set_state('shopify_automation_capabilities',{'scopes':['read_customers','read_orders']})
        with self.assertRaisesRegex(ValueError,'read_all_orders'):
            verified_plan(self.engine,{'trigger_type':'welcome'},self.customer)
        self.shop.orders.assert_not_called()
    def publish(self,kind):
        from tests.test_crm_simple_editor import document
        from tests.test_crm_send_flow import LIVE
        a=self.store.create({'role':'admin','id':'test'},kind,lifecycle=True)
        self.created.append(str(a['id']))
        flow=deepcopy(a['config']['draft'])
        for step in flow['emails']:
            step['document']=document();step['document']['smart_hours']=1
        a=self.store.save_flow({'role':'admin','id':'test'},a['id'],a['name'],flow,1)
        return self.store.publish({'role':'admin','id':'test'},a['id'],a['config']['revision'],env=LIVE)
    def test_welcome_once_and_pause_prevents_delivery(self):
        from crm_lifecycle_runtime import enter,advance
        from crm_logic import now
        a=self.publish('welcome');self.clock=now()+timedelta(seconds=1)
        j=enter(self.engine,a,self.customer['id'],self.customer['id'],'subscribed',self.clock)
        self.assertIsNotNone(j)
        self.assertIsNone(enter(self.engine,a,self.customer['id'],self.customer['id'],'duplicate',self.clock+timedelta(seconds=1)))
        self.store.lifecycle({'role':'admin','id':'test'},a['id'],'pause')
        advance(self.engine,j)
        self.assertFalse(self.store.q('SELECT 1 FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],)))
        self.provider.send.assert_not_called()
    def test_historical_trigger_events_cannot_enroll_after_publication(self):
        from crm_automation_runtime import process_event
        for kind,topic in (('welcome','customers_email_marketing_consent/update'),('post_purchase','orders/paid')):
            a=self.publish(kind)
            old=date(a['activated_at'])-timedelta(seconds=1)
            self.shop.customer.reset_mock();self.shop.order.reset_mock()
            process_event(self.engine,dict(topic=topic,occurred_at=old,object_id='gid://shopify/Order/999',related_customer_id=self.customer['id'],normalized={}),[a])
            self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)['n'],0)
            self.shop.customer.assert_not_called();self.shop.order.assert_not_called()
    def test_winback_reconciliation_uses_published_policy_and_skips_historical_thresholds(self):
        from crm_lifecycle_runtime import reconcile
        a=self.publish('win_back');self.clock=date(a['activated_at'])+timedelta(seconds=1)
        draft=deepcopy(a['config']['draft']);draft['inactive_days']=365
        a=self.store.save_flow({'role':'admin','id':'test'},a['id'],a['name'],draft,a['config']['revision'])
        historical={'customer_id':self.customer['id'],'last_paid_at':self.clock-timedelta(days=180)}
        with patch('crm_lifecycle_audience.listing',return_value=[historical]) as listing,patch('crm_lifecycle_runtime.enter') as enter:
            reconcile(self.engine,a)
        self.assertEqual(listing.call_args.args[1]['config']['draft']['inactive_days'],90)
        enter.assert_not_called();self.provider.send.assert_not_called()
    def test_welcome_purchase_exits_and_paid_order_supersedes_previous(self):
        from crm_lifecycle_runtime import enter,paid_exit
        from crm_logic import now
        welcome=self.publish('welcome');self.clock=now()+timedelta(seconds=1)
        j=enter(self.engine,welcome,self.customer['id'],self.customer['id'],'subscription',self.clock)
        paid_exit(self.engine,self.customer,self.clock+timedelta(seconds=1))
        self.assertEqual(self.store.q('SELECT stop_reason FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)['stop_reason'],'paid_order')
        a=self.publish('post_purchase');self.clock=now()+timedelta(seconds=2)
        first=order(identity='gid://shopify/Order/701');first.update(createdAt=self.clock.isoformat(),paid_at=None,customer={'id':self.customer['id']},name='#701',displayFulfillmentStatus='UNFULFILLED')
        self.shop.orders.return_value={'nodes':[first],'pageInfo':{'hasNextPage':False}}
        old=enter(self.engine,a,self.customer['id'],first['id'],first['id'],self.clock)
        self.assertIsNotNone(old)
        second={**first,'id':'gid://shopify/Order/702','createdAt':(self.clock+timedelta(days=1)).isoformat()}
        self.clock+=timedelta(days=1)
        self.shop.orders.return_value['nodes']=[second,first]
        new=enter(self.engine,a,self.customer['id'],second['id'],second['id'],self.clock)
        self.assertIsNotNone(new)
        self.assertEqual(self.store.q('SELECT stop_reason FROM crm_automation_enrollments WHERE id=%s',(old['id'],),True)['stop_reason'],'superseded_by_latest_order')
    def test_absolute_deadline_and_restart_idempotency(self):
        from crm_lifecycle_runtime import enter,advance
        from crm_logic import now
        a=self.publish('welcome');self.clock=now()+timedelta(seconds=1)
        j=enter(self.engine,a,self.customer['id'],self.customer['id'],'subscription',self.clock)
        advance(self.engine,j);advance(self.engine,j)
        receipts=self.store.q('SELECT * FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],))
        self.assertEqual(len(receipts),1)
        # Mark a fixture receipt accepted; no provider invocation is needed for scheduling.
        self.store.q("UPDATE crm_marketing_sends SET status='ACCEPTED',first_submitted_at=%s,updated_at=%s WHERE id=%s",(self.clock+timedelta(days=1),self.clock+timedelta(days=1),receipts[0]['id']))
        self.clock+=timedelta(days=1)
        advance(self.engine,j)
        saved=self.store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)
        self.assertEqual(date(saved['next_due_at']),date(j['trigger_at'])+timedelta(days=3))
        self.provider.send.assert_not_called()
    def test_winback_new_purchase_resets_cycle_and_duplicate_workers_deduplicate(self):
        from crm_lifecycle_runtime import enter,validate_send
        from crm_logic import now
        from concurrent.futures import ThreadPoolExecutor
        a=self.publish('win_back');self.clock=now()+timedelta(seconds=1)
        old=order(identity='gid://shopify/Order/901');old.update(createdAt=self.clock-timedelta(days=90),paid_at=None,customer={'id':self.customer['id']})
        self.shop.orders.return_value={'nodes':[old],'pageInfo':{'hasNextPage':False}}
        with ThreadPoolExecutor(max_workers=2) as pool:
            entries=list(pool.map(lambda _:enter(self.engine,a,self.customer['id'],old['id'],'same-cycle',self.clock),range(2)))
        self.assertEqual(sum(e is not None for e in entries),1)
        j=next(e for e in entries if e)
        newer={**old,'id':'gid://shopify/Order/902','createdAt':self.clock}
        self.shop.orders.return_value['nodes']=[newer,old]
        self.assertEqual(validate_send(self.engine,a,j,self.customer)[1],'not_yet_inactive')
    def test_submission_frequency_cap_does_not_apply_to_checkout(self):
        from crm_lifecycle_runtime import enter,advance,reserve
        from crm_logic import now
        a=self.publish('welcome');self.clock=now()+timedelta(seconds=1)
        j=enter(self.engine,a,self.customer['id'],self.customer['id'],'subscription',self.clock)
        advance(self.engine,j)
        receipt=self.store.q('SELECT * FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],),True)
        self.store.q("UPDATE crm_marketing_sends SET status='ACCEPTED',first_submitted_at=now() WHERE id=%s",(receipt['id'],))
        row={**receipt,'id':str(uuid.uuid4()),'lease_token':str(uuid.uuid4())}
        with self.store.db() as conn:self.assertFalse(reserve(conn,a,j,row,receipt['recipient_hash']))
        self.provider.send.assert_not_called()

if __name__=='__main__':unittest.main()
