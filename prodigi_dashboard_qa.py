"""Pinned, single-pass dashboard QA. No artwork/document upload, payment or Submit."""
from copy import deepcopy
from datetime import datetime, timezone
import hmac, secrets
import prodigi_preparation as prep
import prodigi_stage as stages
import prodigi_browser as browser
from prodigi_qa import address_matches, clean

POLICY='prodigi-dashboard-inserts-observed-v2'
# Owner confirmed on 2026-11-22 that applicable sales tax is already collected.
TAX_POLICY='owner-confirmed-sales-tax-collected-2026-11-22'
WAITING='Awaiting dashboard QA'
ACTIVE='Checking dashboard QA'
RECOVERY_POLICY='nonblocking-telemetry-v1'
PAGE_RECOVERY_POLICY='fresh-owned-context-v1'
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
    item=prep.validate_order(order,snap,value['order_id'],value['item_id'],binding=value.get('consolidation_binding'))
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


def recover_waiting_item_qa(user,*,page_supported=False):
    """Retire known pre-permit UI waits; preserve independently saved artwork."""
    prep.require_user(user)
    from companion_poll_transaction import connection
    with connection(prep.connect) as conn,conn.cursor() as cur:
        cur.execute("""SELECT key FROM app_settings WHERE key LIKE 'prodigi_prepare:%%'
            AND value->>'status'='Needs review'
            AND (value->>'message'='QA inserts: The expected QA control did not finish loading.'
                 AND value->'dashboard_qa'->>'item_only'='true'
                 OR value->>'message'='QA product-row: Close the existing order editor before QA.'
                 OR value->>'message'='QA tax-declaration: The expected Prodigi control did not finish loading.'
                 OR ((value->>'message' IN ('QA shipping: The exact draft or shipping quotes changed before QA.',
                     'QA inserts: The expected Prodigi control did not finish loading.') OR (%s AND
                     (value->>'message'='Interrupted QA; recheck the saved order without repeating an upload.' OR value->>'message' LIKE 'QA open: %%')))
                     AND (COALESCE(value->>'qa_prepermit_recovery_policy','')<>
                          CASE WHEN value->>'message'='Interrupted QA; recheck the saved order without repeating an upload.'
                            OR value->>'message' LIKE 'QA open: %%' THEN 'fresh-owned-context-v1' ELSE 'nonblocking-telemetry-v1' END
                          OR COALESCE((value->>'qa_prepermit_recoveries')::int,0)<2)))
            AND (value->'dashboard_qa'->>'started'='false' OR
                 (value->>'message'='QA tax-declaration: The expected Prodigi control did not finish loading.'
                  AND value->'dashboard_qa'->>'started'='true'
                  AND COALESCE((value->>'qa_tax_readback_recoveries')::int,0)<1))
            AND value->'browser'->>'verified'='true'
            AND NOT value ? 'submission' AND NOT COALESCE((value->>'hidden')::boolean,false)
            ORDER BY updated_at LIMIT 2""",(page_supported,))
        keys=[row['key'] for row in cur.fetchall()]
    return recover_colour_plans(user)+sum(_recover_item_qa(key,page_supported=page_supported) for key in keys)


def canonical_colour(snapshot):
    mapping=snapshot['mapping']
    return '' if mapping['frame']=='Unframed' else mapping['prodigi_frame_colour']


