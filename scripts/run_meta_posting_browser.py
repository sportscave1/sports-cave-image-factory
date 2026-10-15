"""Own and clean up the loopback-only mocked posting browser fixture."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def main():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0))
        port = probe.getsockname()[1]
    environment={**os.environ,'POST_AD_COMPACT_PROGRESS':'1','META_POSTING_UI_FIXTURE':'1','POSTING_FIXTURE_URL':f'http://127.0.0.1:{port}'}
    command=[sys.executable,'-c',f"import uvicorn; from streamlit.web.server.starlette import App; uvicorn.run(App('tests/meta_posting_progress_fixture.py'),host='127.0.0.1',port={port})"]
    with (ROOT/'tmp/meta_repair_browser_server.log').open('w',encoding='utf8') as log:
        process=subprocess.Popen(command,cwd=ROOT,env=environment,stdout=log,stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            deadline=time.monotonic()+30
            while True:
                if process.poll() is not None:
                    raise RuntimeError('Local posting fixture exited')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=1):
                        break
                except OSError:
                    if time.monotonic()>deadline:
                        raise RuntimeError('Local posting fixture startup timed out')
                    time.sleep(.2)
            return subprocess.run(['node','tests/meta_posting_progress_browser.cjs'],cwd=ROOT,env=environment,timeout=100).returncode
        finally:
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else:
                process.terminate()
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)


if __name__=='__main__':
    raise SystemExit(main())
