"""Read-only, privacy-safe live-stage audit. Never queues or sends email.

Usage: python scripts/diagnose_automation_live.py AUTOMATION_UUID
Uses the application's configured database; reports no customer identifiers,
email addresses, document bodies, checkout URLs or credentials.
"""
import argparse
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crm_store import Store

SUMMARY_SQL = """SELECT a.id AS automation_id,a.status,
 a.config->>'published_version' AS active_publication_version,
 a.config->>'published_at' AS published_at,
 (SELECT jsonb_agg(jsonb_build_object('step_id',s->>'step_id','publication_id',s->>'template_id',
   'version',s->'template_version','delay_seconds',s->'delay_seconds') ORDER BY n)
  FROM jsonb_array_elements(a.steps) WITH ORDINALITY AS stage(s,n)) AS live_stages,
 (SELECT count(*) FROM crm_automation_enrollments e WHERE e.automation_id=a.id AND e.status='ACTIVE') AS active,
 (SELECT count(*) FROM crm_automation_enrollments e WHERE e.automation_id=a.id AND e.status='COMPLETED') AS historical_completed,
 (SELECT count(*) FROM crm_automation_enrollments e WHERE e.automation_id=a.id AND e.status='ACTIVE'
   AND e.next_due_at<=now() AND e.stop_reason<>'awaiting_published_stage') AS due_active,
 (SELECT count(*) FROM crm_automation_enrollments e WHERE e.automation_id=a.id AND e.status='ACTIVE'
   AND EXISTS(SELECT 1 FROM jsonb_array_elements(a.steps) s WHERE NOT EXISTS(
     SELECT 1 FROM jsonb_array_elements(e.steps) old WHERE old->>'step_id'=s->>'step_id'))) AS active_missing_stages
 FROM crm_automations a WHERE a.id=%s"""

DETAIL_SQL = """SELECT e.id AS enrollment_id,e.status,e.current_step,e.stop_reason AS eligibility_reason,
 e.next_due_at,e.retry_after,s.id AS send_id,s.step_index,e.steps->s.step_index->>'step_id' AS stage_id,
 s.template_id AS selected_publication_id,s.template_version AS selected_publication_version,
 s.status AS delivery_status,s.due_at,s.first_submitted_at,s.updated_at,s.provider_email_id,s.error_code
 FROM crm_automation_enrollments e LEFT JOIN crm_marketing_sends s ON s.enrollment_id=e.id AND NOT s.test_send
 WHERE e.automation_id=%s ORDER BY e.created_at DESC,s.step_index LIMIT 200"""


def audit(store, identity):
    # A SELECT-only transaction gives both views a consistent snapshot.
    with store.db() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        return {'summary': conn.execute(SUMMARY_SQL, (identity,)).fetchone(),
                'recent_history': conn.execute(DETAIL_SQL, (identity,)).fetchall()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('automation_id', type=uuid.UUID)
    args = parser.parse_args()
    print(json.dumps(audit(Store(), str(args.automation_id)), default=str, indent=2))
