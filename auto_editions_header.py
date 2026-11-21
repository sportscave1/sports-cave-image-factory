"""Bounded, read-only companion checkpoints for the shared cached header feed."""
import logging

LOG = logging.getLogger(__name__)
SQL = """WITH summary AS (
 SELECT count(*) FILTER (WHERE (status='Awaiting preparation' AND priority>0
   OR to_jsonb(auto_edition_onboarding)->'replacement'->>'stage'='Queued')
   AND COALESCE(to_jsonb(auto_edition_onboarding)->'reset_cancellation'->>'stage','') NOT IN ('Cancelling','Confirmed')) AS waiting
 FROM auto_edition_onboarding
), recent AS (
 SELECT q.product_gid,q.status,q.reason,q.updated_at,q.priority,q.lease_until,
   to_jsonb(q)->'replacement'->>'stage' AS replacement_stage,
   to_jsonb(q)->'reset_cancellation'->>'stage' AS cancellation_stage
 FROM auto_edition_onboarding q
 ORDER BY CASE WHEN status='Preparing' OR to_jsonb(q)->'replacement'->>'stage'='Preparing' THEN 0
   WHEN status='Awaiting preparation' AND priority>0 OR to_jsonb(q)->'replacement'->>'stage' IN ('Queued','Discovering') THEN 1 ELSE 2 END,
   CASE WHEN status='Awaiting preparation' THEN priority END DESC,
   updated_at DESC,product_gid
 LIMIT 10
)
SELECT summary.waiting,
 COALESCE((SELECT (detail->>'paused')::boolean FROM auto_edition_onboarding_audit
   WHERE product_gid='auto-editions-worker-control' AND event IN ('worker_paused','worker_resumed')
   ORDER BY created_at DESC,id DESC LIMIT 1),false) AS paused,
 EXISTS(SELECT 1 FROM auto_edition_preparation_hosts
   WHERE revoked_at IS NULL AND expires_at>now()
     AND last_seen_at>now()-interval '150 seconds') AS online,
 recent.*,
 (SELECT product_title FROM edition_products p
   WHERE p.shopify_product_gid=recent.product_gid LIMIT 1) AS title,
 recent.lease_until>now() AS lease_valid
 FROM summary LEFT JOIN recent ON true"""


def snapshot(connect):
    from companion_read_connection import read_connection
    try:
        with read_connection(connect) as conn, conn.cursor() as cur:
            cur.execute(SQL)
            rows = cur.fetchall()
        first = rows[0]
        jobs = []
        for row in rows:
            if not row.get('product_gid'):
                continue
            status = row['status']
            active = status == 'Preparing' or row.get('replacement_stage') == 'Preparing'
            waiting = status == 'Awaiting preparation' and row['priority'] > 0 or row.get('replacement_stage') == 'Queued'
            if row.get('cancellation_stage') in ('Cancelling', 'Confirmed'):
                state, label = 'pending', 'Cancelling · waiting for safe stop'
            elif active:
                state = 'running'
                stage = row.get('reason')
                label = stage if stage in ('Claimed','Photoshop','Preparing','Uploading','Verifying','Recovering') else 'Preparing'
                if not row.get('lease_valid'):
                    label = 'Recovering · preparation lease expired'
            elif row.get('replacement_stage') == 'Discovering':
                state, label = 'pending', 'Checking replacement source'
            elif row.get('replacement_stage') == 'Failed':
                state, label = 'failed', 'Replacement needs attention'
            elif waiting:
                state, label = 'waiting', 'Queued for preparation'
            elif status == 'Cloud Ready':
                state, label = 'complete', 'Preparation saved'
            elif status == 'Awaiting preparation':
                state, label = 'pending', 'Deferred'
            else:
                state, label = 'failed', 'Preparation needs attention'
            jobs.append(dict(id=row['product_gid'],title=row.get('title') or 'Edition artwork',
                state=state,label=label,percent=100 if state=='complete' else 0,estimated=False))
        return dict(enabled=not first['paused'],online=bool(first['online']),waiting=first['waiting'],jobs=jobs)
    except Exception:
        # Do not take down the other companions or publish database error text.
        LOG.warning('Auto Editions header snapshot unavailable')
        return dict(enabled=True,online=False,waiting=0,jobs=[],unavailable=True)
