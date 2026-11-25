"""Narrow, deterministic missing-certificate reply policy. No mailbox or file I/O."""
import re
from html import escape

from inbox_companion_policy import authored, classify

COLLECTION_URL = 'https://account.sportscaveshop.com/pages/019ef355-648a-7996-8977-897320e5ffd7'
DOCUMENT = re.compile(r'\b(?:certificat(?:e|es)|certifcate|coa|packing\s+slips?|package\s+slips?)\b', re.I)
MISSING = re.compile(
    r"\b(?:missing|not\s+(?:received|included|enclosed|arrived|in\s+(?:the\s+)?(?:box|package|parcel))|"
    r"(?:no|without)\s+(?:a\s+|any\s+|the\s+)?(?:packing|package|certificate|coa)|"
    r"(?:didn['’]?t|haven['’]?t|hasn['’]?t|never|did\s+not|have\s+not|has\s+not)\s+(?:receive[dt]?|get|arrive[dt]?)|"
    r"(?:can|could|would)\s+you\s+(?:please\s+)?(?:send|resend|provide)|"
    r"(?:where|how)\b.{0,55}\b(?:certificate|certificates|coa)|"
    r"(?:send|resend|access|find|download)\s+(?:me\s+)?(?:my|the|a)\s+(?:certificate|coa))\b", re.I)
OTHER_ISSUE = re.compile(r'\b(?:refund|cancel(?:lation)?|damaged|broken|chargeback|wrong\s+(?:item|product|size)|'
                         r'change\s+(?:my\s+|the\s+)?(?:address|order|frame|size))\b', re.I)
READY = {'certificate ready', 'ready', 'complete', 'completed', 'issued'}


def request(subject, text, *, is_reply=False):
    body = authored(text)
    value = body if is_reply or re.match(r'^\s*(?:re|fw|fwd)\s*:', subject, re.I) else subject + '\n' + body
    # The subject can identify the document, but the new authored text must ask for help.
    document = DOCUMENT.search(subject + '\n' + body)
    if not document or not MISSING.search(value):
        return False
    if re.search(r'\b(?:not missing|already (?:received|found)|found (?:my|the) certificate|no longer need)\b', body, re.I):
        return False
    if OTHER_ISSUE.search(body) or classify(subject, body, is_reply=is_reply)['kind'] != 'ignore':
        return False
    return True


def safe_sender(header, mailbox):
    sender = str(header.get('sender', {}).get('email', '')).strip().casefold()
    return bool(sender and sender != mailbox.casefold() and '@' in sender
                and not header.get('error') and not header.get('automated')
                and header.get('message_id')
                and any(str(p.get('email', '')).strip().casefold() == mailbox.casefold() for p in header.get('to', []))
                and not re.search(r'^(?:no[-_]?reply|mailer-daemon|postmaster)(?:[+@._-])', sender)
                and all(str(p.get('email', '')).strip().casefold() == sender for p in header.get('reply_to', [])))


def ready_customer(header, text, orders):
    sender = header['sender']['email'].strip().casefold()
    numbers = set(re.findall(r'\bSC\s*(\d{3,12})\b', header.get('subject', '') + '\n' + authored(text), re.I))
    if len(numbers) > 1:
        return False
    for order in orders:
        if str(order.get('customer_email', '')).strip().casefold() != sender:
            continue
        number = re.sub(r'^#?SC', '', str(order.get('order_name', '')), flags=re.I)
        if numbers and number not in numbers:
            continue
        if str(order.get('fulfillment_status', '')).casefold() in {'cancelled', 'canceled'}:
            continue
        if any(str(e.get('certificate_status', '')).strip().casefold() in READY for e in order.get('editions', [])):
            return True
    return False


def reply_html(header):
    name = str(header.get('sender', {}).get('name', '')).strip().split()
    greeting = 'Hi ' + escape(name[0][:60]) if name else 'Hi'
    return (f'<p>{greeting},</p>'
            f'<p>Click the link – <a href="{COLLECTION_URL}">My Collection</a> – and log in to access your certificate.</p>'
            '<p>Framing is also available if required.</p>'
            '<p>A review through My Collection would be amazing.</p>')
