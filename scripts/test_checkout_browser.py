"""Own and stop loopback-only synthetic Streamlit fixtures for browser checks."""
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def main():
    env={**os.environ,'STREAMLIT_BROWSER_GATHER_USAGE_STATS':'false'}
    for name,port in [('operations',8538),('live',8539)]:
        with (ROOT/f'tmp/checkout-{name}-browser.log').open('w',encoding='utf-8') as log:
            server=subprocess.Popen([sys.executable,'-m','streamlit','run',f'tests/fixtures/crm_checkout_{name}.py',
                '--server.address','127.0.0.1','--server.port',str(port),'--server.headless','true'],
                cwd=ROOT,env=env,stdout=log,stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try:
                deadline=time.monotonic()+30
                while True:
                    if server.poll() is not None:raise RuntimeError('Synthetic checkout fixture failed to start')
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=1):break
                    except OSError:
                        if time.monotonic()>deadline:raise RuntimeError('Fixture startup timed out')
                        time.sleep(.1)
                result=subprocess.run(['node',f'tests/test_crm_checkout_{name}_ui.cjs'],cwd=ROOT,env=env,timeout=150)
                if result.returncode:return result.returncode
            finally:
                server.terminate()
                try:server.wait(timeout=5)
                except subprocess.TimeoutExpired:server.kill();server.wait()
    return 0


if __name__=='__main__':sys.exit(main())
