import sys,json,time,statistics,threading,os
from pathlib import Path
import psutil
meta=json.loads((Path(__file__).resolve().parents[3]/'v8-baseline-overlay.json').read_text())
root=Path(meta['task']['worktree_path']);task=meta['task']['id'];owner=meta['task']['owner'];task_home=root.parent
phase=sys.argv[1]
code_root=Path(meta['source_worktree']) if phase=='before-final' else root
sys.path.insert(0,str(code_root/'scripts/studio'))
import studio,drafts,preview_runtime,preview_boundary,editor,page_catalog
registry=studio.read(task_home/'.studio/registry.json')
draft=next((d for d in registry.get('drafts',[]) if d['task_id']==task),None)
if not draft:draft=drafts.new(task_home,task,owner,'Disposable performance acceptance')
preview=preview_runtime.Preview(task_home,task,owner)
metrics={'phase':phase,'scope':'Real Windows Docker and synthetic OS in new isolated CORE worktree','timings':{},'docker_calls':[]}
original=preview_boundary.docker
def measured(*args,**kwargs):
    started=time.perf_counter()
    try:return original(*args,**kwargs)
    finally:metrics['docker_calls'].append({'operation':args[0],'seconds':round(time.perf_counter()-started,4)})
preview_boundary.docker=measured
def timed(label,fn):
    started=time.perf_counter();result=fn();duration=time.perf_counter()-started
    metrics['timings'].setdefault(label,[]).append(round(duration,4))
    print(json.dumps({'phase':phase,'operation':label,'seconds':round(duration,4)}),flush=True)
    return result
before=(root/'app.py').read_bytes()
try:
    frame=timed('cold_start',preview.start)
    if phase!='before-final':
        container=preview.container_id
        timed('warm_start',preview.start)
        assert preview.container_id==container
    for _ in range(3):timed('frame',lambda:preview.event({'action':'frame'}))
    timed('login',lambda:preview.event({'action':'login-synthetic'}))
    pages=page_catalog.pages(root)
    targets=[p for p in pages if p['key'] in ('home','developer_studio')]
    if len(targets)<2:targets=[p for p in pages if p['key']!='__signin__'][:2]
    metrics['navigation_pages']=[p['key'] for p in targets]
    for p in targets*2:timed('navigate',lambda p=p:preview.event({'action':'navigate','page':p['key']}))
    for mode in ('desktop','tablet','mobile','desktop'):
        frame=timed('resize',lambda mode=mode:preview.event({'action':'size','mode':mode}))
        assert frame['width']=={'desktop':1280,'tablet':820,'mobile':390}[mode]
    opened=timed('editor_open',lambda:editor.open_file(task_home,draft['id'],owner,'app.py'))
    metrics['visual_mappings']=list(opened['visual'])
    component=next(k for k,v in opened['visual'].items() if 'text' in v)
    original_text=opened['visual'][component]['text']
    changed=timed('save_only',lambda:editor.write(task_home,draft['id'],owner,'app.py',opened['hash'],opened['revision'],component=component,changes={'text':original_text+' perf acceptance'}))
    timed('source_to_preview',lambda:preview.refresh_source(['app.py']))
    reopened=editor.open_file(task_home,draft['id'],owner,'app.py')
    editor.write(task_home,draft['id'],owner,'app.py',reopened['hash'],reopened['revision'],component=component,changes={'text':original_text})
    timed('source_to_preview',lambda:preview.refresh_source(['app.py']))
    process=psutil.Process();tree=[process,*process.children(recursive=True)];start_cpu=sum(sum(p.cpu_times()[:2]) for p in tree)
    def container_cpu():
        data=original('exec',preview.name,'cat','/sys/fs/cgroup/cpu.stat').stdout
        return int(next(line.split()[1] for line in data.splitlines() if line.startswith('usage_usec ')))
    cpu_before=container_cpu();started=time.monotonic();time.sleep(10);cpu_after=container_cpu();elapsed=time.monotonic()-started
    stats=json.loads(original('stats','--no-stream','--format','{{json .}}',preview.name).stdout)
    metrics['idle']={'sample_seconds':round(elapsed,2),'host_cpu_seconds':round(sum(sum(p.cpu_times()[:2]) for p in tree)-start_cpu,4),'host_rss_bytes':sum(p.memory_info().rss for p in tree),'host_processes':len(tree),'container_average_cpu_percent':round((cpu_after-cpu_before)/1000000/elapsed*100,3),'container':{k:stats.get(k) for k in ('CPUPerc','MemUsage','PIDs')}}
    timed('stop',preview.stop)
    timed('repeat_cold_start',preview.start)
finally:
    if preview.name:preview.stop()
    assert (root/'app.py').read_bytes()==before,'Acceptance source bytes not restored'
    metrics['source_restored']=True
    metrics['summary']={k:round(statistics.median(v),4) for k,v in metrics['timings'].items()}
    report=root/'docs'/('v8-performance-'+phase+'.json');report.write_text(json.dumps(metrics,indent=2))
    print(json.dumps({'report':str(report),'summary':metrics['summary'],'idle':metrics.get('idle')}),flush=True)
