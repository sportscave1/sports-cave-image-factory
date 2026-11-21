"""SQL proof for bounded upload/native overlap; no new source/lease authority."""


def durable_upload(cur, pid, token, actor, host=None):
    cur.execute("""SELECT 1 FROM companion_package_uploads u
        JOIN auto_edition_onboarding q ON q.product_gid=u.context->>'product_gid'
        AND q.lease_token::text=u.context->>'lease_token' AND q.lease_until>now()
        WHERE u.owner_id=%s AND u.context->>'product_gid'=%s
        AND (q.status='Preparing' OR to_jsonb(q)->'replacement'->>'stage'='Preparing')
        AND COALESCE(to_jsonb(q)->'reset_cancellation'->>'stage','') NOT IN ('Cancelling','Confirmed')
        AND u.context->>'lease_token'=%s AND u.state IN ('Receiving','Queued')
        AND u.expires_at>now() AND (u.data->>'offset')::bigint>0
        AND (%s::text IS NULL OR u.host_hash=%s) LIMIT 1""", (actor,pid,str(token),host,host))
    return bool(cur.fetchone())


def claim_exclusion(cur, pipeline, actor):
    if pipeline is None:
        return None
    if (not isinstance(pipeline, dict) or set(pipeline)!={'product_gid','lease_token','host_hash'}
            or not all(isinstance(value,str) and value for value in pipeline.values())):
        raise ValueError('Exact owned upload required for pipeline admission.')
    pid,token=pipeline['product_gid'],pipeline['lease_token']
    cur.execute("""SELECT 1 FROM auto_edition_onboarding_audit
        WHERE product_gid=%s AND actor_id=%s AND event='claimed' AND detail->>'lease'=%s""",(pid,actor,token))
    if not cur.fetchone():raise ValueError('Upload lease belongs to another operator.')
    if not durable_upload(cur,pid,token,actor,pipeline['host_hash']):
        # Normal polling can beat the first chunk ACK or race completion. It
        # grants no exclusion/claim, and must not turn healthy work Recovering.
        return False
    return pid
