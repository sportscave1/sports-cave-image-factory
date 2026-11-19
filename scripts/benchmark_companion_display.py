"""Synthetic only: no providers, database credentials, or application startup."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json, statistics, time
from concurrent.futures import ThreadPoolExecutor
from worker_health_cache import DisplayIndex

def percentile(values,p):return sorted(values)[min(len(values)-1,int(len(values)*p))]
def run():
    output=[]
    for n in (100,1000,10000):
        payload=dict(jobs=[dict(id=f'gid://shopify/Product/{i+1}',category='Queued' if i%2 else 'Failed',
            design='Synthetic art',stage='Waiting',reason='Fixture') for i in range(n)],cost={'queries':2})
        start=time.perf_counter();index=DisplayIndex(payload);build=(time.perf_counter()-start)*1000
        def read(_):
            start=time.perf_counter();rows=index.select('Queued',limit=50)
            return (time.perf_counter()-start)*1000,len(json.dumps(rows).encode())
        with ThreadPoolExecutor(max_workers=20) as pool: samples=list(pool.map(read,range(1000)))
        latencies=[r[0] for r in samples]
        output.append(dict(jobs=n,viewers=20,requests=1000,build_ms=round(build,2),
            p50_ms=round(statistics.median(latencies),2),p95_ms=round(percentile(latencies,.95),2),
            max_payload_bytes=max(r[1] for r in samples),index_bytes=index.bytes,postgres_queries_per_page=0))
    target=Path('output/companion-phases');target.mkdir(parents=True,exist_ok=True)
    (target/'display-benchmark.json').write_text(json.dumps(output,indent=2))
    print(json.dumps(output,indent=2))
    assert all(row['p95_ms']<500 for row in output)
if __name__=='__main__':run()
