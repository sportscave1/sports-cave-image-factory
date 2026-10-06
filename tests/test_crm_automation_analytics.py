"""Disposable Postgres and fake Shopify only; no production sends or writes."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from crm_logic import now,date,recipient_hash
from crm_automation_analytics import summary,activity,performance,revenue,conversions,checkout_page,flow_state,add_to_flow
from crm_automation_home_data import rows
from tests.test_crm import ADMIN,WORKER
from tests import test_crm_shopify_automation_triggers as trigger_fixture


class PresentationTests(unittest.TestCase):
    def test_multi_step_countdown_and_terminal_states(self):
        at=now();c={'ledger':{'flow_status':'ACTIVE','current_step':1,'next_due_at':(at+timedelta(hours=23,minutes=14,seconds=9)).isoformat()}}
        self.assertEqual(flow_state(c,at),('In Flow — Email 2 pending','Sends in 23:14:09'))
        c['ledger']['next_due_at']=(at-timedelta(seconds=1)).isoformat()
        self.assertEqual(flow_state(c,at)[1],'Due · awaiting worker')
        c['ledger']['automation_status']='PAUSED'
        self.assertEqual(flow_state(c,at),('Paused','Future sends held'))
        c['ledger']['flow_status']='COMPLETED'
        self.assertEqual(flow_state(c,at)[0],'Flow complete')
        c['completedAt']=at.isoformat()
        self.assertEqual(flow_state(c,at),('Recovered','Future sends suppressed'))

    def test_accepted_receipt_next_countdown_matches_worker_clock(self):
        at=now();c={'ledger':{'flow_status':'ACTIVE','current_step':0,'next_due_at':at.isoformat(),
           'steps':[{'delay_seconds':0},{'delay_seconds':86400}],
           'sends':[{'step':0,'status':'ACCEPTED','updated_at':at.isoformat()}]}}
        self.assertEqual(flow_state(c,at),('In Flow — Email 2 pending','Sends in 24:00:00'))
        c['ledger']['current_step']=1
        c['ledger']['sends'].append({'step':1,'status':'ACCEPTED','updated_at':at.isoformat()})
        self.assertEqual(flow_state(c,at),('All emails sent','Awaiting flow completion'))

    def test_currency_escape_unavailable_and_real_trends(self):
        from crm_automation_home import kpi_html,money
        self.assertEqual(money({}),'—')
        html=kpi_html({'sent_emails':100,'delivery_rate':99,'revenue':{'AUD':200},'previous':{'sent_emails':50,'delivery_rate':98,'revenue':{'AUD':100}}})
        self.assertIn('+100.0%',html);self.assertIn('+1.0 pp',html)
        self.assertEqual(html.count('class="sc-auto-kpi"'),6)
        self.assertEqual(money({'NZD':10,'AUD':20}),'AUD 20.00 · NZD 10.00')

    def test_summary_rejects_partial_payload(self):
        from crm_automation_home import payload
        for key,value in (('counts',{}),('delivery',{'sent_emails':0}),('table',None)):
            with self.assertRaises(ValueError):payload((key,None),lambda:value)
        with self.assertRaises(ValueError):payload(('counts',None),lambda:dict.fromkeys(('active','all_count','drafts','paused','archived')))
        self.assertEqual(payload(('table',None),lambda:[]),[[]])

    def test_diagnostic_is_backend_only(self):
        import inspect
        from crm_automation_ui import chooser,detail
        self.assertNotIn('crm_automation_diagnostic_ui',inspect.getsource(detail))
        self.assertNotIn('capabilities(',inspect.getsource(chooser))


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable Postgres required')
class AnalyticsTests(unittest.TestCase):
    setUp=trigger_fixture.TriggerTests.setUp
    published=trigger_fixture.TriggerTests.published
    event=trigger_fixture.TriggerTests.event

    def test_reporting_indexes_are_additive_idempotent_and_rls_retained(self):
        sql=Path('migrations/20261005145500_crm_automation_reporting_indexes.sql').read_text()
        for _ in range(2):
            for statement in sql.split(';'):
                if statement.strip():self.store.q(statement)
        indexes=self.store.q("SELECT indexname FROM pg_indexes WHERE indexname=ANY(%s)",(['crm_auto_sent_time','crm_auto_entry_time','crm_auto_terminal_time','crm_auto_delivery_time','crm_auto_checkout_flow','crm_attribution_auto_time'],))
        self.assertEqual(len(indexes),6)
        self.assertTrue(all(r['relrowsecurity'] for r in self.store.q("SELECT relrowsecurity FROM pg_class WHERE relname=ANY(%s)",(['crm_automation_enrollments','crm_marketing_sends','crm_delivery_events','crm_order_attribution'],))))

    def test_duplicate_native_and_legacy_are_unpublished_and_preserve_original(self):
        a=self.published();copy=self.store.duplicate(ADMIN,a['id'])
        self.created.append(str(copy['id']))
        self.assertEqual(copy['status'],'DRAFT');self.assertEqual(copy['steps'],[])
        self.assertNotEqual(copy['config']['draft']['emails'][0]['step_id'],a['config']['draft']['emails'][0]['step_id'])
        legacy=self.store.q("INSERT INTO crm_automations(automation_key,name,trigger_type,status,steps,config) VALUES(%s,'Legacy fixture','winback','PAUSED','[]','{}') RETURNING *",('legacy:'+str(uuid.uuid4()),),True)
        copy=self.store.duplicate(ADMIN,legacy['id']);self.created.extend([str(legacy['id']),str(copy['id'])])
        self.assertEqual(copy['status'],'DRAFT');self.assertEqual(self.store.get('automations',legacy['id'])['status'],'PAUSED')
        self.provider.send.assert_not_called()

    def prepared(self):
        a=self.published('abandoned',delays=(0,86400))
        created=date(a['activated_at'])+timedelta(seconds=1)
        self.clock=created+timedelta(hours=2)
        self.event('checkouts/create',{'token':self.token,'customer':{'id':self.customer['id']},'created_at':created.isoformat()},created)
        c={'id':'gid://shopify/AbandonedCheckout/123','createdAt':created.isoformat(),'updatedAt':created.isoformat(),
           'completedAt':None,'customer':deepcopy(self.customer),'abandonedCheckoutUrl':'https://fixture.myshopify.com/checkouts/'+self.token+'/recover',
           'totalPriceSet':{'shopMoney':{'amount':'199.50','currencyCode':'AUD'}},'shippingAddress':{'countryCodeV2':'AU'}}
        self.shop.checkout.return_value=c
        return a,c

    def add(self,a,c):
        with patch('crm_automation_analytics.now',return_value=self.clock):
            return add_to_flow(self.shop,self.store,ADMIN,a['id'],c['id'])

    def test_manual_enrollment_idempotent_immutable_no_inline_send(self):
        a,c=self.prepared();j=self.add(a,c)
        self.assertEqual(j['checkout_key'],self.key);self.assertEqual(j['steps'],a['steps'])
        self.assertEqual(date(j['next_due_at']),self.clock)
        with self.assertRaises(ValueError):self.add(a,c)
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)['n'],1)
        self.provider.send.assert_not_called()

    def test_manual_guards_consent_recovery_identity_unsigned_historical_and_delay(self):
        a,c=self.prepared()
        original=deepcopy(c)
        for mutation in ({'completedAt':now().isoformat()},{'id':'wrong'},{'updatedAt':self.clock.isoformat()}):
            self.shop.checkout.return_value={**original,**mutation}
            with self.assertRaises(ValueError):self.add(a,c)
        self.shop.checkout.return_value=original
        self.customer['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
        with self.assertRaises(ValueError):self.add(a,c)
        self.customer['emailMarketingConsent']['marketingState']='SUBSCRIBED'
        with self.assertRaises(PermissionError):add_to_flow(self.shop,self.store,WORKER,a['id'],c['id'])
        self.store.q('UPDATE crm_shopify_checkouts SET activity_at=%s WHERE checkout_key=%s',(self.clock,self.key))
        with self.assertRaises(ValueError):self.add(a,c)
        self.store.q("UPDATE crm_shopify_checkouts SET status='RECOVERED' WHERE checkout_key=%s",(self.key,))
        with self.assertRaises(ValueError):self.add(a,c)
        self.assertFalse(self.store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],)))
        self.provider.send.assert_not_called()

    def test_draft_paused_and_missing_readiness_block_manual_entry(self):
        a,c=self.prepared();self.store.lifecycle(ADMIN,a['id'],'pause')
        with self.assertRaises(ValueError):self.add(a,c)
        self.store.set_state('shopify_automation_capabilities',{})
        self.store.q("UPDATE crm_automations SET status='ACTIVE' WHERE id=%s",(a['id'],))
        with self.assertRaises(ValueError):self.add(a,c)
        self.provider.send.assert_not_called()

    def test_concurrent_checkout_update_rechecked_under_enrollment_lock(self):
        from crm_automation_runtime import enter
        a,c=self.prepared()
        self.store.q('UPDATE crm_shopify_checkouts SET activity_at=%s WHERE checkout_key=%s',(self.clock,self.key))
        self.assertIsNone(enter(self.engine,a,self.customer['id'],c['id'],'checkout:'+self.key,self.clock,checkout_key=self.key,manual_checkout=True))
        self.provider.send.assert_not_called()

    def test_reporting_deduplication_period_currency_activity_and_checkout_overlay(self):
        a,c=self.prepared();j=self.add(a,c)
        send=self.store.enqueue('automation:'+str(j['id'])+':0',self.customer['id'],recipient_hash(self.customer['email']),
          {'id':a['steps'][0]['template_id'],'version':a['steps'][0]['template_version']},enrollment_id=j['id'],step_index=0)
        sent_at=now()
        self.store.q("UPDATE crm_marketing_sends SET status='ACCEPTED',first_submitted_at=%s WHERE id=%s",(sent_at,send['id']))
        for kind in ('email.delivered','email.opened','email.clicked','email.bounced'):
            for _ in range(2):self.store.q('INSERT INTO crm_delivery_events(event_id,provider_id,event_type,occurred_at,send_id) VALUES(%s,%s,%s,%s,%s)',(str(uuid.uuid4()),str(uuid.uuid4()),kind,sent_at,send['id']))
        for currency,amount,eligible,age in (('AUD',10,True,0),('NZD',20,True,0),('AUD',500,False,0),('AUD',100,True,40)):
            self.store.q('''INSERT INTO crm_order_attribution(shopify_order_id,customer_id,order_created_at,visit_at,amount,currency,eligible,evidence)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)''',('gid://shopify/Order/'+str(uuid.uuid4()),self.customer['id'],sent_at-timedelta(days=age),sent_at,amount,currency,eligible,json.dumps({'automation_id':str(a['id'])})))
        window=(sent_at-timedelta(days=30),sent_at+timedelta(seconds=1))
        history=performance(self.store,a['id'],window)
        self.assertEqual([history[0][k] for k in ('sent','delivered','opened','clicked')],[1]*4)
        self.assertEqual(revenue(self.store,window,a['id'])['revenue'],{'AUD':10,'NZD':20})
        self.assertEqual(conversions(self.store,a['id'],window),2)
        record=rows(self.store,search=a['name'])[0]
        self.assertEqual([record[k] for k in ('entered','sent','delivered','opened','clicked','orders')],[1,1,1,1,1,3])
        self.assertEqual(record['revenue'],{'AUD':110,'NZD':20})
        self.assertEqual(record['bounced'],1) # duplicate provider events count once per accepted send
        self.assertIn('Email sent',[e['event'] for e in activity(self.store,a['id'])])
        self.assertIn('Added to flow',[e['event'] for e in activity(self.store,a['id'])])
        self.shop.query.return_value={'abandonedCheckouts':{'nodes':[c],'pageInfo':{'hasNextPage':False}}}
        page=checkout_page(self.shop,self.store,a['id'])
        self.assertEqual(str(page['nodes'][0]['ledger']['enrollment_id']),str(j['id']))
        self.assertEqual(page['nodes'][0]['ledger']['sends'][0]['status'],'ACCEPTED')
        self.store.q("UPDATE crm_shopify_checkouts SET status='RECOVERED' WHERE checkout_key=%s",(self.key,))
        self.assertEqual(flow_state(checkout_page(self.shop,self.store,a['id'])['nodes'][0])[0],'Recovered')
        data=summary(self.store,window)
        self.assertIn('previous',data);self.assertGreater(data['sent_emails'],0)
        self.provider.send.assert_not_called()


if __name__=='__main__':unittest.main()
