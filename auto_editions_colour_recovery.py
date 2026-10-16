"""Bounded, opt-in recovery of colour failures only; no resets or allocations."""
import os
import json
from worker_diagnostics import explain

COLOUR_CODES={'PROFILE_MISSING','COLOUR_POLICY_PENDING','PROFILE_INSPECTOR_FAILURE','ICC_MISMATCH','COLOUR_INCOMPATIBLE'}


def audit(rows):
    unique={row['product_gid']:row for row in rows}
    groups={}
    for row in unique.values():
        if row.get('preparation_hash'):code='PREPARED_RETAINED'
        else:code=explain(row.get('reason'))['code']
        groups.setdefault(code,[]).append(row['product_gid'])
    return dict(designs=len(unique),groups={code:dict(count=len(ids),products=ids) for code,ids in groups.items()})


def recover(queue,actor,*,policies=None,limit=10,dry_run=True):
    """Release gate is separate from profile approval; default is a read-only plan.

    Missing profiles need an approved exact membership. Inspection errors,
    mismatches and supplier incompatibility always require further review.
    Approved tagged-source export packages use a separately reviewed import
    lane; this function never retries generic ICC mismatch failures.
    """
    if not 1<=limit<=50 or not actor:raise ValueError('Identified bounded colour recovery required.')
    if not dry_run and os.getenv('AUTO_EDITIONS_COLOUR_RECOVERY_ENABLED','').lower()!='true':
        raise PermissionError('Colour recovery awaits an authorised release and recovery enablement.')
    from auto_editions_colour_policy import resolve,load_policies
    policies=load_policies() if policies is None else policies
    if not policies:return []
    members=[m['source'] for policy in policies for m in policy.get('members',[])]
    selected=[]
    with queue.connect() as conn,conn.cursor() as cur:
        # Shared queue lock serializes claims/pause/recovery. No prepared assets,
        # active replacements or changed mappings can enter this operation.
        cur.execute('LOCK TABLE auto_edition_onboarding IN SHARE ROW EXCLUSIVE MODE')
        import worker_health
        if worker_health.control(cur)['paused']:return []
        cur.execute("""SELECT q.* FROM auto_edition_onboarding q
            JOIN product_psd_mappings m ON m.shopify_product_gid=q.product_gid AND m.dropbox_file_id=q.file_id
            WHERE q.status IN ('Blocked','Needs PSD Repair') AND q.preparation_hash IS NULL
              AND q.source IN (SELECT value FROM jsonb_array_elements(%s::jsonb))
              AND (q.lease_until IS NULL OR q.lease_until<now())
              AND COALESCE(to_jsonb(q)->'replacement'->>'stage','') IN ('','Complete')
              AND NOT EXISTS(SELECT 1 FROM auto_edition_preparations p WHERE p.manifest->'source'->>'product_gid'=q.product_gid)
              AND NOT EXISTS(SELECT 1 FROM auto_edition_onboarding_audit a WHERE a.product_gid=q.product_gid AND a.event='colour_retry')
              AND (lower(q.reason) LIKE '%%colour policy awaiting approval%%'
                OR lower(q.reason) LIKE '%%colour profile is unavailable%%'
                OR lower(q.reason) LIKE '%%source_profile_requires_review%%'
                OR lower(q.reason) LIKE '%%colour settings require owner review%%')
            ORDER BY CASE WHEN q.priority=8 THEN 11 ELSE q.priority END DESC,q.created_at
            LIMIT 50 FOR UPDATE OF q""",(json.dumps(members),))
        for row in cur.fetchall():
            code=explain(row.get('reason'))['code']
            if code not in ('PROFILE_MISSING','COLOUR_POLICY_PENDING'):continue
            try:_,policy=resolve(row.get('source'),policies)
            except ValueError:continue
            selected.append(dict(product_gid=row['product_gid'],source=row['source'],policy=policy))
            if not dry_run:
                cur.execute("""UPDATE auto_edition_onboarding SET status='Awaiting preparation',
                    reason='Profile correction approved',attempts=0,lease_token=NULL,lease_until=NULL,updated_at=now()
                    WHERE product_gid=%s AND preparation_hash IS NULL""",(row['product_gid'],))
                queue.audit(cur,row['product_gid'],actor,'colour_retry',dict(source=row['source'],policy=policy))
            if len(selected)>=limit:break
    return selected
