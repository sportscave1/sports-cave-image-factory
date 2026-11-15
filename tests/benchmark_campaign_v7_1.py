"""Comparative warm server render measurements; synthetic, zero external I/O."""
import json,time,statistics,math
from pathlib import Path
from streamlit.testing.v1 import AppTest
result=[]
for view in ('detail','home'):
    for phase in ('before','after'):
        app=AppTest.from_file('tests/fixtures/campaign_v7_1_preview.py',default_timeout=30)
        app.query_params.update({'view':view,'before':'1' if phase=='before' else '0'})
        app.run();assert not app.exception,list(app.exception)
        samples=[]
        for i in range(20):
            start=time.perf_counter();app.run();samples.append((time.perf_counter()-start)*1000)
            assert not app.exception,list(app.exception)
        result.append({'view':view,'phase':phase,'n':len(samples),'p50_ms':statistics.median(samples),'p95_ms':sorted(samples)[math.ceil(.95*len(samples))-1],'samples_ms':samples})
Path('docs/campaign-v7-1-evidence').mkdir(exist_ok=True)
Path('docs/campaign-v7-1-evidence/render-benchmarks.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps([{k:v for k,v in r.items() if k!='samples_ms'} for r in result]))
