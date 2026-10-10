import argparse,ast,json,time,statistics,cProfile,pstats,os
from pathlib import Path
from streamlit.testing.v1 import AppTest
import sidebar_theme,top_bar
root=Path.cwd();p=argparse.ArgumentParser();p.add_argument('--variant',choices=['baseline','compact'],required=True);p.add_argument('--trial',type=int,required=True);args=p.parse_args()
if args.variant=='baseline':
 old=ast.parse((root/'tmp/navigation-v4/sidebar_theme.before.py').read_text())
 sidebar_theme.SIDEBAR_CSS=next(ast.literal_eval(n.value) for n in old.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SIDEBAR_CSS' for t in n.targets))
 top_bar.COMPONENT_PATH=root/'tmp/navigation-v4/topbar.before.html'
else:
 top_bar.COMPONENT_PATH=root/'tmp/navigation-v4/topbar.pre-validation.html'
 module=ast.parse((root/'tmp/navigation-v4/sidebar.compact.py').read_text())
 sidebar_theme.SIDEBAR_CSS=next(ast.literal_eval(n.value) for n in module.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SIDEBAR_CSS' for t in n.targets))
top_bar._component_source.cache_clear()
at=AppTest.from_file(str(root/'tests/fixtures/top_navigation_preview.py'),default_timeout=20)
t=time.perf_counter();at.run();cold=(time.perf_counter()-t)*1000
for _ in range(5):at.run()
samples=[]
for _ in range(20):
 t=time.perf_counter();at.run();samples.append((time.perf_counter()-t)*1000)
 if at.exception:raise RuntimeError(str(at.exception))
result={'variant':args.variant,'trial':args.trial,'first_run_ms':cold,'warmup':5,'samples_ms':samples,'p50_ms':statistics.median(samples),'p95_ms':sorted(samples)[18],'component_path':str(top_bar.COMPONENT_PATH)}
(root/f'tmp/navigation-v4/acceptance/{args.variant}-{args.trial}.json').write_text(json.dumps(result,indent=2))
