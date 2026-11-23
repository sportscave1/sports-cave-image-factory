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
import prodigi_stage as stages

WAITING = 'Awaiting product selection'
ACTIVE = 'Selecting product'
READBACK_POLICY='supplier-price-readback-v1'


def business(order, target):
    result = browser.business(order, target)
    for item in result['items']:
        if str(item['id']) == str(target):
            for key in ('sku', 'catalogueVariantId', 'catalogueProductId', 'attributes',
                        'assets', 'sizing', 'unitPrice', 'lineTotal', 'name', 'productName'):
                item.pop(key, None)
    return result


def after_selection_business(value):
    """Selection can recalculate existing draft line prices, not their currency."""
    result=deepcopy(value)
    for item in result.get('items',[]):
        for key in ('unitPrice','lineTotal'):
            if isinstance(item.get(key),dict):item[key].pop('amount',None)
    return result


def changed_fields(before,after,path=''):
    """Bounded structural paths only; never persist customer/provider values."""
    if before==after:return []
    if isinstance(before,dict) and isinstance(after,dict):
        result=[]
        for k in sorted(before.keys()|after.keys()):
            field=path+'.'+k if path else k
            result.extend([field] if k not in before or k not in after else changed_fields(before[k],after[k],field))
            if len(result)>=40:break
        return result[:40]
    if isinstance(before,list) and isinstance(after,list) and len(before)==len(after):
        return [p for i,(a,b) in enumerate(zip(before,after))
                for p in changed_fields(a,b,f'{path}[{i}]')][:40]
    return [path]


def checked(value, provider, resolver):
    snap = browser.snapshot(value, resolver, False)
    order = provider.order(value['order_id'])
    item = prep.validate_order(order, snap, value['order_id'], value['item_id'], allow_unselected=True,binding=value.get('consolidation_binding'))
    if order.get('charges') or browser.has_existing_artwork(item):
        raise ValueError('Product selection requires an unpaid draft with no existing artwork.')
    return snap, order, item


@stages.stale_result(None)
def claim(*,preferred_order=''):
    with stages.edit(browser.LOCK) as cur:
        cur.execute("SELECT key,value FROM app_settings WHERE key LIKE 'prodigi_prepare:%%' AND value->>'status'=%s ORDER BY CASE WHEN value->>'order_id'=%s THEN 0 ELSE 1 END,updated_at LIMIT 20", (WAITING,preferred_order))
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
    with stages.edit(browser.LOCK) as cur:
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


@stages.stale_result({'status':'Handoff unavailable'})
def finish(key,token,stage='product',*,error=''):
    with stages.edit(browser.LOCK) as cur:
        try: raw,value=authorised(cur,key,token)
        except (ValueError,PermissionError): return {'status':'Handoff unavailable'}
        return complete(cur,raw,value,stage,error=error)


def complete(cur,key,value,stage,*,error=''):
    receipt=value['product_browser']
    if receipt.get('verified'): return {'status':value['status']}
    receipt['client_stage']=stage
    if error:receipt['client_error']=str(error)[:240]
    try:
        provider,resolver,_,_=browser.context(key)
        snap,order,item=checked(value,provider,resolver)
        prep.validate_order(order,snap,value['order_id'],value['item_id'],binding=value.get('consolidation_binding'))
        current_business=business(order,item['id'])
        observed=changed_fields(receipt['before'],current_business)
        before_stable=after_selection_business(receipt['before']);current_stable=after_selection_business(current_business)
        receipt['readback_changed_fields']=changed_fields(before_stable,current_stable)
        receipt['readback_repriced_fields']=[p for p in observed if p.endswith(('.unitPrice.amount','.lineTotal.amount'))]
        if not receipt['started'] or current_stable!=before_stable:
            raise ValueError('The supplier order changed outside the permitted product selection.')
        reset=value.get('reset_authorisation')
        if reset:
            if (reset.get('generation')!=value.get('reset_generation') or reset.get('used_at')
                    or reset.get('order_id')!=str(order['id']) or reset.get('item_id')!=str(item['id'])
                    or reset.get('assets')!=(item.get('assets') or [])
                    or after_selection_business(business(reset['before'],item['id']))!=before_stable):
                raise ValueError('The reset authorisation changed before product selection was verified.')
            # This readback proved the permitted product change and pinned every
            # other business field. Carry that exact state into the upload fence.
            reset['before']=browser.business(order,item['id'])
            reset['product_selection_verified_at']=prep.now()
        receipt.update(verified=True,verified_at=prep.now(),sku=item['sku'],colour=(item.get('attributes') or {}).get('color',''))
        value.update(status=browser.WAITING,message='Original Fulfilment product and frame verified. Uploading this edition next, before selecting another product.')
        value.setdefault('history',[]).append(dict(at=prep.now(),event='blank_product_selected',sku=item['sku']))
    except ValueError as error:
        detail=' Companion: '+receipt['client_error'] if receipt.get('client_error') else ''
        value.update(status='Needs review',message='Product selection: '+str(error)+detail)
        prep.record_failure(value,'product_selection.'+stage,value['message'],type(error).__name__)
    browser.save(cur,key,value)
    return {'status':value['status']}


