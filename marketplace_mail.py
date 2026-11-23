"""Reuse the OS Resend subscription. No second account, mail queue or message copy."""
from email.utils import parseaddr
import os
import smtplib
import ssl

from marketplace import email


def smtp_plan(environ=None):
    env = os.environ if environ is None else environ
    # Prefer the CRM's paired sender/key. A key can be restricted to its domain;
    # never silently pair a reporting key with a different marketing sender.
    pairs = (('RESEND_MARKETING_API_KEY', env.get('RESEND_FROM_EMAIL', '')),
             ('RESEND_API_KEY', parseaddr(env.get('ACTIVITY_DIGEST_FROM', ''))[1]))
    key_name, sender = next(((key, address) for key, address in pairs if env.get(key) and address), ('', ''))
    if sender:
        sender = email(sender)
    return {'provider': 'Resend', 'host': 'smtp.resend.com', 'port': 465, 'username': 'resend',
            'sender_email': sender, 'sender_name': 'Sports Cave Marketplace',
            'key_variable': key_name, 'configured': bool(key_name and sender)}


def check_smtp(environ=None, factory=None):
    env = os.environ if environ is None else environ
    plan = smtp_plan(env)
    if not plan['configured']:
        raise ValueError('The existing OS Resend sender and sending key must be configured together.')
    connection = None
    try:
        connection = (factory or smtplib.SMTP_SSL)(plan['host'], plan['port'], timeout=12,
                                                   context=ssl.create_default_context())
        connection.login(plan['username'], env[plan['key_variable']])
    except (OSError, smtplib.SMTPException):
        raise ValueError('Resend SMTP could not be verified. Check the existing sending key and domain.') from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass
    # Authentication only. Never calls MAIL, RCPT, DATA or sendmail.
    return plan
