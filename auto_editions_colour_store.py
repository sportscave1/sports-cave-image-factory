"""Audited owner policies and pinned, once-only colour recovery.

Only administrator routes write approvals. Preparation-host routes can read this
configuration, but cannot approve policies or assert workflow membership.
"""
import json
from auto_editions_colour_policy import validate, fingerprint, approve, resolve


def configuration(connect):
    from auto_editions_colour_review import registry
    policies=registry();receipts=[]
    with connect() as conn,conn.cursor() as cur:
        cur.execute("""SELECT event,detail FROM auto_edition_onboarding_audit
            WHERE event IN ('colour_policy_approved','colour_workflow_verified')
            ORDER BY id LIMIT 1201""")
        rows=cur.fetchall()
    if len(rows)>1200:raise ValueError('Colour registry needs archival before further activation.')
    for row in rows:
        if row['event']=='colour_policy_approved':
            p=row['detail']['policy'];validate(p)
            if not any(x['approval_hash']==p['approval_hash'] for x in policies):policies.append(p)
        else:receipts.append(row['detail']['receipt'])
    if len(policies)>200 or len(receipts)>1000:raise ValueError('Colour registry capacity reached.')
    import os
    from pathlib import Path
    default=json.loads((Path(__file__).parent/'config/auto_editions/colour-runtime-20261017.json').read_text())['default_group']
    return dict(policies=policies,memberships=receipts,default_group=os.getenv('AUTO_EDITIONS_UNTAGGED_RGB_DEFAULT',default))


def resume_locked(cur,queue,pid,source,actor,policies,*,memberships=(),default_group=''):
    # Serialize with claims, reset and mapping changes; caller holds table lock.
    cur.execute('''SELECT q.*,m.dropbox_file_id FROM auto_edition_onboarding q
        JOIN product_psd_mappings m ON m.shopify_product_gid=q.product_gid
        WHERE q.product_gid=%s FOR UPDATE OF q,m''',(pid,))
    row=cur.fetchone()
    if not row or row['source']!=source or row['dropbox_file_id']!=source['file_id']:
        raise ValueError('Source or mapping changed. Refresh before resuming.')
    cur.execute("""SELECT detail FROM auto_edition_onboarding_audit WHERE product_gid=%s
        AND event='colour_retry' AND detail->'source'->>'file_id'=%s
        AND detail->'source'->>'content_hash'=%s LIMIT 1""",(pid,source['file_id'],source['content_hash']))
    if cur.fetchone():return dict(resumed=False,already_requested=True)
    from worker_diagnostics import explain
    if row.get('preparation_hash') or row['status'] not in ('Blocked','Needs PSD Repair'):
        raise ValueError('This job is active, successful or no longer blocked. It was left untouched.')
    if explain(row.get('reason'))['code'] not in ('PROFILE_MISSING','COLOUR_POLICY_PENDING'):
        raise ValueError('This failure needs separate inspection; a missing-profile approval cannot resolve it.')
    cur.execute("""SELECT EXISTS(SELECT 1 FROM auto_edition_onboarding WHERE product_gid=%s
        AND lease_until>now()) AS active,
        EXISTS(SELECT 1 FROM auto_edition_preparations WHERE manifest->'source'->>'product_gid'=%s) AS retained""",(pid,pid))
    guards=cur.fetchone()
    if guards['active'] or guards['retained'] or (row.get('replacement') or {}).get('stage','') not in ('','Complete'):
        raise ValueError('Active lease, replacement or retained preparation requires separate review.')
    _,policy=resolve(source,policies,memberships=memberships,default_group=default_group)
    cur.execute("""UPDATE auto_edition_onboarding SET status='Awaiting preparation',
        reason='Profile correction approved',attempts=0,lease_token=NULL,lease_until=NULL,updated_at=now()
        WHERE product_gid=%s""",(pid,))
    queue.audit(cur,pid,actor,'colour_retry',dict(source=source,policy=policy))
    import worker_health
    return dict(resumed=True,already_requested=False,paused=worker_health.control(cur)['paused'])


def approve_and_resume(queue,pid,body,actor,read_metadata):
    """Idempotency is the exact proposal fingerprint, never a client status field."""
    if set(body)!={'proposal','reviewed_hash'} or not actor:raise ValueError('Exact owner-reviewed proposal required.')
    proposed=body['proposal']
    if len(proposed.get('members',[]))!=1 or proposed['members'][0]['source'].get('product_gid')!=pid:
        raise ValueError('Review approval must pin this exact product source.')
    source=proposed['members'][0]['source']
    import auto_editions as ae
    if ae.source_identity(pid,read_metadata(source['file_id']))!=source:
        raise ValueError('Provider source changed. Inspect the new source before approval.')
    approved=approve(proposed,actor,body['reviewed_hash'])
    config=configuration(queue.connect)
    with queue.connect() as conn,conn.cursor() as cur:
        cur.execute('LOCK TABLE auto_edition_onboarding IN SHARE ROW EXCLUSIVE MODE')
        cur.execute("""SELECT detail FROM auto_edition_onboarding_audit WHERE product_gid=%s
            AND event='colour_policy_approved' AND detail->>'reviewed_hash'=%s LIMIT 1""",(pid,body['reviewed_hash']))
        previous=cur.fetchone()
        if previous:approved=previous['detail']['policy']
        # Policy and retry are one transaction: stale/active sources never gain
        # an approval accidentally, and a lost HTTP response is safely retryable.
        result=resume_locked(cur,queue,pid,source,actor,[*config['policies'],approved]
            if not any(p['approval_hash']==approved['approval_hash'] for p in config['policies']) else config['policies'],
            memberships=config['memberships'],default_group=config['default_group'])
        if result['already_requested'] and not previous:
            raise ValueError('Resume already requested under an existing approval. A different policy was not activated.')
        if not previous:queue.audit(cur,pid,actor,'colour_policy_approved',dict(
            policy=approved,reviewed_hash=body['reviewed_hash'],interpretation='Explicit owner-approved interpretation; original creator intent is unknown.'))
    return dict(ok=True,policy=approved['approval_hash'],**result)


def resume_existing(queue,pid,source,actor,read_metadata):
    import auto_editions as ae
    if ae.source_identity(pid,read_metadata(source['file_id']))!=source:raise ValueError('Provider source changed.')
    config=configuration(queue.connect)
    with queue.connect() as conn,conn.cursor() as cur:
        cur.execute('LOCK TABLE auto_edition_onboarding IN SHARE ROW EXCLUSIVE MODE')
        return resume_locked(cur,queue,pid,source,actor,config['policies'],
            memberships=config['memberships'],default_group=config['default_group'])
