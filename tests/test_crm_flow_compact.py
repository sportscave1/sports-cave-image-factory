"""Flow-only projections; no provider calls or production database."""
from datetime import timedelta
import json
import os
import unittest
import uuid
from unittest.mock import patch
from crm_checkout_analytics import report,checkouts,window
from crm_automation_home_data import step_metrics
from crm_logic import now
from tests import test_crm_native_automations as native


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class CompactFlowTests(unittest.TestCase):
    setUp=native.NativeAutomationTests.setUp
    published=native.NativeAutomationTests.published

    def test_orders_are_unique_attributed_purchases_and_history_is_preserved(self):
        row=self.published(delays=(0,86400))
        first,second=[s['step_id'] for s in row['steps']]
        ids=[]
        for flow,step,eligible in [(str(row['id']),first,True),(str(row['id']),second,True),
                                    (str(row['id']),second,False),(str(uuid.uuid4()),first,True)]:
            identity='gid://shopify/Order/'+uuid.uuid4().hex;ids.append(identity)
            args=(identity,json.dumps({'automation_id':flow,'step_id':step}),eligible)
            for _ in range(2):
                self.store.q('''INSERT INTO crm_order_attribution(shopify_order_id,evidence,eligible,order_created_at,currency,amount)
                    VALUES(%s,%s::jsonb,%s,now(),'AUD',50) ON CONFLICT(shopify_order_id) DO NOTHING''',args)
        bounds=window('All time');normal=report(self.store,row['id'],bounds)
        with patch.object(self.store,'q',wraps=self.store.q) as query:
            compact=report(self.store,row['id'],bounds,include_history=False)
        self.assertNotIn('daily AS',query.call_args.args[0])
        self.assertNotIn('jsonb_agg(d ORDER',query.call_args.args[0])
        self.assertEqual(compact['orders'],2)
        self.assertEqual(compact['conversions'],normal['conversions'])
        self.assertEqual(compact['revenue'],normal['revenue'])
        self.assertEqual(compact['revenue'],{'AUD':100})
        steps={r['step_id']:r for r in step_metrics(self.store,row['id'],bounds)}
        self.assertEqual((steps[first]['orders'],steps[second]['orders']),(1,1))
        self.assertEqual(report(self.store,row['id'],(now()+timedelta(days=1),now()+timedelta(days=2)),include_history=False)['orders'],0)
        self.assertEqual(len(self.store.q('SELECT shopify_order_id FROM crm_order_attribution WHERE shopify_order_id=ANY(%s)',(ids,))),4)
        self.provider.send.assert_not_called()

    def test_keyset_checkout_pages_filter_before_expensive_joins(self):
        row=self.published(delays=(0,))
        prefix='page-'+uuid.uuid4().hex
        self.store.q('''INSERT INTO crm_shopify_checkouts(checkout_key,shop,customer_id,source_event_id,created_at,activity_at,status,analytics)
          SELECT %s||i,'fixture','c-'||i,'page-fixture',now()-i*interval '1 minute',now(),'ABANDONED',
          jsonb_build_object('shopify_abandoned',true,'name','Page Customer '||i,'email','page'||i||'@example.test')
          FROM generate_series(1,65) i''',(prefix,))
        bounds=window('All time')
        with patch.object(self.store,'q',wraps=self.store.q) as query:
            first=checkouts(self.store,row['id'],bounds,page_size=51,search=prefix)
        self.assertLess(query.call_args.args[0].index('LIMIT %s'),query.call_args.args[0].index('journeys AS'))
        self.assertEqual(len(first),51)
        last=first[49];second=checkouts(self.store,row['id'],bounds,page_size=51,after=(last['created_at'],last['checkout_key']),search=prefix)
        self.assertEqual(len(second),15)
        self.assertFalse(set(r['checkout_key'] for r in first[:50]) & set(r['checkout_key'] for r in second))
        filtered=checkouts(self.store,row['id'],bounds,page_size=51,search=prefix+'12')
        self.assertEqual([c['checkout_key'] for c in filtered],[prefix+'12'])
        self.assertEqual(checkouts(self.store,row['id'],bounds,page_size=51,search="%' OR 1=1 --"),[])
        self.assertEqual(report(self.store,row['id'],bounds,include_history=False)['orders'],0)
        self.provider.send.assert_not_called()


if __name__=='__main__':unittest.main()
