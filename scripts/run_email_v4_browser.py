"""Own disposable SQL + UI fixture processes for Email V4 browser regressions."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def main():
    ui_port=8543 if os.getenv('EMAIL_V4_CAMPAIGNS')=='1' else 8533
    for port in (8873,ui_port):
        with socket.socket() as probe:probe.bind(('127.0.0.1',port))
    env={**os.environ,'CRM_TEST_POSTGRES':'1','CRM_FIXTURE_SQL_PORT':'8873','PYTHONUTF8':'1'}
    processes=[];logs=[]
    try:
        commands=[('sql',['node','tests/crm_postgres_server.mjs']),('ui',[sys.executable,'tests/fixtures/email_v4_server.py'])]
        for name,command in commands:
            log=(ROOT/'tmp'/('email_v4_browser_'+name+'.log')).open('w',encoding='utf8');logs.append(log)
            processes.append(subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
            deadline=time.monotonic()+40
            while True:
                if processes[-1].poll() is not None:raise RuntimeError(name+' fixture exited')
                try:
                    request=urllib.request.Request('http://127.0.0.1:'+('8873' if name=='sql' else str(ui_port)),
                        data=b'{"sql":"SELECT 1"}' if name=='sql' else None,
                        headers={'Content-Type':'application/json'})
                    with urllib.request.urlopen(request,timeout=1):break
                except OSError:
                    if time.monotonic()>deadline:raise RuntimeError(name+' startup timed out')
                    time.sleep(.2)
        for path in sys.argv[1:] or ['tests/test_crm_automation_publish_barrier.cjs','tests/test_crm_automation_publish_ui.cjs','tests/test_crm_email_v4_ui.cjs']:
            result=subprocess.run(['node',path],cwd=ROOT,env=env)
            if result.returncode:return result.returncode
        return 0
    finally:
        for process in reversed(processes):
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else:process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()
        for log in logs:log.close()


if __name__=='__main__':sys.exit(main())
