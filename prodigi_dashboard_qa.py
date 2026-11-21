"""Pinned, single-pass dashboard QA. No artwork/document upload, payment or Submit."""
from copy import deepcopy
from datetime import datetime, timezone
import hmac, secrets
import prodigi_preparation as prep
import prodigi_browser as browser
from prodigi_qa import address_matches, clean

POLICY='prodigi-dashboard-inserts-qa-v1'
WAITING='Awaiting dashboard QA'
ACTIVE='Checking dashboard QA'
SET='SC EDITION BRANDING'
TYPES={'Round packaging sticker','Packing slip (colour)'}
CHECKS={'product_option':'Product and variant SKU','frame':'Frame colour','size':'Print size','artwork_upload':'Exact saved design','edition_number':'Allocated edition number','sent_to_production':'Full-image fit and orientation','image_quality':'Prodigi image quality: Excellent','customer_address':'Customer shipping details','shipping':'Cheapest shipping / required Express','certificate':'SC EDITION BRANDING saved inserts','packing_slip':'Colour packing slip and round packaging sticker','inserts_available':'Supplier insert availability','final_check':'All QA checks passed'}


def intent(value):
    # Fulfilment may append recipient details after a pipe; those are not a service.
    value=clean(value).split('|',1)[0].strip()
    if __import__('re').search(r'\bexpress\b',value):return 'express'
    if __import__('re').match(r'^standard(?:\s|$)',value) or value in ('budget','economy','australia post'):return 'standard'
    raise ValueError('The customer shipping service is unknown; review it before changing shipping.')