def recover_colour_plans(user):
    """Retire only the known unused grouped handoff with mixed colour casing."""
    prep.require_user(user)
    from companion_poll_transaction import connection
    with connection(prep.connect) as conn,conn.cursor() as q:
        q.execute("""SELECT key FROM app_settings WHERE key LIKE 'prodigi_prepare:%%'
          AND value->>'status'=%s AND value->'dashboard_qa'->>'started'='false'
          AND jsonb_array_length(value->'dashboard_qa'->'batch')>1
          AND (value->'dashboard_qa'->>'claimed_at')::timestamptz<now()-interval '90 seconds'
          AND COALESCE((value->>'qa_colour_plan_recoveries')::int,0)<1
          AND COALESCE(value->'dashboard_qa'->>'colour_policy','')<>'canonical-v1'
          AND NOT value ? 'submission' AND NOT COALESCE((value->>'hidden')::boolean,false)
          ORDER BY updated_at LIMIT 2""",(ACTIVE,))
        keys=[row['key'] for row in q.fetchall()]
    recovered=0
    for key in keys:
        try:recovered+=bool(_recover_colour_plan(key))
        except (ValueError,PermissionError):pass
    return recovered


@stages.stale_result(False)
def _recover_colour_plan(key):
    provider,resolver,_,_=browser.context(key)
    resolver=stages.resolver_once(resolver)
    with stages.edit(browser.LOCK) as q:
        value=browser.read(q,key);receipt=value.get('dashboard_qa') or {}
        if (value.get('status')!=ACTIVE or receipt.get('started') is not False
            or value.get('qa_colour_plan_recoveries',0)>=1 or value.get('submission')
            or receipt.get('colour_policy')=='canonical-v1'):return False
        if (datetime.now(timezone.utc)-datetime.fromisoformat(receipt['claimed_at'])).total_seconds()<90:return False
        ids=receipt.get('batch') or []
        if not 2<=len(ids)<=100 or len(set(ids))!=len(ids):return False
        before_item=next((i for i in receipt.get('before',{}).get('items',[]) if str(i.get('id'))==str(value['item_id'])),{})
        raw=(before_item.get('attributes') or {}).get('color','');colour=canonical_colour(value['snapshot'])
        if raw==colour or clean(raw)!=clean(colour):return False
        _,order,_=current(value,provider,resolver)
        units=[]
        for aid in ids:
            unit=browser.read(q,prep.PREFIX+str(int(aid)));other=unit.get('dashboard_qa') or {}
            if (unit.get('status')!=ACTIVE or other.get('started') is not False
                or other.get('token_hash')!=receipt.get('token_hash') or other.get('batch')!=ids
                or unit.get('qa_colour_plan_recoveries',0)>=1 or unit.get('submission')):return False
            current_for_order(unit,order,resolver)
            if pinned_order(other['before'])!=pinned_order(order):return False
            if clean(other['before'].get('shippingMethod'))!=clean(order.get('shippingMethod')):return False
            units.append(unit)
        if {str(u['item_id']) for u in units}!={str(i['id']) for i in order['items']}:return False
        for unit in units:
            unit.setdefault('dashboard_qa_history',[]).append({'claimed_at':receipt['claimed_at'],'event':'mixed_colour_plan_retired'})
            unit.pop('dashboard_qa');unit['qa_colour_plan_recoveries']=1
            unit.update(status=WAITING,message='Retrying the unused grouped QA plan with consistent verified frame colours.')
            browser.save(q,prep.PREFIX+str(unit['allocation_id']),unit)
        return True


