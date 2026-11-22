"""One browser selection for an exactly identified, blank imported product.

No supplier API writes. A durable permit precedes Select; independent readback
must prove the canonical SKU/frame and unchanged business before artwork runs.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hmac
import secrets

import prodigi_browser as browser
import prodigi_preparation as prep

WAITING = 'Awaiting product selection'
ACTIVE = 'Selecting product'


def business(order, target):
    result = browser.business(order, target)
    for item in result['items']:
        if str(item['id']) == str(target):
            for key in ('sku', 'catalogueVariantId', 'catalogueProductId', 'attributes',
                        'assets', 'sizing', 'unitPrice', 'lineTotal', 'name', 'productName'):
                item.pop(key, None)
    return result


def checked(value, provider, resolver):
    snap = browser.snapshot(value, resolver, False)
    order = provider.order(value['order_id'])
    item = prep.validate_order(order, snap, value['order_id'], value['item_id'], allow_unselected=True,binding=value.get('consolidation_binding'))
    if order.get('charges') or browser.has_existing_artwork(item):
        raise ValueError('Product selection requires an unpaid draft with no existing artwork.')
    return snap, order, item


def claim():
    with prep.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_try_advisory_xact_lock(%s) AS acquired', (browser.LOCK,))
        if not cur.fetchone()['acquired']: return None
        cur.execute("SELECT key,value FROM app_settings WHERE key LIKE 'prodigi_prepare:%%' AND value->>'status'=%s ORDER BY updated_at LIMIT 20", (WAITING,))
        for row in cur.fetchall():
            key, value = row['key'], row['value']
            if value.get('hidden') or not value.get('browser_requested') or any(value.get(k) for k in ('browser','write_intent','submission','product_browser')): continue
            try:
                provider, resolver, _, sandbox = browser.context(key)
                if sandbox: continue
                snap, order, item = checked(value, provider, resolver)
                if item.get('sku') not in (None, ''):
                    value.update(status='Queued', message='Product already selected; verifying artwork preparation.')
                    browser.save(cur, key, value)
                    continue
                cur.execute("SELECT 1 FROM app_settings WHERE key LIKE 'prodigi_prepare:%%' AND key<>%s AND value->>'order_id'=%s AND value ? 'product_browser' AND NOT COALESCE((value->'product_browser'->>'verified')::boolean,false) LIMIT 1", (key,value['order_id']))
                if cur.fetchone(): continue # Serialize selection within a multi-item order.
                mapping = snap['mapping']
                import os_pages
                size = mapping.get('size') or {'A1':'XL','A2':'L','A3':'M','A4':'S'}.get(mapping['prodigi_code'].rsplit('-',1)[-1], '')
                canonical = os_pages.prodigi_mapping_for_frame_size(mapping['frame'], size)
                if (canonical['prodigi_code'] != mapping['prodigi_code'] or canonical['prodigi_frame_colour'] != mapping['prodigi_frame_colour']):
                    raise ValueError('Product selection differs from the original Fulfilment reference.')
                token = secrets.token_urlsafe(32)
                value['product_browser'] = dict(token_hash=prep.digest(token), started=False,
                    before=business(order,item['id']), blank_item=deepcopy(item), claimed_at=prep.now())
                value.update(status=ACTIVE, message='Selecting the original Fulfilment product and frame.')
                browser.save(cur,key,value)
                return dict(kind='product',key='product:'+key,token=token,environment='live',
                    order_id=value['order_id'],item_id=value['item_id'],reference=order['merchantReference'],
                    sku=mapping['prodigi_code'],colour='' if mapping['frame']=='Unframed' else mapping['prodigi_frame_colour'],
                    order_url=f'https://dashboard.prodigi.com/orders/{value["order_id"]}/detail',sha256=prep.digest(snap))
            except ValueError as error:
                value.update(status='Needs review',message=str(error))
                prep.record_failure(value,'product_selection',str(error),type(error).__name__)
                browser.save(cur,key,value)
    return None


def authorised(cur,key,token):
    if not key.startswith('product:prodigi_prepare:'): raise ValueError('Unknown product handoff.')
    key=key.removeprefix('product:')
    value=browser.read(cur,key)
    if not hmac.compare_digest((value.get('product_browser') or {}).get('token_hash',''),prep.digest(token)):
        raise PermissionError('Product handoff token rejected.')
    return key,value


def permit(key,token,sha256):
    with prep.connect() as conn,conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)',(browser.LOCK,))
        raw,value=authorised(cur,key,token)
        receipt=value['product_browser']
        if receipt['started'] or value['status']!=ACTIVE or value.get('submission'):
            raise ValueError('Product selection permit already used or stopped.')
        if (datetime.now(timezone.utc)-datetime.fromisoformat(receipt['claimed_at'])).total_seconds()>900:
            raise ValueError('Product selection handoff expired.')
        provider,resolver,_,_=browser.context(raw)
        snap,order,item=checked(value,provider,resolver)
        if sha256!=prep.digest(snap) or item!=receipt['blank_item'] or business(order,item['id'])!=receipt['before']:
            raise ValueError('Order or mapping changed before product selection.')
        receipt.update(started=True,permitted_at=prep.now())
        browser.save(cur,raw,value)
    return {'permitted':True}


def finish(key,token,stage='product'):
    with prep.connect() as conn,conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)',(browser.LOCK,))
        try: raw,value=authorised(cur,key,token)
        except (ValueError,PermissionError): return {'status':'Handoff unavailable'}
        return complete(cur,raw,value,stage)


def complete(cur,key,value,stage):
    receipt=value['product_browser']
    if receipt.get('verified'): return {'status':value['status']}
    try:
        provider,resolver,_,_=browser.context(key)
        snap,order,item=checked(value,provider,resolver)
        prep.validate_order(order,snap,value['order_id'],value['item_id'],binding=value.get('consolidation_binding'))
        if not receipt['started'] or business(order,item['id'])!=receipt['before']:
            raise ValueError('The supplier order changed outside the permitted product selection.')
        receipt.update(verified=True,verified_at=prep.now(),sku=item['sku'],colour=(item.get('attributes') or {}).get('color',''))
        value.update(status=browser.WAITING,message='Original Fulfilment product and frame verified. Uploading this edition next, before selecting another product.')
        value.setdefault('history',[]).append(dict(at=prep.now(),event='blank_product_selected',sku=item['sku']))
    except ValueError as error:
        value.update(status='Needs review',message='Product selection: '+str(error))
        prep.record_failure(value,'product_selection.'+stage,value['message'],type(error).__name__)
    browser.save(cur,key,value)
    return {'status':value['status']}


def recheck(user,key):
    prep.require_user(user)
    with prep.connect() as conn,conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)',(browser.LOCK,))
        value=browser.read(cur,key)
        receipt=value['product_browser']
        if not receipt['started']:
            value.pop('product_browser')
            value.update(status='Queued',message='Retrying untouched product selection.')
            browser.save(cur,key,value)
        else:
            complete(cur,key,value,'recheck') # Readback only; never repeat an uncertain Select.
        return value
