"""60-second synthetic concurrency/failure soak; no database or network."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import json,time,statistics
from worker_health_cache import Snapshot
cache=Snapshot(ttl=.4)
lock=Lock();state={'refreshes':0,'active':0,'peak_refreshes':0,'stale_reads':0,'cold_reads':0,'reads':0}
latencies=[]
def loader():
    with lock:
        state['refreshes']+=1;number=state['refreshes'];state['active']+=1;state['peak_refreshes']=max(state['peak_refreshes'],state['active'])
    try:
        time.sleep(.03)
        if number%7==0:raise RuntimeError('Injected transient outage')
        return dict(cost={'queries':2},jobs=[dict(id=f'gid://shopify/Product/{n+1}',category='Queued',design='Synthetic') for n in range(10000)])
    finally:
        with lock:state['active']-=1
started=time.monotonic();end=started+60

def reader(n):
    count=0
    while time.monotonic()<end:
        before=time.perf_counter()
        try:
            index,meta=cache.read_index(loader)
            assert len(index.select(limit=50))==50 and index.filters['All']==10000
            with lock:state['stale_reads']+=meta['state']=='stale'
        except TimeoutError:
            with lock:state['cold_reads']+=1
        with lock:
            latencies.append((time.perf_counter()-before)*1000);state['reads']+=1
        count+=1
        if n==0 and count%150==0:cache.invalidate()
        time.sleep(.05)
with ThreadPoolExecutor(max_workers=20) as pool:list(pool.map(reader,range(20)))
report={**state,'seconds':round(time.monotonic()-started,2),'viewers':20,'jobs':10000,
        'p50_ms':round(statistics.median(latencies),2),'p95_ms':round(sorted(latencies)[int(len(latencies)*.95)],2)}
target=Path('output/companion-phases');target.mkdir(parents=True,exist_ok=True)
(target/'display-soak.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
assert report['peak_refreshes']==1 and report['stale_reads']>0 and report['p95_ms']<500
