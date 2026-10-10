"""Own disposable local fixtures; never connect to production or reuse busy ports."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def main():
    mode=os.getenv('EMAIL_V6_MODE','campaign');ui=8556 if mode=='campaign' else 8557;sql=8896
    for port in (sql,ui):
        with socket.socket() as probe:probe.bind(('127.0.0.1',port))
    env={**os.environ,'CRM_TEST_POSTGRES':'1','CRM_FIXTURE_SQL_PORT':str(sql),'PYTHONUTF8':'1',
         'EMAIL_V6_MODE':mode,'EMAIL_V6_UI_PORT':str(ui),'EMAIL_V5_MEASURE':'1','CRM_THUMBNAIL_BROWSER_CHANNEL':'msedge'}
    processes=[];logs=[]
    try:
        for name,command,port in [('sql',['node','tests/crm_postgres_server.mjs'],sql),('ui',[sys.executable,'tests/fixtures/email_v6_server.py'],ui)]:
            log=(ROOT/'tmp'/('email-v6-'+name+'.log')).open('w',encoding='utf8');logs.append(log)
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0);processes.append(process)
            deadline=time.monotonic()+45
            while True:
                if process.poll() is not None:raise RuntimeError(name+' fixture exited; inspect tmp/email-v6-'+name+'.log')
                try:
                    request=urllib.request.Request('http://127.0.0.1:'+str(port),data=b'{"sql":"SELECT 1"}' if name=='sql' else None,headers={'Content-Type':'application/json'})
                    with urllib.request.urlopen(request,timeout=1):break
                except OSError:
                    if time.monotonic()>deadline:raise RuntimeError(name+' fixture startup timed out')
                    time.sleep(.2)
        for script in sys.argv[1:] or ['tests/test_crm_email_v6_ui.cjs']:
            result=subprocess.run(['node',script],cwd=ROOT,env=env)
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
