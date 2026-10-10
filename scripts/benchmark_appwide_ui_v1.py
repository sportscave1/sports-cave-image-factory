"""Local rerun timings for the same real render function and synthetic workload."""
import json,math,statistics,sys,time,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from streamlit.testing.v1 import AppTest
results=[]
for route in ['Prodigi','Webhook Events','Sync Runs','App Errors','Persistence Check']:
 for phase in ['before','after']:
  app=AppTest.from_file(str(ROOT/'tests/fixtures/appwide_ui_v1_preview.py'),default_timeout=15)
  app.query_params.update(phase=phase,route=route)
  app.run()
  assert not app.exception, app.exception
  samples=[]
  render_samples=[]
  for _ in range(20):
   start=time.perf_counter();app.run();samples.append((time.perf_counter()-start)*1000)
   assert not app.exception,app.exception
   render_samples.append(float(re.search(r'data-render-ms="([0-9.]+)"',app.get("html")[-1].proto.body).group(1)))
  results.append({'route':route,'phase':phase,'sample_count':len(samples),'p50_ms':round(statistics.median(samples),2),'p95_ms':round(sorted(samples)[math.ceil(.95*len(samples))-1],2),'samples_ms':samples,'render_p50_ms':round(statistics.median(render_samples),2),'render_p95_ms':round(sorted(render_samples)[math.ceil(.95*len(render_samples))-1],2),'render_samples_ms':render_samples})
path=ROOT/'docs/appwide-ui-v1-evidence/local-rerun-timings.json'
path.write_text(json.dumps({'scope':'Streamlit AppTest warm reruns, actual render functions, synthetic read responses. Source extraction cached after warmup; includes test-driver overhead. Render-only metrics exclude source extraction and shell CSS. Excludes browser/network/production latency. No live performance claim.','results':results},indent=2))
print(json.dumps([{k:v for k,v in r.items() if k!='samples_ms'} for r in results],indent=2))
