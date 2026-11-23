"""Paired Prodigi sign-in recovery. Passwords never enter workflow records.

A login only restores browser authentication. Resumption independently checks
the saved supplier order and retires unused permits; used permits get readback.
"""
import hmac
import json
import re
import secrets
from urllib.parse import parse_qs, urlencode, urlsplit

import prodigi_browser as browser
import prodigi_preparation as prep
import prodigi_stage as stages
from companion_poll_transaction import connection

EMAIL = 'hello@sportscave.com.au'
SESSION = 'orders_prodigi_signin'
FIELDS = {'artwork': ('browser', 'Browser uploading', browser.WAITING),
          'product': ('product_browser', 'Selecting product', 'Awaiting product selection'),
          'qa': ('dashboard_qa', 'Checking dashboard QA', 'Awaiting dashboard QA')}
DETAIL = 'Sign into Prodigi in Edge. Waiting orders resume automatically after sign-in.'


def order_url(value):
    oid = str(value.get('order_id', ''))
    if not re.fullmatch(r'[A-Za-z0-9-]{1,100}', oid):
        raise ValueError('Invalid supplier order identity.')
    return 'https://dashboard.prodigi.com/orders/' + oid + '/detail'


def login_url(value):
    return 'https://dashboard.prodigi.com/login?' + urlencode({'redirect': urlsplit(order_url(value)).path})


def valid_login(actual, value):
    try:
        url = urlsplit(actual)
        return (url.scheme == 'https' and url.netloc == 'dashboard.prodigi.com'
                and url.path == '/login' and not url.fragment
                and parse_qs(url.query, keep_blank_values=True) == {'redirect': [urlsplit(order_url(value)).path]})
    except (ValueError, TypeError):
        return False


def scoped(cur, key, kind):
    if kind not in FIELDS or not isinstance(key, str) or not re.fullmatch(r'prodigi_prepare:\d+', key):
        raise ValueError('Invalid sign-in recovery scope.')
    value = browser.read(cur, key)
    field, active, waiting = FIELDS[kind]
    receipt = value.get(field) or {}
    return value, receipt, field, active, waiting


def owned(value, receipt, user, pairing, wait_id):
    wait = value.get('signin_wait') or {}
    if (not wait_id or wait.get('id') != wait_id or wait.get('actor_id') != str(user.get('id', ''))
            or wait.get('desktop_hash') != prep.digest(pairing)
            or not hmac.compare_digest(wait.get('claim', ''), receipt.get('token_hash', ''))):
        raise PermissionError('This sign-in wait was retired or belongs to another desktop.')
    return wait


def pause(user, pairing, data):
    key = data['key'].removeprefix('product:')
    with stages.edit(browser.LOCK) as cur:
        value, receipt, field, active, _ = scoped(cur, key, data['kind'])
        if (not isinstance(data['token'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', data['token'])
                or not hmac.compare_digest(receipt.get('token_hash', ''), prep.digest(data['token']))):
            raise PermissionError('Sign-in handoff token rejected.')
        if not valid_login(data['login_url'], value):
            raise ValueError('Sign-in must return to this exact Prodigi order.')
        if value.get('submission') or receipt.get('verified') or value.get('status') not in (active, 'Needs review'):
            return {'status': 'retired'}
        wait = value.get('signin_wait') or {}
        if not (wait.get('claim') == receipt.get('token_hash') and wait.get('state') == 'waiting'):
            wait = dict(id=secrets.token_urlsafe(24), kind=data['kind'], state='waiting',
                        actor_id=str(user.get('id', '')), desktop_hash=prep.digest(pairing),
                        claim=receipt['token_hash'], created_at=prep.now(),
                        mode='readback' if receipt.get('started') else 'unused')
        owned({**value, 'signin_wait': wait}, receipt, user, pairing, wait['id'])
        value['signin_wait'] = wait
        value['message'] = DETAIL
        browser.save(cur, key, value)
    with connection(prep.connect) as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)', (browser.LOCK,))
        cur.execute('SELECT value FROM app_settings WHERE key=%s FOR UPDATE', (SESSION,))
        previous = cur.fetchone()
        if not previous or not previous['value'].get('active'):
            incident = dict(active=True, attempted=False, id=secrets.token_urlsafe(24), created_at=prep.now())
            cur.execute('INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now()) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()',
                        (SESSION, json.dumps(incident)))
    return {'status': 'waiting', 'wait': public_wait(key, value)}


def public_wait(key, value):
    wait = value['signin_wait']
    return dict(key=key, id=wait['id'], kind=wait['kind'], order_url=order_url(value),
                login_url=login_url(value), mode=wait['mode'])


def pending(user, pairing):
    with connection(prep.connect) as conn, conn.cursor() as cur:
        cur.execute("""SELECT key,value FROM app_settings WHERE key LIKE 'prodigi_prepare:%%'
            AND value->'signin_wait'->>'state'='waiting'
            AND value->'signin_wait'->>'actor_id'=%s AND value->'signin_wait'->>'desktop_hash'=%s
            AND NOT COALESCE((value->>'hidden')::boolean,false) ORDER BY updated_at LIMIT 100""",
            (str(user.get('id', '')), prep.digest(pairing)))
        rows = cur.fetchall()
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (SESSION,))
        session_row = cur.fetchone()
        session = session_row['value'] if session_row else {}
    waits = [public_wait(row['key'], row['value']) for row in rows]
    # An incident stays attempted until all its orders have reconciled. Another
    # order, worker reload or lost response must not cause a password retry loop.
    if not waits:
        with connection(prep.connect) as conn, conn.cursor() as cur:
            cur.execute("""UPDATE app_settings SET value=value || '{"active":false}'::jsonb,updated_at=now()
                WHERE key=%s AND value->>'active'='true'
                AND NOT EXISTS(SELECT 1 FROM app_settings WHERE key LIKE 'prodigi_prepare:%%'
                    AND value->'signin_wait'->>'state'='waiting' AND NOT COALESCE((value->>'hidden')::boolean,false))""", (SESSION,))
    return {'waits': waits, 'detail': DETAIL, 'username': EMAIL,
            'automatic': not (session.get('active') and session.get('attempted')),
            'incident': session.get('id', '')}


