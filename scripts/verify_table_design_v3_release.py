"""Offline release gate. No production credentials or publishing operations."""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def stop(process):
    if process.poll() is None:
        if os.name == 'nt':
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else:
            process.terminate()
        process.wait(timeout=10)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dependency-root',type=Path,required=True)
    parser.add_argument('--phase',choices=['all','unit','browser'],default='all')
    args=parser.parse_args()
    scratch=ROOT/'tmp/table-v3-release-validation';scratch.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'PYTHONIOENCODING':'utf8','PYTHONPATH':str(ROOT),'TEMP':str(scratch),'TMP':str(scratch),
         'CRM_THUMBNAIL_BROWSER_CHANNEL':'chrome','STREAMLIT_BROWSER_GATHER_USAGE_STATS':'false'}
    results=[]
    def run(name,command,timeout=300):
        log=scratch/(name+'.log')
        with log.open('w',encoding='utf8') as output:
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:code=process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                stop(process);raise RuntimeError(f'{name} timed out; see {log}')
        result={'name':name,'exit_code':code,'log':str(log.relative_to(ROOT))}
        results.append(result)
        (scratch/'results.json').write_text(json.dumps(results,indent=2),encoding='utf8')
        print(name+': '+('PASS' if code==0 else 'FAIL'),flush=True)
        if code:
            known=json.loads((ROOT/'tests/fixtures/table_v3_known_baseline_failures.json').read_text())
            text=log.read_text(encoding='utf8')
            failures=re.findall(r'^(?:FAIL|ERROR): (.+)$',text,re.M)
            signature={'failures':failures,'assertions':re.findall(r'^AssertionError: (.+)$',text,re.M),
                       'ran':int(re.search(r'^Ran (\d+) tests?',text,re.M)[1]),
                       'summary':re.search(r'^FAILED .+$',text,re.M)[0]}
            if name not in known or signature!=known[name]:
                raise RuntimeError(f'{name} failed; see {log}')
            print(name+': matches documented pre-existing baseline failures; current behaviour gates remain mandatory',flush=True)
            result['baseline_failures']=failures
            (scratch/'results.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    if args.phase in ('all','unit'):
        dependency=Path('tests/fixtures/crm/node_modules/@electric-sql/pglite')
        if not (ROOT/dependency/'dist/index.js').exists():
            shutil.copytree(args.dependency_root/dependency,ROOT/dependency,dirs_exist_ok=True)
        for script in ['sync_table_design.py','validate_render_topology.py']:
            run(script,[sys.executable,'scripts/'+script]+(['--check'] if script.startswith('sync_') else []))
        suites=['test_table_design_v3','test_orders_compact','test_orders_row_deduplication',
                'test_orders_bounded_reader','test_orders_loading_ui','test_orders_prodigi_loading_repair',
                'test_edition_ops_table_editing','test_edition_ops_stability','test_edition_ops_new_product_pull',
                'test_edition_ops_complete_recovery','test_edition_ops_catalogue','test_edition_ops_allocation_integrity',
                'test_design_tracking','test_ads_creative_refresh','test_ads_posting_handoff',
                'test_meta_posting','test_meta_posting_repair','test_meta_posting_jobs','test_meta_posting_progress',
                'test_meta_carousel_posting','test_posting_import_csv',
                'test_crm_flow_settings_removed','test_crm_email_v5','test_crm_thumbnail_cache',
                'test_reporting_page','test_analytics_contracts','test_social_media_page','test_sidebar_theme','test_top_bar']
        # Independent AppTest processes avoid cross-suite Streamlit state leakage.
        for suite in suites:run(suite,[sys.executable,'-m','unittest','tests.'+suite])
        run('meta_review_all',[sys.executable,'-m','unittest','discover','-s','tests','-p','test_meta_review*.py'])
        run('crm_sql',[sys.executable,'scripts/run_email_reliability.py','--modules','tests.fixtures.crm_safety_without_thumbnail_workers','tests.test_crm_thumbnail_store'],timeout=360)
    if args.phase in ('all','browser'):
        run('table_chrome_edge',[sys.executable,'scripts/test_table_design_v3.py'],timeout=540)
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        env['META_REVIEW_FIXTURE_URL']=f'http://127.0.0.1:{port}'
        env['META_REVIEW_BENCH_PREFIX']='table-v3-release-meta'
        with (scratch/'meta-server.log').open('w',encoding='utf8') as log:
            server=subprocess.Popen([sys.executable,'-m','streamlit','run','tests/fixtures/meta_review_v3_preview.py',
                '--server.address','127.0.0.1','--server.port',str(port),'--server.headless','true'],cwd=ROOT,env=env,
                stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                deadline=time.monotonic()+40
                while True:
                    if server.poll() is not None:raise RuntimeError('Meta fixture stopped')
                    try:
                        with urllib.request.urlopen(env['META_REVIEW_FIXTURE_URL']+'/_stcore/health',timeout=1):break
                    except OSError:
                        if time.monotonic()>deadline:raise RuntimeError('Meta fixture startup timed out')
                        time.sleep(.2)
                run('meta_chrome_edge',[sys.executable,'tests/check_meta_review_v3_ui.py'],timeout=300)
            finally:stop(server)
        run('crm_checkout_browser',[sys.executable,'scripts/test_checkout_browser.py'],timeout=360)
    print('Release gate passed; '+str(sum(len(r.get('baseline_failures',[])) for r in results))+' documented baseline assertions remain unchanged.',flush=True)
    return 0

if __name__=='__main__':sys.exit(main())
