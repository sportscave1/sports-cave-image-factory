"""Read-only checkout timing labels; never schedules or mutates an enrollment."""
from datetime import timedelta
from math import ceil
from crm_logic import date, now
from crm_checkout_identity import recovered, block_label


def time_to_send(row, at=None):
    at = at or now()
    if recovered(row):
        return 'Recovered'
    flow = row.get('flow_status')
    reason = row.get('stop_reason')
    evaluation = row.get('evaluation') or {}
    if flow == 'STOPPED':
        return block_label(reason)
    if not row.get('enrollment_id'):
        result = evaluation.get('result')
        if result in ('Suppressed', 'Unsubscribed', 'Missing email', 'Invalid email', 'Not eligible'):
            return result
        return 'Sent' if any(s.get('status') == 'ACCEPTED' and s.get('provider_id') for s in row.get('sends', [])) else '—'
    if row.get('archived_at'):
        return 'Archived'
    if row.get('automation_status') == 'PAUSED':
        return 'Paused'
    # Recovery history spans flows; timing belongs only to this enrollment.
    sends = [s for s in row.get('sends', [])
             if str(s.get('enrollment_id')) == str(row['enrollment_id'])]
    accepted = any(s.get('status') == 'ACCEPTED' and s.get('provider_id') for s in sends)
    if flow == 'COMPLETED':
        return 'Sent' if accepted else 'Complete'
    if flow != 'ACTIVE':
        return 'Not scheduled'
    index = int(row.get('current_step') or 0)
    receipt = next((s for s in sends if s.get('step') == index), None)
    due = date(row.get('next_due_at'))
    if receipt:
        status = receipt.get('status')
        if status == 'ACCEPTED' and receipt.get('provider_id'):
            steps = row.get('steps') or []
            if index + 1 >= len(steps):
                return 'Sent'
            # Mirror the existing worker's next-step clock, for display only.
            sent = date(receipt.get('updated_at'))
            if not sent:
                return 'Awaiting schedule'
            due = sent + timedelta(seconds=steps[index + 1]['delay_seconds'])
        elif status == 'BLOCKED':
            return block_label(receipt.get('error'))
        elif status == 'FAILED':
            return 'Send failed'
        elif status == 'UNCERTAIN':
            return 'Awaiting confirmation'
        elif status in ('CLAIMED', 'SUBMITTING'):
            return 'Processing'
        elif status == 'PENDING':
            return 'Queued'
    if not due:
        return 'Awaiting schedule'
    minutes = ceil((due - at).total_seconds() / 60)
    if minutes <= 0:
        return 'Due now'
    days, remainder = divmod(minutes, 1440)
    hours, minutes = divmod(remainder, 60)
    if days:
        return f'{days}d {hours}h remaining'
    if hours:
        return f'{hours}h {minutes}m remaining'
    return f'{minutes}m remaining'
