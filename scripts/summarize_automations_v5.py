"""Summarize owned local navigation evidence; never contacts live services."""
import hashlib,json,math,re,statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/automations-v5-evidence'
EXPECTED={f'{browser}-{steps}' for browser in ('chrome','msedge') for steps in (1,3,6,12)}
JOURNEYS={'os_to_overview_cold':'OS → Automations','overview_to_flow':'Overview → Flow','flow_to_overview':'Flow → Overview','flow_to_editor':'Flow → Edit Email','editor_to_flow':'Editor → Flow'}

def stats(values):
    return {'n':len(values),'p50':round(statistics.median(values),3),'p95':round(sorted(values)[math.ceil(.95*len(values))-1],3)} if values else {'n':0,'p50':None,'p95':None}

def pair(values):
    return f"{values['p50']:g} / {values['p95']:g} ms (n={values['n']})" if values['n'] else 'Not observed'

def flatten(data,key):return [item for group in data.values() for item in group.get(key,[])]

def main():
    OUT.mkdir(exist_ok=True)
    runs={variant:json.loads((ROOT/f'tmp/automations-v5-{variant}.json').read_text()) for variant in ('before','after')}
    sidebar={variant:json.loads((ROOT/f'tmp/automations-v5-{variant}-overview.json').read_text()) for variant in runs}
    for variant,data in runs.items():
        assert set(data)==EXPECTED,(variant,set(data))
        if variant=='after':
            for name,group in data.items():
                assert not group.get('failed_transitions'),name
                assert group['history_reload']=='PASS',name
                assert all(group['widths'].values()) and all(group['flow_widths'].values()),name
                assert len(group['width_navigation'])==7,name
        (OUT/f'{variant}-navigation.json').write_text(json.dumps(data,indent=2)+'\n')
        assert set(sidebar[variant])==EXPECTED
        (OUT/f'{variant}-overview.json').write_text(json.dumps(sidebar[variant],indent=2)+'\n')
        for name,samples in sidebar[variant].items():
            data[name]['os_to_overview_cold_click_to_ready']=[samples[0]['click_to_ready_ms']]
            data[name]['os_to_overview_cold_paints']=[samples[0]['paints']]
    summary={};lines=['All timings below are local trusted-click-to-ready measurements. p95 uses the','nearest rank; six samples per group make each group p95 its maximum. The aggregate','mixes browsers and stage counts, so the per-group table is also required. Baseline','failed transitions are excluded from successful timings and listed separately.','', '| Journey | Before p50/p95 | After p50/p95 | Median improvement |','|---|---|---|---|']
    for key,label in JOURNEYS.items():
        a=stats(flatten(runs['before'],key+'_click_to_ready'));b=stats(flatten(runs['after'],key+'_click_to_ready'))
        gain=round((1-b['p50']/a['p50'])*100,1)
        summary[key]={'before':a,'after':b,'median_improvement_percent':gain}
        lines.append(f'| {label} | {pair(a)} | {pair(b)} | {gain:g}% |')
    lines+=['','The OS entry is a cold **session route** with authentication already supplied by','the fixture. It is not a fully cold process or real login. Flow first opens are','the first attempt per group; repeated opens are attempts 2–6. Resource/preview','caches persist within each owned server, so later browser groups are not globally','cold. Baseline editor failures reduce the successful sample count.','', '| Browser / stages | Before repeated Flow p50/p95 | After repeated Flow p50/p95 | After first Flow | After Back p50/p95 |','|---|---|---|---|---|']
    for name in runs['after']:
        a=stats(runs['before'][name]['overview_to_flow_click_to_ready'][1:]);b=stats(runs['after'][name]['overview_to_flow_click_to_ready'][1:])
        first=runs['after'][name]['overview_to_flow_click_to_ready'][0]
        back=stats(runs['after'][name]['flow_to_overview_click_to_ready'])
        lines.append(f'| {name} | {pair(a)} | {pair(b)} | {first} ms | {pair(back)} |')
    lines+=['','| After journey / observed phase | p50/p95 |','|---|---|']
    paints={}
    for key,label in JOURNEYS.items():
        paints[key]={}
        for phase in ('accepted','shell','first','all','optional'):
            s=stats([p[phase] for p in flatten(runs['after'],key+'_paints') if phase in p]);paints[key][phase]=s
            lines.append(f'| {label} / {phase} | {pair(s)} |')
    feedback=stats([v['feedback_ms'] for samples in sidebar['after'].values() for v in samples if isinstance(v.get('feedback_ms'),(float,int))])
    flowfeedback=stats([x for x in flatten(runs['after'],'flow_feedback_ms') if isinstance(x,(float,int))])
    lines+=['',f"Sidebar feedback: {pair(feedback)}. Flow-link busy feedback: {pair(flowfeedback)}.",
            'OS entry phases and readiness come from a dedicated paired pass that waits',
            'for the shared opaque loading overlay to clear. Original navigation-run OS',
            'DOM-only observations are preserved but do not supply the reported OS timings.',
            '`accepted` observes the server-rendered route marker matching both URL fields;',
            'it combines transport, route processing and the synthetic account permission gate.',
            'Authentication, imports, toolbar construction and render reconciliation cannot be',
            'separated into independent wall-clock phases by this instrumentation. `shell`',
            'includes the truthful opening status; `first` is the first stage/row/input;',
            '`all` observes all Edit buttons for Flow, while ready additionally waits for',
            'Save draft. Optional observations can precede ready and do not measure every',
            'provider/preview task. The raw evidence retains missing phases explicitly.',
            '', '| Journey | Before document navigations / new WebSockets | After document navigations / new WebSockets | After app starts / completed renders |',
            '|---|---|---|---|']
    for key,label in JOURNEYS.items():
        d=[sum(flatten(runs[v],key+'_documents')) for v in ('before','after')]
        w=[sum(flatten(runs[v],key+'_websockets')) for v in ('before','after')]
        full=sum(flatten(runs['after'],key+'_full_runs'))
        complete=0
        if key=='os_to_overview_cold':
            full=sum(values[0]['app_run_starts'] for values in sidebar['after'].values())
            complete=sum(values[0]['completed_app_runs'] for values in sidebar['after'].values())
        else:assert full==0
        lines.append(f'| {label} | {d[0]} / {w[0]} | {d[1]} / {w[1]} | {full} / {complete} |')
    settlements={v:[g['full_runs_during_settlement'] for g in runs[v].values()] for v in runs}
    warm_sidebar={variant:stats([s['click_to_ready_ms'] for samples in sidebar[variant].values() for s in samples[1:]]) for variant in runs}
    lines+=['',f'Warm sidebar → overview entry: before {pair(warm_sidebar["before"])}; after {pair(warm_sidebar["after"])}.',
            'These are two subsequent real Dashboard → Automations entries per browser/stage group.']
    failures=[{'group':name,**failure} for name,g in runs['before'].items() for failure in g.get('failed_transitions',[])]
    lines+=['',f'Background overview settlement over 4.5 seconds: before {settlements["before"]}; after {settlements["after"]} full-app runs.',
            'Before document navigation necessarily restarts the session; the baseline',
            'did not independently instrument every same-document app rerun per action.',
            'The original fixture counter includes interrupted app starts. Dedicated sidebar',
            'instrumentation separately counts starts and completed renders; scoped Flow',
            'transitions have zero starts and therefore zero completed full-app renders.',
            'Browser reload deliberately creates a new document/socket and is',
            'tested separately from route transitions.', '',f'Baseline failed transitions: `{json.dumps(failures)}`. Recovery waits/reloads are',
            'not counted as successful measurements. Revised transitions all complete.',
            '', '### Database and connection observations', '',
            'The following totals cover the entire run, including optional reads, retries,',
            'history/reload checks and width probes. After has extra width navigation checks;',
            'these totals are not matched per-click query counts or a connection speed comparison.',
            'Connection acquisition is the synthetic wrapper factory; BEGIN measures local',
            'lock/HTTP overhead. Neither measures production TCP/TLS or connection pooling.',
            '', '| Run / operation | Calls | p50/p95 duration |','|---|---|---|']
    database={}
    for variant in runs:
        log=(ROOT/f'tmp/automations-v5-{variant}-server.log').read_text(encoding='utf8')
        groups={}
        for category,duration in re.findall(r'V5_DB_QUERY kind=(\w+) duration_ms=([\d.]+)',log):groups.setdefault(category,[]).append(float(duration))
        for category,tag in (('connection_factory','CONNECTION'),('begin','BEGIN')):
            groups[category]=[float(x) for x in re.findall(r'V5_DB_'+tag+r' duration_ms=([\d.]+)',log)]
        database[variant]={k:stats(v) for k,v in groups.items()}
        for category,values in database[variant].items():lines.append(f'| {variant} / {category} | {values["n"]} | {pair(values)} |')
    lines+=['', 'Within a fresh native display render, the essential definition is read once',
            'and shared with its toolbar/sequence. A warm existing display row requires one',
            'freshness statement instead of another full-definition statement; mutation',
            'paths still verify fresh data. Each uncached overview identity operation uses',
            'one connection and three statements (two local timeout settings and SELECT);',
            'psycopg pipelines those statements on production. Session hits within the',
            'existing 30-second identity TTL use no identity SQL. Counts, delivery, attribution,',
            'recent activity, publication reconciliation and stage analytics remain secondary.',
            'Definition freshness and publication/draft status are still authoritative gates.',
            '', 'The local results show achieved and missed targets directly; do not infer',
            'production target attainment from this table. Large Flow construction and',
            'Streamlit widget transport/reconciliation remain material after the database',
            'read has returned. No isolated profiler result proves a universal framework floor.']
    (OUT/'summary.json').write_text(json.dumps({'journeys':summary,'warm_sidebar':warm_sidebar,'paints':paints,'sidebar_feedback':feedback,'flow_feedback':flowfeedback,'database':database,'baseline_failures':failures,'settlements':settlements},indent=2)+'\n')
    report=ROOT/'docs/AUTOMATIONS_V5_INSTANT_NAVIGATION_PERFORMANCE.md'
    text=report.read_text(encoding='utf8')
    start=text.index('## Measurements\n');end=text.index('## Production read-only observations')
    report.write_text(text[:start]+'## Measurements\n\n'+'\n'.join(lines)+'\n\n'+text[end:],encoding='utf8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
