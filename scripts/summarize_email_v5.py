"""Summarize opt-in local V5 browser measurements; no network access."""
import json
import math
from pathlib import Path
import statistics
import re

def main():
    destination=Path('docs/email-performance-v5');destination.mkdir(exist_ok=True)
    summary={}
    for label in ('baseline-clean','current-clean'):
        data=json.loads(Path('tmp/email-v5-'+label+'.json').read_text(encoding='utf-8'))
        # Keep SQL shapes and timings, never query arguments or customer data.
        (destination/(label+'.json')).write_text(json.dumps(data,indent=2),encoding='utf-8')
        summary[label]={}
        for kind in ('cold','warm'):
            rows=[r for r in data['samples'] if r['kind']==kind]
            summary[label][kind]={}
            for key in ('firstUsefulMs','previewReadyMs','reads','dbWaitMs','editorTabMs','templatesMs','previewSwitchMs','backMs'):
                values=sorted(r[key] for r in rows)
                summary[label][kind][key]={'n':len(values),'p50':round(statistics.median(values),1),'p95':round(values[math.ceil(.95*len(values))-1],1)}
    old=json.loads(Path('docs/email-performance-v4/measurements.json').read_text(encoding='utf-8'))
    summary['v4_regressions']=old['regressions']
    summary['regression_runs']={}
    for label,file in (('baseline','email-v5-baseline-final.txt'),('final','email-v5-all-final.txt'),('focused','email-v5-focused-final.txt'),('final_popover','email-v5-popover-final.txt')):
        path=Path('tmp')/file
        if not path.exists():continue
        log=path.read_text(encoding='utf-8',errors='replace')
        result=re.search(r'Ran (\d+) tests in ([\d.]+)s',log)
        if not result:continue
        failures=re.findall(r'^FAIL: (.+)$',log,re.M);errors=re.findall(r'^ERROR: (.+)$',log,re.M)
        skip=re.search(r'skipped=(\d+)',log);skipped=int(skip[1]) if skip else 0
        summary['regression_runs'][label]={'run':int(result[1]),'seconds':float(result[2]),'failures':failures,'errors':errors,'skipped':skipped,'passed':int(result[1])-len(failures)-len(errors)-skipped}
    for label in ('baseline','final'):
        run=summary['regression_runs'].get(label)
        if run:run['failures_and_errors']=run['failures']+run['errors']
    runs=summary['regression_runs']
    if 'baseline' in runs and 'final' in runs:
        summary['new_regressions']=sorted(set(runs['final']['failures_and_errors'])-set(runs['baseline']['failures_and_errors']))
    for source,target in (('email-v5-saves-after.json','campaign-saves.json'),('email_v4_v5.json','publication-local.json')):
        path=Path('tmp')/source
        if path.exists():(destination/target).write_text(path.read_text(encoding='utf-8'),encoding='utf-8')
    (destination/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')

if __name__=='__main__':main()
