"""Private marketplace conversations, offers and seller-provided PayPal invoices.

Each message is its own bounded record. Participant indexes and key-range reads
use the existing primary key; no customer table is exposed through PostgREST.
"""
from copy import deepcopy
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from marketplace import clean_text, email, identifier, now
from marketplace_accounts import digest
from marketplace_store import MarketplaceStore, PREFIX, read, put, lock


def invoice_url(value):
    raw = str(value or '')
    if any(ord(c) < 32 for c in raw):
        raise ValueError('Paste the share link from your PayPal invoice.')
    value = raw.strip()
    if len(value) > 300 or any(ord(c) < 33 for c in value):
        raise ValueError('Paste the share link from your PayPal invoice.')
    parsed = urlsplit(value)
    code = r'INV2-(?:[A-Z0-9]{4}-){3}[A-Z0-9]{4}'
    if (parsed.scheme != 'https' or parsed.netloc not in ('www.paypal.com', 'paypal.com')
            or parsed.query or parsed.username or parsed.password
            or not ((parsed.path == '/invoice/p/' and re.fullmatch(code, parsed.fragment))
                    or (re.fullmatch('/invoice/payerView/details/' + code, parsed.path) and not parsed.fragment))):
        raise ValueError('Use a PayPal invoice share link, starting https://www.paypal.com/invoice/.')
    return urlunsplit(('https', 'www.paypal.com', parsed.path, '', parsed.fragment))


def amount(value):
    from decimal import Decimal
    value = str(value or '').strip()
    if not re.fullmatch(r'\d{1,5}(?:\.\d{1,2})?', value):
        raise ValueError('Enter a total in AUD with up to two decimal places.')
    result = int(Decimal(value) * 100)
    if not 100 <= result <= 5100000:
        raise ValueError('Enter a total between A$1 and A$51,000, including postage.')
    return result


def scan(conn, prefix, *, limit=100, after='', recent=False):
    lower = PREFIX + prefix + after
    # Suffixes are UUIDs, hashes or zero-padded numbers. A letter sorts after
    # these under both C and the production locale; '~' sorts before them there.
    upper = PREFIX + prefix + 'z'
    order = 'updated_at DESC' if recent else 'key'
    return [r['value'] for r in conn.execute(
        'SELECT value FROM crm_runtime_state WHERE key > %s AND key < %s AND key LIKE %s ORDER BY ' + order + ' LIMIT %s',
        (lower, upper, PREFIX + prefix + '%', limit)).fetchall()]


