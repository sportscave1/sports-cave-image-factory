"""Local-first Worker Health read model and audited queue-claim control.

No provider requests, original files, customer allocations or approval writes.
"""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import hashlib,json,logging,math,os,re,statistics,time
from zoneinfo import ZoneInfo
import worker_diagnostics as diagnostics

CONTROL='auto-editions-worker-control'
STATES=('Live','Idle','Paused','Degraded','Failed','Offline','Recovering')


def telemetry_enabled():return os.getenv('WORKER_HEALTH_TELEMETRY_ENABLED','').lower()=='true'


def code_hash():
    return hashlib.sha256((Path(__file__).parent/'scripts/studio/auto_editions_local.py').read_text(encoding='utf-8-sig').replace('\r\n','\n').encode()).hexdigest()


def control(cur):
    cur.execute("""SELECT id,created_at,detail FROM auto_edition_onboarding_audit
        WHERE product_gid=%s AND event IN ('worker_paused','worker_resumed')
        ORDER BY created_at DESC,id DESC LIMIT 1""",(CONTROL,))
    row=cur.fetchone()
    return dict(paused=bool(row and row['detail'].get('paused')),requested_at=row['created_at'].isoformat() if row else None,audit_id=row['id'] if row else None)


def set_pause(connect,paused,actor):
    if type(paused) is not bool or not actor:raise ValueError('Identified pause/resume decision required.')
    from auto_editions_onboarding_store import Queue
    with connect() as conn,conn.cursor() as cur:
        cur.execute('LOCK TABLE auto_edition_onboarding IN SHARE ROW EXCLUSIVE MODE')
        old=control(cur)
        if old['paused']!=paused:
            Queue.audit(cur,CONTROL,actor,'worker_paused' if paused else 'worker_resumed',{'paused':paused})
        result=control(cur)
        cur.execute("""SELECT EXISTS(SELECT 1 FROM auto_edition_onboarding q WHERE lease_until>now()
            AND (status='Preparing' OR to_jsonb(q)->'replacement'->>'stage'='Preparing')) AS active""")
        active=cur.fetchone()['active']
    return {**result,'state':'Pausing' if paused and active else 'Paused' if paused else 'Resumed'}


def validate_heartbeat(value):
    allowed={'state','stage','revision','code_hash','protocol','product_gid','last_progress_at','retry_at','recovery_failures','checkpoint_pending','processor_lock','diagnostic'}
    if not isinstance(value,dict) or set(value)-allowed:raise ValueError('Bounded worker evidence required.')
    out={}
    for key,val in value.items():
        if key=='diagnostic':out[key]=diagnostics.accepted(val);continue
        if key=='state' and val not in STATES:raise ValueError('Invalid worker state.')
        if key=='stage' and val not in diagnostics.STAGES:raise ValueError('Invalid worker stage.')
        if key in ('code_hash','revision') and not re.fullmatch(r'[a-zA-Z0-9._-]{1,64}',str(val)):raise ValueError('Invalid worker version.')
        if key=='product_gid' and val is not None and not re.fullmatch(r'gid://shopify/Product/[1-9][0-9]*',str(val)):raise ValueError('Invalid product identity.')
        if key in ('last_progress_at','retry_at','recovery_failures','protocol') and (type(val) not in (int,float) or not math.isfinite(val) or not 0<=val<=10**11):raise ValueError('Invalid worker measurement.')
        if key in ('checkpoint_pending','processor_lock') and type(val) is not bool:raise ValueError('Invalid worker checkpoint flag.')
        out[key]=val
    return out