@stages.stale_result(False)
def _recover_item_qa(key,*,page_supported=False):
    provider,resolver,_,_=browser.context(key)
    with stages.edit(browser.LOCK) as cur:
        value=browser.read(cur,key);receipt=value.get('dashboard_qa') or {}
        page_wait=(value.get('message')=='Interrupted QA; recheck the saved order without repeating an upload.' or value.get('message','').startswith('QA open: '))
        if page_wait and not page_supported:return False
        prepermit=value.get('message') in ('QA shipping: The exact draft or shipping quotes changed before QA.',
            'QA inserts: The expected Prodigi control did not finish loading.',
            'Interrupted QA; recheck the saved order without repeating an upload.') or value.get('message','').startswith('QA open: ')
        tax_readback=(value.get('message')=='QA tax-declaration: The expected Prodigi control did not finish loading.'
                      and receipt.get('started') is True and receipt.get('tax_policy')==TAX_POLICY
                      and value.get('qa_tax_readback_recoveries',0)<1)
        known=(tax_readback or value.get('message')=='QA inserts: The expected QA control did not finish loading.' and receipt.get('item_only')
               or value.get('message')=='QA product-row: Close the existing order editor before QA.' or prepermit)
        if (value.get('status')!='Needs review' or not known or (receipt.get('started') is not False and not tax_readback) or value.get('submission')):
            return False
        recovery_policy=PAGE_RECOVERY_POLICY if page_wait else RECOVERY_POLICY
        recoveries=value.get('qa_prepermit_recoveries',0) if value.get('qa_prepermit_recovery_policy')==recovery_policy else 0
        if prepermit and recoveries>=2:return False
        try:
            _,order,_=current(value,provider,resolver)
            if tax_readback:
                # Some provider reads omit this dashboard-only flag. Missing is
                # not confirmation: admit a fresh full DOM QA pass, never mark it
                # passed here. An explicit unsaved value must still block.
                if order.get('usSalesTaxAlreadyCollected') is False:
                    __import__('logging').getLogger(__name__).info('Tax QA recovery held: provider_tax_false');return False
                if clean(order.get('shippingMethod'))!=receipt.get('shipping',{}).get('target'):
                    __import__('logging').getLogger(__name__).info('Tax QA recovery held: shipping_target_changed');return False
            before=pinned_order(receipt['before']);after=pinned_order(order)
            if before!=after:
                if tax_readback:
                    fields=','.join(sorted(k for k in before.keys()|after.keys() if before.get(k)!=after.get(k)))
                    __import__('logging').getLogger(__name__).info('Tax QA recovery held: business_changed fields=%s',fields)
                return False
            if prepermit and clean(receipt['before'].get('shippingMethod'))!=clean(order.get('shippingMethod')):return False
        except (ValueError,PermissionError) as exc:
            if tax_readback:__import__('logging').getLogger(__name__).info('Tax QA recovery held: current_validation kind=%s',type(exc).__name__)
            return False
        value.setdefault('dashboard_qa_history',[]).append({k:receipt.get(k) for k in ('claimed_at','checked_at','verified','item_only')})
        value.pop('dashboard_qa');value.pop('last_failure',None)
        if tax_readback:value['qa_tax_readback_recoveries']=value.get('qa_tax_readback_recoveries',0)+1
        if prepermit:value.update(qa_prepermit_recoveries=recoveries+1,qa_prepermit_recovery_policy=recovery_policy)
        value.update(status=WAITING,message='Rechecking saved tax and full QA; verified artwork retained.' if tax_readback else 'Retrying the pre-permit QA check; verified artwork retained.' if prepermit else 'Rechecking the saved edition; shared checks wait until every item is ready.')
        browser.save(cur,key,value)
    return True


def enqueue(value,provider,resolver,persist,*,verified_order=None):
    # Upload completion has just independently verified this exact readback and
    # source. Reuse it for queue admission, avoiding another provider/file read.
    # claim(), permit() and submission still independently revalidate everything.
    if verified_order is None:
        _,order,_=current(value,provider,resolver)
        checked_resolver=resolver
    else:
        order=verified_order
        checked_resolver=lambda aid:value['snapshot'] if aid==value['allocation_id'] else resolver(aid)
        current_for_order(value,order,checked_resolver)
    from prodigi_consolidation import hold_qa
    if hold_qa(value):
        value.update(status='Merge preparing',message='Preparing all additional numbered items before combined QA.');persist(value);return value
    from prodigi_order_group import members,WaitingForItems
    try:members(value,order,checked_resolver)
    except WaitingForItems:
        # This edition is saved: check it now, without waiting for sibling uploads.
        # A final fresh whole-order batch remains required before any submission.
        pass
    value.pop('last_failure',None)
    value.update(status=WAITING,message='Checking branding inserts, Excellent quality, shipping and customer details before the configured submission step.')
    persist(value)
    return value


