"""Own local fixture processes only. Denies production operations in fixtures."""
import json,os,socket,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

def main():
    ROOT.joinpath('tmp').mkdir(exist_ok=True)
    sql_port,ui_port=port(),port()
    env={**os.environ,'CRM_TEST_POSTGRES':'1','CRM_FIXTURE_SQL_PORT':str(sql_port),
         'FLOW_V4_OPERATIONS_PORT':str(ui_port),'CRM_THUMBNAIL_BROWSER_CHANNEL':'chrome',
         'CRM_THUMBNAIL_CACHE_DIR':str(ROOT/'tmp'/'flow-v4-browser-cache'),
         'PYTHONPATH':str(ROOT),'PYTHONUTF8':'1'}
    children=[];logs=[]
    def start(command,name,process_env=None):
        log=open(ROOT/'tmp'/name,'w',encoding='utf8');logs.append(log)
        p=subprocess.Popen(command,cwd=ROOT,env=process_env or env,stdout=log,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));children.append(p);return p
    def wait(url,p,body=None):
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            if p.poll() is not None:raise RuntimeError('Local fixture exited; inspect tmp logs.')
            try:
                request=urllib.request.Request(url,data=body,headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request,timeout=1):return
            except OSError:time.sleep(.1)
        raise RuntimeError('Local fixture did not start.')
    try:
        if '--visual' in sys.argv:
            before_port,after_port=port(),port()
            env.update(FLOW_V4_BEFORE_PORT=str(before_port),FLOW_V4_AFTER_PORT=str(after_port))
            for baseline,p in ((True,before_port),(False,after_port)):
                process_env={**env,'FLOW_V4_BASELINE':'1' if baseline else '0',
                    'CRM_THUMBNAIL_CACHE_DIR':str(ROOT/'tmp'/('flow-v4-visual-before' if baseline else 'flow-v4-visual-after'))}
                ui=start([sys.executable,'-m','streamlit','run','tests/fixtures/crm_flow_v4_preview.py',
                    '--server.address=127.0.0.1',f'--server.port={p}',
                    '--server.headless=true','--browser.gatherUsageStats=false'],f'flow-v4-visual-{baseline}.log',process_env)
                wait(f'http://127.0.0.1:{p}/_stcore/health',ui)
            return subprocess.run([sys.executable,'tests/check_crm_flow_v4_ui.py'],cwd=ROOT,env=env,timeout=600).returncode
        sql=start(['node','tests/crm_postgres_server.mjs'],'flow-v4-sql.log')
        wait(f'http://127.0.0.1:{sql_port}',sql,json.dumps({'sql':'SELECT 1'}).encode())
        ui=start([sys.executable,'-m','streamlit','run','tests/fixtures/crm_automation_preview.py',
             '--server.address=127.0.0.1',f'--server.port={ui_port}',
             '--server.headless=true','--browser.gatherUsageStats=false'],'flow-v4-operations-server.log')
        wait(f'http://127.0.0.1:{ui_port}/_stcore/health',ui)
        for channel in ('chrome','msedge'):
            env['FLOW_V4_CHANNEL']=channel
            result=subprocess.run([sys.executable,'tests/check_crm_flow_v4_operations.py'],cwd=ROOT,env=env,timeout=300)
            if result.returncode:return result.returncode
        return 0
    finally:
        for p in reversed(children):
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.wait()
        for log in logs:log.close()

if __name__=='__main__':sys.exit(main())
