"""Actual local PostgreSQL operations, synthetic audience, blocked transports."""
import sys,os,time,json,statistics,math,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.chdir(ROOT)
from tests.campaign_real_postgres import connect
import tests.crm_db_fixture as fixture
fixture.connect=connect
from tests.test_crm_campaign_preparation import PreparationTests
from tests.test_crm import ADMIN
from tests.test_crm_campaign_v8 import timing
from crm_campaign_schedule import change_pending
from crm_campaign_progress import read_progress
identity=(ROOT.parent/'.tmp-full-system-audit/final-benchmark-identity.txt').read_text().strip()
case=PreparationTests();case.setUp();samples=[]
try:
    for run in range(22):
        editor,review,shop=case.reviewed()
        start=time.perf_counter();receipt=case.accepted(editor,review);ms=(time.perf_counter()-start)*1000
        assert receipt['status']=='PREPARING'
        if run>=2:samples.append(dict(metric='durable_acceptance',ms=ms))
        revision=case.store.state('campaign-timing:'+identity)['operation_id']
        start=time.perf_counter()
        change_pending(case.store,ADMIN,identity,timing(day='2099-10-'+('11' if run%2 else '12')),str(uuid.uuid4()),confirmed=True,expected_operation_id=revision)
        ms=(time.perf_counter()-start)*1000
        if run>=2:samples.append(dict(metric='schedule_save',ms=ms))
        start=time.perf_counter();progress=read_progress(case.store,[identity]);ms=(time.perf_counter()-start)*1000
        assert progress[identity]['total']==1085 and progress[identity]['submitted']==0
        if run>=2:samples.append(dict(metric='progress_refresh',ms=ms))
finally:case.tearDown();case.doCleanups()
summary=[]
for metric in sorted({r['metric'] for r in samples}):
    values=sorted(r['ms'] for r in samples if r['metric']==metric)
    summary.append(dict(metric=metric,n=len(values),p50_ms=statistics.median(values),p95_ms=values[math.ceil(.95*len(values))-1]))
(ROOT.parent/'.tmp-full-system-audit/final-operations.json').write_text(json.dumps(dict(summary=summary,samples=samples),indent=2))
print(json.dumps(summary))