def record_heartbeat(connect,component,instance,value):
    value=validate_heartbeat(value)
    if component not in ('Render','Companion') or not re.fullmatch(r'[a-zA-Z0-9._-]{1,96}',instance):raise ValueError('Invalid heartbeat owner.')
    if not telemetry_enabled():return False
    try:
        with connect() as conn,conn.cursor() as cur:
            cur.execute('SELECT payload FROM auto_edition_worker_heartbeats WHERE component=%s AND instance_id=%s',(component,instance))
            old=cur.fetchone();old=old['payload'] if old else {}
            cur.execute("""INSERT INTO auto_edition_worker_heartbeats(component,instance_id,payload) VALUES(%s,%s,%s::jsonb)
                ON CONFLICT(component,instance_id) DO UPDATE SET payload=excluded.payload,seen_at=now()""",(component,instance,json.dumps(value)))
            changed=old.get('state')!=value.get('state') or old.get('recovery_failures')!=value.get('recovery_failures')
            if changed and (value.get('state') in ('Degraded','Recovering','Failed') or old.get('state')=='Recovering' and value.get('state') in ('Live','Idle')):
                resumed=old.get('state')=='Recovering' and value.get('state') in ('Live','Idle')
                detail=diagnostics.explain('owned recovery resumed' if resumed else '',value.get('stage','Unknown'),component)
                detail.update(value.get('diagnostic') or {})
                detail.update(revision=value.get('revision'),attempt=value.get('recovery_failures'),recovery_attempted=bool(value.get('retry_at') or resumed),
                    recovery_result='Recovered' if resumed else 'Retry scheduled' if value.get('retry_at') else 'Cause not yet determined',
                    next_retry_at=datetime.fromtimestamp(value['retry_at'],timezone.utc).isoformat() if value.get('retry_at') else None)
                from auto_editions_onboarding_store import Queue
                Queue.audit(cur,value.get('product_gid') or 'worker-'+component,'worker-health/'+component,'diagnostic',detail)
        return True
    except Exception as error:
        logging.getLogger(__name__).warning('worker_health_heartbeat_unavailable component=%s error_type=%s',component,type(error).__name__)
        return False # Optional telemetry cannot break an owned preparation.


def stamp(value):
    if value is None:return None
    if isinstance(value,str):
        try:value=datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError:return None
    if not isinstance(value,datetime):return None
    if value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
    return value


def sydney(value):
    value=stamp(value)
    return value.astimezone(ZoneInfo('Australia/Sydney')).strftime('%d %b %Y %H:%M:%S %Z') if value else None


def seconds(value,now):
    value=stamp(value)
    return max(0,(now-value).total_seconds()) if value else None


