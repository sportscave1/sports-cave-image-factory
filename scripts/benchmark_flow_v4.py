"""Local renderer/cache measurements, not production service guarantees."""
import sys,os,json,time,importlib.util,statistics,math,uuid
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
os.environ['PYTHONPATH']=str(root)
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG
from tests.test_crm_flow_v4 import discount_document
from crm_thumbnail_render import preview_document
from crm_campaign_content import render_campaign
from crm_recovery_discount import substitute

def stats(values):return dict(n=len(values),p50=round(statistics.median(values),3),p95=round(sorted(values)[max(0,math.ceil(len(values)*.95)-1)],3))
nonce=uuid.uuid4().hex
results={'scope':'local Chrome isolated subprocesses; synthetic documents; no production DB/network/customer data','queue':[]}
for before in (True,False):
    path=root/('tmp/flow-v4-before/crm_thumbnail_cache.py' if before else 'crm_thumbnail_cache.py')
    spec=importlib.util.spec_from_file_location('bench_cache',path);cache=importlib.util.module_from_spec(spec);spec.loader.exec_module(cache)
    folder=root/'tmp'/('flow-v4-bench-cache-before' if before else 'flow-v4-bench-cache-after')
    os.environ['CRM_THUMBNAIL_CACHE_DIR']=str(folder)
    for run in range(3):
        keys=[cache.token(['queue-fixture',nonce,run,i]) for i in range(6)]
        start=time.perf_counter()
        for i,key in enumerate(keys):
            doc=document();doc['custom_html']=f'<h1>Stage {i+1}</h1><p>Neutral fixture</p>'
            cache.request(key,lambda doc=doc:(doc,CFG))
        ready={}
        while len(ready)<len(keys) and time.perf_counter()-start<180:
            for i,key in enumerate(keys):
                if i not in ready and cache.cached(key):ready[i]=round(1000*(time.perf_counter()-start),2)
            time.sleep(.03)
        assert len(ready)==len(keys),(before,cache.FAILURES)
        results['queue'].append(dict(before=before,run=run,stage_ready_ms=ready,
            diagnostics={str(i):cache.diagnostic(key) for i,key in enumerate(keys)} if hasattr(cache,'diagnostic') else {}))
    values=[]
    for _ in range(100):
        start=time.perf_counter();cache.request(keys[0],lambda:(_ for _ in ()).throw(AssertionError('cache hit must not read source')));values.append(1000*(time.perf_counter()-start))
    results['cache_before' if before else 'cache_after']=stats(values)
    cache.POOL.shutdown()
doc=discount_document()
results['discount_baseline_unresolved']= '{{discount_code}}' in render_campaign(doc,CFG)['html']
results['discount_after_resolved']= 'FIXTURE5' in render_campaign(preview_document(doc),CFG)['html']
Path('tmp/flow-v4-python-benchmarks.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
