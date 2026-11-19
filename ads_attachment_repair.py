"""One-shot repair permits under the existing durable ad-job lease."""
import time
from uuid import uuid4


def advance(value, event):
    """Mutate a generating checkpoint; return whether this call owns Send."""
    from ads_companion_transfer import FILES
    import design_publish_ad as ads
    if value.get('stage') != 'generating' or value.get('posting_id'):
        return False
    missing = [name for name in FILES if name not in value.get('artifacts', {})]
    if not missing:
        if value.get('attachment_repair'):
            value['attachment_repair']['state'] = 'finished'
        return False
    repair = value.get('attachment_repair')
    if repair and event.get('repair_seen') == repair['id'] and repair['state'] == 'sending':
        repair.update(state='submitted', submitted_at=time.time())
        value.update(collect_only=True, detail='Repair requested in the saved chat; collecting restored attachments')
    if event.get('transfer_failed') is True and (not repair or (
            repair['state'] == 'submitted' and event.get('repair_id') == repair['id'] and event.get('repair_seen') != repair['id'])):
        if not ads.CHAT.fullmatch(value.get('chat_url', '')):
            raise ValueError('Attachment repair needs the original saved ad chat.')
        attempt = int((repair or {}).get('attempt', 0)) + 1
        if attempt > 2:
            raise ValueError('ChatGPT attachments still fail after two automatic repairs. Saved files and posting receipts were preserved; review the saved chat.')
        repair = dict(id=str(uuid4()), attempt=attempt, state='ready', names=missing, created_at=time.time())
        value['attachment_repair'] = repair
        value['detail'] = 'Automatically restoring broken attachments in the saved chat'
    if not repair:
        return False
    if repair['state'] in ('ready', 'sending') and time.time() - repair['created_at'] > 300:
        raise ValueError('Could not confirm the attachment repair message. Check the saved chat; no duplicate repair was sent.')
    if repair['state'] == 'submitted' and time.time() - repair['submitted_at'] > 1800:
        raise ValueError('The attachment repair did not deliver all files within 30 minutes. Check the saved chat; existing files were preserved.')
    if event.get('repair_claim') == repair['id'] and repair['state'] == 'ready':
        repair['state'] = 'sending'
        return True  # Caller must persist before returning this one-shot permit.
    return False
