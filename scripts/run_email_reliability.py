"""Run CRM tests against a fresh loopback-only, in-memory PostgreSQL fixture.

No Supabase credentials are used. Shopify and Resend are mocked by the suites.
Each invocation destroys its own fixture when tests finish.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
MODULES=('checkout_queue_repair','checkout_enrollment_requests','checkout_eligibility',
         'checkout_reliability','automation_analytics','automation_timing','native_automations',
         'shopify_receiver_reliability','shopify_automation_triggers','campaign_v2','batch_dispatch',
         'send_flow','production_unsubscribe','native_unsubscribe','postgres','email_reliability',
         'automation_diagnostics','send_progress','home_live_progress','production_v2','checkout_progress')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all-crm',action='store_true')
    parser.add_argument('--modules',nargs='+',help='Specific unittest modules against a fresh fixture')
    args=parser.parse_args()
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    env={**os.environ,'CRM_TEST_POSTGRES':'1','CRM_FIXTURE_SQL_PORT':str(port),
         'TEMP':str(ROOT/'tmp'),'TMP':str(ROOT/'tmp')}
    server=subprocess.Popen(['node','tests/crm_postgres_server.mjs'],cwd=ROOT,env=env,
                            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        deadline=time.monotonic()+30
        while True:
            if server.poll() is not None:raise RuntimeError('Local SQL fixture failed to start.')
            try:
                req=urllib.request.Request(f'http://127.0.0.1:{port}',data=json.dumps({'sql':'SELECT 1'}).encode(),headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=1):break
            except OSError:
                if time.monotonic()>=deadline:raise RuntimeError('Local SQL fixture startup timed out.')
                time.sleep(.1)
        command=[sys.executable,'-m','unittest']
        command+=args.modules or (['discover','-s','tests','-p','test_crm_*.py'] if args.all_crm else ['tests.test_crm_'+name for name in MODULES]+['tests.test_sports_cave_worker'])
        return subprocess.run(command,cwd=ROOT,env=env).returncode
    finally:
        server.terminate()
        try:server.wait(timeout=5)
        except subprocess.TimeoutExpired:server.kill();server.wait()


if __name__=='__main__':sys.exit(main())
