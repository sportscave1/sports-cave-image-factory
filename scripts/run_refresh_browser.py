"""Own a local mocked Creative Refresh server for browser regression checks."""
import os
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    port=8557
    with socket.socket() as probe:probe.bind(('127.0.0.1',port))
    (ROOT/'tmp').mkdir(exist_ok=True)
    from PIL import Image
    from tests.fixtures.refresh_ui import ready_carousel
    from tests.test_ads_refresh_save_restore import RefreshSaveRestoreTests
    import ads_page as ads
    Image.new('RGB',(1024,1024),(42,90,140)).save(ROOT/'tmp/refresh-test-upload.png')
    result,workflow=ready_carousel()
    # Match the fixture's source digests; they are provenance, not pixel analysis.
    context = result['creative_refresh_context']
    for i, card in enumerate(context['source_winner']['carousel_cards'], 1):
        card['image_sha256'] = f'fixture-card-{i}'
    result = ads.build_ads_result_record(result['product_name'], result['category'], result['country'], 'Carousel',
        product_id=result['product_id'], product_url=result['product_url'], variation_token='synthetic-v3', creative_refresh_context=context)
    ie, _ = RefreshSaveRestoreTests().ready_ie()
    (ROOT/'tmp/refresh-expected-prompts.json').write_text(json.dumps({
        'Carousel': ads.creation_instructions(result['master_prompt']),
        'Instant Experience': ads.creation_instructions(ie['master_prompt']),
    }), encoding='utf-8')
    (ROOT/'tmp/refresh-test-copy-valid.csv').write_bytes(ads.build_carousel_copy_csv(result,workflow))
    workflow['ad_notes']['carousel']['cards'][0]['headline']='Local CSV Review'
    (ROOT/'tmp/refresh-test-copy.csv').write_bytes(ads.build_carousel_copy_csv(result,workflow))
    env={**os.environ,'PYTHONUTF8':'1','PYTHONPATH':str(ROOT)}
    env['NODE_PATH'] = str(ROOT/'tmp/browser-runtime/node_modules')
    if '--baseline' in sys.argv:
        path=ROOT/'tmp/refresh-baseline'
        path.mkdir(exist_ok=True)
        for name in ('ads_refresh_plan','ads_refresh_generation','ads_refresh_reference','ads_refresh_saved','meta_review_handoff','ads_page'):
            (path/(name+'.py')).write_bytes(subprocess.check_output(['git','show','b274b054235be54854fd972006eb9e7a46a707c7:'+name+'.py'],cwd=ROOT))
        env['REFRESH_BASELINE_SOURCE']=str(path)
    label='before' if '--baseline' in sys.argv else 'after'
    env['REFRESH_BROWSER_LABEL']=label
    with (ROOT/f'tmp/refresh-browser-{label}.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([sys.executable,'-m','streamlit','run','tests/fixtures/refresh_ui.py',
            '--server.address','127.0.0.1','--server.port',str(port),'--server.headless','true',
            '--server.fileWatcherType','none','--browser.gatherUsageStats','false'],cwd=ROOT,env=env,
            stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            deadline=time.monotonic()+40
            while True:
                if process.poll() is not None:raise RuntimeError('Local fixture exited')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=1):break
                except OSError:
                    if time.monotonic()>deadline:raise RuntimeError('Fixture startup timed out')
                    time.sleep(.2)
            return subprocess.run(['node','tests/test_ads_refresh_ui.cjs'],cwd=ROOT,env=env).returncode
        finally:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else:process.terminate()
            process.wait(timeout=5)


if __name__=='__main__':sys.exit(main())
