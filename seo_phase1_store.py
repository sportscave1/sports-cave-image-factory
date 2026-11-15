"""Transactional adapters over existing SEO JSON and legacy workflow records."""
from copy import deepcopy
import json
import seo_workspace as workspace
import seo_phase1 as model
import os_accounts

TASK_TO_PLAN = {'approved':'Open','assigned':'In progress','in_progress':'In progress','ready_for_review':'Ready for review','deferred':'Deferred','completed':'Done','measuring':'Done','measured':'Done','cancelled':'Dismissed'}
PLAN_TO_TASK = {'Open':'approved','In progress':'in_progress','Ready for review':'ready_for_review','Deferred':'deferred','Done':'completed','Dismissed':'cancelled'}
RECOMMENDATION_TO_PLAN = {'draft':'Open','awaiting_approval':'Ready for review','approved':'Open','edited_and_approved':'Open','converted_to_task':'In progress','in_progress':'In progress','snoozed':'Deferred','rejected':'Dismissed','completed':'Done','measuring':'Done','measured':'Done'}
PLAN_TO_RECOMMENDATION = {'Open':'draft','In progress':'in_progress','Ready for review':'awaiting_approval','Deferred':'snoozed','Done':'completed','Dismissed':'rejected'}
DRAFT_TO_PLAN = {'Idea':'Open','Brief':'Open','Draft':'In progress','Ready for Owner':'Ready for review','Published':'Done','Archived':'Dismissed','Complete':'Done','Deferred':'Deferred'}
PLAN_TO_DRAFT = {'Open':'Brief','In progress':'Draft','Ready for review':'Ready for Owner','Deferred':'Deferred','Done':'Complete','Dismissed':'Archived'}
SOURCES = {'growth_task':'seo_growth_tasks','recommendation':'seo_growth_recommendations'}


def sync_sources(state, *, tasks=(), recommendations=(), actor=None):
    previous_events=deepcopy(state['workspace_events'])
    model.import_saved_work(state,tasks=tasks,recommendations=recommendations,actor=actor)
    state['workspace_events']=previous_events
    indexed={r.get('source_ref'):r for r in state['plan_items'] if r.get('source_ref')}
    for kind, records, mapping in (('growth_task',tasks,TASK_TO_PLAN),('recommendation',recommendations,RECOMMENDATION_TO_PLAN)):
        for source in records:
            row=indexed.get(kind+':'+str(source['id']))
            if not row: continue
            old=row.get('source_status')
            if old is not None and old!=source['status']:
                model.event(state,'Task change',row['id'],source='Legacy '+kind,detail={'from':old,'to':source['status'],'direction':'source to Plan'})
            row.update(status=mapping.get(source['status'],'Open'),source_status=source['status'],source_version=str(source.get('updated_at') or ''),source_edit_admin=True,
                title=source.get('title') or source.get('recommended_action') or row['title'],reason=source.get('reason') or row.get('reason',''),
                admin_only=kind=='growth_task' and source['status'] not in TASK_TO_PLAN)
    for row in state['plan_items']:
        ref=row.get('source_ref','')
        if ref.startswith('draft:'):
            draft=next((r for r in state['blog_records'] if r['id']==ref.split(':',1)[1]),None)
            if draft:
                row['status']=DRAFT_TO_PLAN.get(draft.get('status'),draft.get('workflow_status') or row['status'])
                row['source_status']=draft.get('status','')


def merge_changes(current, base, proposed):
    """Merge disjoint record edits, rejecting conflicting edits rather than losing work."""
    merged=deepcopy(current)
    for collection in workspace.SEO_COLLECTIONS:
        before={r['id']:r for r in base.get(collection,[]) if r.get('id')}
        live={r['id']:r for r in merged.get(collection,[]) if r.get('id')}
        for row in proposed.get(collection,[]):
            ident=row.get('id')
            if not ident or row==before.get(ident): continue
            existing=live.get(ident)
            if existing is not None and existing!=before.get(ident) and existing!=row:
                raise workspace.SEOStoreError('This record changed in another session. Reload before saving; your changes were not applied.')
            if collection=='plan_items' and row.get('status') not in model.CLOSED:
                duplicate=next((r for r in live.values() if r['id']!=ident and r.get('fingerprint')==row.get('fingerprint') and r.get('status') not in model.CLOSED),None)
                if duplicate: raise workspace.SEOStoreError('An equivalent open task was saved by another session. Reload Plan to open it.')
            live[ident]=deepcopy(row)
        merged[collection]=list(live.values())
    if proposed.get('settings')!=base.get('settings'):
        if current.get('settings')!=base.get('settings'):
            raise workspace.SEOStoreError('Settings changed in another session. Reload before saving.')
        merged['settings']=deepcopy(proposed['settings'])
    return merged