def recheck(user,key,*,allow_expired_blank=False):
    prep.require_user(user)
    with stages.edit(browser.LOCK) as cur:
        value=browser.read(cur,key)
        receipt=value['product_browser']
        # Explicit owner Reset only: retire an expired pre-click handoff after
        # proving the exact original blank item/business is still unchanged.
        # Ordinary readback and polling must never replay an uncertain Select.
        expired=False
        try:expired=(datetime.now(timezone.utc)-datetime.fromisoformat(receipt['permitted_at'])).total_seconds()>900
        except (KeyError,TypeError,ValueError):pass
        if (allow_expired_blank and expired and receipt.get('started') and not receipt.get('verified')
            and value.get('status')=='Needs review' and not any(value.get(k) for k in ('browser','write_intent','submission'))
            and (value.get('last_failure') or {}).get('stage')=='product_selection.product-select'):
            provider,resolver,_,_=browser.context(key)
            _,order,item=checked(value,provider,resolver)
            if not item.get('sku') and item==receipt['blank_item'] and business(order,item['id'])==receipt['before']:
                value.setdefault('product_browser_history',[]).append(deepcopy(receipt))
                value.pop('product_browser');value.pop('last_failure',None)
                value.update(status=WAITING,message='Expired untouched product selection retired for owner Reset.')
                browser.save(cur,key,value)
                return value
        if not receipt['started']:
            value.pop('product_browser')
            value.update(status='Queued',message='Retrying untouched product selection.')
            browser.save(cur,key,value)
        else:
            complete(cur,key,value,'recheck') # Readback only; never repeat an uncertain Select.
        return value


def recover_readbacks(user):
    """Bounded independent readback after Select, never replay the Select click."""
    prep.require_user(user)
    from companion_poll_transaction import connection
    with connection(prep.connect) as c,c.cursor() as q:
        q.execute("""SELECT key FROM app_settings WHERE key LIKE 'prodigi_prepare:%%'
          AND value->>'status'='Needs review'
          AND value->'product_browser'->>'started'='true'
          AND NOT COALESCE((value->'product_browser'->>'verified')::boolean,false)
          AND value->'product_browser'->>'client_stage'='product-readback'
          AND (COALESCE(value->>'product_readback_recovery_policy','')<>'supplier-price-readback-v1'
               OR COALESCE((value->>'product_readback_recoveries')::int,0)<2)
          AND NOT value ? 'submission' AND NOT value ? 'browser'
          AND NOT COALESCE((value->>'hidden')::boolean,false)
          ORDER BY updated_at LIMIT 2""")
        keys=[r['key'] for r in q.fetchall()]
    return sum(_recover_readback(key) for key in keys)


@stages.stale_result(False)
def _recover_readback(key):
    with stages.edit(browser.LOCK) as q:
        value=browser.read(q,key);receipt=value.get('product_browser') or {}
        if (value.get('status')!='Needs review' or not receipt.get('started') or receipt.get('verified')
            or receipt.get('client_stage')!='product-readback' or value.get('submission') or value.get('browser')
            or (value.get('product_readback_recovery_policy')==READBACK_POLICY and value.get('product_readback_recoveries',0)>=2)):return False
        count=value.get('product_readback_recoveries',0) if value.get('product_readback_recovery_policy')==READBACK_POLICY else 0
        value.update(product_readback_recoveries=count+1,product_readback_recovery_policy=READBACK_POLICY)
        # Keep the original receipt and consumed permit for independent proof.
        complete(q,key,value,'product-readback')
        if receipt.get('verified'):value.pop('last_failure',None)
        browser.save(q,key,value)
        return receipt.get('verified') is True