def project(rows,states,beats,successes,pause,*,now=None,expected_revision=None,telemetry_error=False):
    now=now or datetime.now(timezone.utc);expected_revision=expected_revision or os.getenv('RENDER_GIT_COMMIT','local')
    latest={}
    for row in beats:
        if row['component'] not in latest or stamp(row['seen_at'])>stamp(latest[row['component']]['seen_at']):latest[row['component']]=row
    subsystem=[]
    for component in ('Render','Companion'):
        heartbeat=latest.get(component);payload=heartbeat['payload'] if heartbeat else {}
        age=seconds(heartbeat['seen_at'],now) if heartbeat else None
        state='Offline' if age is not None and age>150 else 'Unavailable' if not heartbeat else payload.get('state','Live')
        why='No independent heartbeat recorded.' if not heartbeat else 'Missed heartbeat.' if age>150 else ''
        if state in ('Degraded','Failed','Recovering') and not why:why='Unhealthy worker cycle; inspect its diagnostic trace.'
        version=payload.get('revision')
        mismatch=(version not in (None,'local') and expected_revision!='local' and not expected_revision.startswith(version) and not version.startswith(expected_revision))
        if component=='Companion' and payload.get('code_hash') and payload['code_hash']!=code_hash():mismatch=True
        if mismatch and state!='Offline':state='Degraded';why='Worker/helper version differs from the application.'
        subsystem.append(dict(component=component,label='Windows Photoshop companion' if component=='Companion' else 'Render worker',status=state,
            last_seen=sydney(heartbeat['seen_at']) if heartbeat else None,age_seconds=age,revision=version,reason=why))
    counts={k:0 for k in ('eligible','completed','queued','active','failed','review','repair','unavailable','remaining')}
    jobs=[]
    for row in {r['product_gid']:r for r in rows}.values():
        state=states.get(row['product_gid'],{});label=state.get('status','Unavailable')
        auto_approved=state.get('approval_status')=='Auto Approved'
        eligible=bool(row.get('eligible'))
        if eligible:counts['eligible']+=1
        completed=eligible and bool(state.get('uploaded')) and label in ('Cloud Ready','Production Ready','Needs Review','Review')
        if completed:counts['completed']+=1
        validation_pending=label=='Preparing' and row['status']!='Preparing' and (row.get('replacement') or {}).get('stage')!='Preparing'
        category=('Active' if label in ('Preparing','Uploading','Recovering') else 'Queued' if label in ('Queued','Deferred','Connect') else
                  'Needs Review' if label in ('Review','Needs Review') else 'Completed' if label in ('Cloud Ready','Production Ready') else 'Failed')
        replacement_stage=(row.get('replacement') or {}).get('stage')
        preparation_owned=row['status']=='Preparing' or replacement_stage=='Preparing'
        lease_expired=bool(preparation_owned and (not row.get('lease_until') or stamp(row['lease_until'])<=now))
        if __import__('auto_editions_technical').enabled() and label=='Uploading':
            if (row['status']=='Awaiting preparation' or state.get('substage')=='Queued technical verification'
                    or replacement_stage in ('Discovering','Queued')):category='Queued'
            if lease_expired:
                category='Failed';label='Failed'
                state={**state,'reason':'Companion lease expired. Durable worker recovery is pending.'}
        if validation_pending:category='Queued';label='Queued'
        if category=='Queued' and not eligible:category='Failed';label='Needs Repair'
        if category=='Active':counts['active']+=1
        elif category=='Queued':counts['queued']+=1
        elif category=='Needs Review':counts['review']+=1
        elif label=='Needs Repair':counts['repair']+=1
        elif label=='Unavailable':counts['unavailable']+=1
        elif category=='Failed':counts['failed']+=1
        start=row.get('claimed_at');elapsed=seconds(start,now)
        finished=row.get('completed_at') if row.get('preparation_hash') else row.get('updated_at') if row['status'] in ('Blocked','Needs PSD Repair') else None
        measured=max(0,(stamp(finished)-stamp(start)).total_seconds()) if finished and start else None
        stage=row.get('reason') if row.get('reason') in diagnostics.STAGES else 'Preparing' if category=='Active' else 'Review' if category=='Needs Review' else 'Claimed' if category=='Queued' else 'Unknown'
        if __import__('auto_editions_technical').enabled() and state.get('substage'):stage=state['substage']
        if validation_pending:stage='Verifying'
        recorded={} if __import__('auto_editions_technical').enabled() and row.get('preparation_hash') else row.get('last_diagnostic') or {}
        if category=='Failed':stage=recorded.get('stage') if recorded.get('stage') in diagnostics.STAGES else stage
        proof_reason=state.get('reason') or row.get('reason')
        explanation=diagnostics.operator_details(proof_reason,stage,recorded.get('code') if category=='Failed' else None)
        if stage=='Unknown':stage='Stage unavailable'
        jobs.append(dict(id=row['product_gid'],design=str(row.get('product_title') or row['product_gid'])[:180],priority=row['priority'],
            stage=stage,status='Uploading' if __import__('auto_editions_technical').enabled() and category in ('Active','Queued') else 'Pending' if row.get('wh_requested') and row['status']=='Awaiting preparation' and category=='Queued' else 'Auto Approved' if auto_approved and label=='Cloud Ready' else label,approval_status=state.get('approval_status'),category=category,elapsed_seconds=elapsed if category=='Active' else None,duration_seconds=measured,
            last_activity=sydney(row.get('updated_at')),last_activity_iso=stamp(row['updated_at']).isoformat(),
            checkpoint=__import__('auto_editions_status').CHECKPOINTS.get(row.get('latest_checkpoint'),state.get('checkpoint') or 'No checkpoint'),reason=explanation['description'] if category=='Failed' else state.get('reason',''),
            diagnostic=explanation if category=='Failed' or explanation['code'] in ('PROFILE_MISSING','COLOUR_POLICY_PENDING','PROFILE_INSPECTOR_FAILURE','PROFILE_APPROVED','COLOUR_INCOMPATIBLE') else None,
            colour_recovered=bool(row.get('colour_recovered')),colour_affected=bool(row.get('colour_affected')),attempts=row['attempts'],completed=completed,
            validation_pending=validation_pending,actions=state.get('actions',[]),lease_expired=lease_expired))
        jobs[-1].update(retry_eligible=bool(eligible and row['status'] in ('Blocked','Needs PSD Repair') and not row.get('preparation_hash') and not (row.get('replacement') or {}).get('manual_required')),
            repair_required=row['status']=='Needs PSD Repair' or explanation['manual_repair'])
        if __import__('auto_editions_technical').enabled() and row.get('preparation_hash') and label=='Failed' and 'retry' in state.get('actions',[]):jobs[-1]['retry_eligible']=True
    counts['remaining']=counts['queued']+counts['active']
    current=next((j for j in jobs if j['category']=='Active'),None)
    durations=[float(s['duration_seconds']) for s in successes if s.get('duration_seconds') is not None and 1<=float(s['duration_seconds'])<=86400]
    last=successes[0] if successes else None
    eta=None;eta_label='Calculating'
    if pause['paused']:eta_label='Paused'
    elif not counts['remaining']:eta=0;eta_label='No runnable backlog'
    elif last and seconds(last['created_at'],now)>2700:eta_label='Unavailable'
    elif len(durations)>=3:
        typical=statistics.median(durations)
        elapsed=current.get('elapsed_seconds') or 0 if current else 0
        if current and elapsed>typical*2:eta_label='Unavailable'
        else:eta=typical*counts['queued']+(max(0,typical-elapsed) if current else 0);eta_label='Estimated runnable backlog'
    health_lookup={h['component']:h for h in subsystem}
    overall='Live' if current else 'Idle'
    if counts['remaining'] and health_lookup['Companion']['status']=='Offline':overall='Offline'
    starts=[stamp(r.get('claimed_at')) for r in rows if r.get('claimed_at')]
    last_output=stamp(last['created_at']) if last else min(starts) if starts else None
    stalled=bool(not pause['paused'] and counts['remaining'] and last_output and seconds(last_output,now)>2700)
    if any(h['status'] in ('Degraded','Offline','Unavailable','Failed','Recovering') for h in subsystem) or counts['unavailable'] or stalled or telemetry_error:
        if overall!='Offline':overall='Degraded'
    if counts['eligible'] and not counts['remaining'] and not counts['completed'] and counts['failed']+counts['repair']:
        overall='Failed'
    if pause['paused']:overall='Pausing' if current else 'Paused'
    if overall in ('Offline','Degraded','Failed') and counts['remaining']:eta=None;eta_label='Unavailable'
    if not pause['paused'] and any(j['validation_pending'] for j in jobs):eta=None;eta_label='Unavailable'
    expired=sum(j['lease_expired'] for j in jobs)
    recovery=latest.get('Companion',{}).get('payload',{})
    upload_fail=next((j for j in jobs if (j.get('diagnostic') or {}).get('code')=='UPLOAD_INTERRUPTED'),None)
    subsystem.extend([
        dict(component='Dropbox',label='Dropbox/cloud upload',status='Degraded' if upload_fail else 'Last verified' if last else 'Unavailable',
             last_seen=sydney(last['created_at']) if last else None,revision=None,
             reason='Recorded upload failure needs recovery.' if upload_fail else 'Last verified package receipt; no live provider probe.' if last else 'No verified upload checkpoint.'),
        dict(component='Database',label='Supabase/queue',status='Live',last_seen=sydney(now),revision=None,reason='Authoritative queue read succeeded.'),
        dict(component='Recovery',label='Automatic recovery',status='Unavailable' if health_lookup['Companion']['status'] in ('Offline','Unavailable') else 'Degraded' if expired or recovery.get('checkpoint_pending') or recovery.get('processor_lock') or recovery.get('recovery_failures',0)>=3 else 'Monitoring',
             last_seen=health_lookup['Companion']['last_seen'],revision=None,
             reason='Expired lease or retained checkpoint/lock requires recovery.' if expired or recovery.get('checkpoint_pending') or recovery.get('processor_lock') else 'No independent recovery heartbeat.' if not recovery else 'Existing bounded recovery and owned leases remain active.',
             retry_at=sydney(datetime.fromtimestamp(recovery['retry_at'],timezone.utc)) if recovery.get('retry_at') else None)
    ])
    warnings=[]
    if stalled:warnings.append('Worker has runnable jobs but no verified successful output in 45 minutes.')
    if current and (current['elapsed_seconds'] or 0)>900:warnings.append('Current job has no measured completion after 15 minutes; inspect its durable stage.')
    last_progress=recovery.get('last_progress_at')
    if current and recovery.get('product_gid')==current['id'] and last_progress and now.timestamp()-last_progress>900:
        warnings.append('Companion reports no stage change for 15 minutes; current-job progress is not measurable.')
        if overall not in ('Paused','Pausing','Offline'):overall='Degraded';eta=None;eta_label='Unavailable'
    if telemetry_error:warnings.append('Independent heartbeat telemetry unavailable; apply the reviewed migration/setting before relying on subsystem health.')
    jobs.sort(key=lambda j:({'Active':0,'Failed':1,'Needs Review':2,'Queued':3,'Completed':4}[j['category']],-j['priority'],j['design']))
    colour_codes={'PROFILE_MISSING','COLOUR_POLICY_PENDING','PROFILE_INSPECTOR_FAILURE','ICC_MISMATCH','COLOUR_INCOMPATIBLE','PROFILE_APPROVED'}
    affected=[j for j in jobs if j['colour_affected'] or (j.get('diagnostic') or {}).get('code') in colour_codes]
    repaired=sum(j['colour_recovered'] and j['completed'] for j in affected)
    return dict(colour=dict(affected=len(affected),repaired=repaired,remaining=len(affected)-repaired),
        overall=overall,current=current,counts=counts,progress=dict(completed=counts['completed'],total=counts['eligible'],
        ratio=counts['completed']/counts['eligible'] if counts['eligible'] else None,current_job_ratio=None),
        eta_seconds=eta,eta_label=eta_label,eta_samples=len(durations),last_completed=dict(design=last.get('product_title') or last['product_gid'],at=sydney(last['created_at'])) if last else None,
        updated_at=sydney(now),updated_at_iso=now.isoformat(),health=subsystem,warnings=warnings,control=pause,jobs=jobs,revision=expected_revision)


