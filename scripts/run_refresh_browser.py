"""Own a local mocked Creative Refresh server for browser regression checks."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    port=int(os.getenv('REFRESH_UI_PORT','8557'))
    with socket.socket() as probe:probe.bind(('127.0.0.1',port))
    (ROOT/'tmp').mkdir(exist_ok=True)
    from PIL import Image
    from tests.fixtures.refresh_ui import ready_carousel
    import ads_page as ads
    Image.new('RGB',(1024,1024),(42,90,140)).save(ROOT/'tmp/refresh-test-upload.png')
    result,workflow=ready_carousel()
    workflow['ad_notes']['carousel']['cards'][0]['headline']='Local CSV Review'
    (ROOT/'tmp/refresh-test-copy.csv').write_bytes(ads.build_carousel_copy_csv(result,workflow))
    env={**os.environ,'PYTHONUTF8':'1','PYTHONPATH':str(ROOT)}
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
            test=next((arg for arg in sys.argv[1:] if arg.endswith('.cjs')),'tests/test_ads_refresh_ui.cjs')
            return subprocess.run(['node',test],cwd=ROOT,env=env).returncode
        finally:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else:process.terminate()
            process.wait(timeout=5)


if __name__=='__main__':sys.exit(main())
