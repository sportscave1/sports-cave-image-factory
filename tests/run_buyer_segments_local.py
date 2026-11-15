"""Credential-free, loopback-only combined regression runner."""
import os, sys, subprocess, time
from pathlib import Path

root=Path(__file__).resolve().parents[1]
out=root/'.tmp-product-sport-tags-v2'
keep={'PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','LOCALAPPDATA','APPDATA','PROGRAMFILES','PROGRAMFILES(X86)'}
env={k:v for k,v in os.environ.items() if k.upper() in keep}
env.update(TEMP=str(out),TMP=str(out),USERPROFILE=str(out/'profile'),HOME=str(out/'profile'),
           PYTHONPATH=str(root),PYTHONDONTWRITEBYTECODE='1',CRM_TEST_POSTGRES='1',CRM_FIXTURE_SQL_PORT='8898')
modules=sys.argv[1:] or ['tests.test_campaign_buyer_segments','tests.test_crm_campaign_v2',
    'tests.test_crm_campaign_v8','tests.test_crm_batch_dispatch','tests.test_crm_campaign_preparation',
    'tests.test_crm_campaigns_v1','tests.test_crm_campaign_loading','tests.test_crm_campaign_first_paint']
code='''import socket,unittest,sys,os
from unittest.mock import patch
original=socket.socket.connect
def guard(sock,address):
 if isinstance(address,tuple) and address[0] not in ('127.0.0.1','::1','localhost'):raise AssertionError('External network prohibited')
 return original(sock,address)
with patch.object(socket.socket,'connect',guard), patch('crm_thumbnail_cache.request',return_value=('LOADING',None)):
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:]))
 # AppTest leaves process-global Streamlit background executors alive. All test
 # tearDown methods have run; terminate this disposable child with the actual
 # result rather than wait for unrelated UI polling executors at interpreter exit.
 sys.stdout.flush();sys.stderr.flush()
 os._exit(int(not result.wasSuccessful()))
'''
log_path=out/('campaign-buyer-tests-'+str(time.time_ns())+'.log')
with log_path.open('w',encoding='utf-8') as log:
    result=subprocess.run([sys.executable,'-c',code,*modules],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
print('Combined campaign tests exit:',result.returncode)
print('Log:',log_path)
raise SystemExit(result.returncode)
