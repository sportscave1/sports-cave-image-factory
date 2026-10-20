"""Inbox-only, bounded presentation operations. No transport or send authority."""
from datetime import date
from email.utils import getaddresses
import time

import os_accounts
from support_email_provider import MailboxError, _quoted_search


def filters(value):
    if not isinstance(value, dict) or set(value) - {'unread', 'flagged', 'attachments', 'since', 'before', 'sender', 'recipient', 'subject', 'scope'}:
        raise MailboxError('Invalid search filters.')
    result = {}
    for key in ('unread', 'flagged', 'attachments'):
        if key in value and not isinstance(value[key], bool):raise MailboxError('Invalid search filter.')
        if value.get(key):result[key] = True
    for key in ('sender', 'recipient', 'subject'):
        text = str(value.get(key, '')).strip()
        if text:
            _quoted_search(text)
            result[key] = text
    for key in ('since', 'before'):
        if value.get(key):
            try:result[key] = date.fromisoformat(str(value[key])).isoformat()
            except ValueError:raise MailboxError('Use a valid search date.') from None
    if result.get('since') and result.get('before') and result['since'] >= result['before']:
        raise MailboxError('The end date must be after the start date (end date is exclusive).')
    if value.get('scope', 'folder') not in {'folder', 'all'}:raise MailboxError('Invalid search scope.')
    if value.get('scope') == 'all':result['scope'] = 'all'
    return result


def criteria(value):
    f = filters(value)
    terms = []
    for key, imap in [('unread','UNSEEN'),('flagged','FLAGGED')]:
        if f.get(key):terms.append(imap)
    for key, imap in [('sender','FROM'),('recipient','TO'),('subject','SUBJECT')]:
        if f.get(key):terms.append(imap+' '+_quoted_search(f[key]))
    for key, imap in [('since','SINCE'),('before','BEFORE')]:
        if f.get(key):terms.append(imap+' '+date.fromisoformat(f[key]).strftime('%d-%b-%Y'))
    return ' '.join(terms)


def contacts(workspace, query):
    """No global cache; recent addresses come from this actor's drafts and sends."""
    if not os_accounts.can_access_page(workspace.user, 'Email'):raise PermissionError('Email permission required.')
    term = str(query or '').strip().casefold()
    if not 2 <= len(term) <= 80 or any(ord(c)<32 for c in term):return []
    rows = []
    for draft in workspace.state.get('local_drafts', []):
        for name, email in getaddresses([str(draft.get('recipients', ''))]):
            if term in (name+' '+email).casefold() and '@' in email:
                rows.append(dict(name=name, email=email, source='Your recent drafts'))
    if workspace.durable:
        for email in workspace.durable.recent_recipients(workspace.config.address, workspace.user['id']):
            if term in email.casefold():rows.append(dict(name='',email=email,source='Your recent sends'))
    if os_accounts.can_access_page(workspace.user, 'CRM Customers'):
        from support_email_store import search_contacts
        rows.extend(search_contacts(workspace.user, term))
    unique = {}
    for row in rows:
        email = row.get('email','').strip()
        if '@' in email and not any(c in email for c in '\r\n<> '):unique.setdefault(email.casefold(), row)
    return list(unique.values())[:8]


def handle(workspace, action, event):
    s = workspace.state
    if action == 'contact_search':
        query = str(event.get('query', ''))[:80]
        # A typed lookup cannot enumerate the CRM on startup or without permission.
        if time.monotonic()-s.get('contact_checked',0)<.2:return True
        s['contact_checked'] = time.monotonic()
        try:s['contact_result'] = dict(query=query, rows=contacts(workspace, query), error='')
        except Exception:s['contact_result'] = dict(query=query, rows=[], error='Contacts unavailable. Enter an address manually.')
        return True
    if action == 'dismiss_notice':
        s['notice'] = ''
        return True
    if action == 'collapse_message':
        message = workspace._header(event.get('message_key'))
        from support_email_workspace import reference_key
        key = reference_key(message)
        s['expanded'].discard(key)
        s.get('body_errors', {}).pop(key, None)
        if s.get('body_pending') == key:workspace._cancel_body_load()
        s['image_grants'] = set()
        return True
    if action == 'expand_conversation':
        from support_email_workspace import reference_key
        s['expanded'].update(reference_key(m) for m in s.get('conversation',[]) if workspace._content(m))
        s['notice'] = 'Cached messages expanded. Open any remaining message to load it.'
        return True
    if action == 'collapse_conversation':
        s['expanded'] = set();s['image_grants'] = set()
        s['body_errors'] = {}
        workspace._cancel_body_load()
        return True
    if action == 'restore':
        message = workspace._header(event.get('message_key'))
        if message['folder'] != workspace.roles.get('trash'):raise MailboxError('Restore is available only in Trash.')
        # No guessed original destination: the menu always asks for a discovered folder.
        workspace.message_action('move', message, event.get('destination'))
        return True
    if action != 'bulk_action':return False
    items = event.get('items')
    operation = event.get('operation')
    if operation not in {'mark_read','mark_unread','star','unstar','archive','move','trash'}:
        raise MailboxError('Unsupported bulk action.')
    if not isinstance(items,list) or not 1<=len(items)<=50:raise MailboxError('Select between 1 and 50 visible messages.')
    if len({item.get('key') for item in items if isinstance(item,dict)}) != len(items):raise MailboxError('Invalid or duplicate selection.')
    results=[]
    for item in items:
        key=item.get('key')
        try:
            message=workspace._header(key)
            if item.get('identity') != workspace._reader_identity(message):raise MailboxError('Message identity changed. Refresh and select it again.')
        except MailboxError as exc:
            results.append(dict(key=key,status='not_attempted',message=str(exc)));continue
        try:
            flag = '\\Seen' if operation.startswith('mark_') else '\\Flagged'
            if operation in {'mark_read','mark_unread','star','unstar'} and ((flag in message['flags']) == (operation in {'mark_read','star'})):
                results.append(dict(key=key,status='unchanged',message='Already in this state in the current snapshot; no provider write.'));continue
            workspace.message_action(operation,message,event.get('destination'))
            results.append(dict(key=key,status='confirmed',message=s.get('notice') or 'Confirmed'))
        except Exception:
            # A disconnected write can be ambiguous. Do not replay or assert rollback.
            results.append(dict(key=key,status='unconfirmed',message='Not confirmed. Refresh and verify the message before retrying.'))
    s['bulk_result']=dict(id=event['id'],items=results)
    count=sum(r['status']=='confirmed' for r in results)
    s['notice']=f'{count} of {len(results)} message actions confirmed.'
    s['image_grants']=set()
    return True
