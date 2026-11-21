"""Explicit sandbox acceptance rows, separate from every live order/allocation.

Customer data stays on the authorised production server. Development tests use
synthetic fixtures. This module can create only sandbox drafts, never submit.
"""
from copy import deepcopy
import json
import os
import uuid

import prodigi_preparation as prep
from prodigi_client import Client, ProdigiError, identifier

PREFIX = 'prodigi_sandbox_test:'
LOCK = 19721123


class SandboxClient(Client):
    def __init__(self, key=None, transport=None):
        raw = key or os.getenv('PRODIGI_SANDBOX_API_KEY', '')
        if not raw or raw.removeprefix('sandbox_') == os.getenv('PRODIGI_API_KEY', '').removeprefix('live_'):
            raise ProdigiError('Configure the separate Prodigi sandbox key before creating a test.')
        super().__init__(raw, transport, mode='sandbox')

    def create_draft(self, body, token):
        if self.mode != 'sandbox' or not self.key.startswith('sandbox_') or body.get('submit') is not False:
            raise ProdigiError('Sandbox drafts only; payment and production are unavailable.')
        if not str(body.get('merchantReference', '')).startswith('SC-SANDBOX-'):
            raise ProdigiError('A labelled sandbox reference is required.')
        try:
            result = self.transport.request('POST', 'https://api.prodigi.com/v5/orders',
                headers={'X-API-Key': self.key, 'Idempotency-Key': token, 'Content-Type': 'application/json'},
                json=body, timeout=(5, 20), allow_redirects=False)
        except Exception:
            raise ProdigiError('Sandbox creation acknowledgement uncertain; recheck the same test before retrying.') from None
        if result.status_code not in (200, 201, 202):
            raise ProdigiError(f'Sandbox draft creation returned HTTP {result.status_code}.')
        data = result.json().get('data') or {}
        return identifier(data.get('id'))


def save(cur, value):
    value['updated_at'] = prep.now()
    cur.execute('''INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now())
        ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()''',
        (PREFIX + value['id'], json.dumps(value)))


def list_tests():
    with prep.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key LIKE %s ORDER BY updated_at DESC LIMIT 10', (PREFIX+'%',))
        return [r['value'] for r in cur.fetchall()]


def adapted(source, reference, recipient):
    snap = deepcopy(source)
    snap.update(order_reference=reference, recipient=deepcopy(recipient))
    snap['identity'].update(order_id=reference, line_id=reference+'-unit', ordinal=1)
    return snap


def payload(snapshot):
    mapping = snapshot['mapping']
    attributes = {} if mapping['frame'] == 'Unframed' else {'color': mapping['prodigi_frame_colour'].lower()}
    return {'merchantReference': snapshot['order_reference'], 'submit': False,
        'shippingMethod': snapshot['shipping'],
        'recipient': {k: v for k, v in snapshot['recipient'].items() if k in ('name','email','phoneNumber','address')},
        'items': [{'merchantReference': snapshot['identity']['line_id'], 'sku': mapping['prodigi_code'],
                   'quantity': 1, 'sizing': 'fitPrintArea', 'attributes': attributes}]}


def request(user, allocation_id):
    prep.require_user(user)
    if not prep.enabled():
        raise ValueError('Enable Orders preparation first.')
    SandboxClient()  # Reject missing/cross-environment credentials before storing anything.
    source = prep.resolve(int(allocation_id))
    live = Client()
    order_id, item_id = prep.discover(source, live)
    order = live.order(order_id)  # Read only, including completed/production source orders.
    item = next(i for i in order['items'] if str(i['id']) == item_id)
    from prodigi_qa import address_matches
    if not address_matches(source.get('recipient'), order.get('recipient')):
        raise ValueError('The source customer address differs from the OS; review before copying it.')
    if item.get('sku') != source['mapping']['prodigi_code'] or item.get('quantity') != 1:
        raise ValueError('Source product/quantity differs from the selected numbered unit.')
    if (source['mapping']['frame'] != 'Unframed' and str((item.get('attributes') or {}).get('color','')).casefold()
            != source['mapping']['prodigi_frame_colour'].casefold()):
        raise ValueError('Source frame differs from the selected numbered unit.')
    key = str(uuid.uuid4())
    reference = 'SC-SANDBOX-' + key
    recipient = deepcopy(order['recipient'])
    recipient['state_aliases'] = source['recipient'].get('state_aliases', [])
    snap = adapted(source, reference, recipient)
    value = dict(id=key, environment='sandbox', allocation_id=int(allocation_id),
        source_order_id=order_id, source_item_id=item_id, source_snapshot=source,
        snapshot=snap, fingerprint=prep.digest(snap), order_id='', item_id='',
        status='Queued', checks={}, history=[], message='Sandbox only; waiting for Orders companion.',
        requester=str(user['id']), hidden=False)
    with prep.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK,))
        cur.execute('SELECT value FROM app_settings WHERE key LIKE %s', (PREFIX+'%',))
        existing = [r['value'] for r in cur.fetchall()]
        if any(not r.get('hidden') and r['allocation_id'] == value['allocation_id'] for r in existing):
            raise ValueError('This unit already has a visible sandbox test. Review/remove that row first.')
        save(cur, value)
    return value