def credentials(user, pairing, data):
    import shared_credentials as credentials
    # A fresh account/credential permission check is mandatory on each release.
    # Never place these values in a tick, receipt, audit payload or exception.
    username = credentials.read_credential_for_action(user, 'prodigi', 'username', 'credential_prodigi_login')
    password = credentials.read_credential_for_action(user, 'prodigi', 'password', 'credential_prodigi_login')
    with connection(prep.connect) as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)', (browser.LOCK,))
        value, receipt, _, active, _ = scoped(cur, data['key'], data['kind'])
        wait = owned(value, receipt, user, pairing, data['id'])
        if wait.get('state') != 'waiting' or value.get('submission') or value.get('status') not in (active, 'Needs review'):
            raise PermissionError('Sign-in recovery is no longer active.')
        if not valid_login(data['login_url'], value):
            raise ValueError('Prodigi login destination rejected.')
        cur.execute('SELECT value FROM app_settings WHERE key=%s FOR UPDATE', (SESSION,))
        row = cur.fetchone()
        session = row['value'] if row else {}
        if session.get('active') and session.get('attempted'):
            return {'available': False, 'reason': 'Complete the Prodigi sign-in in Edge. Automatic password entry was already attempted; waiting orders will resume afterwards.'}
        session.update(active=True, attempted=True, attempted_at=prep.now(), actor_id=str(user.get('id', '')))
        cur.execute('INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now()) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()',
                    (SESSION, json.dumps(session)))
    if not password or username and username.strip().casefold() != EMAIL:
        return {'available': False, 'reason': 'Check the saved Prodigi credentials or sign in manually. Orders will resume automatically.'}
    return {'available': True, 'username': EMAIL, 'password': password}


