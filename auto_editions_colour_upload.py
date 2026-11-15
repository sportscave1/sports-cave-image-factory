"""Content-bound provenance for explicitly verified workflow uploads.

An administrator supplies independent creation/export evidence at upload start.
The uploaded bytes are independently inspected and matched to Dropbox's receipt;
ordinary uploads never acquire workflow membership from names or destinations.
"""
import json,re,tempfile,threading
from pathlib import Path
SLOTS=threading.BoundedSemaphore(2)


def begin(value,user,size):
    import os_accounts
    from auto_editions_colour_store import configuration
    import supabase_backend
    if not os_accounts.is_admin(user) or not all(os_accounts.can_access_page(user,p) for p in ('Files','Orders','Edition Ops')):
        raise PermissionError('Verified workflow uploads require an authorised editions administrator.')
    if (not isinstance(value,dict) or set(value)!={'workflow_id','provenance','verified_workflow','content_hash'}
            or value['verified_workflow'] is not True or not re.fullmatch('[a-f0-9]{64}',str(value['content_hash'])) or not 0<size<=1024**3):
        raise ValueError('Explicitly verified workflow and bounded PSD upload required.')
    evidence=value['provenance']
    if not isinstance(evidence,list) or not 1<=len(evidence)<=8 or not all(
        isinstance(e,dict) and e.get('name') and e.get('purpose') and re.fullmatch('[a-f0-9]{64}',str(e.get('sha256',''))) for e in evidence):
        raise ValueError('Independent hashed creation/export provenance required.')
    config=configuration(supabase_backend.read_connection)
    candidates=[p for p in config['policies'] if p.get('scope',{}).get('workflow_id')==value['workflow_id'] and p['group']==config['default_group']]
    if len(candidates)!=1:raise ValueError('This workflow has no uniquely configured owner-approved default.')
    if not SLOTS.acquire(blocking=False):raise ValueError('Two verified workflow uploads are in progress. Retry after one completes.')
    try:
        file=tempfile.NamedTemporaryFile(prefix='sc-colour-upload-',suffix='.psd',delete=False);file.close()
        return dict(path=file.name,offset=0,policy=candidates[0],provenance=evidence,actor=str(user['id']),slot=True,content_hash=value['content_hash'])
    except Exception:SLOTS.release();raise


def discard(state):
    if state:
        Path(state['path']).unlink(missing_ok=True)
        if state.pop('slot',False):SLOTS.release()


def capture(state,offset,data):
    if state.get('error'):return
    if state['offset']!=offset:
        state['error']='Upload offset recovery needs separate provenance verification.';discard(state);return
    with Path(state['path']).open('ab') as stream:stream.write(data)
    state['offset']+=len(data)


def finish(state,metadata,connect):
    try:
        if state.get('error'):raise ValueError(state['error'])
        import auto_editions as ae
        from auto_editions_colour_workflows import verified_membership
        # Product membership is intentionally not inferred. The receipt binds
        # provider file/content and may later be mapped to any product.
        source=ae.source_identity('gid://shopify/Product/1',metadata)
        if source['content_hash']!=state['content_hash']:raise ValueError('Creation/export manifest belongs to different uploaded content.')
        receipt=verified_membership(state['policy'],state['path'],source,state['provenance'],state['actor'])
        from auto_editions_onboarding_store import Queue
        with connect() as conn,conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",('colour-workflow:'+receipt['receipt_hash'],))
            cur.execute("""SELECT id FROM auto_edition_onboarding_audit WHERE event='colour_workflow_verified'
                AND detail->'receipt'->>'receipt_hash'=%s LIMIT 1""",(receipt['receipt_hash'],))
            if not cur.fetchone():Queue.audit(cur,'colour-workflow-upload',state['actor'],'colour_workflow_verified',dict(receipt=receipt))
        return dict(status='verified',receipt_hash=receipt['receipt_hash'])
    finally:discard(state)
