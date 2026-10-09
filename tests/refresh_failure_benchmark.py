"""CPU and request-count measurement; no network or artificial request delay."""
import json
from pathlib import Path
import subprocess
import time
import types
from unittest.mock import Mock,patch
import meta_carousel_view as current

def main():
    baseline=types.ModuleType('baseline_carousel_view');baseline.__file__=current.__file__
    exec(compile(subprocess.check_output(['git','show','HEAD:meta_carousel_view.py']).decode('utf8'),current.__file__,'exec'),baseline.__dict__)
    source={'carousel_cards':[{'position':i,'image_sha256':str(i),'image_url':'https://example.test/image'} for i in range(1,5)]}
    results={'scenario':'4 archived cards, 20 rerenders during a storage outage; no simulated latency'}
    with patch('meta_review_store.load_media',side_effect=TimeoutError('fixture outage')):
        for module in (baseline,current):module.render(Mock(session_state={}),source,archived=True)
    for name,module in [('before',baseline),('after',current)]:
        ui=Mock(session_state={})
        with patch('meta_review_store.load_media',side_effect=TimeoutError('fixture outage')) as reads:
            start=time.perf_counter()
            for _ in range(20):module.render(ui,source,archived=True)
            results[name]={'archive_reads':reads.call_count,'cpu_wall_ms':round((time.perf_counter()-start)*1000,3)}
    Path('tmp/refresh-failure-benchmark.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results))

if __name__=='__main__':main()
