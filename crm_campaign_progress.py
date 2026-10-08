"""Read-only delivery progress. Durable send rows, never provider/audience reads."""
import time
from datetime import timedelta
from uuid import UUID

ACTIVE = ('PENDING', 'CLAIMED', 'SUBMITTING')
TERMINAL = ('ACCEPTED', 'BLOCKED', 'FAILED')
HELD = ('UNCERTAIN',)
POLL_SECONDS = 2.5
IDLE_SECONDS = 30
COMPLETION_SECONDS = 20
STALL_SECONDS = 600


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
    from crm_logic import now, date
    last = row.get('last_progress_at') or row.get('sending_started_at') or row.get('updated_at')
    stalled = bool(row['status'] == 'SENDING' and last and
                   date(last) < now() - timedelta(seconds=STALL_SECONDS) and
                   (not row.get('next_due_at') or date(row['next_due_at']) <= now()))
    return {**row, 'total': total, 'submitted': submitted, 'skipped': skipped,
            'failed': failed, 'held': held, 'pending': pending, 'processed': processed,
            'percent': min(1., processed / total) if total else 0.,
            'complete': complete, 'stalled': stalled, 'attention': bool(held or failed or stalled or (complete and not submitted)),
            'title': ('Campaign complete · needs attention' if held or failed or not submitted else 'Campaign sent')
                     if complete else 'Send appears stalled · view details' if stalled else 'Campaign needs attention' if held else
                     'Campaign scheduled' if row['status'] == 'SCHEDULED' else
                     'Campaign paused' if row['status'] == 'PAUSED' else
                     'Campaign failed' if row['status'] == 'FAILED' else
                     'Campaign cancelled' if row['status'] == 'CANCELLED' else 'Sending campaign'}


def read_progress(store, identities):
    ids = list(dict.fromkeys(str(UUID(str(i))) for i in identities))
    if not ids: return {}
    # campaign_id is the leading column of two existing UNIQUE indexes.
    # One statement sees campaign status and send counts in the same snapshot.
    rows = store.q('''SELECT c.id,c.name,c.status,c.updated_at,c.sent_at,c.scheduled_at,
      c.campaign_send_id AS send_id,c.sending_started_at,
      p.worker_started_at,p.last_progress_at,p.next_due_at,
      COALESCE(p.counts,'{}'::jsonb) AS counts,
      COALESCE(p.failures,'{}'::jsonb) AS failures
      FROM crm_campaigns c LEFT JOIN LATERAL (
        SELECT jsonb_object_agg(t.status,t.n) AS counts,jsonb_object_agg(t.status,t.failures) AS failures,
          min(t.worker_started_at) AS worker_started_at,max(t.last_progress_at) AS last_progress_at,
          min(t.next_due_at) AS next_due_at FROM (
          SELECT s.status,count(*) AS n,min(s.first_submitted_at) AS worker_started_at,
            array_agg(DISTINCT s.error_code) FILTER (WHERE s.status IN ('FAILED','UNCERTAIN','BLOCKED')) AS failures,
            max(s.updated_at) AS last_progress_at,
            min(s.due_at) FILTER (WHERE s.status IN ('PENDING','CLAIMED','SUBMITTING')) AS next_due_at FROM crm_marketing_sends s
          WHERE s.campaign_id=c.id AND NOT s.test_send GROUP BY s.status
        ) t
      ) p ON true WHERE c.id=ANY(%s::uuid[])''', (ids,))
    result = {str(r['id']): summarize(r) for r in rows}
    return result


def polling_seconds(row):
    if row.get('stalled') or (row.get('held') and not row.get('pending')):return IDLE_SECONDS
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