def shipping_choice(options, requested, current):
    if not isinstance(options,list) or not 1<=len(options)<=10:raise ValueError('Shipping quotes are missing or ambiguous.')
    if any(not isinstance(o,dict) or set(o)!={'service','cents','currency'} or
           o['service'] not in ('budget','standard','express') or type(o['cents']) is not int or
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


def current(value,provider,resolver):
    snap,order,item=browser.checked(value,provider,resolver,False)
    receipt=value.get('browser') or {}
    if not receipt.get('verified') or not receipt.get('full_image_fit_verified'):
        raise ValueError('The saved numbered artwork and full-image fit must be verified first.')
    if len(order.get('items',[]))!=1 or item.get('quantity')!=1:
        raise ValueError('Dashboard QA requires one separately numbered item per supplier order.')
    assets=item.get('assets') or []
    if len(assets)!=1 or prep.digest(assets[0].get('url'))!=value.get('url_hash'):
        raise ValueError('The saved artwork changed; review this exact draft.')
    return snap,order,item


def enqueue(value,provider,resolver,persist):
    current(value,provider,resolver)
    value.pop('last_failure',None)
    value.update(status=WAITING,message='Checking branding inserts, Excellent quality, shipping and customer details before the configured submission step.')
    persist(value)
    return value


def claim():
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
            token=secrets.token_urlsafe(32)
            value['dashboard_qa']=dict(token_hash=prep.digest(token),claimed_at=prep.now(),before=order,started=False,policy=POLICY)
            value.update(status=ACTIVE,message='Companion is checking this saved order in one QA pass; no certificate upload.')
            browser.save(q,key,value)
            return dict(kind='qa',key=key,token=token,environment='live',order_id=value['order_id'],
                order_url='https://dashboard.prodigi.com/orders/'+value['order_id']+'/detail',
                reference=order['merchantReference'],sku=item['sku'],colour=(item.get('attributes') or {}).get('color',''),
                shipping_intent=intent(snap.get('shipping')),branding_set=SET)
        except ValueError as error:
            value.update(status='Needs review',message=str(error));prep.record_failure(value,'dashboard_qa',str(error));browser.save(q,key,value)


def authorised(q,key,token):
    if not key.startswith(prep.PREFIX) or not key.removeprefix(prep.PREFIX).isdigit():raise ValueError('Unknown live QA handoff.')
    value=browser.read(q,key);receipt=value.get('dashboard_qa') or {}
    if not hmac.compare_digest(receipt.get('token_hash',''),prep.digest(token)):raise PermissionError('QA handoff token rejected.')
    if receipt.get('policy')!=POLICY or (datetime.now(timezone.utc)-datetime.fromisoformat(receipt['claimed_at'])).total_seconds()>900:
        raise ValueError('QA handoff expired; recheck this order.')
    return value,receipt


def permit(key,token,evidence):
    provider,resolver,_,_=browser.context(key)
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT pg_advisory_xact_lock(%s)',(browser.LOCK,))
        value,receipt=authorised(q,key,token)
        if receipt.get('started') or value['status']!=ACTIVE:raise ValueError('QA shipping permit already used.')
        snap,order,_=current(value,provider,resolver)
        if pinned_order(receipt['before'])!=pinned_order(order) or clean(receipt['before'].get('shippingMethod'))!=clean(order.get('shippingMethod')):
            raise ValueError('The supplier draft changed before the shipping check.')
        if not isinstance(evidence,dict) or set(evidence)!={'options','current','target'}:raise ValueError('Shipping evidence is incomplete.')
        target=shipping_choice(evidence['options'],intent(snap.get('shipping')),evidence['current'])
        if target!=evidence['target'] or clean(order.get('shippingMethod'))!=evidence['current']:
            raise ValueError('The selected shipping quote differs from this saved order.')
        receipt.update(started=True,shipping=deepcopy(evidence),permitted_at=prep.now())
        browser.save(q,key,value)
    return {'permitted':True}


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


def insert_checks(evidence,asset_resolver=None):
    if not isinstance(evidence,dict) or set(evidence)!={'set_name','saved','expected','available'}:return False,False
    def rows(items):
        if not isinstance(items,list) or len(items)!=2:return None
        if any(not isinstance(i,dict) or set(i)!={'name','asset'} or i['name'] not in TYPES or
               not isinstance(i['asset'],str) or not __import__('re').fullmatch(r'[A-Za-z0-9-]{1,100}',i['asset']) for i in items):return None
        return {(i['name'],i['asset']) for i in items}
    saved,expected=rows(evidence['saved']),rows(evidence['expected'])
    # Dashboard previews use library UUIDs; saved branding uses transform IDs.
    # Resolve the provider's own canonical URL, never infer image equivalence.
    if saved is not None and expected is not None and saved!=expected and asset_resolver:
        from urllib.parse import urlparse
        normalised=set()
        for name,asset_id in expected:
            asset=asset_resolver(asset_id)
            parsed=urlparse(asset.get('url') or '')
            match=__import__('re').fullmatch(r'/image-library/transform/([A-Za-z0-9-]+)/image',parsed.path)
            if str(asset.get('id'))!=asset_id or parsed.scheme!='https' or parsed.hostname!='live-services.pwinty.com' or not match:
                return False,False
            normalised.add((name,match[1]))
        expected=normalised
    selected=(evidence['set_name']==SET and saved is not None and expected is not None and len(saved)==len(expected)==2
              and {n for n,_ in expected}==TYPES and saved==expected)
    return selected,selected and evidence['available'] is True


def evaluate(value,snapshot,order,item,evidence,*,identity_verified,asset_resolver=None):
    if not isinstance(evidence,dict) or set(evidence)!={'quality','sku','colour','shipping','inserts'}:raise ValueError('Dashboard QA evidence is incomplete.')
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
    checks['final_check']=all(checks.values()) and not order.get('issues') and order.get('status')=='draft'
    labels={'product_option':'Product/SKU differs.','frame':'Frame colour differs.','size':'Size mapping differs.',
        'artwork_upload':'Exact saved design is not verified.','edition_number':'Allocated edition number is not verified.',
        'sent_to_production':'Full-image fit/orientation is not verified.','image_quality':'Prodigi image quality must show Excellent.',
        'customer_address':'Customer shipping details differ from the saved Shopify order.',
        'shipping':'The cheapest quoted shipping (or required Express) is not selected.',
        'certificate':'Saved inserts do not match SC EDITION BRANDING.',
        'packing_slip':'The exact colour packing slip and round packaging sticker are not selected.',
        'inserts_available':'Prodigi reports unavailable inserts, or availability could not be verified.',
        'final_check':'QA has unresolved checks or supplier issues.'}
    return dict(policy=POLICY,checks=checks,blockers=[labels[k] for k,v in checks.items() if not v],
        checked_at=prep.now(),basis='Pinned artwork receipt and edition proofs, saved supplier order, live Excellent rating, saved branding assets and current shipping quotes',
        supplier_status=order.get('status'),supplier_download_confirmed=bool(assets and clean(assets[0].get('status'))=='complete'))


def finish(key,token,evidence,error=''):
    provider,resolver,_,_=browser.context(key)
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT pg_advisory_xact_lock(%s)',(browser.LOCK,))
        value,receipt=authorised(q,key,token)
        if receipt.get('verified'):return {'status':value['status']}
        try:
            if error:raise ValueError(error[:240])
            if not receipt.get('started'):raise ValueError('QA stopped before the shipping permit; recheck this same order.')
            snap,order,item=current(value,provider,resolver)
            if pinned_order(receipt['before'])!=pinned_order(order):raise ValueError('Product, artwork, address or inserts changed during QA.')
            result=evaluate(value,snap,order,item,evidence,identity_verified=identity_proof(snap),asset_resolver=getattr(provider,'asset',None))
            value.update(qa=result,checks=result['checks'],status='Ready for manual payment' if all(result['checks'].values()) else 'Needs QA',
                message='All QA passed. Submission follows the owner’s Orders companion setting.' if all(result['checks'].values()) else ' '.join(result['blockers']))
            pinned=pinned_order(order);pinned['shippingMethod']=order.get('shippingMethod')
            receipt.update(verified=True,evidence=evidence,checked_at=prep.now(),validated_order_hash=prep.digest(pinned))
        except Exception as exc:
            value.update(status='Needs review',message=str(exc) if isinstance(exc,ValueError) else 'Dashboard QA could not be verified; recheck this exact draft.')
            prep.record_failure(value,'dashboard_qa',value['message'],type(exc).__name__)
        browser.save(q,key,value)
    return {'status':value['status']}
