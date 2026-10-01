"""Read-only delivery progress. Durable send rows, never provider/audience reads."""
import time
from uuid import UUID

ACTIVE = ('PENDING', 'CLAIMED', 'SUBMITTING')
TERMINAL = ('ACCEPTED', 'BLOCKED', 'FAILED')
HELD = ('UNCERTAIN',)
POLL_SECONDS = 2.5
IDLE_SECONDS = 30
COMPLETION_SECONDS = 20


def summarize(row):
    """Held/unknown rows require attention; SENT alone confirms completion."""
    counts = row.get('counts') or {}
    total = sum(int(n) for n in counts.values())
    submitted = int(counts.get('ACCEPTED', 0))
    skipped = int(counts.get('BLOCKED', 0))
    failed = int(counts.get('FAILED', 0))
    pending = sum(int(counts.get(s, 0)) for s in ACTIVE)
    held = total - pending - submitted - skipped - failed
    processed = submitted + skipped + failed + held
    complete = row['status'] == 'SENT'
    return {**row, 'total': total, 'submitted': submitted, 'skipped': skipped,
            'failed': failed, 'held': held, 'pending': pending, 'processed': processed,
            'percent': min(1., processed / total) if total else 0.,
            'complete': complete, 'attention': bool(held or failed),
            'title': ('Campaign complete · needs attention' if held or failed else 'Campaign sent')
                     if complete else 'Campaign needs attention' if held else
                     'Campaign scheduled' if row['status'] == 'SCHEDULED' else
                     'Campaign paused' if row['status'] == 'PAUSED' else
                     'Campaign cancelled' if row['status'] == 'CANCELLED' else 'Sending campaign'}


def read_progress(store, identities):
    ids = list(dict.fromkeys(str(UUID(str(i))) for i in identities))
    if not ids: return {}
    # campaign_id is the leading column of two existing UNIQUE indexes.
    # One statement sees campaign status and send counts in the same snapshot.
    rows = store.q('''SELECT c.id,c.name,c.status,c.updated_at,c.sent_at,c.scheduled_at,
      COALESCE(p.counts,'{}'::jsonb) AS counts
      FROM crm_campaigns c LEFT JOIN LATERAL (
        SELECT jsonb_object_agg(t.status,t.n) AS counts FROM (
          SELECT s.status,count(*) AS n FROM crm_marketing_sends s
          WHERE s.campaign_id=c.id AND NOT s.test_send GROUP BY s.status
        ) t
      ) p ON true WHERE c.id=ANY(%s::uuid[])''', (ids,))
    return {str(r['id']): summarize(r) for r in rows}


def polling_seconds(row):
    if row['status'] in ('SENDING','BUILDING'):return POLL_SECONDS
    if row['status']=='SCHEDULED' and row.get('scheduled_at'):
        from datetime import timedelta
        from crm_logic import now,date
        if date(row['scheduled_at'])<=now()+timedelta(minutes=1):return POLL_SECONDS
    return IDLE_SECONDS


def track(state, receipt, name):
    identity = str(UUID(str(receipt['id'])))
    state.setdefault('campaign_send_progress', {}).setdefault(identity, {'name': name})
    state['campaign_send_dialog_id'] = identity
    state.pop('campaign_progress_cache', None)
    return identity


def load_progress(store, state, identities, *, clock=time.monotonic):
    ids = tuple(sorted(str(i) for i in identities))
    cached = state.get('campaign_progress_cache')
    at = clock()
    if cached and cached['ids'] == ids and at - cached['at'] < 2:
        return cached['rows']
    rows = read_progress(store, ids)
    state['campaign_progress_cache'] = {'ids': ids, 'at': at, 'rows': rows}
    return rows


def expire(state, rows, *, clock=time.monotonic):
    tracked = state.get('campaign_send_progress', {})
    for identity, row in rows.items():
        item = tracked.get(identity)
        if item is None: continue
        if row['complete'] and not row['attention']:
            item.setdefault('completed_at', clock())
            if clock() - item['completed_at'] >= COMPLETION_SECONDS and state.get('campaign_send_dialog_id') != identity:
                tracked.pop(identity, None)
        else: item.pop('completed_at', None)
