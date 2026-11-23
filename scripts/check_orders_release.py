"""Offline release gate. No deployment, credentials, pairing or supplier actions."""
import argparse,json,os,re,subprocess,sys,time
from pathlib import Path

PYTHON=['test_prodigi_upload_recovery.py','test_prodigi_handoff_recovery.py','test_prodigi_first_prices.py','test_prodigi_reset_selection.py',
 'test_prodigi_verified_sibling.py','test_inbox_companion.py','test_prodigi_product_browser.py','test_prodigi_browser.py','test_prodigi_dashboard_qa.py',
 'test_prodigi_order_group.py','test_prodigi_submission.py','test_prodigi_stage.py','test_prodigi_reset.py',
 'test_orders_fast_handoffs.py','test_orders_runtime.py','test_orders_qa_scaling.py','test_orders_prodigi_grid.py',
 'test_orders_feed.py','test_orders_fragment_context.py','test_orders_wake.py','test_orders_auto_jpg.py','test_companion_poll_transaction.py','test_orders_release_package.py']
NODE=['test_prodigi_upload_recovery.cjs','test_prodigi_signin.cjs','test_inbox_companion.cjs','test_orders_progress.cjs','test_prodigi_wait.cjs','test_orders_fault_soak.cjs','test_prodigi_browser.cjs',
 'test_orders_companion.cjs','test_prodigi_dashboard_qa.cjs','test_orders_wake.cjs','test_queue_wake_lifetime.cjs',
 'test_upload_companion_worker_lifetime.cjs','test_upload_companion_origin.cjs','test_orders_live_feed.cjs',
 'test_orders_row_patching.cjs','test_orders_grid_ui.cjs']

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pglite',default=os.getenv('AUTO_EDITIONS_TEST_PGLITE',''))
    parser.add_argument('--evidence',required=True)
    args=parser.parse_args()
    if not args.pglite or not Path(args.pglite).is_file():parser.error('A disposable local PGlite runtime is required; database tests may not be skipped.')
    root=Path(__file__).resolve().parents[1];out=Path(args.evidence).resolve();out.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'PYTHONPATH':os.pathsep.join([str(root),str(root/'tests')]),'AUTO_EDITIONS_TEST_PGLITE':str(Path(args.pglite).resolve()),'PYTHONIOENCODING':'utf-8'}
    report=dict(version=json.loads((root/'windows-upload-companion/manifest.json').read_text())['version'],
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),suites={},benchmarks=[])
    commands={'python':[sys.executable,'-m','pytest',*[str(root/'tests'/p) for p in PYTHON],'-q','-s'],
        'node':['node','--test',*[str(root/'tests'/p) for p in NODE]],
        'topology':[sys.executable,str(root/'scripts/validate_render_topology.py')]}
    passed=True
    for name,command in commands.items():
        started=time.monotonic()
        run=subprocess.run(command,cwd=root,env=env,text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=900)
        output=run.stdout+'\n'+run.stderr;(out/(name+'.log')).write_text(output,encoding='utf-8')
        skipped=bool(re.search(r'\b\d+ skipped\b',output))
        result=dict(exit_code=run.returncode,elapsed_s=round(time.monotonic()-started,2),skipped=skipped)
        report['suites'][name]=result;passed=passed and run.returncode==0 and not skipped
        for line in output.splitlines():
            if 'QA_BENCH ' in line:report['benchmarks'].append(json.loads(line.split('QA_BENCH ',1)[1]))
        print(name+': '+json.dumps(result),flush=True)
    report['passed']=passed
    (out/'release-gate.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Evidence: '+str(out/'release-gate.json'))
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