@stages.stale_result(None)
def claim(*,tax_supported=False,exact_item_supported=False,batch_supported=False,sequential_supported=False,item_qa_supported=False,preferred_order=''):
    with stages.edit(browser.LOCK) as q:
        q.execute("SELECT key,value FROM app_settings WHERE key LIKE 'prodigi_prepare:%%' AND value->>'status'=%s AND NOT COALESCE((value->>'hidden')::boolean,false) ORDER BY CASE WHEN value->>'order_id'=%s THEN 0 ELSE 1 END,updated_at LIMIT 1",(WAITING,preferred_order))
        row=q.fetchone()
        if not row:return None
        value=row['value'];key=row['key']
        if value.get('dashboard_qa'):return None
        provider,resolver,_,_=browser.context(key)
        resolver=stages.resolver_once(resolver)
        try:
            snap,order,item=current(value,provider,resolver)
            if len(order.get('items',[]))>1 and not exact_item_supported:return None
            tax_required=clean((snap.get('recipient') or {}).get('address',{}).get('countryCode'))=='us'
            if tax_required and not tax_supported:return None
            token=secrets.token_urlsafe(32)
            values=[value];item_only=False
            if batch_supported and len(order.get('items',[]))>1:
                from prodigi_order_group import members,WaitingForItems
                try:values=members(value,order,resolver)
                except WaitingForItems:
                    if not sequential_supported or not item_qa_supported:return None
                    item_only=True
                if len(values)>100:raise ValueError('More than 100 numbered items require a separate order review.')
                if any(v['allocation_id']!=value['allocation_id'] and v.get('status')==ACTIVE for v in values):return None
                if any(v.get('submission') and not v.get('merge_pending') for v in values):raise ValueError('A submitted item cannot enter a new draft QA batch.')
                if any(intent(v['snapshot'].get('shipping'))!=intent(snap.get('shipping')) for v in values):
                    raise ValueError('Items in one supplier order have different shipping requirements.')
            batch=[v['allocation_id'] for v in values]
            stamp=prep.now()
            for unit in values:
                current_for_order(unit,order,resolver)
                previous=unit.get('dashboard_qa')
                if previous:unit.setdefault('dashboard_qa_history',[]).append({k:previous.get(k) for k in ('policy','claimed_at','checked_at','verified')})
                unit['dashboard_qa']=dict(token_hash=prep.digest(token),claimed_at=stamp,before=order,started=False,policy=POLICY,tax_policy=TAX_POLICY,tax_required=tax_required,batch=batch,item_only=item_only,colour_policy='canonical-v1')
                unit.update(status=ACTIVE,message='Checking this edition before preparing the next item.' if item_only else 'Checking all numbered items, shipping, inserts and tax in one QA pass.')
                browser.save(q,prep.PREFIX+str(unit['allocation_id']),unit)
            return dict(kind='qa',key=key,token=token,environment='live',order_id=value['order_id'],item_id=value['item_id'],exact_item=exact_item_supported,
                order_url='https://dashboard.prodigi.com/orders/'+value['order_id']+'/detail',
                reference=order['merchantReference'],sku=item['sku'],colour=canonical_colour(snap),fresh_saved_order=True,
                shipping_intent=intent(snap.get('shipping')),branding_set=SET,tax_declaration=True,tax_required=tax_required,
                **({'item_only':True} if item_only else {}),
                **({'items':[dict(item_id=v['item_id'],sku=v['snapshot']['mapping']['prodigi_code'],colour=canonical_colour(v['snapshot'])) for v in values]} if len(values)>1 else {}))
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
    if not isinstance(ids,list) or not 1<=len(ids)<=100 or len(set(ids))!=len(ids) or value['allocation_id'] not in ids:
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
    resolver=stages.resolver_once(resolver)
    with stages.edit(browser.LOCK) as q:
        value,receipt=authorised(q,key,token)
        if value.get('merge_pending'):
            from prodigi_consolidation import check_write
            check_write(value,provider,resolver)
        values=batch_values(q,value,receipt,token)
        if receipt.get('item_only'):raise ValueError('Item QA cannot change order shipping or tax; wait for final whole-order QA.')
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
    if snapshot.get('source_kind')=='framed_certificate':
        from certificate_frame_fulfilment import identity_proof as certificate_proof
        return certificate_proof(snapshot)
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


