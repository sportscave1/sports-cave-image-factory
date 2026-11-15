"""Real loopback SQL + synthetic 1ms reads/2ms submissions. No external I/O.

CRM_TEST_POSTGRES=1 python -m tests.benchmark_crm_batch_dispatch
Reads the unchanged HEAD implementation for a reproducible pre-change baseline.
Does not include the old worker's 30-second sleeps or actual Resend pacing.
"""
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import patch
import json
import os
import subprocess
import time
import uuid
from crm_engine import Engine
from crm_campaign_dispatch import dispatch
from crm_resend import Config
from tests.crm_db_fixture import Connection,connect
from tests.test_crm_batch_dispatch import DispatchTests,Transport
from tests.test_crm_campaign_v2 import authority,profile
from tests.test_crm_send_flow import LIVE


def baseline(path,name):
    source=subprocess.run(['git','show','HEAD:'+path],check=True,capture_output=True,text=True).stdout
    namespace={'__name__':name};exec(compile(source,path,'exec'),namespace);return namespace


class Single:
    def __init__(self):self.calls=0;self.gets=0;self.first=None;self.last=None
    def suppressed(self,address):self.gets+=2;time.sleep(.002);return False
    def send(self,*args):
        self.calls+=1;self.first=self.first or datetime.now(timezone.utc).isoformat()
        time.sleep(.002);self.last=datetime.now(timezone.utc).isoformat();return str(uuid.uuid4())


class Batched(Transport):
    def __init__(self):super().__init__();self.first=None;self.last=None
    def send(self,messages,key):
        self.first=self.first or datetime.now(timezone.utc).isoformat();time.sleep(.002)
        result=super().send(messages,key);self.last=datetime.now(timezone.utc).isoformat();return result


def run():
    fixture=DispatchTests();fixture.setUp();results={}
    try:
        for mode in ('before','after'):
            identity=fixture.queue(1095)
            fixture.store.q("UPDATE crm_campaigns SET status='PAUSED' WHERE id<>%s AND status='SENDING'",(identity,))
            counts={'sql_statements':0,'database_writes':0,'transactions':0,'shopify_calls_during_dispatch':0}
            original=Connection.execute
            def execute(self,sql,args=()):
                counts['sql_statements']+=1
                if sql.strip().startswith(('UPDATE','INSERT','DELETE','WITH due')):counts['database_writes']+=1
                if sql=='COMMIT':counts['transactions']+=1
                return original(self,sql,args)
            if mode=='before':
                store=baseline('crm_store.py','old_store')['Store'](connect)
                legacy=baseline('crm_engine.py','old_engine')['Engine']
                content=fixture.store.template(fixture.store.q('SELECT template_id FROM crm_campaigns WHERE id=%s',(identity,),True)['template_id'],1)
                frozen=content['dispatch']['recipients']
                rows=fixture.sends(identity)
                shop=authority([])
                def customer(customer_id,**kwargs):
                    counts['shopify_calls_during_dispatch']+=1;time.sleep(.001)
                    row=next(r for r in rows if r['shopify_customer_id']==customer_id)
                    recipient=frozen[row['recipient_hash']]
                    from tests.crm_fixtures import native_customer
                    p=profile(customer_id.rsplit('/',1)[-1],'NZ');p['email']=recipient['address']
                    result=native_customer(p);result['defaultEmailAddress']['marketingUnsubscribeUrl']=recipient['unsubscribe_url'];return result
                shop.customer.side_effect=customer;provider=Single();engine=legacy(store,shop,provider,Config(LIVE))
                def work():
                    while engine.send_one():pass
            else:
                provider=Batched();engine=Engine(fixture.store,fixture.shop,SimpleNamespace(batch_transport=provider),Config(LIVE))
                def work():dispatch(engine)
            started=time.perf_counter()
            with patch.object(Connection,'execute',execute),patch.dict(os.environ,LIVE):work()
            duration=time.perf_counter()-started
            rows=fixture.sends(identity);accepted=sum(r['status']=='ACCEPTED' for r in rows)
            if accepted!=1095:raise AssertionError(f'{mode}: accepted {accepted}')
            results[mode]={'recipient_total':1095,'submitted':accepted,**counts,
                'individual_email_calls':provider.calls if mode=='before' else 0,
                'batch_email_calls':len(provider.calls) if mode=='after' else 0,
                'resend_api_calls':provider.calls+provider.gets if mode=='before' else len(provider.calls),
                'first_submission_timestamp':provider.first,'last_submission_timestamp':provider.last,
                'total_duration_seconds':round(duration,3),'emails_per_second':round(accepted/duration,2)}
        results['limitations']='Synthetic latencies, mocked provider stop-state; after excludes provider list HTTP calls. Before excludes actual 0.55s API pacing and 30s tick gaps. No production throughput measurement.'
        print(json.dumps(results,indent=2))
    finally:fixture.tearDown()


if __name__=='__main__':run()