def resume(user, pairing, data):
    """Retire an unused token after fresh checks; never extend its 15-minute lease."""
    key, kind = data['key'], data['kind']
    # Consumed uploads and product selections have dedicated readback-only APIs.
    with stages.edit(browser.LOCK) as cur:
        value, receipt, field, active, waiting = scoped(cur, key, kind)
        previous_wait = value.get('signin_wait') or {}
        if not previous_wait or previous_wait.get('id') != data['id']:
            return {'status': 'retired'}
        if (previous_wait.get('actor_id') == str(user.get('id', ''))
                and previous_wait.get('desktop_hash') == prep.digest(pairing)
                and previous_wait.get('claim') != receipt.get('token_hash')):
            value.pop('signin_wait', None)
            browser.save(cur, key, value)
            return {'status': 'retired'}
        wait = owned(value, receipt, user, pairing, data['id'])
        consumed = receipt.get('started') is True
        if wait.get('state') != 'waiting':
            return {'status': 'retired'}
        if value.get('submission') or receipt.get('verified') or value.get('status') not in (active, 'Needs review'):
            value.pop('signin_wait', None)
            browser.save(cur, key, value)
            return {'status': 'retired'}
    if consumed and kind in ('artwork', 'product'):
        result = browser.recheck(user, key) if kind == 'artwork' else __import__('prodigi_product_browser').recheck(user, key)
        with stages.edit(browser.LOCK) as cur:
            value = browser.read(cur, key)
            current = value.get('signin_wait') or {}
            if current.get('id') != data['id']:
                return {'status': 'retired'}
            value.pop('signin_wait', None)
            browser.save(cur, key, value)
        return {'status': 'review' if result.get('status') == 'Needs review' else 'resumed'}

    provider, resolver, _, sandbox = browser.context(key)
    if sandbox:
        raise ValueError('Live Prodigi sign-in recovery cannot use a sandbox.')
    with stages.edit(browser.LOCK) as cur:
        value, receipt, field, active, waiting = scoped(cur, key, kind)
        wait = owned(value, receipt, user, pairing, data['id'])
        if (wait.get('state') != 'waiting' or value.get('status') not in (active, 'Needs review')
                or (receipt.get('started') is True) != consumed
                or value.get('submission') or value.get('write_intent') or receipt.get('verified')):
            raise ValueError('This order changed before sign-in resumption.')
        units = [(key, value)]
        try:
            if kind == 'product':
                import prodigi_product_browser as product
                _, order, item = product.checked(value, provider, resolver)
                if receipt.get('started') or item != receipt['blank_item'] or product.business(order, item['id']) != receipt['before']:
                    raise ValueError('The original blank product changed.')
            elif kind == 'artwork':
                _, order, item = browser.checked(value, provider, resolver, False)
                from prodigi_reset import replacement_allowed
                replacement = browser.has_existing_artwork(item) and replacement_allowed(value, order, item)
                if (receipt.get('started') or browser.has_existing_artwork(item) and not replacement
                        or (item.get('assets') or []) != receipt.get('empty_slots', [])
                        or browser.business(order, item['id']) != receipt['before']):
                    raise ValueError('The original empty artwork item changed.')
            else:
                import prodigi_dashboard_qa as qa
                _, order, _ = qa.current(value, provider, resolver)
                ids = receipt.get('batch') or [value['allocation_id']]
                if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or len(set(ids)) != len(ids) or value['allocation_id'] not in ids:
                    raise ValueError('QA group membership changed.')
                units = []
                for aid in ids:
                    unit_key = prep.PREFIX + str(aid)
                    unit = browser.read(cur, unit_key)
                    other = unit.get('dashboard_qa') or {}
                    if (unit.get('status') not in (active, 'Needs review') or unit.get('submission')
                            or other.get('token_hash') != receipt['token_hash'] or other.get('batch', ids) != ids
                            or unit.get('order_id') != value['order_id'] or other.get('started') != receipt.get('started')):
                        raise ValueError('QA group changed while signing in.')
                    qa.current_for_order(unit, order, resolver)
                    expected_shipping = other.get('shipping', {}).get('target') if consumed else other['before'].get('shippingMethod')
                    if (qa.pinned_order(other['before']) != qa.pinned_order(order)
                            or qa.clean(order.get('shippingMethod')) != qa.clean(expected_shipping)
                            or consumed and order.get('usSalesTaxAlreadyCollected') is False):
                        raise ValueError('The previous QA action needs review of the saved supplier state.')
                    units.append((unit_key, unit))
        except ValueError as error:
            value['signin_wait'].update(state='review', resolved_at=prep.now())
            value.update(status='Needs review', message='Prodigi sign-in recovered; ' + str(error) + ' Review this saved order. Other orders can continue.')
            browser.save(cur, key, value)
            return {'status': 'review'}
        for unit_key, unit in units:
            old = unit.pop(field)
            unit.pop('signin_wait', None)
            unit.pop('last_failure', None)
            unit['signin_history'] = (unit.get('signin_history', []) + [dict(at=prep.now(), kind=kind,
                event='saved_qa_rechecked' if consumed else 'unused_handoff_retired', claimed_at=old.get('claimed_at'))])[-8:]
            unit.update(status=waiting, message='Prodigi sign-in restored. Continuing this same order with fresh verification and a new handoff.')
            browser.save(cur, unit_key, unit)
    return {'status': 'resumed'}


async def endpoint(request):
    from prodigi_preparation_api import desktop
    from product_upload_api import HEADERS, failure
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    try:
        auth = request.headers.get('authorization', '')
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}', auth):
            raise PermissionError('Pair this desktop first.')
        raw = bytearray()
        async for block in request.stream():
            raw.extend(block)
            if len(raw) > 2048:
                raise ValueError('Invalid sign-in request.')
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError('Invalid sign-in request.')
        action = data.get('action')
        shapes = {'pending': {'action'}, 'wait': {'action', 'key', 'kind', 'token', 'login_url'},
                  'credentials': {'action', 'key', 'kind', 'id', 'login_url'}, 'resume': {'action', 'key', 'kind', 'id'}}
        if not isinstance(action, str) or action not in shapes or set(data) != shapes[action] or any(not isinstance(v, str) for v in data.values()):
            raise ValueError('Invalid sign-in request.')
        actor = await run_in_threadpool(desktop, auth[7:])
        fn = {'pending': pending, 'wait': pause, 'credentials': credentials, 'resume': resume}[action]
        result = await run_in_threadpool(fn, actor, auth[7:], *([] if action == 'pending' else [data]))
        return JSONResponse(result, headers=HEADERS)
    except Exception as error:
        # Never log request bodies or exception values on a credential route.
        return failure(error)
