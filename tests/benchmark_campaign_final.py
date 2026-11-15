"""Comparable local workspace render samples. No production or provider I/O.

Source roots run in separate processes so baseline imports cannot leak into the
candidate. The real sidebar fixture includes its AST extraction cost; profiling
records that separately. Query latency is explicitly synthetic, not network time.
"""
import os,sys,json,time,statistics,math,argparse,cProfile,pstats,io
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--source',required=True)
parser.add_argument('--output',required=True)
parser.add_argument('--delay',default='0')
parser.add_argument('--view',choices=('home','workspace'))
args=parser.parse_args()
source=Path(args.source).resolve();output=Path(args.output).resolve()
fixture=Path(__file__).resolve().parent/'fixtures/campaign_final_preview.py'
os.environ['CAMPAIGN_SOURCE_ROOT']=str(source)
os.environ['CAMPAIGN_QUERY_DELAY']=args.delay
sys.path.insert(0,str(source));os.chdir(source)
from streamlit.testing.v1 import AppTest
import crm_brand_templates
def app(view):
    a=AppTest.from_file(str(fixture),default_timeout=30)
    a.query_params['view']=view
    return a
samples=[]
for view in ((args.view,) if args.view else ('home','workspace')):
    for run in range(22):
        crm_brand_templates._CACHE.clear()
        a=app(view)
        for kind in ('initial','warm'):
            start=time.perf_counter();a.run();elapsed=(time.perf_counter()-start)*1000
            assert not a.exception,list(a.exception)
            if run>=2:samples.append(dict(view=view,kind=kind,ms=elapsed,queries=a.session_state['fixture-counts']['queries']))
profile=cProfile.Profile();profile.enable();app('workspace').run();profile.disable()
buffer=io.StringIO();pstats.Stats(profile,stream=buffer).sort_stats('cumulative').print_stats(25)
summary=[]
for view in ('home','workspace'):
    for kind in ('initial','warm'):
        group=[r for r in samples if r['view']==view and r['kind']==kind];values=sorted(r['ms'] for r in group)
        if values:summary.append(dict(view=view,kind=kind,n=len(values),p50_ms=statistics.median(values),p95_ms=values[math.ceil(.95*len(values))-1],queries=sorted(set(r['queries'] for r in group))))
output.write_text(json.dumps(dict(source=str(source),query_delay_seconds=args.delay,summary=summary,samples=samples,profile=buffer.getvalue()),indent=2))
print(json.dumps(summary))
