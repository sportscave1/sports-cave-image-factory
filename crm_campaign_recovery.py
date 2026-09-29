"""Durable editor checkpoints and per-user active draft; no delivery operations."""
from copy import deepcopy
from functools import wraps
import hashlib
import json
import uuid

from crm_campaign_content import validate_document
from crm_navigation import require
from crm_store import StoreUnavailable


def preference_key(user):
    require(user,'crm_campaigns_manage')
    actor=str(user.get('id') or user.get('username') or '')
    if not actor:raise PermissionError('Sign in before saving a campaign.')
    return 'campaign-editor:'+hashlib.sha256(actor.encode()).hexdigest()


def checkpoint(editor):
    return {'name':editor['name'],'document':deepcopy(editor['document'])}


def editable(store,identity):
    return store.q("""SELECT d.* FROM crm_campaign_drafts d WHERE d.id=%s
        AND d.archived_at IS NULL AND d.status IN ('DRAFT','TESTED','TEST_READY','NEEDS_REVIEW')
        AND NOT EXISTS(SELECT 1 FROM crm_campaigns c WHERE c.id=d.id)""",(str(uuid.UUID(str(identity))),),True)


def activate(store,user,identity):
    key=preference_key(user)
    if identity and not editable(store,identity):raise ValueError('Campaign is no longer editable.')
    store.set_state(key,{'last_active_campaign_id':str(identity) if identity else None})


def restore(store,user,explicit=None):
    identity=explicit or store.state(preference_key(user)).get('last_active_campaign_id')
    if not identity:return None
    try:return editable(store,identity)
    except ValueError:return None


def save_checkpoint(store,user,editor):
    """Atomic checkpoint + active pointer, optimistic locking and retry identity."""
    key=preference_key(user);doc=deepcopy(editor['document']);validate_document(doc)
    name=editor['name']
    if not isinstance(name,str) or len(name)>150:raise ValueError('Use a campaign name of at most 150 characters.')
    # The editor seed survives in the browser recovery record. A lost response
    # cannot create a second draft when the exact same first save is retried.
    seed=editor.setdefault('recovery_seed',uuid.uuid4().hex)
    identity=str(editor.get('id') or uuid.uuid5(uuid.NAMESPACE_URL,key+':'+seed))
    with store.db() as conn:
        conn.execute("INSERT INTO crm_runtime_state(key,value) VALUES(%s,'{}'::jsonb) ON CONFLICT DO NOTHING",(key,))
        conn.execute('SELECT key FROM crm_runtime_state WHERE key=%s FOR UPDATE',(key,))
        old=conn.execute('SELECT * FROM crm_campaign_drafts WHERE id=%s FOR UPDATE',(identity,)).fetchone()
        if old:
            if old['archived_at'] or old['status'] not in ('DRAFT','TESTED','TEST_READY','NEEDS_REVIEW') or conn.execute('SELECT 1 FROM crm_campaigns WHERE id=%s',(identity,)).fetchone():
                raise ValueError('Campaign is no longer editable. Your local recovery copy is retained.')
            if old['document']==doc and old['name']==name:row=old
            elif old['version']!=editor.get('version'):
                raise ValueError('A newer draft exists. Your edits are retained; reload the saved draft or save a separate recovery copy.')
            else:
                row=conn.execute("UPDATE crm_campaign_drafts SET name=%s,document=%s::jsonb,status='DRAFT',version=version+1,updated_at=now(),tested_version=NULL WHERE id=%s RETURNING *",(name,json.dumps(doc),identity)).fetchone()
        else:
            if editor.get('id'):raise ValueError('Draft is unavailable. Your local recovery copy is retained.')
            row=conn.execute("INSERT INTO crm_campaign_drafts(id,name,document,status,created_by) VALUES(%s,%s,%s::jsonb,'DRAFT',%s) RETURNING *",(identity,name,json.dumps(doc),str(user.get('id') or user.get('username')))).fetchone()
        if not old or row['version']!=old['version']:
            store._history(conn,row,'campaign_autosaved',str(user.get('id') or user.get('username')),old or {})
        conn.execute('UPDATE crm_runtime_state SET value=%s::jsonb,updated_at=now() WHERE key=%s',(json.dumps({'last_active_campaign_id':identity}),key))
    return row


def flush_current(*,force=False):
    import streamlit as st
    context=st.session_state.get('campaign_recovery_context');editor=st.session_state.get('campaign_editor')
    if not editor:return True
    if editor.get('recovery_readonly'):return True
    if not context:
        if st.session_state.get('campaign_persistence_unavailable'):
            st.session_state['campaign_save_status']='Save failed'
            st.session_state['campaign_save_error']='Persistence unavailable. Your work is retained; retry saving before leaving.'
            return False
        return True
    store,user=context
    saved=st.session_state.get('campaign_saved',{})
    if not force and saved and checkpoint(editor)==checkpoint(saved):return True
    try:
        updated=save_checkpoint(store,user,editor)
        editor.update(updated)
        st.query_params['campaign']=str(editor['id'])
        st.session_state['campaign_saved']=deepcopy(editor)
        st.session_state['campaign_save_status']='Saved'
        st.session_state.pop('campaign_save_error',None)
        return True
    except (ValueError,StoreUnavailable,PermissionError) as exc:
        st.session_state['campaign_save_status']='Save failed'
        st.session_state['campaign_save_error']=str(exc)
        return False


def autosaving(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        try:return fn(*args,**kwargs)
        finally:flush_current()
    return wrapped


def browser_checkpoint(store,user,editor,record):
    """A browser copy may advance only its own known server revision."""
    if not isinstance(record,dict) or record.get('scope')!=preference_key(user):raise ValueError('Recovery identity does not match.')
    recovered=record.get('editor')
    if not isinstance(recovered,dict):raise ValueError('Invalid recovery copy.')
    identity=recovered.get('id')
    if not identity and recovered.get('recovery_seed'):
        identity=str(uuid.uuid5(uuid.NAMESPACE_URL,preference_key(user)+':'+recovered['recovery_seed']))
    if identity:
        current=editable(store,identity)
        if not current and recovered.get('id'):raise ValueError('Recovery draft is no longer editable.')
        if current and current['version']!=recovered.get('version'):
            if checkpoint(current)==checkpoint(recovered):return current
            # Native widget blur and the debounced bridge can race. Rebase only
            # provably non-conflicting fields, never replace a newer field value.
            base=record.get('base')
            if not base:raise ValueError('A newer saved draft exists. Recovery copy retained without overwriting it.')
            merged=merge_checkpoint(checkpoint(base),checkpoint(recovered),checkpoint(current))
            recovered={**current,**merged}
    return save_checkpoint(store,user,recovered)


def merge_checkpoint(base,local,server):
    if local==base:return deepcopy(server)
    if server==base or local==server:return deepcopy(local)
    if all(isinstance(v,dict) for v in (base,local,server)) and base.keys()==local.keys()==server.keys():
        return {k:merge_checkpoint(base[k],local[k],server[k]) for k in base}
    raise ValueError('A newer saved draft conflicts with browser edits. Recovery copy retained without overwriting it.')
