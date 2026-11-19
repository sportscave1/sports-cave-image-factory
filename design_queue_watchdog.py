"""Durable progress tracking; a stalled design never monopolises the queue."""
import json
import time


def observe(cur, key, event):
    from datetime import timezone
    cur.execute('SELECT stage,updated_at FROM morning_design_jobs WHERE id=%s', (key,))
    job=cur.fetchone()
    if not job or job['stage']!=2:
        return
    activity=event.get('activity')
    if not isinstance(activity,str) or len(activity)>80:
        return
    setting='design_queue_progress:'+key
    cur.execute('SELECT value FROM app_settings WHERE key=%s',(setting,))
    saved=cur.fetchone()
    now=time.time()
    baseline=job['updated_at'].replace(tzinfo=job['updated_at'].tzinfo or timezone.utc).timestamp()
    state=saved['value'] if saved else {}
    if state.get('started_at')!=baseline:
        state=dict(activity=activity,changed_at=baseline,started_at=baseline)
    if state.get('activity')!=activity:
        state.update(activity=activity,changed_at=now)
        state.pop('finished_at',None)
    finished=event.get('finished') is True and event.get('generating') is False
    if finished:
        state.setdefault('finished_at',now)
    else:
        state.pop('finished_at',None)
    cur.execute('''INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now())
        ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()''',(setting,json.dumps(state)))
    if finished and now-state['finished_at']>=300:
        reason='ChatGPT finished, but a verified final Review delivery did not arrive within five minutes.'
    elif now-state['changed_at']>=1800:
        reason='No detectable ChatGPT progress for 30 minutes.'
    else:
        return
    cur.execute('''UPDATE morning_design_jobs SET stage=5,message=%s,updated_at=now()
        WHERE id=%s AND stage=2''',(reason+' Queue continues. Saved chat and files retained; no automatic resubmission. Late verified delivery will still be checked.',key))


def release_stalled(cur):
    """Missing browser reports must not bypass the durable inactivity deadline."""
    cur.execute('''SELECT j.id,j.stage,j.updated_at,p.value FROM morning_design_jobs j
        LEFT JOIN app_settings p ON p.key='design_queue_progress:'||j.id::text
        WHERE j.stage BETWEEN 2 AND 3''')
    now = time.time()
    for job in cur.fetchall():
        baseline = job['updated_at'].timestamp()
        state = job['value'] or {}
        state = state if state.get('started_at') == baseline else {}
        if state.get('finished_at') is not None and now-state['finished_at'] >= 300:
            reason = 'ChatGPT finished, but a verified final Review delivery did not arrive within five minutes.'
        elif now-state.get('changed_at', baseline) >= 1800:
            reason = 'No verified ChatGPT progress for 30 minutes, including unavailable browser reports.'
        else:
            continue
        cur.execute('''UPDATE morning_design_jobs SET stage=5,message=%s,updated_at=now()
            WHERE id=%s AND stage BETWEEN 2 AND 3''',
            (reason+' Queue continues. Saved chat and files retained; no automatic resubmission. Late verified delivery will still be checked.', job['id']))
