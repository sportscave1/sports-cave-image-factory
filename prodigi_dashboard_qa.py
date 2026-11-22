"""Pinned, single-pass dashboard QA. No artwork/document upload, payment or Submit."""
from copy import deepcopy
from datetime import datetime, timezone
import hmac, secrets
import prodigi_preparation as prep
import prodigi_browser as browser
from prodigi_qa import address_matches, clean

POLICY='prodigi-dashboard-inserts-observed-v2'
# Owner confirmed on 2026-11-22 that applicable sales tax is already collected.
TAX_POLICY='owner-confirmed-sales-tax-collected-2026-11-22'
WAITING='Awaiting dashboard QA'
ACTIVE='Checking dashboard QA'
SET='SC EDITION BRANDING'
TYPES={'Round packaging sticker','Packing slip (colour)'}
CHECKS={'product_option':'Product and variant SKU','frame':'Frame colour','size':'Print size','artwork_upload':'Exact saved design','edition_number':'Allocated edition number','sent_to_production':'Full-image fit and orientation','image_quality':'Prodigi image quality: Excellent','customer_address':'Customer shipping details','shipping':'Cheapest shipping / required Express','certificate':'Saved supplier inserts','packing_slip':'Observed packing slip and sticker','inserts_available':'Supplier inserts present','final_check':'All QA checks passed'}


def intent(value):
    # Fulfilment may append recipient details after a pipe; those are not a service.
    value=clean(value).split('|',1)[0].strip()
    if __import__('re').search(r'\bexpress\b',value):return 'express'
    if __import__('re').match(r'^(?:(?:us|usa|united states|uk|united kingdom|au|australia|nz|new zealand|ca|canada|international|domestic)\s+)?standard(?:\s|$)',value) or value in ('budget','economy','australia post'):return 'standard'
    raise ValueError('The customer shipping service is unknown; review it before changing shipping.')


def shipping_choice(options, requested, current):
    if not isinstance(options,list) or not 1<=len(options)<=10:raise ValueError('Shipping quotes are missing or ambiguous.')
    if any(not isinstance(o,dict) or set(o)!={'service','cents','currency'} or
           o['service'] not in ('budget','standard','standardplus','express','overnight') or type(o['cents']) is not int or
           not 0<=o['cents']<=10000000 or o['currency'] not in ('$','£','€') for o in options):
        raise ValueError('Shipping quotes could not be verified.')
    if len({o['currency'] for o in options})!=1 or len({o['service'] for o in options})!=len(options):
        raise ValueError('Shipping quotes have mixed currencies or duplicate services.')
    if requested=='express':
        if not any(o['service']=='express' for o in options):raise ValueError('Express shipping is unavailable.')
        return 'express'
    if requested!='standard':raise ValueError('Unknown shipping policy.')
    lowest=min(o['cents'] for o in options)
    cheapest=[o['service'] for o in options if o['cents']==lowest]
    # A tie is already the lowest price; avoid an unnecessary supplier write.
    return current if current in cheapest else cheapest[0]


def pinned_order(order):
    result=browser.business(order,'')
    result.pop('shippingMethod',None)
    for item in result['items']:
        for asset in item.get('assets',[]):asset.pop('status',None)
    return result


def current_for_order(value,order,resolver):
    snap=browser.snapshot(value,resolver,False)
    item=prep.validate_order(order,snap,value['order_id'],value['item_id'])
    if order.get('charges'):raise ValueError('A charged order cannot be changed by QA.')
    receipt=value.get('browser') or {}
    if not receipt.get('verified') or not receipt.get('full_image_fit_verified'):
        raise ValueError('The saved numbered artwork and full-image fit must be verified first.')
    if item.get('quantity')!=1:
        raise ValueError('Dashboard QA requires one separately numbered item per supplier order.')
    assets=item.get('assets') or []
    if len(assets)!=1 or prep.digest(assets[0].get('url'))!=value.get('url_hash'):
        raise ValueError('The saved artwork changed; review this exact draft.')
    return snap,order,item


def current(value,provider,resolver):
    return current_for_order(value,provider.order(value['order_id']),resolver)


def enqueue(value,provider,resolver,persist):
    _,order,_=current(value,provider,resolver)
    from prodigi_order_group import members,WaitingForItems
    try:members(value,order,resolver)
    except WaitingForItems as error:
        value.update(status='Checking QA',message=str(error));persist(value);return value
    value.pop('last_failure',None)
    value.update(status=WAITING,message='Checking branding inserts, Excellent quality, shipping and customer details before the configured submission step.')
    persist(value)
    return value


