"""Opt-in read-path scaling audit on fabricated local data, never providers."""
from copy import deepcopy
from datetime import timedelta
import json
import math
import os
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from tests.test_crm_automation_publication import PublicationTests,ADMIN,LIVE


class Audit(PublicationTests):
    def test_audit(self):
        from crm_automation_definition import email_step
        from crm_checkout_analytics import checkouts,window
        from crm_logic import now
        from crm_campaign_store import CampaignStore
        from crm_campaign_send import review
        from tests.test_crm_send_flow import CFG
        from tests.test_crm_campaign_v2 import authority,profile,audience
        from tests.test_crm_simple_editor import document
        result={'scope':'loopback PGlite, 12 warm samples + first read; real SQL, fake customer/provider data','table':{},'campaign_review':{}}
        def timing(call,n=12):
            values=[];first=None;value=None
            for i in range(n+1):
                at=perf_counter();value=call();ms=(perf_counter()-at)*1000
                if i:values.append(ms)
                else:first=ms
            ordered=sorted(values)
            return {'n':n,'first_ms':round(first,3),'p50_ms':round(ordered[n//2],3),'p95_ms':round(ordered[math.ceil(.95*n)-1],3)},value
        for count in (1,3,6):
            row=self.draft('abandoned');flow=deepcopy(row['config']['draft'])
            flow['emails']=[email_step(flow['emails'][0]['document'],600*(i+1)) for i in range(count)]
            row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
            self.job(row);self.run_job();old=self.state(row)
            flow['emails'][0]['document']['content']['subject']+=' second version'
            row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,old['config']['revision'])
            self.job(row);self.run_job();current=self.state(row)
            for total in (50,500,5000):
                self.store.q('TRUNCATE crm_marketing_sends,crm_automation_enrollments,crm_shopify_checkouts CASCADE')
                self.store.q("""INSERT INTO crm_shopify_checkouts(checkout_key,shop,customer_id,source_event_id,created_at,activity_at,status,admin_checkout_id,analytics)
                  SELECT 'local-'||i,'fixture.myshopify.com','customer-'||i,'fixture',now()-i*interval '1 second',now()-i*interval '1 second',
                  CASE WHEN i%7=0 THEN 'RECOVERED' ELSE 'ABANDONED' END,'checkout-'||i,
                  jsonb_build_object('shopify_abandoned',true,'email','fixture'||i||'@example.test') FROM generate_series(1,%s) i""",(total,))
                self.store.q("""INSERT INTO crm_automation_enrollments(automation_id,shopify_customer_id,trigger_shopify_id,trigger_key,trigger_at,steps,status,next_due_at,checkout_key)
                  SELECT %s,customer_id,admin_checkout_id,checkout_key,created_at,
                  CASE WHEN substring(checkout_key from 7)::int%2=0 THEN %s::jsonb ELSE %s::jsonb END,
                  CASE WHEN substring(checkout_key from 7)::int%7=0 THEN 'RECOVERED' ELSE 'ACTIVE' END,
                  activity_at+interval '10 minutes',checkout_key FROM crm_shopify_checkouts""",(row['id'],json.dumps(old['steps']),json.dumps(current['steps'])))
                self.store.q("""INSERT INTO crm_marketing_sends(idempotency_key,enrollment_id,step_index,template_id,template_version,status,provider_email_id)
                  SELECT 'fixture-'||id,id,0,(steps->0->>'template_id')::uuid,(steps->0->>'template_version')::int,
                    CASE substring(checkout_key from 7)::int%4 WHEN 0 THEN 'ACCEPTED' WHEN 1 THEN 'PENDING' WHEN 2 THEN 'UNCERTAIN' ELSE 'FAILED' END,
                    CASE WHEN substring(checkout_key from 7)::int%4=0 THEN 'receipt-'||id END FROM crm_automation_enrollments""")
                self.store.q('ANALYZE crm_shopify_checkouts');self.store.q('ANALYZE crm_automation_enrollments');self.store.q('ANALYZE crm_marketing_sends')
                bounds=window('All time');metric,rows=timing(lambda:checkouts(self.store,row['id'],bounds,page_size=50))
                self.assertEqual(len(rows),50)
                metric['payload_bytes']=len(json.dumps(rows,default=str).encode())
                captured=[];original=self.store.q
                def capture(sql,args=(),one=False):captured.append((sql,args));return original(sql,args,one)
                with patch.object(self.store,'q',side_effect=capture):checkouts(self.store,row['id'],bounds,page_size=50)
                self.assertEqual(len(captured),1)
                plan=self.store.q('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+captured[0][0],captured[0][1],True)
                metric['plan']=plan;result['table'][f'{total}_checkouts_{count}_emails']=metric
        # Fresh mocked recipient authority + actual immutable review snapshot.
        campaign=CampaignStore(self.store.connect);shop=authority([profile(i) for i in range(1,51)])
        with patch.object(campaign,'render_settings',return_value=deepcopy(CFG)):
            for mode in ('now','schedule'):
                doc=document();doc.update(market_audience=True,market='AU',audience=audience('AU'),send_timing={'mode':mode})
                if mode=='schedule':doc['send_timing'].update(date=(now()+timedelta(days=2)).date().isoformat(),time='07:00')
                editor=campaign.save(ADMIN,'Local review benchmark',doc,env=LIVE)
                metric,reviewed=timing(lambda:review(shop,campaign,editor,env=LIVE))
                self.assertEqual(reviewed['blockers'],[])
                self.assertTrue(reviewed['snapshot_id']);result['campaign_review'][mode]=metric
        target=Path('tmp/email_v4_audit.json');target.write_text(json.dumps(result,indent=2,default=str),encoding='utf8')
        print('Audit measurements:',json.dumps({**result,'table':{k:{x:y for x,y in v.items() if x!='plan'} for k,v in result['table'].items()}}))