class SharedSEOStore(workspace.PostgresSEOStore):
    """JSON save and legacy transitions share one transaction and row lock."""
    def __init__(self, backend=None, *, user=None):
        super().__init__(backend)
        self.user=user or {}
        self.base=None
        self.raw_base=None
        self.source_errors=[]

    def ensure_schema(self):
        # Existing production tables must be prepared outside interactive requests.
        if self._schema_ready:return
        with self._backend().connect() as conn:
            row=conn.execute("SELECT to_regclass('seo_workspace_state') AS name").fetchone()
        if not row or not row['name']:
            raise workspace.SEOStoreError('SEO storage has not been prepared. Apply the existing SEO workspace migrations in the deployment process.')
        self._schema_ready=True

    def load(self):
        self.ensure_schema()
        with self._backend().connect() as conn:
            saved=conn.execute('SELECT payload FROM seo_workspace_state WHERE workspace_key=%s',(workspace.SEO_WORKSPACE_KEY,)).fetchone()
        state=workspace.normalise_state((saved or {}).get('payload') or {})
        self.raw_base=deepcopy(state)
        sources={}
        self.source_errors=[]
        for kind,table in SOURCES.items():
            try:
                with self._backend().connect() as conn:
                    records=conn.execute(f'SELECT * FROM {table} WHERE workspace_key=%s ORDER BY updated_at DESC LIMIT 1000',(workspace.SEO_WORKSPACE_KEY,)).fetchall()
                sources[kind]=workspace._json_safe(records)
            except Exception:self.source_errors.append(kind)
        sync_sources(state,tasks=sources.get('growth_task',()),recommendations=sources.get('recommendation',()),actor=self.user)
        self.base=deepcopy(state)
        return state

    def _sync_legacy(self, cur, before, row):
        ref=row.get('source_ref','')
        if ':' not in ref:return
        kind,ident=ref.split(':',1)
        if kind not in SOURCES:return
        changed=any(row.get(k)!=before.get(k) for k in ('status','title','reason','priority'))
        if not changed:return
        if not os_accounts.is_admin(self.user):
            raise workspace.SEOStoreError('Only an administrator can change an existing legacy task or proposal.')
        table=SOURCES[kind]
        source=cur.execute(f'SELECT * FROM {table} WHERE workspace_key=%s AND id=%s FOR UPDATE',(workspace.SEO_WORKSPACE_KEY,ident)).fetchone()
        if not source:raise workspace.SEOStoreError('The legacy source no longer exists. Reload Plan.')
        if str(workspace._json_safe(source.get('updated_at')) or '')!=before.get('source_version'):
            raise workspace.SEOStoreError('The legacy source changed in another session. Reload Plan before saving.')
        status=source['status']
        if row.get('status')!=before.get('status'):
            status=(PLAN_TO_TASK if kind=='growth_task' else PLAN_TO_RECOMMENDATION)[row['status']]
        if kind=='growth_task':
            saved=cur.execute("UPDATE seo_growth_tasks SET status=%s,title=%s,reason=%s,completed_at=CASE WHEN %s='completed' THEN COALESCE(completed_at,now()) WHEN %s NOT IN ('measuring','measured') THEN NULL ELSE completed_at END,updated_at=now() WHERE workspace_key=%s AND id=%s RETURNING *",(status,row['title'],row.get('reason',''),status,status,workspace.SEO_WORKSPACE_KEY,ident)).fetchone()
        else:
            if status in {'approved','edited_and_approved'}:
                status='awaiting_approval'
                row['status']='Ready for review'
            # Plan never grants internal content approval. Status/content edits invalidate it.
            saved=cur.execute("UPDATE seo_growth_recommendations SET status=%s,recommended_action=%s,reason=%s,priority=%s,approved_by='',approved_at=NULL,snoozed_until=CASE WHEN %s='snoozed' THEN CURRENT_DATE+14 ELSE NULL END,updated_at=now() WHERE workspace_key=%s AND id=%s RETURNING *",(status,row['title'],row.get('reason',''),row.get('priority',''),status,workspace.SEO_WORKSPACE_KEY,ident)).fetchone()
        row['source_status']=status
        row['source_version']=str(workspace._json_safe(saved['updated_at']))

    def save(self,state,*,actor_id=''):
        self.ensure_schema()
        if self.base is None:raise workspace.SEOStoreError('Load the workspace before saving.')
        proposed=workspace.normalise_state(workspace._json_safe(state))
        try:
            with self._backend().connect() as conn:
                cur=conn.cursor()
                # Also serialize the first insert, when no row exists to lock yet.
                cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('seo-phase1:'+workspace.SEO_WORKSPACE_KEY,))
                saved=cur.execute('SELECT payload FROM seo_workspace_state WHERE workspace_key=%s FOR UPDATE',(workspace.SEO_WORKSPACE_KEY,)).fetchone()
                current=workspace.normalise_state((saved or {}).get('payload') or {})
                # Source-derived wrappers are a view until the first save. Include them
                # in the proposed delta while comparing persisted records to raw_base.
                merged=merge_changes(current,self.raw_base,proposed)
                old={r['id']:r for r in self.base['plan_items']}
                for row in merged['plan_items']:
                    if row['id'] in old:self._sync_legacy(cur,old[row['id']],row)
                    ref=row.get('source_ref','')
                    if ref.startswith('draft:') and row.get('status')!=(old.get(row['id']) or {}).get('status'):
                        draft=next((d for d in merged['blog_records'] if d['id']==ref.split(':',1)[1]),None)
                        if draft:
                            draft['status']=PLAN_TO_DRAFT[row['status']]
                            draft['workflow_status']=row['status']
                            draft['updated_at']=workspace.utc_now()
                cur.execute("INSERT INTO seo_workspace_state(workspace_key,schema_version,payload,updated_by,updated_at) VALUES(%s,%s,%s::jsonb,%s,now()) ON CONFLICT(workspace_key) DO UPDATE SET payload=EXCLUDED.payload,updated_by=EXCLUDED.updated_by,updated_at=now()",(workspace.SEO_WORKSPACE_KEY,workspace.SEO_SCHEMA_VERSION,json.dumps(merged),actor_id))
            self.base=deepcopy(merged);self.raw_base=deepcopy(merged)
            self._cached_state=deepcopy(merged)
            return merged
        except workspace.SEOStoreError:raise
        except Exception as error:
            raise workspace.SEOStoreError('The workspace could not be saved. No legacy transition or Plan change was committed.') from error
