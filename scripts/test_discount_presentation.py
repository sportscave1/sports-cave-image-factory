"""Disposable loopback SQL plus mocked provider regression tests; no live writes."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def main():
    port=8898
    with socket.socket() as probe:probe.bind(('127.0.0.1',port))
    env={**os.environ,'CRM_TEST_POSTGRES':'1','CRM_FIXTURE_SQL_PORT':str(port),
         'PYTHONPATH':str(ROOT),'PYTHONUTF8':'1'}
    with (ROOT/'tmp/discount-presentation-sql.log').open('w',encoding='utf8') as log:
        process=subprocess.Popen(['node','tests/crm_postgres_server.mjs'],cwd=ROOT,env=env,
            stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            deadline=time.monotonic()+40
            while True:
                if process.poll() is not None:raise RuntimeError('Disposable SQL exited')
                try:
                    request=urllib.request.Request(f'http://127.0.0.1:{port}',data=b'{"sql":"SELECT 1"}',headers={'Content-Type':'application/json'})
                    with urllib.request.urlopen(request,timeout=1):break
                except OSError:
                    if time.monotonic()>deadline:raise RuntimeError('Disposable SQL startup timed out')
                    time.sleep(.2)
            runner="from unittest.mock import patch; import unittest; " \
                   "guard=patch('requests.sessions.Session.request',side_effect=AssertionError('External provider requests forbidden')); " \
                   "guard.start(); unittest.main(module=None)"
            tests=['tests.test_crm_discount_editor_v2','tests.test_crm_discounts',
                   'tests.test_crm_discount_delivery',*sys.argv[1:]]
            if '--baseline-sections' in sys.argv:
                runner='''import subprocess,sys,types
for name in ('crm_discount_section','crm_abandoned_checkout_ui'):
    module=types.ModuleType(name);module.__file__=name+'.py';sys.modules[name]=module
    exec(compile(subprocess.check_output(['git','show','HEAD:'+name+'.py']).decode('utf8'),module.__file__,'exec'),module.__dict__)
'''+runner
                tests=['tests.test_crm_campaign_sections.SectionPersistenceTests.test_ui_defaults_rerun_and_edits_persist_without_hidden_conversions']
            return subprocess.run([sys.executable,'-c',runner,*tests],cwd=ROOT,env=env).returncode
        finally:
            process.terminate();process.wait(timeout=5)

if __name__=='__main__':sys.exit(main())
