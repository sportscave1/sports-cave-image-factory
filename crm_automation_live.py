"""Live definitions, stable delivery slots and submission-time publication fencing.

Enrollment steps are an append-only identity ledger, not a publication authority.
Existing receipt indexes and idempotency keys never move. Historical terminal
enrollments are deliberately excluded from reconciliation.
"""
from copy import deepcopy
from datetime import timedelta
import json
import logging
from crm_logic import date
from crm_automation_timing import enrollment_steps

LOG = logging.getLogger('crm_automation_runtime')


def current_step(automation, step_id):
    return next((s for s in automation['steps'] if s.get('step_id') == step_id), None)


def reconcile(store, enrollment, at):
    with store.db() as conn:
        # Same lock order as publication and begin_send: automation, enrollment.
        a = conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',
                         (enrollment['automation_id'],)).fetchone()
        e = conn.execute('SELECT * FROM crm_automation_enrollments WHERE id=%s FOR UPDATE',
                         (enrollment['id'],)).fetchone()
        if not a or not e or a['status'] != 'ACTIVE' or e['status'] != 'ACTIVE':
            return None
        receipts = conn.execute('SELECT * FROM crm_marketing_sends WHERE enrollment_id=%s AND NOT test_send',
                                (e['id'],)).fetchall()
        # An ambiguous provider outcome must never be skipped or replayed.
        if any(r['status'] == 'UNCERTAIN' for r in receipts):
            conn.execute("UPDATE crm_automation_enrollments SET status='STOPPED',stop_reason='submission_uncertain',updated_at=now() WHERE id=%s", (e['id'],))
            return None
        if any(r['status'] == 'SUBMITTING' for r in receipts):
            conn.execute("UPDATE crm_automation_enrollments SET retry_after=now()+interval '1 minute' WHERE id=%s", (e['id'],))
            return None
        steps = deepcopy(e['steps'])
        if not steps:
            raise ValueError('Enrollment stage identities are missing')
        if not steps[0].get('live_sequence'):
            # Preserve pre-upgrade progression, even with missing receipts.
            # This records a historical pass, never invents a successful send.
            for i, step in enumerate(steps):
                if i < e['current_step']:
                    step['historical_pass'] = True
            steps[0]['live_sequence'] = True
        slots = {s['step_id']: i for i, s in enumerate(steps)}
        live = enrollment_steps(a)
        for stage in live:
            if stage['step_id'] not in slots:
                slots[stage['step_id']] = len(steps)
                steps.append(deepcopy(stage))
        accepted = {r['step_index']: r for r in receipts if r['status'] == 'ACCEPTED'}
        if accepted and e.get('checkout_key'):
            conn.execute("UPDATE crm_shopify_checkouts SET status='RECOVERY_EMAIL_SENT',updated_at=now() WHERE checkout_key=%s AND status NOT IN ('RECOVERED','RECOVERY_EMAIL_SENT')", (e['checkout_key'],))
        for index, receipt in accepted.items():
            if not steps[index].get('delivery_complete'):
                steps[index]['delivery_complete'] = True
                LOG.info('automation_submission automation_id=%s journey_id=%s step_id=%s provider_message_id=%s sent_at=%s',
                         a['id'], e['id'], steps[index]['step_id'], receipt.get('provider_email_id'), receipt.get('first_submitted_at'))
        next_stage = next((s for s in live if not steps[slots[s['step_id']]].get('historical_pass')
                           and not steps[slots[s['step_id']]].get('delivery_complete')), None)
        index = slots[next_stage['step_id']] if next_stage else len(steps)
        if next_stage and index == e['current_step'] and index < len(e['steps']):
            due = e['next_due_at']  # Republishing content never restarts a timer.
        elif next_stage:
            anchors = [date(r['updated_at']) for r in accepted.values()]
            anchor = max(anchors) if anchors else date(e['trigger_at'])
            due = anchor + timedelta(seconds=next_stage['delay_seconds'])
        else:
            # An active enrollment waits for future stages. Old COMPLETED rows
            # are never reopened. Bounded polling survives restarts/deploys.
            due = at + timedelta(minutes=5)
        reason = '' if next_stage else 'awaiting_published_stage'
        result = conn.execute("""UPDATE crm_automation_enrollments SET steps=%s::jsonb,
          current_step=%s,next_due_at=%s,stop_reason=%s,retry_after=NULL,last_checked_at=now(),updated_at=now()
          WHERE id=%s RETURNING *""", (json.dumps(steps), index, due, reason, e['id'])).fetchone()
        # A removed/disabled stage may have a queued receipt. It stays in audit
        # history but cannot be claimed while another stable slot is current.
        if next_stage:
            LOG.info('automation_eligibility automation_id=%s journey_id=%s step_id=%s publication_version=%s due_at=%s reason=scheduled',
                     a['id'], e['id'], next_stage['step_id'], next_stage['template_version'], due)
        return result


def resolve(store, row, enrollment):
    """Read the current pointer for rendering; begin_send fences this selection."""
    a = store.get('automations', enrollment['automation_id'])
    slot = enrollment['steps'][row['step_index']]
    stage = current_step(a, slot['step_id']) if a else None
    if not stage:
        return None
    row['template_id'] = stage['template_id']
    row['template_version'] = stage['template_version']
    row['_live_step_id'] = stage['step_id']
    content = store.template(row['template_id'], row['template_version'])
    if (content.get('format') != 'automation_delivery_v1' or
            content.get('step_id') != stage['step_id'] or
            content.get('automation_id') != str(a['id']) or
            content.get('automation_version') != stage['template_version']):
        raise ValueError('Active publication content does not match its identity')
    return content
