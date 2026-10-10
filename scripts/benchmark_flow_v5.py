"""Measure collapsed-panel Python overhead only; not full navigation latency."""
import importlib.util,inspect,json,math,statistics,sys,time
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import crm_flow_page as after
spec=importlib.util.spec_from_file_location('flow_v5_before',Path('tmp/flow-v5-before/crm_flow_page.py'))
before=importlib.util.module_from_spec(spec);spec.loader.exec_module(before)
result={}
for name,module in (('before',before),('after',after)):
    samples=[]
    ui=Mock();ui.session_state={};ui.expander.side_effect=lambda *a,**k:nullcontext(SimpleNamespace(open=False))
    ui.popover.side_effect=ui.expander.side_effect
    store=Mock();shop=Mock()
    with patch.object(module,'st',ui),patch.object(module,'checkout_panel') as load,patch.object(module,'arm') as refresh:
        for _ in range(1000):
            at=time.perf_counter()
            inspect.unwrap(module.recipient_details)(store,{},'fixture')
            inspect.unwrap(module.checkouts)(shop,store,{},dict(id='fixture'))
            samples.append(1000*(time.perf_counter()-at))
        load.assert_not_called();refresh.assert_not_called();store.flow.assert_not_called();store.q.assert_not_called()
    values=sorted(samples)
    result[name]={'n':len(values),'p50_ms':statistics.median(values),'p95_ms':values[math.ceil(len(values)*.95)-1],'checkout_reads':0,'timeline_reads':0,'shopify_requests':0}
Path('docs/flow-v5-evidence/collapsed-panels.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