class Health:
    def __init__(self,connect):self.connect=connect

    def _read_snapshot(self,include_beats,after=''):
        with self.connect() as conn,conn.cursor() as cur:
            queue_sql="""SELECT q.product_gid,q.file_id,q.status,q.priority,q.reason,q.attempts,
                q.preparation_hash,q.lease_until,q.updated_at,to_jsonb(q)->'replacement' AS replacement,p.product_title,
                EXISTS(SELECT 1 FROM auto_edition_onboarding_audit ca WHERE ca.product_gid=q.product_gid AND ca.event='colour_retry') AS colour_affected,
                EXISTS(SELECT 1 FROM auto_edition_onboarding_audit ca WHERE ca.product_gid=q.product_gid AND ca.event='worker_health_queue_request') AS wh_requested,
                EXISTS(SELECT 1 FROM auto_edition_onboarding_audit ca WHERE ca.product_gid=q.product_gid AND ca.event='colour_recovered'
                    AND ca.detail->>'preparation_hash'=q.preparation_hash) AS colour_recovered,
                (m.dropbox_file_id=q.file_id AND p.edition_total BETWEEN 1 AND 1000 AND
                 (SELECT count(*) FROM edition_products other WHERE COALESCE(NULLIF(other.shopify_product_gid,''),other.shopify_product_id)=q.product_gid)=1) AS eligible,
                (SELECT created_at FROM auto_edition_onboarding_audit a WHERE a.product_gid=q.product_gid AND a.event='claimed' ORDER BY created_at DESC,id DESC LIMIT 1) AS claimed_at,
                (SELECT event FROM auto_edition_onboarding_audit a WHERE a.product_gid=q.product_gid AND a.event IN ('queued','mapping_confirmed','claimed','Preparing','Blocked','Cloud Ready','Needs PSD Repair','visual_quality_approved','preparation_metrics','retry','prepare_now') ORDER BY created_at DESC,id DESC LIMIT 1) AS latest_checkpoint,
                (SELECT created_at FROM auto_edition_onboarding_audit a WHERE a.product_gid=q.product_gid AND a.event='preparation_metrics' AND a.detail->>'preparation_hash'=q.preparation_hash ORDER BY created_at DESC,id DESC LIMIT 1) AS completed_at,
                (SELECT detail FROM auto_edition_onboarding_audit a WHERE a.product_gid=q.product_gid AND a.event='diagnostic'
                    AND a.created_at>=COALESCE((SELECT max(c.created_at) FROM auto_edition_onboarding_audit c WHERE c.product_gid=q.product_gid AND c.event='claimed'),q.created_at)
                    ORDER BY created_at DESC,id DESC LIMIT 1) AS last_diagnostic
                FROM auto_edition_onboarding q LEFT JOIN product_psd_mappings m ON m.shopify_product_gid=q.product_gid
                LEFT JOIN edition_products p ON COALESCE(NULLIF(p.shopify_product_gid,''),p.shopify_product_id)=q.product_gid
                WHERE q.product_gid>%s ORDER BY q.product_gid LIMIT 500"""
            successes_sql="""SELECT a.id,a.product_gid,p.product_title,a.created_at,
                EXTRACT(EPOCH FROM a.created_at-c.created_at) AS duration_seconds
                FROM auto_edition_onboarding_audit a
                LEFT JOIN edition_products p ON p.shopify_product_gid=a.product_gid
                LEFT JOIN LATERAL(SELECT created_at FROM auto_edition_onboarding_audit c
                    WHERE c.product_gid=a.product_gid AND c.event='claimed' AND c.created_at<=a.created_at
                    ORDER BY c.created_at DESC,c.id DESC LIMIT 1)c ON true
                WHERE a.event='preparation_metrics' ORDER BY a.id DESC LIMIT 20"""
            beats_sql="SELECT * FROM auto_edition_worker_heartbeats ORDER BY seen_at DESC LIMIT 16" if include_beats else "SELECT NULL WHERE false"
            cur.execute("""WITH queue_rows AS ("""+queue_sql+"""), successes AS ("""+successes_sql+"""),
                beats AS ("""+beats_sql+""") SELECT
                COALESCE((SELECT jsonb_agg(to_jsonb(q)) FROM queue_rows q),'[]'::jsonb) AS rows,
                COALESCE((SELECT jsonb_agg(to_jsonb(s)) FROM successes s),'[]'::jsonb) AS successes,
                COALESCE((SELECT jsonb_agg(to_jsonb(b)) FROM beats b),'[]'::jsonb) AS beats,
                COALESCE((SELECT jsonb_build_object('paused',COALESCE((detail->>'paused')::boolean,false),
                    'requested_at',created_at,'audit_id',id) FROM auto_edition_onboarding_audit
                    WHERE product_gid=%s AND event IN ('worker_paused','worker_resumed')
                    ORDER BY created_at DESC,id DESC LIMIT 1),
                    '{"paused":false,"requested_at":null,"audit_id":null}'::jsonb) AS pause""",(after,CONTROL))
            return dict(cur.fetchone())

    def snapshot(self):
        from auto_editions_status import batch
        start=time.perf_counter();enabled=telemetry_enabled();telemetry_error=not enabled;reads=1
        try:raw=self._read_snapshot(enabled)
        except Exception:
            if not enabled:raise
            # A missing optional heartbeat table must not hide authoritative jobs.
            # Retry in a NEW transaction after the failed optional read.
            raw=self._read_snapshot(False);telemetry_error=True;reads+=1
        rows=raw['rows'];beats=raw['beats'];successes=raw['successes'];pause=raw['pause']
        while len(raw['rows'])==500:
            raw=self._read_snapshot(False,raw['rows'][-1]['product_gid']);reads+=1;rows.extend(raw['rows'])
        state_rows=[];state_reads=0
        ids=list(dict.fromkeys(r['product_gid'] for r in rows))
        for index in range(0,len(ids),500):
            part=batch(self.connect,ids[index:index+500],writable=True,evidence=True)
            state_rows.extend(part['rows']);state_reads+=part['query_count']
        states=dict(rows=state_rows,query_count=state_reads)
        result=project(rows,{r['product_gid']:r for r in states['rows']},beats,successes,pause,telemetry_error=telemetry_error)
        result['cost']=dict(queries=reads+states['query_count'],dropbox_calls=0,duration_ms=round((time.perf_counter()-start)*1000,2))
        return result

    def logs(self,*,cursor=0,severity='',component='',design='',date_from='',date_to='',search=''):
        if severity not in ('','info','warning','error') or component not in ('',*diagnostics.COMPONENTS):raise ValueError('Invalid diagnostic filter.')
        if design and not re.fullmatch(r'gid://shopify/Product/[1-9][0-9]*',design):raise ValueError('Invalid design filter.')
        start=datetime.strptime(date_from,'%Y-%m-%d').replace(tzinfo=ZoneInfo('Australia/Sydney')) if date_from else datetime(2020,1,1,tzinfo=timezone.utc)
        end=datetime.strptime(date_to,'%Y-%m-%d').replace(tzinfo=ZoneInfo('Australia/Sydney'))+timedelta(days=1) if date_to else datetime.now(timezone.utc)+timedelta(days=1)
        # Cursor scans at most 200 indexed audit records per request, never an unbounded history.
        with self.connect() as conn,conn.cursor() as cur:
            cur.execute("""SELECT a.*,q.attempts,q.status AS current_status,p.product_title,
                (SELECT event FROM auto_edition_onboarding_audit prev WHERE prev.product_gid=a.product_gid
                    AND prev.id<a.id AND prev.event IN ('claimed','Preparing','recovering','preparation_metrics','visual_quality_approved')
                    ORDER BY prev.id DESC LIMIT 1) AS last_checkpoint
                FROM auto_edition_onboarding_audit a LEFT JOIN auto_edition_onboarding q ON q.product_gid=a.product_gid
                LEFT JOIN edition_products p ON p.shopify_product_gid=a.product_gid
                WHERE a.event IN ('diagnostic','Blocked','Needs PSD Repair','reset_failed','recovering','worker_paused','worker_resumed','colour_retry','colour_recovered','automatic_visual_assessment')
                  AND (%s=0 OR a.id<%s) AND a.created_at>=%s AND a.created_at<%s AND (%s='' OR a.product_gid=%s)
                  AND (a.event NOT IN ('Blocked','Needs PSD Repair') OR NOT EXISTS(SELECT 1 FROM auto_edition_onboarding_audit d WHERE d.product_gid=a.product_gid AND d.created_at=a.created_at AND d.event='diagnostic'))
                ORDER BY a.id DESC LIMIT 200""",(int(cursor),int(cursor),start,end,design,design))
            raw=[dict(r) for r in cur.fetchall()]
        out=[];scanned=None
        for row in raw:
            scanned=row['id'];detail=row['detail'] or {}
            if row['event'] in ('Blocked','Needs PSD Repair') and detail.get('preparation_hash'):continue
            value=diagnostics.explain(detail.get('reason'),detail.get('stage','Unknown'))
            if row['event']=='colour_retry':value=diagnostics.explain('Profile correction approved','Recovery')
            if row['event']=='diagnostic':
                try:value=diagnostics.accepted({k:detail[k] for k in ('code','stage','component') if k in detail})
                except ValueError:pass
            if row['event'] in ('worker_paused','worker_resumed','recovering'):
                value=dict(code=row['event'].upper(),component='Render' if row['event'].startswith('worker_') else 'Companion',stage='Recovery',
                    severity='info' if row['event'].startswith('worker_') else 'warning',description={'worker_paused':'Administrator paused new claims.','worker_resumed':'Administrator resumed new claims.','recovering':'Owned preparation is awaiting automatic recovery.'}[row['event']],recommended_action='No action required unless processing remains unhealthy.')
            if severity and value['severity']!=severity or component and value['component']!=component:continue
            if search and search.casefold() not in (str(row.get('product_title',''))+' '+value['description']+' '+value['code']).casefold():continue
            if value['stage']=='Unknown':value['stage']='Stage unavailable'
            out.append(dict(**value,id=row['id'],trace='AE-'+str(row['id']),timestamp=sydney(row['created_at']),
                product_gid=row['product_gid'],design=str(row.get('product_title') or 'Worker control')[:180],attempts=detail.get('attempt',row.get('attempts')),
                last_checkpoint=row.get('last_checkpoint'),revision=detail.get('revision') if re.fullmatch(r'[a-zA-Z0-9._-]{1,64}',str(detail.get('revision') or '')) else None,
                recovery_attempted=bool(detail.get('recovery_attempted') or row['event'] in ('recovering','colour_retry','colour_recovered')),
                recovery_result='Recovered' if row['event']=='colour_recovered' else detail.get('recovery_result') if detail.get('recovery_result') in ('Recovered','Retry scheduled','Cause not yet determined') else 'Awaiting next owned checkpoint' if row['event'] in ('recovering','colour_retry') else None,
                next_retry_at=sydney(detail['next_retry_at']) if detail.get('next_retry_at') else None,
                technical_error=diagnostics.technical_text(detail.get('reason') or detail.get('error') or detail.get('message')) or None))
            if len(out)==50:break
        return dict(rows=out,next_cursor=scanned if scanned and (len(out)==50 or len(raw)==200) else None,scanned=len(raw))
