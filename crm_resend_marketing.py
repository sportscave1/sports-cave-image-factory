"""Stage 1 CRM delivery. No inbox, audience, queue or webhook dependencies.

Only the explicitly confirmed admin diagnostic can send while marketing is off.
Provider responses never cross the boundary except for a validated receipt ID.
"""
import logging
import os
import re
from datetime import datetime, timezone
from email.utils import formataddr
from uuid import UUID

import requests
import os_accounts

LOG = logging.getLogger(__name__)
SUBJECT = 'Sports Cave OS — Resend Test'
TEXT = ('Sports Cave OS Resend delivery is connected successfully.\n\n'
        'This is a test email only. No production campaign is sent by this test.')
HTML = ('<!doctype html><html><body style="font-family:Arial,sans-serif;color:#222;'
        'background:#faf8f2;padding:24px"><main style="max-width:560px;margin:auto;'
        'background:white;padding:28px;border-top:4px solid #d5a642">'
        '<h2>Sports Cave</h2><p>Sports Cave OS Resend delivery is connected successfully.</p>'
        '<p>This is a test email only. No production campaign is sent by this test.</p>'
        '<small>Sports Cave OS · Delivery test</small></main></body></html>')
ERRORS = {
    'configuration_missing': 'Resend configuration is missing or invalid.',
    'invalid_recipient': 'Enter exactly one valid recipient email address.',
    'confirmation_required': 'Confirm this admin test send first.',
    'authentication_failed': 'API authentication failed.',
    'sender_rejected': 'Sender/domain rejected.',
    'invalid_request': 'Resend rejected the test request.',
    'resend_unavailable': 'Resend unavailable. Acceptance is uncertain; check Resend before sending another test.',
    'audit_unavailable': 'Audit storage is unavailable. No test email was sent.',
    'marketing_disabled': 'Production marketing delivery is disabled.',
    'stage_one_only': 'Production marketing delivery is not available in Stage 1.',
}


class DeliveryError(RuntimeError):
    def __init__(self, category):
        self.category = category
        super().__init__(ERRORS[category])


def single_email(value):
    """Accept one bare ASCII mailbox, never a list, object or display-name header."""
    if type(value) is not str or len(value) > 254 or value != value.strip():
        return ''
    if not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", value):
        return ''
    local, domain = value.rsplit('@', 1)
    if len(local) > 64 or local.startswith('.') or local.endswith('.') or '..' in local:
        return ''
    if any(not part or len(part) > 63 or part.startswith('-') or part.endswith('-') for part in domain.split('.')):
        return ''
    return value


def _config(env=None):
    env = os.environ if env is None else env
    return {name: str(env.get(name, '')).strip() for name in (
        'RESEND_MARKETING_API_KEY', 'RESEND_FROM_EMAIL', 'RESEND_FROM_NAME',
        'RESEND_REPLY_TO', 'CRM_MARKETING_ENABLED')}


def get_resend_marketing_config_status(env=None):
    cfg = _config(env)
    sender = single_email(cfg['RESEND_FROM_EMAIL'])
    reply = single_email(cfg['RESEND_REPLY_TO'])
    name = cfg['RESEND_FROM_NAME']
    name_ok = bool(name and len(name) <= 150 and not any(ord(c) < 32 for c in name))
    api = bool(cfg['RESEND_MARKETING_API_KEY'])
    return {'api_configured': api, 'from_configured': bool(sender),
            'from_name_configured': name_ok, 'reply_to_configured': bool(reply),
            'sender': sender, 'reply_to': reply, 'domain': sender.split('@')[-1] if sender else '',
            'marketing_enabled': cfg['CRM_MARKETING_ENABLED'].lower() == 'true',
            'configured': bool(api and sender and name_ok and reply)}