class ChatStore(MarketplaceStore):
    @staticmethod
    def _active(conn, uid):
        row = read(conn, 'account:' + identifier(uid))
        if not row or row['status'] != 'active':
            raise PermissionError('This marketplace account is unavailable.')
        return row

    @staticmethod
    def _membership(conn, thread_id, uid):
        thread = read(conn, 'thread:' + identifier(thread_id))
        if not thread or uid not in (thread['buyer_id'], thread.get('seller_id')):
            raise ValueError('Conversation unavailable.')
        ChatStore._active(conn, uid)
        return thread

    def accounts(self):
        with self.db() as conn:
            return scan(conn, 'account:', limit=500, recent=True)

    def set_account_status(self, uid, status, actor):
        if status not in ('active', 'blocked'):
            raise ValueError('Choose active or blocked.')
        with self.db() as conn:
            key = 'account:' + identifier(uid)
            lock(conn, key)
            row = read(conn, key)
            if not row:
                raise ValueError('Account unavailable.')
            row.update(status=status, reviewed_at=now(), reviewed_by=str(actor))
            put(conn, key, row)

    def invite(self, address, name, actor):
        address, name = email(address), clean_text(name, 'display name', 70)
        with self.db() as conn:
            key = 'invitation:' + digest(address)
            lock(conn, key)
            if read(conn, 'account-email:' + digest(address)):
                raise ValueError('This email already has a marketplace account.')
            row = {'email': address, 'name': name, 'created_at': now(), 'created_by': str(actor),
                   'status': 'awaiting signup'}
            put(conn, key, row)
        return row

    def invitations(self):
        with self.db() as conn:
            return scan(conn, 'invitation:', limit=100, recent=True)

    def _claim(self, conn, profile):
        # Verified email is supplied by Accounts, never by an API payload. An
        # existing seller_id is immutable, including after email re-registration.
        pending = scan(conn, 'seller-pending:' + digest(profile['email']) + ':', limit=100)
        for index in pending:
            key = 'thread:' + index['id']
            lock(conn, key)
            thread = read(conn, key)
            if not thread or thread.get('seller_id') or thread['seller_email_hash'] != digest(profile['email']):
                continue
            lock(conn, 'listing:' + thread['listing_id'])
            listing = read(conn, 'listing:' + thread['listing_id'])
            if not listing or listing.get('seller_user_id') not in (None, profile['id']):
                continue
            thread['seller_id'] = profile['id']
            listing['seller_user_id'] = profile['id']
            put(conn, 'listing:' + listing['id'], listing)
            put(conn, key, thread)
            self._indexes(conn, thread)
            conn.execute('DELETE FROM crm_runtime_state WHERE key=%s',
                         (PREFIX + 'seller-pending:' + digest(profile['email']) + ':' + thread['id'],))

    def inbox(self, uid):
        with self.db() as conn:
            profile = self._active(conn, uid)
            self._claim(conn, profile)
            indexes = scan(conn, 'member-thread:' + uid + ':', recent=True, limit=100)
            threads = [read(conn, 'thread:' + row['id']) for row in indexes]
            return [self._public_thread(t, uid) for t in threads if t and uid in (t['buyer_id'], t.get('seller_id'))]

    @staticmethod
    def _public_thread(thread, uid):
        return {k: deepcopy(thread[k]) for k in ('id', 'listing_id', 'item_title', 'buyer_name', 'seller_name',
                'seq', 'created_at', 'updated_at') if k in thread} | {
                'role': 'buyer' if thread['buyer_id'] == uid else 'seller',
                'seller_joined': bool(thread.get('seller_id')), 'reported': bool(thread.get('report')),
                'blocked': bool(thread.get('blocked_by')), 'blocked_by_me': uid in thread.get('blocked_by', [])}

    def conversation(self, thread_id, uid, after=0, *, mark_read=False):
        if not isinstance(after, int) or not 0 <= after <= 1000000:
            raise ValueError('Invalid message cursor.')
        with self.db() as conn:
            thread = self._membership(conn, thread_id, uid)
            rows = scan(conn, 'message:' + thread['id'] + ':', after=f'{after:012d}', limit=51)
            if mark_read:
                from marketplace_notifications import acknowledge
                seen = rows[min(len(rows), 50) - 1]['seq'] if rows else min(after, thread['seq'])
                acknowledge(conn, thread, uid, seen)
            return {'conversation': self._public_thread(thread, uid),
                    'messages': rows[:50], 'has_more': len(rows) > 50}

    def set_email_notifications(self, uid, enabled):
        if type(enabled) is not bool:
            raise ValueError('Choose whether to receive email alerts.')
        with self.db() as conn:
            key = 'account:' + identifier(uid)
            lock(conn, key)
            row = self._active(conn, uid)
            row['email_notifications'] = enabled
            put(conn, key, row)

    @staticmethod
    def _indexes(conn, thread):
        for uid in (thread['buyer_id'], thread.get('seller_id')):
            if uid:
                put(conn, f'member-thread:{uid}:{thread["id"]}', {'id': thread['id']})
        if not thread.get('seller_id'):
            put(conn, f'seller-pending:{thread["seller_email_hash"]}:{thread["id"]}', {'id': thread['id']})

    @staticmethod
    def _rate(conn, uid):
        timestamp = datetime.now(timezone.utc)
        key = 'chat-rate:' + uid
        lock(conn, key)
        row = read(conn, key, {})
        minute, hour = timestamp.strftime('%Y%m%d%H%M'), timestamp.strftime('%Y%m%d%H')
        m = row.get('minute_count', 0) if row.get('minute') == minute else 0
        h = row.get('hour_count', 0) if row.get('hour') == hour else 0
        if m >= 20 or h >= 200:
            raise ValueError('Please wait before sending more messages.')
        put(conn, key, {'minute': minute, 'hour': hour, 'minute_count': m + 1, 'hour_count': h + 1})

    def start(self, uid, listing_id, payload):
        listing_id, uid = identifier(listing_id), identifier(uid)
        with self.db() as conn:
            buyer = self._active(conn, uid)
            self._rate(conn, uid)
            key = f'thread-for:{listing_id}:{uid}'
            lock(conn, key)
            pointer = read(conn, key)
            thread_id = pointer['id'] if pointer else str(uuid4())
            lock(conn, 'thread:' + thread_id)
            lock(conn, 'listing:' + listing_id)
            listing = read(conn, 'listing:' + listing_id)
            if not listing or listing['status'] != 'published':
                raise ValueError('This item is no longer available for new conversations.')
            if listing['seller_email'].lower() == buyer['email'] or listing.get('seller_user_id') == uid:
                raise ValueError('This is your listing. Reply to buyers from your inbox.')
            if pointer:
                thread = self._membership(conn, thread_id, uid)
            else:
                owner = read(conn, 'account-email:' + digest(listing['seller_email'].lower()))
                seller_id = listing.get('seller_user_id') or (owner or {}).get('id')
                if seller_id:
                    self._active(conn, seller_id)
                    listing['seller_user_id'] = seller_id
                    put(conn, 'listing:' + listing_id, listing)
                thread = {'id': thread_id, 'listing_id': listing_id, 'item_title': listing['title'],
                    'buyer_id': uid, 'buyer_name': buyer['name'], 'seller_id': seller_id,
                    'seller_name': listing['seller_name'], 'seller_email_hash': digest(listing['seller_email'].lower()),
                    'seq': 0, 'created_at': now(), 'updated_at': now(), 'blocked_by': []}
                put(conn, key, {'id': thread_id})
            result = self._append(conn, thread, uid, payload)
        return result

    def send(self, thread_id, uid, payload):
        with self.db() as conn:
            self._active(conn, uid)
            self._rate(conn, uid)
            lock(conn, 'thread:' + identifier(thread_id))
            thread = self._membership(conn, thread_id, uid)
            return self._append(conn, thread, uid, payload)

    def _append(self, conn, thread, uid, payload):
        request_id = identifier(payload.get('request_id'))
        receipt = 'message-request:' + thread['id'] + ':' + uid + ':' + request_id
        previous = read(conn, receipt)
        if previous:
            return previous
        if thread.get('blocked_by'):
            raise PermissionError('Messaging is paused in this conversation.')
        self._active(conn, thread['buyer_id'])
        if thread.get('seller_id'):
            self._active(conn, thread['seller_id'])
        kind = payload.get('kind', 'text')
        if kind != 'text':
            lock(conn, 'listing:' + thread['listing_id'])
        listing = read(conn, 'listing:' + thread['listing_id'])
        seller = uid == thread.get('seller_id')
        message = {'kind': kind, 'sender': 'seller' if seller else 'buyer', 'created_at': now()}
        if kind == 'text':
            message['text'] = clean_text(payload.get('text'), 'your message', 2000)
        elif kind in ('offer', 'invoice'):
            if not listing or listing['status'] != 'published':
                raise ValueError('Offers and invoices are paused while this listing is unavailable.')
            if seller != (kind == 'invoice'):
                raise PermissionError('Buyers make offers. Only the seller can send an invoice.')
            message.update(amount_cents=amount(payload.get('amount')), currency='AUD')
            if kind == 'invoice':
                message.update(url=invoice_url(payload.get('url')), status='shared')
            else:
                message['status'] = 'pending'
            if payload.get('text'):
                message['text'] = clean_text(payload['text'], 'your note', 500)
        elif kind == 'offer_response':
            if not listing or listing['status'] != 'published':
                raise ValueError('Offers are paused while this listing is unavailable.')
            if not seller:
                raise PermissionError('Only the seller can respond to an offer.')
            try:
                seq = int(payload['offer_seq'])
            except (ValueError, TypeError, KeyError):
                raise ValueError('Choose an offer.') from None
            offer_key = f'message:{thread["id"]}:{seq:012d}'
            offer = read(conn, offer_key)
            choice = payload.get('choice')
            if not offer or offer['kind'] != 'offer' or offer['status'] != 'pending' or choice not in ('accepted', 'declined'):
                raise ValueError('This offer already changed. Refresh the conversation.')
            offer['status'] = choice
            put(conn, offer_key, offer)
            message.update(offer_seq=seq, choice=choice, amount_cents=offer['amount_cents'], currency='AUD')
        else:
            raise ValueError('Choose a message, offer or PayPal invoice.')
        if thread['seq'] >= 100000:
            raise ValueError('This conversation has reached its message limit. Contact Sports Cave.')
        thread['seq'] += 1
        thread['updated_at'] = now()
        message['seq'] = thread['seq']
        put(conn, f'message:{thread["id"]}:{thread["seq"]:012d}', message)
        put(conn, 'thread:' + thread['id'], thread)
        self._indexes(conn, thread)
        result = {'id': thread['id'], 'seq': message['seq']}
        put(conn, receipt, result)
        from marketplace_notifications import enqueue
        enqueue(conn, thread, message)
        return result

    def safety(self, thread_id, uid, action, reason=''):
        with self.db() as conn:
            lock(conn, 'thread:' + identifier(thread_id))
            thread = self._membership(conn, thread_id, uid)
            if action in ('block', 'unblock'):
                blocked = set(thread.get('blocked_by', []))
                (blocked.add if action == 'block' else blocked.discard)(uid)
                thread['blocked_by'] = sorted(blocked)
            elif action == 'report':
                thread['report'] = {'reason': clean_text(reason, 'a reason for the report', 500),
                                    'at': now(), 'by': uid, 'status': 'new'}
            else:
                raise ValueError('Choose block, unblock or report.')
            thread['updated_at'] = now()
            put(conn, 'thread:' + thread['id'], thread)
            self._indexes(conn, thread)

    def admin_threads(self):
        with self.db() as conn:
            return scan(conn, 'thread:', limit=200, recent=True)

    def admin_messages(self, thread_id, after=0):
        with self.db() as conn:
            return scan(conn, 'message:' + identifier(thread_id) + ':', after=f'{after:012d}', limit=50)

    def resolve_report(self, thread_id, actor):
        with self.db() as conn:
            key = 'thread:' + identifier(thread_id)
            lock(conn, key)
            thread = read(conn, key)
            if thread and thread.get('report'):
                thread['report'].update(status='reviewed', reviewed_by=str(actor), reviewed_at=now())
                put(conn, key, thread)
