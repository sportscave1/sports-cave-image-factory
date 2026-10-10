"""Audited list tombstones; never deletes delivery, order or attribution facts."""
from crm_navigation import require

VISIBLE = "NOT EXISTS(SELECT 1 FROM crm_campaign_history h WHERE h.campaign_id=d.id AND h.action='campaign_deleted')"
# Used in the bounded listing and rechecked under the same draft/queue locks.
PROTECTED = """EXISTS(SELECT 1 FROM crm_campaign_preparation WHERE campaign_id=d.id)
 OR EXISTS(SELECT 1 FROM crm_marketing_sends s WHERE s.campaign_id=d.id
 AND (s.status IN ('ACCEPTED','SUBMITTING','UNCERTAIN','CLAIMED') OR s.provider_email_id IS NOT NULL
 OR EXISTS(SELECT 1 FROM crm_delivery_events e WHERE e.send_id=s.id OR e.provider_id=s.provider_email_id)))
 OR EXISTS(SELECT 1 FROM crm_order_attribution a WHERE a.campaign_id=d.id)
 OR EXISTS(SELECT 1 FROM crm_website_events e WHERE e.campaign_key=d.document->>'campaign_key')"""
ELIGIBLE = """(c.status IS NULL OR c.status IN ('SENT','CANCELLED','FAILED'))
 AND (d.status IN ('DRAFT','NEEDS_REVIEW','TEST_READY') OR d.archived_at IS NOT NULL OR c.status IN ('SENT','CANCELLED','FAILED'))
 AND NOT (""" + PROTECTED + ")"


def tombstone(conn, store, user, identity, version, *, confirmed=False, historical=False):
    require(user, 'crm_campaigns_manage')
    if confirmed is not True: raise ValueError('Explicit campaign deletion confirmation is required.')
    draft=conn.execute('SELECT * FROM crm_campaign_drafts WHERE id=%s FOR UPDATE',(identity,)).fetchone()
    if not draft or draft['version']!=version: raise ValueError('Campaign changed. Reopen the confirmation.')
    conn.execute('SELECT id FROM crm_campaigns WHERE id=%s FOR UPDATE',(identity,)).fetchall()
    conn.execute('SELECT id FROM crm_marketing_sends WHERE campaign_id=%s FOR UPDATE',(identity,)).fetchall()
    row=conn.execute('SELECT ('+ELIGIBLE+') AS deletable,('+VISIBLE+') AS visible,c.status AS delivery_status '
        'FROM crm_campaign_drafts d LEFT JOIN crm_campaigns c ON c.id=d.id WHERE d.id=%s',(identity,)).fetchone()
    if not row['visible']: return {'deleted':True}
    # Only the explicit one-time admin cleanup may hide archived successful history.
    archived_history=historical and draft['archived_at'] and row['delivery_status'] in (None,'SENT','CANCELLED','FAILED')
    if not row['deletable'] and not archived_history:
        raise ValueError('Campaign has accepted delivery, evidence, or active sending state. It cannot be deleted here.')
    deleted=conn.execute("UPDATE crm_campaign_drafts SET archived_at=COALESCE(archived_at,now()),status='ARCHIVED',version=version+1,updated_at=now() WHERE id=%s RETURNING *",(identity,)).fetchone()
    store._history(conn,deleted,'campaign_deleted',str(user.get('id','')),draft)
    return {'deleted':True}


def delete_campaign(store,user,identity,version,*,confirmed=False):
    with store.db() as conn:
        return tombstone(conn,store,user,identity,version,confirmed=confirmed)


def remove_cached_row(state, store, row):
    """Detach stale list/count futures, retaining delivery/order KPI jobs and values."""
    from concurrent.futures import Future
    from time import monotonic
    category='archived' if row.get('archived_at') else 'sent' if row.get('delivery_status')=='SENT' else 'active' if row.get('delivery_status') else 'drafts'
    cache=state.setdefault('campaign_home_cache',{})
    resolved=state.setdefault('campaign_home_resolved',{})
    for identity in list(cache):
        if identity[0]==store.connect and identity[1][0] in ('table','counts'): cache.pop(identity)
    for identity,value in list(resolved.items()):
        if identity[0]!=store.connect: continue
        if identity[1][0]=='table':
            resolved[identity]=[r for r in value if str(r['id'])!=str(row['id'])]
        elif identity[1][0]=='counts':
            updated=dict(value)
            for field in ('all_count',category): updated[field]=max(0,updated[field]-1)
            resolved[identity]=updated
            ready=Future();ready.set_result(updated);cache[identity]=(monotonic(),ready)
            state['campaign_home_counts']=updated
