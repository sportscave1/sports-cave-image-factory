"""Owned loopback SQL and real routed Streamlit harness; no live services."""
import json, os, socket, subprocess, sys, time, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def main():
    sql_port,ui_port=port(),port();children=[];logs=[]
    variant='before' if '--before' in sys.argv else 'after'
    label='faults' if '--faults' in sys.argv else variant+'-overview' if '--overview-paint' in sys.argv else variant
    env={**os.environ,'CRM_TEST_POSTGRES':'1','CRM_FIXTURE_SQL_PORT':str(sql_port),
         'AUTOMATIONS_V5_PORT':str(ui_port),'AUTOMATIONS_V5_VARIANT':variant,
         'AUTOMATIONS_V5_BASELINE':'1' if variant=='before' else '0',
         'CRM_THUMBNAIL_CACHE_DIR':str(ROOT/'tmp'/('automations-v5-'+variant+'-cache')),
         'PYTHONPATH':os.pathsep.join(filter(None,[os.environ.get('PYTHONPATH'),str(ROOT)])),'PYTHONUTF8':'1'}
    def start(command,label):
        log=open(ROOT/'tmp'/('automations-v5-'+('faults' if '--faults' in sys.argv else variant+'-overview' if '--overview-paint' in sys.argv else variant)+'-'+label+'.log'),'w',encoding='utf8');logs.append(log)
        p=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));children.append(p);return p
    def wait(url,p,data=None):
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            if p.poll() is not None:raise RuntimeError('Fixture exited: inspect logs')
            try:
                with urllib.request.urlopen(urllib.request.Request(url,data=data,headers={'Content-Type':'application/json'}),timeout=1):return
            except OSError:time.sleep(.1)
        raise RuntimeError('Fixture startup timed out')
    try:
        sql=start(['node','tests/crm_postgres_server.mjs'],'sql');wait(f'http://127.0.0.1:{sql_port}',sql,b'{"sql":"SELECT 1"}')
        ui=start([sys.executable,'-m','streamlit','run','tests/fixtures/automation_v5_routed.py','--server.address=127.0.0.1',f'--server.port={ui_port}','--server.headless=true','--browser.gatherUsageStats=false','--global.developmentMode=false'],'server')
        wait(f'http://127.0.0.1:{ui_port}/_stcore/health',ui)
        check='tests/check_automations_v5_faults.py' if '--faults' in sys.argv else 'tests/check_automations_v5_overview_paint.py' if '--overview-paint' in sys.argv else 'tests/check_automations_v5.py'
        return subprocess.run([sys.executable,check],cwd=ROOT,env=env,timeout=900).returncode
    finally:
        for p in reversed(children):
            if p.poll() is None:
                if os.name=='nt':
                    # venv Python launchers have a physical child interpreter.
                    # Stop only this recorded Popen tree, including renderers.
                    subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
                else:p.terminate()
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.wait()
        for log in logs:log.close()
if __name__=='__main__':sys.exit(main())