def claim(*,tax_supported=False,exact_item_supported=False,batch_supported=False):
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT pg_try_advisory_xact_lock(%s) AS acquired',(browser.LOCK,))
        if not q.fetchone()['acquired']:return None
        q.execute("SELECT key,value FROM app_settings WHERE key LIKE 'prodigi_prepare:%%' AND value->>'status'=%s AND NOT COALESCE((value->>'hidden')::boolean,false) ORDER BY updated_at LIMIT 1",(WAITING,))
        row=q.fetchone()
        if not row:return None
        value=row['value'];key=row['key']
        if value.get('dashboard_qa'):return None
        provider,resolver,_,_=browser.context(key)
        try:
            snap,order,item=current(value,provider,resolver)
            if len(order.get('items',[]))>1 and not exact_item_supported:return None
            tax_required=clean((snap.get('recipient') or {}).get('address',{}).get('countryCode'))=='us'
            if tax_required and not tax_supported:return None
            token=secrets.token_urlsafe(32)
            values=[value]
            if batch_supported and len(order.get('items',[]))>1:
                from prodigi_order_group import members
                values=members(value,order,resolver)
                if len(values)>20:raise ValueError('More than 20 numbered items require a separate order review.')
                if any(v['allocation_id']!=value['allocation_id'] and v.get('status')==ACTIVE for v in values):return None
                if any(v.get('submission') for v in values):raise ValueError('A submitted item cannot enter a new draft QA batch.')
                if any(intent(v['snapshot'].get('shipping'))!=intent(snap.get('shipping')) for v in values):
                    raise ValueError('Items in one supplier order have different shipping requirements.')
            batch=[v['allocation_id'] for v in values]
            stamp=prep.now()
            for unit in values:
                current_for_order(unit,order,resolver)
                previous=unit.get('dashboard_qa')
                if previous:unit.setdefault('dashboard_qa_history',[]).append({k:previous.get(k) for k in ('policy','claimed_at','checked_at','verified')})
                unit['dashboard_qa']=dict(token_hash=prep.digest(token),claimed_at=stamp,before=order,started=False,policy=POLICY,tax_policy=TAX_POLICY,tax_required=tax_required,batch=batch)
                unit.update(status=ACTIVE,message='Checking all numbered items, shipping, inserts and tax in one QA pass.')
                browser.save(q,prep.PREFIX+str(unit['allocation_id']),unit)
            return dict(kind='qa',key=key,token=token,environment='live',order_id=value['order_id'],item_id=value['item_id'],exact_item=exact_item_supported,
                order_url='https://dashboard.prodigi.com/orders/'+value['order_id']+'/detail',
                reference=order['merchantReference'],sku=item['sku'],colour=(item.get('attributes') or {}).get('color',''),
                shipping_intent=intent(snap.get('shipping')),branding_set=SET,tax_declaration=True,tax_required=tax_required,
                **({'items':[dict(item_id=v['item_id'],sku=v['snapshot']['mapping']['prodigi_code'],colour='' if v['snapshot']['mapping']['frame']=='Unframed' else v['snapshot']['mapping']['prodigi_frame_colour']) for v in values]} if len(values)>1 else {}))
        except ValueError as error:
            value.update(status='Needs review',message=str(error));prep.record_failure(value,'dashboard_qa',str(error));browser.save(q,key,value)


def authorised(q,key,token):
    if not key.startswith(prep.PREFIX) or not key.removeprefix(prep.PREFIX).isdigit():raise ValueError('Unknown live QA handoff.')
    value=browser.read(q,key);receipt=value.get('dashboard_qa') or {}
    if not hmac.compare_digest(receipt.get('token_hash',''),prep.digest(token)):raise PermissionError('QA handoff token rejected.')
    if receipt.get('policy')!=POLICY or (datetime.now(timezone.utc)-datetime.fromisoformat(receipt['claimed_at'])).total_seconds()>900:
        raise ValueError('QA handoff expired; recheck this order.')
    return value,receipt


def batch_values(q,value,receipt,token):
    ids=receipt.get('batch') or [value['allocation_id']]
    if not isinstance(ids,list) or not 1<=len(ids)<=20 or len(set(ids))!=len(ids) or value['allocation_id'] not in ids:
        raise ValueError('QA group membership is invalid.')
    result=[]
    for aid in ids:
        unit,other=authorised(q,prep.PREFIX+str(aid),token)
        if unit['order_id']!=value['order_id'] or other.get('batch',ids)!=ids:
            raise ValueError('The grouped QA handoff changed.')
        result.append(unit)
    return result


