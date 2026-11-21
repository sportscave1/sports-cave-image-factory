"""Restricted Prodigi v5 adapter: read existing orders and edit draft artwork only.

Deliberately has no create, submit, resume, payment or fulfilment operation.
"""
import os
import re
import requests
from urllib.parse import urlencode


class ProdigiError(ValueError):
    pass


def identifier(value):
    value = str(value or '')
    if not re.fullmatch(r'[A-Za-z0-9-]{1,100}', value):
        raise ProdigiError('A verified Prodigi order/item ID is required.')
    return value


class Client:
    def __init__(self, key=None, transport=None, *, mode='live'):
        if mode not in ('live', 'sandbox'):
            raise ProdigiError('Select live or sandbox explicitly.')
        self.key = key or os.getenv('PRODIGI_SANDBOX_API_KEY' if mode == 'sandbox' else 'PRODIGI_API_KEY', '')
        if not self.key:
            raise ProdigiError('The server Prodigi API key is not configured.')
        if self.key.startswith(('live_', 'sandbox_')) and not self.key.startswith(mode + '_'):
            raise ProdigiError('The API key belongs to a different environment.')
        # Prodigi's dashboards display raw UUID keys; v5 requires a mode prefix.
        if not self.key.startswith(mode + '_'):
            self.key = mode + '_' + self.key
        self.mode = mode
        self.transport = transport or requests.Session()
        # This is a server API client, independent of every person's browser
        # session. Do not retain/replay provider Set-Cookie responses either.
        if transport is None:
            import http.cookiejar
            class NoCookies(http.cookiejar.DefaultCookiePolicy):
                def set_ok(self, cookie, request): return False
                def return_ok(self, cookie, request): return False
            self.transport.cookies.set_policy(NoCookies())

    def request(self, method, path, body=None, *, listing=False):
        allowed = ((method == 'GET' and re.fullmatch(r'/orders/[A-Za-z0-9-]{1,100}', path))
                   or (method == 'GET' and path.startswith('/orders?merchantReference=') and listing)
                   or (method == 'PATCH' and re.fullmatch(r'/orders/[A-Za-z0-9-]{1,100}/items/[A-Za-z0-9-]{1,100}', path)))
        if not allowed:
            raise ProdigiError('Only existing order reads and draft artwork edits are supported.')
        if method == 'PATCH' and any(os.getenv(flag, '').lower() != 'true' for flag in
                ('SPORTS_CAVE_PRODIGI_PREPARE', 'SPORTS_CAVE_PRODIGI_DRAFT_EDIT_ACCEPTED')):
            raise ProdigiError('Artwork writes are disabled pending imported-order acceptance.')
        try:
            response = self.transport.request(method, 'https://api.prodigi.com/v5' + path,
                headers={'X-API-Key': self.key, 'Content-Type': 'application/json'},
                json=body, timeout=(5, 20), allow_redirects=False)
        except requests.RequestException:
            raise ProdigiError('Prodigi did not acknowledge the request. Reconcile the same item before retrying.') from None
        if response.status_code not in (200, 201):
            # Provider bodies can contain addresses, signed URLs and credentials.
            raise ProdigiError(f'Prodigi returned HTTP {response.status_code}; no replacement order was created.')
        envelope = response.json()
        data = envelope.get('data')
        if listing:
            total = envelope.get('total')
            if not isinstance(data, list) or (total is not None and total > len(data)):
                raise ProdigiError('The Prodigi order lookup is incomplete or ambiguous.')
            return data
        if not isinstance(data, dict):
            raise ProdigiError('Prodigi returned an unsupported order response.')
        return data

    def order(self, order_id):
        return self.request('GET', '/orders/' + identifier(order_id))

    def find(self, reference):
        return self.request('GET', '/orders?' + urlencode({'merchantReference': reference, 'limit': 100}), listing=True)

    def artwork(self, order_id, item_id, url, md5):
        # No arbitrary paths or request payloads from a browser/worker.
        return self.request('PATCH', '/orders/' + identifier(order_id) + '/items/' + identifier(item_id),
            {'assets': [{'printArea': 'default', 'url': url, 'md5Hash': md5}]})
