"""Durable retries of original ad checkpoints; never allocate replacement jobs."""
import re
import time
from uuid import uuid4

VERSION = 1
LEGACY_PREFIXES = (
    'A dependency did not respond.', 'The three covers and ad copy did not arrive',
    'Ad generation exceeded six hours.', 'ChatGPT attachments still fail after two automatic repairs.',
    'The attachment repair did not deliver all files', 'Could not confirm the attachment repair message.',
    'Meta Posting needs review.', 'Meta catalogue membership is still unverified after 24 hours.',
)
POLICY_BLOCK = re.compile(r'moderation|safety rejection|policy rejection|content policy', re.I)


class RetryAd(ValueError):
    def __init__(self, message, *, code='dependency', mode=None):
        super().__init__(message)
        self.code, self.mode = code, mode


def schedule(value, reason, *, code='dependency', mode=None, delay=None):
    """Back off without occupying the queue; preserve every receipt and permit."""
    now = time.time()
    previous = value.get('auto_recovery') or {}
    attempt = int(previous.get('attempts', 0)) + 1
    checkpoint = (value.get('resume_stage') or 'preparing') if value['stage'] == 'waiting' else value['stage']
    if value.get('posting_id'):
        checkpoint = 'posting'
    elif checkpoint == 'failed':
        checkpoint = 'generating' if value.get('chat_url') and value.get('folder') else 'preparing'
    delay = min(900, 60 * 2 ** min(attempt - 1, 4)) if delay is None else delay
    if (value.get('attachment_repair') or {}).get('attempt', 0) >= 2:
        delay = max(delay, 900)
    value.update(stage='waiting', resume_stage=checkpoint, recovery_checked_version=VERSION,
                 detail=f'Automatic recovery scheduled in {int(delay)} seconds. {str(reason)[:450]}')
    value['auto_recovery'] = dict(state='scheduled', attempts=attempt, next_at=now+delay,
        checkpoint=checkpoint, code=code, mode=mode or previous.get('mode'), reason=str(reason)[:600])
    return value


def legacy(value):
    """Only known recoverable old failures opt in; provider refusals stay intact."""
    reason = str(value.get('detail') or '')
    value['recovery_checked_version'] = VERSION
    if POLICY_BLOCK.search(reason) or not reason.startswith(LEGACY_PREFIXES):
        return False
    mode = 'complete_missing' if reason.startswith(('The three covers and ad copy did not arrive', 'Ad generation exceeded six hours.')) else None
    schedule(value, reason, code='legacy', mode=mode, delay=0)
    return True


def activate(value):
    """Resume only saved inputs, not the original Send or an uncertain repair."""
    retry = value['auto_recovery']
    retry['state'] = 'running'
    value['stage'] = value.pop('resume_stage', retry['checkpoint'])
    value.pop('timed_stage', None)
    value.pop('dependency_failed_at', None)
    if value['stage'] == 'opening':
        value['handoff_started_at'] = time.time()
    if value['stage'] == 'generating':
        value.update(collect_only=True, resume_token=str(uuid4()),
                     generation_started_at=time.time(), last_chat_activity_at=time.time())
        value.pop('chat_finished_at', None)
        repair = value.get('attachment_repair')
        # A new recovery message is allowed only after the previous permit was
        # acknowledged and a different, finished assistant response was observed.
        # Uncertain sends retain their original permit indefinitely.
        if (repair and repair['state'] == 'submitted' and
                value.get('last_finished_activity') is not None and
                value['last_finished_activity'] != repair.get('start_activity') and
                value.get('last_finished_at', 0) >= repair['submitted_at']):
            value.setdefault('attachment_repair_history', []).append(repair)
            value['attachment_repair_history'] = value['attachment_repair_history'][-10:]
            if repair.get('mode') == 'complete_missing':
                retry['mode'] = 'complete_missing'
            value.pop('attachment_repair')
            repair = None
        if repair:
            # Reopen collection, retaining any consumed Send permit. Never
            # infer that a missing acknowledgement permits another click.
            if repair['state'] == 'submitted':
                repair['submitted_at'] = time.time()
            elif repair['state'] in ('ready', 'sending'):
                repair['observation_started_at'] = time.time()
        if retry.get('mode') == 'complete_missing' and not repair:
            value['completion_needed'] = True
    value['detail'] = 'Automatically resuming the saved '+retry['checkpoint']+' checkpoint'


def posting_can_resume(row):
    from meta_posting_recovery import requires_reconciliation
    if row.get('running_here') or row.get('lease_active') or requires_reconciliation(row):
        return False
    return row.get('status') not in ('COMPLETE', 'AMBIGUOUS', 'ABANDONED_EXTERNALLY')