def permit(key,token,evidence):
    provider,resolver,_,_=browser.context(key)
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT pg_advisory_xact_lock(%s)',(browser.LOCK,))
        value,receipt=authorised(q,key,token)
        values=batch_values(q,value,receipt,token)
        if receipt.get('started') or value['status']!=ACTIVE:raise ValueError('QA shipping permit already used.')
        snap,order,_=current(value,provider,resolver)
        for unit in values:current_for_order(unit,order,resolver)
        if pinned_order(receipt['before'])!=pinned_order(order) or clean(receipt['before'].get('shippingMethod'))!=clean(order.get('shippingMethod')):
            raise ValueError('The supplier draft changed before the shipping check.')
        if not isinstance(evidence,dict) or set(evidence)!={'options','current','target'}:raise ValueError('Shipping evidence is incomplete.')
        target=shipping_choice(evidence['options'],intent(snap.get('shipping')),evidence['current'])
        if target!=evidence['target'] or clean(order.get('shippingMethod'))!=evidence['current']:
            raise ValueError('The selected shipping quote differs from this saved order.')
        for unit in values:
            other=unit['dashboard_qa']
            if other.get('started') or unit['status']!=ACTIVE:raise ValueError('A grouped QA permit was already used.')
            other.update(started=True,shipping=deepcopy(evidence),permitted_at=prep.now())
            browser.save(q,prep.PREFIX+str(unit['allocation_id']),unit)
    return {'permitted':True,'tax_declaration':receipt.get('tax_policy')==TAX_POLICY}


def identity_proof(snapshot):
    import auto_editions_runtime as runtime
    job,_=runtime.job_for(snapshot['allocation_id'])
    registry,_=runtime.stores();preparation=registry.read(job['preparation_hash']) or {}
    proofs=preparation.get('proofs') or []
    return (job['id']==snapshot['job_id'] and job['number']==snapshot['number'] and job['total']==snapshot['total']
        and snapshot.get('rendered_number')==snapshot['number'] and snapshot.get('rendered_total')==snapshot['total']
        and bool(snapshot.get('output',{}).get('sha256'))
        and any(p.get('outside_number_exact') is True for p in proofs)
        and {1,snapshot['total']}<={p.get('number') for p in proofs if p.get('pixel_exact') is True})


def observed_inserts(evidence):
    """Record supplier-selected names, independent of branding templates/assets."""
    rows=evidence.get('saved') if isinstance(evidence,dict) else None
    if not isinstance(rows,list) or not 0<len(rows)<=100:return []
    if any(not isinstance(row,dict) or not isinstance(row.get('name'),str) or not row['name'].strip() for row in rows):return []
    return list(dict.fromkeys(' '.join(row['name'].split())[:200] for row in rows))


def insert_checks(evidence,asset_resolver=None):
    # Owner policy: presence is required; set, asset and availability are informational.
    present=bool(observed_inserts(evidence))
    return present,present


def evaluate(value,snapshot,order,item,evidence,*,identity_verified,asset_resolver=None):
    required={'quality','sku','colour','shipping','inserts'}
    if not isinstance(evidence,dict) or not required<=set(evidence) or set(evidence)-required-{'tax_collected','item_id'}:raise ValueError('Dashboard QA evidence is incomplete.')
    if len(order.get('items',[]))>1 and str(evidence.get('item_id'))!=str(value['item_id']):raise ValueError('The dashboard QA evidence belongs to another supplier item.')
    receipt=value['dashboard_qa'];shipping=evidence['shipping']
    if not isinstance(shipping,dict) or set(shipping)!={'options','selected'}:raise ValueError('Shipping readback is incomplete.')
    planned=receipt['shipping']
    choice=shipping_choice(shipping['options'],intent(snapshot.get('shipping')),shipping['selected'])
    quote_ok=(shipping['options']==planned['options'] and choice==planned['target']==shipping['selected']==clean(order.get('shippingMethod')))
    selected,available=insert_checks(evidence['inserts'],asset_resolver)
    mapping=snapshot['mapping'];frame=mapping['frame']=='Unframed' or clean((item.get('attributes') or {}).get('color'))==clean(mapping['prodigi_frame_colour'])
    assets=item.get('assets') or []
    attached=(value.get('browser') or {}).get('verified') is True and len(assets)==1 and prep.digest(assets[0].get('url'))==value.get('url_hash')
    checks=dict(product_option=item.get('sku')==evidence['sku']==mapping['prodigi_code'],frame=frame and clean(evidence['colour'])==clean((item.get('attributes') or {}).get('color')),
        size=item.get('sku')==mapping['prodigi_code'],artwork_upload=attached and identity_verified,
        edition_number=identity_verified,sent_to_production=(value.get('browser') or {}).get('full_image_fit_verified') is True,
        image_quality=evidence['quality']=='Excellent',customer_address=address_matches(snapshot.get('recipient'),order.get('recipient')),
        shipping=quote_ok,certificate=selected,packing_slip=selected,inserts_available=available)
    checks['final_check']=all(checks.values()) and not order.get('issues') and (order.get('status')=='draft')
    labels={'product_option':'Product/SKU differs.','frame':'Frame colour differs.','size':'Size mapping differs.',
        'artwork_upload':'Exact saved design is not verified.','edition_number':'Allocated edition number is not verified.',
        'sent_to_production':'Full-image fit/orientation is not verified.','image_quality':'Prodigi image quality must show Excellent.',
        'customer_address':'Customer shipping details differ from the saved Shopify order.',
        'shipping':'The cheapest quoted shipping (or required Express) is not selected.',
        'certificate':'No saved inserts are shown in Prodigi.',
        'packing_slip':'No saved inserts are shown in Prodigi.',
        'inserts_available':'No saved inserts are shown in Prodigi.',
        'final_check':'QA has unresolved checks or supplier issues.'}
    return dict(policy=POLICY,checks=checks,blockers=list(dict.fromkeys(labels[k] for k,v in checks.items() if not v)),
        inserts=dict(names=observed_inserts(evidence['inserts']),supplier_available=evidence['inserts'].get('available')),
        checked_at=prep.now(),basis='Pinned artwork receipt and edition proofs, saved supplier order, live Excellent rating, observed supplier inserts and current shipping quotes',
        supplier_status=order.get('status'),supplier_download_confirmed=bool(assets and clean(assets[0].get('status'))=='complete'))