def item_checks(value,snapshot,order,item,evidence,*,identity_verified):
    mapping=snapshot['mapping'];frame=mapping['frame']=='Unframed' or clean((item.get('attributes') or {}).get('color'))==clean(mapping['prodigi_frame_colour'])
    assets=item.get('assets') or []
    attached=(value.get('browser') or {}).get('verified') is True and len(assets)==1 and prep.digest(assets[0].get('url'))==value.get('url_hash')
    return dict(product_option=item.get('sku')==evidence['sku']==mapping['prodigi_code'],frame=frame and clean(evidence['colour'])==clean((item.get('attributes') or {}).get('color')),
        size=item.get('sku')==mapping['prodigi_code'],artwork_upload=attached and identity_verified,
        edition_number=identity_verified,sent_to_production=(value.get('browser') or {}).get('full_image_fit_verified') is True,
        image_quality=evidence['quality']=='Excellent',customer_address=address_matches(snapshot.get('recipient'),order.get('recipient')))


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
    assets=item.get('assets') or []
    checks=item_checks(value,snapshot,order,item,evidence,identity_verified=identity_verified)
    checks.update(shipping=quote_ok,certificate=selected,packing_slip=selected,inserts_available=available)
    checks['final_check']=all(checks.values()) and not order.get('issues') and (order.get('status')=='draft' or bool(value.get('consolidation_binding') and value.get('merge_pending') and order.get('status')=='paused'))
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


@stages.stale_result({'status':'Handoff unavailable'})
def finish(key,token,evidence,error=''):
    provider,resolver,_,_=browser.context(key)
    resolver=stages.resolver_once(resolver)
    with stages.edit(browser.LOCK) as q:
        try:
            value,receipt=authorised(q,key,token)
            if receipt.get('verified'):return {'status':value['status']}
            values=batch_values(q,value,receipt,token)
        except (ValueError,PermissionError):
            return {'status':'Handoff unavailable'} # Reset retired this token; release the desktop queue.
        try:
            if error:raise ValueError(error[:240])
            if receipt.get('item_only'):
                if len(values)!=1 or receipt.get('started'):raise ValueError('Item-only QA scope changed.')
                if not isinstance(evidence,dict) or set(evidence)!={'item_id','sku','colour','quality'} or evidence['item_id']!=value['item_id']:
                    raise ValueError('The exact item-only QA evidence is incomplete.')
                snap,order,item=current(value,provider,resolver)
                if pinned_order(receipt['before'])!=pinned_order(order):raise ValueError('The saved supplier order changed during item QA.')
                checks=item_checks(value,snap,order,item,evidence,identity_verified=identity_proof(snap))
                passed=all(checks.values());checks['final_check']=False
                stamp=prep.now()
                value.update(checks=checks,qa=dict(policy=POLICY,scope='item',checks=checks,checked_at=stamp),
                    status='Waiting for order' if passed else 'Needs QA',
                    message='This edition passed item QA. Shared shipping, tax and inserts will be checked after all items are ready.' if passed else 'This edition failed item QA; review its artwork, variant, quality or shipping details.')
                receipt.update(verified=passed,evidence=evidence,checked_at=stamp,scope='item')
                browser.save(q,key,value)
                return {'status':value['status']}
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
                if all(result['checks'].values()) and other.get('item_only'):
                    unit.update(status='Waiting for order',message='This edition passed QA. Preparing the next item before final whole-order QA and one submission.')
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