def _audit(user, operation, recipient, sender, status, message_id='', error_category='', campaign=None):
    # Direct existing audit writer: avoid the general wrapper's raw exception logging.
    try:
        from supabase_backend import record_activity_log
        return bool(record_activity_log(
            action_type='resend_test_send', page='CRM & Marketing',
            message='Admin Resend delivery test: ' + status,
            entity_type='crm_delivery_test', entity_id=operation,
            event_key='resend-test:' + operation + ':' + status,
            actor=str(user.get('id') or user.get('username') or ''),
            metadata={'timestamp': datetime.now(timezone.utc).isoformat(),
                      'action': 'resend_test_send', 'recipient': recipient,
                      'sender': sender, 'provider': 'resend', 'message_id': message_id,
                      'status': status, 'error_category': error_category,
                      'test_kind': 'CAMPAIGN TEST' if campaign else 'ADMIN DIAGNOSTIC',
                      'campaign': campaign},
        ))
    except Exception:
        LOG.warning('resend_test_send audit_unavailable')
        return False


def send_resend_test_email(*, user, recipient, confirmed, operation_id, env=None, session=None):
    """One fixed diagnostic, called only by the admin form. No recipient collections.

    No retries. The UI reuses a UUID for this attempt; Resend receives it as the
    idempotency key. No body/template/segment/customer overrides are accepted.
    """
    return _send_admin_email(user=user, recipient=recipient, confirmed=confirmed, operation_id=operation_id,
                             env=env, session=session, message={'subject':SUBJECT,'html':HTML,'text':TEXT})


def _send_admin_email(*, user, recipient, confirmed, operation_id, message, env=None, session=None, campaign=None):
    """Internal single-recipient transport shared by vetted renderers, never audiences."""
    if not os_accounts.is_admin(user):
        raise PermissionError('Only an active administrator can send a Resend test.')
    if confirmed is not True:
        raise DeliveryError('confirmation_required')
    if not single_email(recipient):
        raise DeliveryError('invalid_recipient')
    try:
        operation = str(UUID(str(operation_id)))
    except (ValueError, TypeError, AttributeError):
        raise DeliveryError('confirmation_required') from None
    cfg = _config(env)
    if not get_resend_marketing_config_status(cfg)['configured']:
        raise DeliveryError('configuration_missing')
    sender = formataddr((cfg['RESEND_FROM_NAME'], cfg['RESEND_FROM_EMAIL']))
    audit_extra = {'campaign':campaign} if campaign else {}
    if not _audit(user, operation, recipient, sender, 'requested', **audit_extra):
        raise DeliveryError('audit_unavailable')
    payload = {'from': sender, 'reply_to': cfg['RESEND_REPLY_TO'], 'to': [recipient],
               'subject': message['subject'], 'html': message['html'], 'text': message['text'],
               'tags': [{'name': 'purpose', 'value': 'campaign_test' if campaign else 'admin_delivery_test'}]}
    category = 'resend_unavailable'
    http_status = 0
    message_id = ''
    try:
        client = session or requests
        response = client.post('https://api.resend.com/emails', json=payload,
                               headers={'Authorization': 'Bearer ' + cfg['RESEND_MARKETING_API_KEY'],
                                        'Idempotency-Key': 'crm-admin-test/' + operation},
                               timeout=15, allow_redirects=False)
        http_status = response.status_code
        if 200 <= http_status < 300:
            # Resend IDs are UUIDs; reject arbitrary provider text rather than echo it.
            message_id = str(UUID(response.json()['id']))
        elif http_status == 401:
            category = 'authentication_failed'
        elif http_status == 403:
            category = 'sender_rejected'
        elif http_status in (400, 422):
            category = 'invalid_request'
    except Exception:
        # Never log exception messages, response bodies, headers or request objects.
        pass
    if not message_id:
        LOG.warning('resend_test_send failed category=%s http_status=%s', category, http_status)
        _audit(user, operation, recipient, sender,
               'uncertain' if category == 'resend_unavailable' else 'failed', error_category=category, **audit_extra)
        raise DeliveryError(category) from None
    saved = _audit(user, operation, recipient, sender, 'accepted', message_id=message_id, **audit_extra)
    return {'message': 'Test email accepted by Resend', 'message_id': message_id,
            'audit_saved': saved, 'accepted_at': datetime.now(timezone.utc).isoformat()}


def send_marketing_email(*args, **kwargs):
    """Reserved production boundary; Stage 1 cannot dispatch campaigns or audiences."""
    if not get_resend_marketing_config_status()['marketing_enabled']:
        raise DeliveryError('marketing_disabled')
    raise DeliveryError('stage_one_only')
