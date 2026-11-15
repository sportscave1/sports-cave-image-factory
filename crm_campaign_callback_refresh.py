"""One pooled, bounded revision probe while Campaigns is visible."""
from crm_campaign_home_cache import job,resolve

POLL_SECONDS=3
SQL="SELECT value->>'revision' AS revision FROM crm_runtime_state WHERE key='resend_callback_revision'"


def read_revision(store):
    if store.connect:
        row=store.q(SQL,one=True)
    else:
        # Reuse existing read transport, not a new connection on every page poll.
        from supabase_backend import read_connection
        with read_connection() as conn:row=conn.execute(SQL).fetchone()
    return [{'revision':row['revision'] if row else None}]


def watch(state,store):
    key=('callbacks',)
    future=job(state,store,key,lambda:read_revision(store),ttl=POLL_SECONDS)
    result,status=resolve(state,store,key,future)
    state.setdefault('campaign_home_activity',{})['callbacks']=status
    if result is None:return
    revision=result[0]['revision']
    had_previous='campaign_home_callback_revision' in state
    previous=state.get('campaign_home_callback_revision')
    state['campaign_home_callback_revision']=revision
    # The first probe can finish after the first table read. A nonempty revision
    # must also refresh that projection, including a callback received meanwhile.
    if (had_previous and revision!=previous) or (not had_previous and revision is not None):state['campaign_home_callback_dirty']=True
    if state.get('campaign_home_callback_dirty'):
        # Status, authoring and reporting windows are retained. Only projections
        # affected by callback facts refresh, with last-good values kept on error.
        pending=False
        cache=state.get('campaign_home_cache',{})
        for identity,(_,active) in list(cache.items()):
            if identity[0]!=store.connect or identity[1][0] not in ('table','delivery'):continue
            if not active.done():pending=True;continue
            fields=('sent_emails','click_rate','bounce_rate') if identity[1][0]=='delivery' else None
            resolve(state,store,identity[1],active,fields=fields)
            cache.pop(identity,None)
        state['campaign_home_callback_dirty']=pending
