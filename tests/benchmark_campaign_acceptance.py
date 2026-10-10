"""Local comparative SQL/mock benchmark; never measures production latency."""
import importlib.util
import json
import math
from pathlib import Path
import statistics
import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch
from tests.test_crm_campaign_preparation import PreparationTests
from crm_campaign_send import final_audience,review
from crm_campaign_audience_prepare import fingerprint
from crm_campaign_preparation import accept,tick
from tests.test_crm_send_flow import CFG,LIVE
from tests.test_crm import ADMIN

baseline=Path('tmp/campaign-v7-acceptance-baseline/crm_campaign_send.py')
spec=importlib.util.spec_from_file_location('campaign_acceptance_before',baseline)
before=importlib.util.module_from_spec(spec);spec.loader.exec_module(before)
records=[]
def measure(fn):
    started=time.perf_counter();value=fn();return value,(time.perf_counter()-started)*1000

for size in (50,250,1000,1100,2000):
    for scheduled in (False,True):
        for phase in ('before','after'):
            samples=[]
            for iteration in range(5):
                case=PreparationTests();case.setUp()
                statements={'n':0};base_db=case.store.db
                class CountedConnection:
                    def __init__(self):self.inner=base_db()
                    def __enter__(self):self.inner.__enter__();return self
                    def __exit__(self,*args):return self.inner.__exit__(*args)
                    def execute(self,*args,**kwargs):statements['n']+=1;return self.inner.execute(*args,**kwargs)
                case.store.db=CountedConnection
                try:
                    editor,initial,shop=case.reviewed(size,scheduled)
                    original=shop.customer_batch.side_effect
                    def slow_profiles(ids,**kw):time.sleep(.01);return original(ids,**kw)
                    shop.customer_batch.side_effect=slow_profiles
                    audience,audience_ms=measure(lambda:final_audience(shop,case.store,editor['document']))
                    prepared=SimpleNamespace(settings=CFG,identity=fingerprint(shop,editor['document'],CFG),result=lambda:audience)
                    ready,readiness_ms=measure(lambda:review(shop,case.store,editor,LIVE,audience_job=prepared))
                    calls=shop.customer_batch.call_count
                    queries=statements['n']
                    op=str(uuid.uuid4())
                    if phase=='before':
                        receipt,confirmation_ms=measure(lambda:before.queue_campaign(shop,case.store,ADMIN,editor,op,env=LIVE,snapshot_id=ready['snapshot_id']))
                        preparation_ms=0
                        foreground_calls=shop.customer_batch.call_count-calls
                        background_calls=0
                        foreground_db=statements['n']-queries;background_db=0
                    else:
                        receipt,confirmation_ms=measure(lambda:accept(case.store,ADMIN,editor,op,env=LIVE,snapshot_id=ready['snapshot_id'],confirmed=True))
                        foreground_calls=shop.customer_batch.call_count-calls
                        foreground_db=statements['n']-queries;queries=statements['n']
                        _,preparation_ms=measure(lambda:tick(case.store,shop,env=LIVE))
                        background_calls=shop.customer_batch.call_count-calls
                        background_db=statements['n']-queries
                    assert foreground_calls==0 if phase=='after' else foreground_calls==math.ceil(size/50)
                    samples.append({'audience_ms':audience_ms,'readiness_ms':readiness_ms,'confirmation_ms':confirmation_ms,
                                    'background_preparation_ms':preparation_ms,'foreground_profile_batches':foreground_calls,
                                    'background_profile_batches':background_calls,'external_http_calls':0,'receipt_status':receipt['status']})
                    samples[-1].update(foreground_db_statements=foreground_db,background_db_statements=background_db)
                finally:case.tearDown();case.doCleanups()
            def stats(field):
                values=[s[field] for s in samples]
                return {'p50_ms':statistics.median(values),'p95_ms':sorted(values)[math.ceil(.95*len(values))-1]}
            record={'size':size,'mode':'recipient_local' if scheduled else 'now','phase':phase,'n':len(samples),
                    **{field:stats(field) for field in ('audience_ms','readiness_ms','confirmation_ms','background_preparation_ms')},'samples':samples}
            records.append(record);print(json.dumps({k:v for k,v in record.items() if k!='samples'}),flush=True)
destination=Path('docs/campaign-v7-acceptance-evidence');destination.mkdir(exist_ok=True)
(destination/'benchmarks.json').write_text(json.dumps({'profile_batch_latency_ms':10,'backend':'serialized embedded PostgreSQL fixture','results':records},indent=2),encoding='utf-8')
