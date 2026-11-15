"""Equivalent local SQL/CPU samples; no speed claims about production."""
import importlib.util,json,math,statistics,time,os,unittest
from pathlib import Path
from tests.test_crm_campaign_v8 import DurableTests,state,timing
from tests.test_crm_campaign_v2 import profile
from datetime import datetime,timezone
from crm_campaign_progress import read_progress
from crm_campaign_schedule import plan

def load(name):
    spec=importlib.util.spec_from_file_location('v8_before_'+name,Path('tmp/campaign-v8-before')/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class Samples(unittest.TestCase):
    def test_equivalent_schedule_and_progress_samples(self):
        fixture=DurableTests();fixture.setUp()
        try:
            campaign=fixture.queue(1085);audience=state([profile(i) for i in range(1085)])
            at=datetime(2026,1,1,tzinfo=timezone.utc);before_plan=load('crm_campaign_schedule').plan;before_read=load('crm_campaign_progress').read_progress
            data=[]
            for phase,planner,reader,t in [('before',before_plan,before_read,{'mode':'schedule','date':'2026-10-10','time':'17:00'}),('after',plan,read_progress,timing())]:
                doc={'market':'AU','send_timing':t}
                for run in range(40):
                    start=time.perf_counter();jobs=planner(doc,audience,at);planning=(time.perf_counter()-start)*1000
                    self.assertEqual({j['due_at'] for j in jobs.values()},{'2026-10-10T06:00:00+00:00'})
                    calls=[];original=fixture.store.q
                    def counted(*args,**kwargs):calls.append(1);return original(*args,**kwargs)
                    fixture.store.q=counted
                    try:
                        start=time.perf_counter();progress=reader(fixture.store,[campaign['id']]);reading=(time.perf_counter()-start)*1000
                    finally:fixture.store.q=original
                    self.assertEqual(progress[str(campaign['id'])]['total'],1085)
                    data.append({'phase':phase,'run':run,'planning_ms':planning,'progress_ms':reading,'sql_statements':len(calls),'shopify_api_calls':0,'provider_api_calls':0})
            summary=[]
            for phase in ('before','after'):
                group=[r for r in data if r['phase']==phase];item={'phase':phase,'n':len(group),'sql_statements':1,'shopify_api_calls':0,'provider_api_calls':0}
                for metric in ('planning_ms','progress_ms'):
                    values=sorted(r[metric] for r in group);item[metric]={'p50':statistics.median(values),'p95':values[math.ceil(.95*len(values))-1]}
                summary.append(item)
            out=Path('docs/campaign-v8-evidence');out.mkdir(parents=True,exist_ok=True)
            (out/'performance.json').write_text(json.dumps({'summary':summary,'samples':data},indent=2))
            print(json.dumps(summary))
        finally:fixture.tearDown();fixture.doCleanups()
