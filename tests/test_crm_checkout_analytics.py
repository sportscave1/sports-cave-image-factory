"""Private SQL + mocked Shopify: no live enrollment or mail transport."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch,Mock
import inspect,json,os,unittest,uuid
from crm_checkout_analytics import window,PERIODS,checkouts,report,details,disabled_reason,reconcile,LIST_SQL
from crm_logic import now,date
from crm_automation_analytics import flow_state
from tests.test_crm_automation_analytics import AnalyticsTests
from tests.test_crm import ADMIN

class ContractTests(unittest.TestCase):
    def test_utc_date_windows(self):
        at=now()
        for name,days in PERIODS.items():self.assertEqual(window(name,at),(at-timedelta(days=days) if days else None,at))

    def test_ui_no_pagination_confirmation_or_server_countdown(self):
        import crm_automation_analytics_ui as ui
        text=inspect.getsource(ui)
        for old in ('Next checkout page','Newest checkouts','st.checkbox',"run_every='1s'"):self.assertNotIn(old,text)
        self.assertNotIn('countdown_html',text)
        self.assertIn('crm_checkout_table',text)
        self.assertIn('patch_checkout',text)
        self.assertNotIn('shop.query',inspect.getsource(ui.content))
        self.assertNotIn('shop.query',inspect.getsource(checkouts))
        self.assertNotIn('LATERAL',LIST_SQL)

    def test_safe_errors_never_expose_provider_text(self):
        from crm_automation_analytics_ui import safe_add_error
        self.assertNotIn('private@example.test',safe_add_error(RuntimeError('private@example.test token=secret')))

    def test_selected_row_updates_only_table_cache(self):
        from crm_automation_analytics_ui import patch_checkout,state
        from tests.crm_db_fixture import connect
        from crm_automation_store import AutomationStore
        values={'automation_analytics_reads':{'campaign_home_cache':{},'campaign_home_resolved':{}}}
        store=AutomationStore(connect);key=(connect,('checkout-list','flow',None,now()));metrics=(connect,('analytics-report','flow'))
        values['automation_analytics_reads']['campaign_home_resolved'][key]=[{'checkout_key':'one'},{'checkout_key':'two'}]
        values['automation_analytics_reads']['campaign_home_cache'][metrics]=object()
        with patch('streamlit.session_state',values):patch_checkout(store,'flow',{'checkout_key':'one','flow_status':'ACTIVE'})
        self.assertEqual(values['automation_analytics_reads']['campaign_home_resolved'][key][0]['flow_status'],'ACTIVE')
        self.assertEqual(values['automation_analytics_reads']['campaign_home_resolved'][key][1],{'checkout_key':'two'})
        self.assertIn(metrics,values['automation_analytics_reads']['campaign_home_cache'])

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL required')
class LedgerTests(unittest.TestCase):
    setUp=AnalyticsTests.setUp
    prepared=AnalyticsTests.prepared
    published=AnalyticsTests.published
    event=AnalyticsTests.event
    add=AnalyticsTests.add

    def test_all_periods_return_all_rows_no_provider_or_n_plus_one(self):
        a,c=self.prepared();at=self.clock;created=[]
        for days in (1,10,40,100,400):
            key=uuid.uuid4().hex;created.append((key,days))
            self.store.q("INSERT INTO crm_shopify_checkouts(checkout_key,shop,source_event_id,created_at,activity_at,status) VALUES(%s,'fixture.myshopify.com','fixture',%s,%s,'OPEN')",(key,at-timedelta(days=days),at-timedelta(days=days)))
        self.store.q("UPDATE crm_shopify_checkouts SET analytics=analytics||'{\"shopify_abandoned\":true}'::jsonb WHERE source_event_id='fixture'")
        original=self.store.q
        for label,days in PERIODS.items():
            with patch.object(self.store,'q',wraps=original) as query:
                data=checkouts(self.store,a['id'],window(label,at));self.assertEqual(query.call_count,1)
            keys={r['checkout_key'] for r in data}
            for key,age in created:self.assertEqual(key in keys,days is None or age<=days)
        self.shop.query.assert_not_called();self.shop.checkout.assert_not_called()

    def test_private_matched_projection_no_recovery_token_or_address(self):
        a,c=self.prepared();details(self.store,c)
        data=checkouts(self.store,a['id'],window('All time',self.clock),self.key)[0]
        self.assertEqual(data['admin_checkout_id'],c['id']);self.assertEqual(data['analytics']['amount'],'199.50')
        self.assertNotIn(self.token,json.dumps(data['analytics']))
        wrong=deepcopy(c);wrong['customer']['id']='gid://shopify/Customer/wrong';wrong['customer']['email']='bad@example.test'
        with self.assertRaises(ValueError):details(self.store,wrong)
        self.assertNotEqual(checkouts(self.store,a['id'],window('All time',self.clock),self.key)[0]['analytics']['email'],'bad@example.test')

    def test_manual_historical_allowed_automatic_backfill_still_blocked(self):
        from crm_automation_runtime import reconcile as automatic
        a,c=self.prepared();created=date(a['activated_at'])-timedelta(days=4)
        c.update(createdAt=created.isoformat(),updatedAt=(self.clock-timedelta(hours=2)).isoformat())
        self.store.q('UPDATE crm_shopify_checkouts SET created_at=%s,activity_at=%s WHERE checkout_key=%s',(created,created,self.key))
        self.shop.checkout.return_value=c;self.shop.checkouts.return_value={'nodes':[c],'pageInfo':{'hasNextPage':False}}
        automatic(self.engine,a)
        self.assertFalse(self.store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],)))
        j=self.add(a,c);expected=deepcopy(a['steps']);expected[0].update(manual_checkout=True,delay_seconds=0)
        self.assertEqual(j['steps'],expected)
        with self.assertRaises(ValueError):self.add(a,c)
        self.provider.send.assert_not_called()

    def test_selection_reasons_and_immediate_flow_state(self):
        a,c=self.prepared();details(self.store,c)
        data=checkouts(self.store,a['id'],window('All time',self.clock),self.key)[0]
        self.assertIsNone(disabled_reason(data,a,self.clock))
        self.add(a,c)
        data=checkouts(self.store,a['id'],window('All time',self.clock),self.key)[0]
        self.assertEqual(disabled_reason(data,a,self.clock),'Already in flow')
        self.assertEqual(flow_state({'ledger':data},self.clock)[0],'In Flow — Email 1 pending')
        data['order_id']='gid://shopify/Order/1';data['status']='RECOVERED';self.assertEqual(disabled_reason(data,a,self.clock),'Recovered')
        data['order_id']=None;data['status']='OPEN';data['enrollment_id']=None
        self.assertEqual(disabled_reason(data,{**a,'status':'DRAFT'},self.clock),'Flow is not live')
        data['admin_checkout_id']=None;self.assertIn('identity',disabled_reason(data,a,self.clock))

    def test_bounded_refresh_does_not_enroll(self):
        a,c=self.prepared();self.shop.query.return_value={'abandonedCheckouts':{'nodes':[c],'pageInfo':{'hasNextPage':False}}}
        count,more=reconcile(self.shop,self.store,'All time');self.assertEqual((count,more),({'Updated':1,'Unchanged':0,'Failed':0},False))
        self.assertFalse(self.store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],)))
        self.provider.send.assert_not_called()

    def test_projection_preserves_fields_and_honors_redaction(self):
        a,c=self.prepared();details(self.store,c)
        minimal={**c,'customer':{'id':self.customer['id']},'totalPriceSet':{}}
        details(self.store,minimal)
        self.assertEqual(checkouts(self.store,a['id'],window('All time',self.clock),self.key)[0]['analytics']['amount'],'199.50')
        self.engine._process_event({'topic':'customers/redact','related_customer_id':self.customer['id'],'occurred_at':self.clock})
        details(self.store,c)
        self.assertEqual(self.store.q('SELECT analytics FROM crm_shopify_checkouts WHERE checkout_key=%s',(self.key,),True)['analytics'],{})

    def test_unsigned_suppressed_and_recovered_entry_blocked(self):
        a,c=self.prepared()
        self.store.q('DELETE FROM crm_shopify_checkouts WHERE checkout_key=%s',(self.key,))
        details(self.store,c) # Authenticated Shopify read can create a missing mirror safely.
        self.event('checkouts/create',{'token':self.token,'customer':{'id':self.customer['id']},'created_at':c['createdAt'],'updated_at':c['updatedAt']},date(c['createdAt']))
        self.customer['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
        with self.assertRaises(ValueError):self.add(a,c)
        self.customer['emailMarketingConsent']['marketingState']='SUBSCRIBED'
        from crm_logic import recipient_hash
        self.store.suppress(recipient_hash(self.customer['email']),self.customer['id'],'manual','admin')
        with self.assertRaises(ValueError):self.add(a,c)
        self.provider.send.assert_not_called()

    def test_cached_reopen_and_refresh_error_keep_last_good(self):
        from crm_automation_analytics_ui import read
        from time import sleep
        a,c=self.prepared();memory={};key=('checkout-list',str(a['id']),'Last 30 days');load=Mock(return_value=[{'checkout_key':self.key}])
        with patch('streamlit.session_state',memory):
            for _ in range(30):
                rows,phase=read(self.store,key,load)
                if phase=='READY':break
                sleep(.01)
            self.assertEqual(rows,[{'checkout_key':self.key}]);read(self.store,key,load);self.assertEqual(load.call_count,1)
            failed=Mock(side_effect=RuntimeError('private@example.test'))
            for _ in range(30):
                rows,phase=read(self.store,key,failed,ttl=0)
                if phase=='ERROR':break
                sleep(.01)
            self.assertEqual(rows,[{'checkout_key':self.key}])

    def test_one_report_query_matches_existing_totals_and_deduplicates_events(self):
        from crm_automation_analytics import performance,conversions,revenue
        a,c=self.prepared();j=self.add(a,c)
        from crm_logic import recipient_hash
        send=self.store.enqueue('analytics:'+str(uuid.uuid4()),self.customer['id'],recipient_hash(self.customer['email']),{'id':a['steps'][0]['template_id'],'version':a['steps'][0]['template_version']},enrollment_id=j['id'],step_index=0)
        self.store.q("UPDATE crm_marketing_sends SET status='ACCEPTED',first_submitted_at=%s WHERE id=%s",(self.clock,send['id']))
        for _ in range(3):self.store.q("INSERT INTO crm_delivery_events(event_id,provider_id,event_type,occurred_at,send_id) VALUES(%s,'fixture','email.opened',%s,%s)",(str(uuid.uuid4()),self.clock,send['id']))
        bounds=window('Last 30 days',self.clock+timedelta(seconds=1));original=self.store.q
        with patch.object(self.store,'q',wraps=original) as query:value=report(self.store,a['id'],bounds);self.assertEqual(query.call_count,1)
        self.assertEqual((value['sent'],value['opened']),(1,1));self.assertEqual(value['conversions'],conversions(self.store,a['id'],bounds))
        self.assertEqual(value['revenue'],revenue(self.store,bounds,a['id'])['revenue'])
        def normalize(records):return [(date(r['day']),*[int(r[k]) for k in ('sent','delivered','opened','clicked')]) for r in records]
        self.assertEqual(normalize(value['history']),normalize(performance(self.store,a['id'],bounds)))

    def test_migration_idempotent_rls_preserved(self):
        sql=Path('migrations/20261005064444_crm_checkout_analytics.sql').read_text()
        for _ in range(2):
            for statement in sql.split(';'):
                if statement.strip():self.store.q(statement)
        self.assertTrue(self.store.q("SELECT relrowsecurity FROM pg_class WHERE relname='crm_shopify_checkouts'",one=True)['relrowsecurity'])
        self.assertFalse(self.store.q("SELECT has_table_privilege('anon','crm_shopify_checkouts','SELECT') AS permitted",one=True)['permitted'])

del AnalyticsTests
if __name__=='__main__':unittest.main()