def run(value, provider, resolver, link, persist):
    if value.get('environment') != 'sandbox' or provider.mode != 'sandbox':
        raise ValueError('A separate sandbox provider is required.')
    source = resolver(value['allocation_id'])
    if prep.digest(source) != prep.digest(value['source_snapshot']):
        raise ValueError('Source artwork or allocation changed; sandbox test stopped.')
    if not value['order_id']:
        reference = value['snapshot']['order_reference']
        if value.get('create_intent'):
            found = [o for o in provider.find(reference) if o.get('merchantReference') == reference]
            if len(found) != 1:
                raise ValueError('Sandbox creation uncertain. No second draft will be created.')
            value['order_id'] = identifier(found[0]['id'])
        else:
            value['create_intent'] = True
            value['status'] = 'Creating sandbox draft'
            persist(value)  # Commit the create fence before contacting the sandbox API.
            value['order_id'] = provider.create_draft(payload(value['snapshot']), value['id'])
        persist(value)
    order = provider.order(value['order_id'])
    if order.get('charges') or order.get('status') != 'draft':
        raise ValueError('Sandbox is no longer an unpaid draft; no artwork will be changed.')
    items = [i for i in order.get('items', []) if i.get('merchantReference') == value['snapshot']['identity']['line_id']]
    if len(items) != 1:
        raise ValueError('Sandbox item identity is uncertain.')
    value['item_id'] = identifier(items[0]['id'])
    value['status'] = 'Queued' if not value.get('write_intent') else 'Uploading'
    persist(value)
    def current(_):
        fresh = resolver(value['allocation_id'])
        if prep.digest(fresh) != prep.digest(value['source_snapshot']):
            raise ValueError('Source artwork or allocation changed.')
        return adapted(fresh, value['snapshot']['order_reference'], value['snapshot']['recipient'])
    result = prep.run(value, provider, current, link, persist)
    final = provider.order(value['order_id'])
    if final.get('status') != 'draft' or final.get('charges'):
        raise ValueError('Sandbox must remain an unpaid draft.')
    result['sandbox_unpaid_verified'] = True
    result['message'] = 'SANDBOX: ' + result['message']
    persist(result)
    return result


def tick():
    with prep.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_try_advisory_xact_lock(%s) AS acquired', (LOCK,))
        if not cur.fetchone()['acquired']:
            return None
        cur.execute("SET LOCAL idle_in_transaction_session_timeout = '0'")
        cur.execute('''SELECT value FROM app_settings WHERE key LIKE %s AND value->>'status'
            IN ('Queued','Uploading','Creating sandbox draft') ORDER BY updated_at LIMIT 1''', (PREFIX+'%',))
        found = cur.fetchone()
        if not found:
            return None
        value = found['value']
        fenced = {field: bool(value.get(field)) for field in ('create_intent', 'write_intent')}
        def persist(v):
            with prep.connect() as c, c.cursor() as q:
                new_fence = next((field for field in fenced if v.get(field) and not fenced[field]), None)
                if new_fence:
                    q.execute('''UPDATE app_settings SET value=%s::jsonb,updated_at=now()
                        WHERE key=%s AND NOT COALESCE((value->>%s)::boolean,false) RETURNING key''',
                        (json.dumps(v), PREFIX+v['id'], new_fence))
                    if not q.fetchone():
                        raise prep.UploadFenceLost('Another worker owns this sandbox attempt.')
                    fenced[new_fence] = True
                else:
                    save(q, v)
        try:
            return run(value, SandboxClient(), prep.resolve, prep.artwork_link, persist)
        except prep.UploadFenceLost:
            return None
        except Exception as error:
            value.update(status='Needs review', message=str(error) if isinstance(error, ValueError)
                         else 'Sandbox could not be verified. No production action was taken.')
            persist(value)
            return value


def remove(user, key):
    prep.require_user(user)
    with prep.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK,))
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (PREFIX+str(uuid.UUID(key)),))
        row = cur.fetchone()
        if not row or row['value'].get('environment') != 'sandbox':
            raise ValueError('Sandbox test not found.')
        value = row['value']
        if value['status'] in ('Queued','Uploading','Creating sandbox draft'):
            raise ValueError('Wait for the sandbox worker to finish before removing the test row.')
        value.update(hidden=True, removed_at=prep.now())
        save(cur, value)  # Recoverable test-row removal; no live order or supplier deletion.
