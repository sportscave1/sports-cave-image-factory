"""Isolated SQL-clock lifecycle benchmark. Mocked providers; no real delivery."""
from datetime import datetime,timezone
import importlib.util
import json
import os
from pathlib import Path
import statistics
import time
from types import SimpleNamespace
import uuid
from unittest.mock import Mock,patch
from tests.test_crm_campaign_preparation import PreparationTests
from tests.test_crm_send_flow import LIVE
from tests.test_crm import ADMIN
from tests.test_crm_batch_dispatch import Transport
from crm_campaign_send import review
from crm_campaign_preparation import accept,tick
from crm_campaign_progress import read_progress
from crm_campaign_dispatch import dispatch
from crm_engine import Engine
from crm_resend import Config
spec=importlib.util.spec_from_file_location('lifecycle_before','tmp/campaign-v7-acceptance-baseline/crm_campaign_send.py')
before=importlib.util.module_from_spec(spec);spec.loader.exec_module(before)
records=[]
assert os.environ.get('CRM_FIXTURE_SQL_PORT')=='8884','Dedicated disposable localhost fixture required'
def measured(fn):
    at=time.perf_counter();result=fn();return result,(time.perf_counter()-at)*1000
for size in (50,250,1000,1100,2000):
    for scheduled in (False,True):
        for phase in ('before','after'):
            samples=[]
            for _ in range(3):
                case=PreparationTests();case.setUp();base=case.store.db
                try:
                    # Only this dedicated in-memory localhost database is used
                    # here. Reset synthetic cohorts between samples to avoid
                    # measuring accumulated benchmark-history/resource growth.
                    case.store.q('TRUNCATE crm_campaign_drafts,crm_templates,crm_segment_definitions,crm_runtime_state CASCADE')
                    editor,result,shop=case.reviewed(size)
                    if scheduled:
                        editor['document']['send_timing']={'mode':'schedule','policy_version':2,'time_basis':'recipient_local','date':'2099-10-10','time':'17:00'}
                        # Single verified timezone cohort for a bounded complete
                        # dispatch benchmark. Mixed-zone semantics are tested separately.
                        for customer in shop.campaign_subscribers.return_value['nodes']:
                            customer['defaultAddress']['provinceCode']='NSW'
                            customer['defaultAddress']['zip']='2000'
                            customer['defaultAddress'].pop('province',None)
                            customer['defaultAddress'].pop('timeZone',None)
                            customer.pop('timezone',None);customer.pop('timeZone',None)
                        editor=case.store.save(ADMIN,editor['name'],editor['document'],identity=editor['id'],version=editor['version'],env=LIVE)
                        result=review(shop,case.store,editor,LIVE)
                        assert not result['blockers'],result['blockers']
                    operation=str(uuid.uuid4())
                    if phase=='before':_,confirmation=measured(lambda:before.queue_campaign(shop,case.store,ADMIN,editor,operation,env=LIVE,snapshot_id=result['snapshot_id']));preparation=0
                    else:
                        _,confirmation=measured(lambda:accept(case.store,ADMIN,editor,operation,snapshot_id=result['snapshot_id'],confirmed=True,env=LIVE))
                        _,preparation=measured(lambda:tick(case.store,shop,env=LIVE))
                    at=datetime(2099,10,10,6,0,1,tzinfo=timezone.utc)
                    literal="(TIMESTAMPTZ '"+at.isoformat()+"')"
                    class FakeClockConnection:
                        def __init__(self):self.inner=base()
                        def __enter__(self):self.inner.__enter__();return self
                        def __exit__(self,*args):return self.inner.__exit__(*args)
                        def execute(self,sql,args=()):return self.inner.execute(sql.replace('clock_timestamp()',literal).replace('now()',literal),args)
                    case.store.db=FakeClockConnection
                    wire=Transport();provider=SimpleNamespace(batch_transport=wire)
                    no_profiles=Mock();no_profiles.customer.side_effect=AssertionError('No worker profile lookup')
                    engine,startup=measured(lambda:Engine(case.store,no_profiles,provider,Config(LIVE),clock=lambda:at))
                    from crm_campaign_schedule import activate_due
                    _,activation=measured(lambda:activate_due(case.store))
                    def all_batches():
                        for _ in range(4):
                            if not dispatch(engine):return
                        raise AssertionError('Unbounded dispatch')
                    _,dispatch_ms=measured(all_batches)
                    with patch('crm_automation_capabilities.refresh_due',return_value=False),patch('crm_checkout_analytics.sync_cache'),patch('crm_campaign_attribution.reconcile'):
                        _,completion_ms=measured(lambda:engine.tick(str(uuid.uuid4())))
                    progress,progress_ms=measured(lambda:read_progress(case.store,[editor['id']])[str(editor['id'])])
                    assert progress['complete'] and progress['submitted']==size,progress
                    assert sum(len(messages) for _,messages in wire.calls)==size
                    no_profiles.customer.assert_not_called()
                    samples.append({'confirmation_ms':confirmation,'preparation_ms':preparation,'worker_construction_ms':startup,
                                    'activation_ms':activation,'dispatch_ms':dispatch_ms,'completion_tick_ms':completion_ms,
                                    'completion_projection_ms':progress_ms,'mock_batch_send_calls':len(wire.calls),
                                    'external_http_calls':0,'submitted':progress['submitted'],'status':progress['status']})
                finally:case.store.db=base;case.tearDown();case.doCleanups()
            stats={key:{'p50_ms':statistics.median(s[key] for s in samples),'p95_ms':max(s[key] for s in samples)} for key in samples[0] if key.endswith('_ms')}
            records.append({'size':size,'mode':'recipient_local' if scheduled else 'now','phase':phase,'n':3,**stats,'samples':samples})
            Path('docs/campaign-v7-acceptance-evidence/worker-lifecycle.json').write_text(json.dumps({'sql_clock':at.isoformat(),'fixture_reset':'synthetic cohort reset for each sample on localhost:8884','scheduled_cohort':'verified NSW recipients; mixed zones covered by separate tests','results':records},indent=2),encoding='utf-8')
            print(size,scheduled,phase,flush=True)
Path('docs/campaign-v7-acceptance-evidence/worker-lifecycle.json').write_text(json.dumps({'sql_clock':at.isoformat(),'scheduled_cohort':'verified NSW recipients; mixed zones covered by separate tests','results':records},indent=2),encoding='utf-8')