def finish(key,token,evidence,error=''):
    provider,resolver,_,_=browser.context(key)
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT pg_advisory_xact_lock(%s)',(browser.LOCK,))
        try:
            value,receipt=authorised(q,key,token)
            if receipt.get('verified'):return {'status':value['status']}
            values=batch_values(q,value,receipt,token)
        except (ValueError,PermissionError):
            return {'status':'Handoff unavailable'} # Reset retired this token; release the desktop queue.
        try:
            if error:raise ValueError(error[:240])
            if not receipt.get('started'):raise ValueError('QA stopped before the shipping permit; recheck this same order.')
            order=provider.order(value['order_id'])
            if not isinstance(evidence,dict):raise ValueError('Dashboard QA evidence is incomplete.')
            rows=evidence.get('items')
            if len(values)>1:
                if not isinstance(rows,list) or len(rows)!=len(values) or any(not isinstance(r,dict) or set(r)!={'item_id','sku','colour','quality'} for r in rows):
                    raise ValueError('Every grouped item needs its own quality and product evidence.')
                if len({r['item_id'] for r in rows})!=len(rows) or {r['item_id'] for r in rows}!={v['item_id'] for v in values}:
                    raise ValueError('Grouped QA item IDs differ from the pinned order.')
            elif rows is not None:raise ValueError('Unexpected grouped QA evidence.')
            stamp=prep.now();updates=[]
            for unit in values:
                other=unit['dashboard_qa']
                if not other.get('started'):raise ValueError('A grouped QA shipping permit is missing.')
                snap,_,item=current_for_order(unit,order,resolver)
                if pinned_order(other['before'])!=pinned_order(order):raise ValueError('Product, artwork, address or inserts changed during QA.')
                tax_seen=evidence.get('tax_collected')
                if other.get('tax_required') and tax_seen is not True:raise ValueError('The sales-tax-collected declaration was not confirmed; recheck this draft.')
                if tax_seen is True and order.get('usSalesTaxAlreadyCollected') is False:raise ValueError('Prodigi has not saved the sales-tax-collected declaration yet; recheck this draft.')
                proof={k:v for k,v in evidence.items() if k!='items'}
                if rows is not None:proof.update(next(r for r in rows if r['item_id']==unit['item_id']))
                result=evaluate(unit,snap,order,item,proof,identity_verified=identity_proof(snap),asset_resolver=getattr(provider,'asset',None))
                unit.update(qa=result,checks=result['checks'],status='Ready for manual payment' if all(result['checks'].values()) else 'Needs QA',
                    message='All QA passed. Submission follows the configured Orders companion setting.' if all(result['checks'].values()) else ' '.join(result['blockers']))
                pinned=pinned_order(order);pinned['shippingMethod']=order.get('shippingMethod')
                other.update(tax_collected=tax_seen,verified=True,evidence=proof,checked_at=stamp,validated_order_hash=prep.digest(pinned))
                updates.append(unit)
            values=updates
        except Exception as exc:
            for unit in values:
                unit['dashboard_qa']['verified']=False
                unit.update(status='Needs review',message=str(exc) if isinstance(exc,ValueError) else 'Dashboard QA could not be verified; recheck this exact order.')
                prep.record_failure(unit,'dashboard_qa',unit['message'],type(exc).__name__)
        for unit in values:browser.save(q,prep.PREFIX+str(unit['allocation_id']),unit)
    return {'status':next(v for v in values if v['allocation_id']==value['allocation_id'])['status']}
