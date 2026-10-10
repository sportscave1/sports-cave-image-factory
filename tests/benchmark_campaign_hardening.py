"""Interleaved isolated render timing; same synthetic data and no shell parser."""
import json,math,time,statistics
import tempfile
from pathlib import Path
from streamlit.testing.v1 import AppTest
tempfile.tempdir=str(Path('tmp').resolve())
source=Path('tests/fixtures/campaign_hardening_preview.py').read_text(encoding='utf-8')
source=source.replace("exec(compile(fixture.read_text(encoding='utf-8').split('st.title(get_current_page())')[0],str(fixture),'exec'))","st.set_page_config(layout='wide')")
fixture_path=Path('tmp/campaign-hardening-render.py')
fixture_path.write_text(source,encoding='utf-8')
phases={'v7':'1','before':'hardening','after':'0'}
apps={}
for phase,value in phases.items():
    app=AppTest.from_file(str(fixture_path),default_timeout=30)
    app.query_params.update({'view':'detail','before':value})
    app.run();assert not app.exception,list(app.exception)
    apps[phase]=app
samples=[]
for run in range(44):
    for phase in tuple(phases) if run%2==0 else tuple(reversed(phases)):
        start=time.perf_counter();apps[phase].run();elapsed=(time.perf_counter()-start)*1000
        assert not apps[phase].exception,list(apps[phase].exception)
        if run>=4:samples.append({'phase':phase,'ms':elapsed})
summary=[]
for phase in phases:
    values=sorted(s['ms'] for s in samples if s['phase']==phase)
    summary.append({'phase':phase,'n':len(values),'p50_ms':statistics.median(values),'p95_ms':values[math.ceil(.95*len(values))-1]})
Path('docs/campaign-hardening-evidence/render.json').write_text(json.dumps({'summary':summary,'samples':samples},indent=2))
print(json.dumps(summary))
