"""Guarded browser upload handoff. Supplier API access here is read-only.

An authenticated desktop receives one pinned JPG and one exact draft. A durable
permit precedes Save, carrying the pinned SHA256 verified in both extension
contexts. Completion binds the supplier render to its uploaded asset metadata,
verifies placement and compares original bytes when the supplier exposes them.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import json
import secrets
from urllib.parse import urlsplit,parse_qs

import prodigi_preparation as prep
import prodigi_stage as stages
from prodigi_client import Client

LOCK = 19721124
WAITING = 'Awaiting browser upload'
READINESS_POLICY='fresh-owned-context-v1'


def context(key):
    import re
    import prodigi_sandbox as sandbox
    if re.fullmatch(r'prodigi_prepare:\d+', key):
        return Client(), prep.resolve, prep.artwork_link, False
    if re.fullmatch(r'prodigi_sandbox_test:[a-f0-9-]{36}', key):
        import os
        if os.getenv('SPORTS_CAVE_PRODIGI_SANDBOX_ENABLED','').lower()!='true':
            raise ValueError('Test preparation is disabled; use live Orders.')
        return sandbox.SandboxClient(), sandbox.resolve, lambda s: sandbox.artwork_link(s, key.split(':')[1]), True
    raise ValueError('Unknown Orders handoff.')


def read(cur, key):
    cur.execute('SELECT key,value FROM app_settings WHERE key=%s', (key,))
    row = cur.fetchone()
    if not row or row['value'].get('hidden'):
        raise ValueError('This Orders handoff is unavailable.')
    return row['value']


def save(cur, key, value):
    if isinstance(cur, stages.Stage):
        cur.save(key, value)
        return
    prep.measure_stage(value)
    value['updated_at'] = prep.now()
    cur.execute('''UPDATE app_settings SET value=%s::jsonb,updated_at=now()
        WHERE key=%s AND NOT COALESCE((value->>'hidden')::boolean,false) RETURNING key''',
        (json.dumps(value), key))
    if not cur.fetchone():
        raise ValueError('This handoff was removed.')


def snapshot(value, resolver, sandbox):
    source = resolver(value['allocation_id'])
    expected = value['source_snapshot'] if sandbox else value['snapshot']
    if not prep.same_source(expected,source):
        raise ValueError('The allocated artwork or Fulfilment mapping changed.')
    return value['snapshot']


def business(order, target, *, after_save=False, before=None):
    """Pin everything except this item's artwork and its editor sizing."""
    result = {k:deepcopy(order.get(k)) for k in
        ('id','merchantReference','recipient','shippingMethod','branding','packingSlip','charges')}
    result['items'] = []
    for item in order.get('items', []):
        result['items'].append({k:deepcopy(v) for k,v in item.items()
            if k not in ('status','productionTime') and
            (str(item['id']) != str(target) or k not in
             (('assets','sizing','unitPrice','lineTotal') if after_save else ('assets','sizing')))})
        if after_save:
            # Saving a final image can reprice already-saved siblings too.
            # Only supplier-calculated amounts may vary; currencies, products,
            # quantities and every sibling artwork/placement remain pinned.
            for key in ('unitPrice','lineTotal'):
                money=result['items'][-1].get(key)
                if isinstance(money,dict):money.pop('amount',None)
                if before is not None and str(item['id'])!=str(target):
                    previous=[i for i in before.get('items',[]) if str(i.get('id'))==str(item['id'])]
                    raw=item.get(key)
                    if len(previous)==1 and previous[0].get(key) is None and isinstance(raw,dict):
                        # The first artwork can make previously unpriced siblings
                        # acquire calculated prices. Existing currencies stay pinned.
                        from decimal import Decimal, InvalidOperation
                        import re
                        try:amount=Decimal(str(raw.get('amount')))
                        except InvalidOperation:amount=Decimal('NaN')
                        if (set(raw)=={'amount','currency'} and amount.is_finite() and amount>=0
                                and re.fullmatch('[A-Z]{3}',str(raw.get('currency','')))):
                            result['items'][-1].pop(key,None)
    return result


def checked(value, provider, resolver, sandbox):
    snap = snapshot(value, resolver, sandbox)
    order = provider.order(value['order_id'])
    item = prep.validate_order(order, snap, value['order_id'], value['item_id'],binding=value.get('consolidation_binding'))
    if order.get('charges'):
        raise ValueError('This order has charges; browser preparation stopped.')
    return snap, order, item


def verified_sibling_baseline(cur,value,order,target,provider,resolver):
    """Read back a sibling's separately permitted, verified JPG; never write it."""
    before=deepcopy(value['browser']['before'])
    verified=[]
    for previous in before.get('items',[]):
        item_id=str(previous.get('id'))
        if item_id==str(target):continue
        current=[i for i in order.get('items',[]) if str(i.get('id'))==item_id]
        if len(current)!=1:continue  # The normal whole-order fence rejects it.
        current=current[0]
        if all(previous.get(k)==current.get(k) for k in ('assets','sizing')):continue
        cur.execute("""SELECT key,value FROM app_settings WHERE key LIKE 'prodigi_prepare:%%'
            AND value->>'order_id'=%s AND value->>'item_id'=%s
            AND NOT COALESCE((value->>'hidden')::boolean,false) LIMIT 2""",
            (str(order['id']),item_id))
        rows=cur.fetchall()
        if len(rows)!=1:raise ValueError('Changed sibling artwork has no unique verified handoff.')
        sibling=rows[0]['value'];receipt=sibling.get('browser') or {}
        if (receipt.get('started') is not True or receipt.get('verified') is not True
                or sibling.get('allocation_id')==value['allocation_id']):
            raise ValueError('Changed sibling artwork has not passed its own Save verification.')
        snap=snapshot(sibling,resolver,False)
        prep.validate_order(order,snap,sibling['order_id'],sibling['item_id'],binding=sibling.get('consolidation_binding'))
        assets=current.get('assets') or []
        if (len(assets)!=1 or assets[0].get('printArea')!='default'
                or receipt.get('original_sha256')!=snap['output']['sha256']):
            raise ValueError('Changed sibling artwork does not match its verified source.')
        asset_id,_=verify_original(provider,original_file(assets[0]['url'],snap['dimensions']),
            receipt['filename'],snap['output'],snap['dimensions'])
        if asset_id!=receipt.get('original_asset_id'):
            raise ValueError('Changed sibling artwork is a different supplier asset.')
        # Only the separately verified artwork/fit may advance. SKU, quantity,
        # address, shipping, charges and other business fields remain pinned.
        for key in ('assets','sizing'):
            if key in current:previous[key]=deepcopy(current[key])
            else:previous.pop(key,None)
        verified.append(item_id)
    return before,verified


def has_existing_artwork(item):
    """Prodigi creates a required print-area slot before a file is attached."""
    assets=item.get('assets') or []
    if not assets:return False
    if not isinstance(assets,list) or len(assets)!=1 or not isinstance(assets[0],dict):return True
    slot=assets[0]
    empty=(set(slot)=={'id','printArea','status','pageCount','required'} and isinstance(slot['id'],str) and bool(slot['id'])
        and slot['printArea']=='default' and slot['status']=='NotYetDownloaded' and slot['required'] is True
        and type(slot['pageCount']) is int and slot['pageCount']==0)
    return not empty


@stages.stale_result(None)
def claim(*,exact_item_supported=False,reset_supported=False,upload_recovery_supported=False,preferred_order=''):
    import os
    with stages.edit(LOCK) as cur:
        cur.execute('''SELECT key,value FROM app_settings WHERE
            (key LIKE 'prodigi_prepare:%%' OR key LIKE 'prodigi_sandbox_test:%%')
            AND (key LIKE 'prodigi_prepare:%%' OR %s)
            AND value->>'status'=%s AND NOT COALESCE((value->>'hidden')::boolean,false)
            ORDER BY CASE WHEN value->>'order_id'=%s THEN 0 ELSE 1 END,updated_at LIMIT 20''', (os.getenv('SPORTS_CAVE_PRODIGI_SANDBOX_ENABLED','').lower()=='true',WAITING,preferred_order))
        for row in cur.fetchall():
            key, value = row['key'], row['value']
            if key.startswith('prodigi_sandbox_test:'):
                import os
                if os.getenv('SPORTS_CAVE_PRODIGI_SANDBOX_ENABLED','').lower()!='true':continue
            if key.startswith(prep.PREFIX) and not value.get('browser_requested'):
                continue  # Old requests cannot be activated by enabling the new worker.
            provider, resolver, link, sandbox = context(key)
            if not sandbox and os.getenv('SPORTS_CAVE_PRODIGI_BROWSER_ACCEPTED','').lower() != 'true':
                continue
            if value.get('browser') or value.get('write_intent'):
                continue  # An uncertain upload is never automatically repeated.
            recovery=value.get('upload_recovery')
            if recovery and (not upload_recovery_supported or not exact_item_supported):continue
            try:
                snap, order, item = checked(value, provider, resolver, sandbox)
                replace=has_existing_artwork(item)
                if recovery and (sandbox or replace or recovery.get('source_sha256')!=snap['output']['sha256']
                        or business(order,item['id'])!=recovery.get('before')
                        or (item.get('assets') or [])!=recovery.get('empty_slots')):
                    raise ValueError('The empty upload recovery draft changed; review this same order.')
                reused_asset=None
                if recovery and recovery.get('asset_id'):
                    from prodigi_upload_recovery import reusable_asset
                    reused_asset=reusable_asset(provider,recovery['filename'],snap)
                    if reused_asset!=recovery['asset_id']:
                        raise ValueError('The verified library upload changed before recovery.')
                if replace:
                    from prodigi_reset import replacement_allowed
                    if not replacement_allowed(value,order,item):raise ValueError('Existing supplier artwork requires an explicit full Reset.')
                    if not reset_supported or not exact_item_supported:continue
                # Reset can follow an upload that never reached Save. Its empty
                # supplier slot is not replacement artwork, but the owner still
                # authorised clearing this exact unchanged worker editor.
                reset_empty=False
                if not replace and not sandbox and value.get('reset_authorisation'):
                    from prodigi_reset import replacement_allowed
                    if not replacement_allowed(value,order,item):
                        raise ValueError('The exact reset draft changed; review it before clearing its editor.')
                    if not exact_item_supported or not reset_supported:continue
                    reset_empty=True
                colour = (item.get('attributes') or {}).get('color','')
                matches = [i for i in order['items'] if i.get('sku') == item['sku'] and
                    (i.get('attributes') or {}).get('color','').casefold() == colour.casefold()]
                if len(matches) != 1 and not exact_item_supported:
                    raise ValueError('Identical supplier rows cannot be distinguished in the browser; review manually.')
                url, _ = link(snap)
                token = secrets.token_urlsafe(32)
                value.update(status='Browser uploading',message='Companion is uploading artwork. Payment and production remain manual.')
                filename=f'SC-{value["allocation_id"]}-{snap["job_id"][:16]}-{prep.digest(token)[:8]}.jpg'
                if reused_asset:filename=recovery['filename']
                value['browser'] = dict(token_hash=prep.digest(token), started=False,filename=filename,
                    before=business(order,item['id']),empty_slots=deepcopy(item.get('assets') or []), claimed_at=prep.now(), environment=provider.mode)
                if reused_asset:value['browser']['library_asset_id']=reused_asset
                save(cur,key,value)
                host = 'sandbox-beta-dashboard.pwinty.com' if sandbox else 'dashboard.prodigi.com'
                return dict(key=key,token=token,environment=provider.mode,order_id=value['order_id'],
                    item_id=value['item_id'],reference=order['merchantReference'],sku=item['sku'],colour=colour,
                    order_url=f'https://{host}/orders/{value["order_id"]}/detail',artwork_url=url,
                    sha256=snap['output']['sha256'],bytes=snap['output']['bytes'],dimensions=snap['dimensions'],
                    filename=filename,exact_item=exact_item_supported,
                    **({'fresh_empty_item':True} if recovery else {}),
                    **({'library_asset_id':reused_asset} if reused_asset else {}),
                    **({'selected_empty_product':True} if not sandbox and exact_item_supported and not replace
                       and (value.get('product_browser',{}).get('verified') is True or reset_empty) else {}),
                    **({'replace_artwork':True} if replace else {}))
            except Exception as error:
                value.update(status='Needs review',message=str(error) if isinstance(error,ValueError)
                    else 'Browser preparation could not be verified. No order was submitted.')
                save(cur,key,value)
        return None


def authorised(cur,key,token):
    value = read(cur,key)
    browser = value.get('browser') or {}
    if not hmac.compare_digest(browser.get('token_hash',''),prep.digest(token)):
        raise PermissionError('Orders handoff token rejected.')
    return value


def permit(key,token,sha256):
    provider,resolver,_,sandbox = context(key)
    with stages.edit(LOCK) as cur:
        value=authorised(cur,key,token)
        browser=value['browser']
        if browser['started'] or value['status']!='Browser uploading':
            raise ValueError('This Save permit has already been used. Recheck manually.')
        age=datetime.now(timezone.utc)-datetime.fromisoformat(browser['claimed_at'])
        if age.total_seconds()>900:
            raise ValueError('The browser handoff expired before Save.')
        snap,order,item=checked(value,provider,resolver,sandbox)
        if value.get('merge_pending'):
            from prodigi_consolidation import check_write
            check_write(value,provider,resolver)
        if sha256!=snap['output']['sha256']:
            raise ValueError('The companion did not verify this exact numbered JPG.')
        from prodigi_reset import replacement_allowed
        if ((has_existing_artwork(item) and not replacement_allowed(value,order,item)) or (item.get('assets') or [])!=browser.get('empty_slots',[])
                or business(order,item['id'])!=browser['before']):
            raise ValueError('The supplier order changed before Save.')
        if browser.get('library_asset_id'):
            from prodigi_upload_recovery import reusable_asset
            if reusable_asset(provider,browser['filename'],snap)!=browser['library_asset_id']:
                raise ValueError('The recovered library JPG changed before Save.')
        browser.update(started=True,save_permitted_at=prep.now(),companion_sha256=sha256)
        if value.get('reset_authorisation'):value['reset_authorisation']['used_at']=prep.now()
        save(cur,key,value)  # Commit before the browser is permitted to Save.
    return {'permitted':True}


def original_file(url,dimensions):
    """Prodigi's dashboard asset is a render URL containing its original source."""
    import re
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname!='productimagegenerator.services.prodigi.com' or parsed.path!='/render/':
        raise ValueError('The supplier print-image generator is not recognised.')
    query=parse_qs(parsed.query)
    if any(len(v)!=1 for v in query.values()):
        raise ValueError('Ambiguous supplier print-image settings.')
    params={k:v[0] for k,v in query.items()}
    fixed={'product_id':'edit','print_image':'true','format':'png','debug':'false',
           'rotate':'0','translate':'0,0','border':'0px','tile':'false'}
    if any(params.get(k)!=v for k,v in fixed.items()) or set(params)!=set(fixed)|{'image','scale','variant'}:
        raise ValueError('Supplier crop, rotation or border requires manual review.')
    match=re.fullmatch(r'cover:(\d+)x(\d+)',params['variant'])
    if not match or len(dimensions)!=2 or not all(type(n) is int and n>0 for n in dimensions):
        raise ValueError('Supplier output geometry is unavailable.')
    width,height=map(int,match.groups()); sw,sh=dimensions
    import math
    scale=float(params['scale'])
    expected=min(width/sw,height/sh)/max(width/sw,height/sh)
    if not math.isfinite(scale) or not 100<=width<=50000 or not 100<=height<=50000 or (width>height)!=(sw>sh) or abs(scale-expected)>0.0001:
        raise ValueError('Supplier placement is not the verified full-image fit.')
    source=urlsplit(params['image'])
    if source.scheme!='https' or source.hostname!='live-services.pwinty.com' or source.username or source.password or source.port not in (None,443):
        raise ValueError('Supplier original artwork source is not recognised.')
    return params['image']


def verify_file(url,output):
    import requests
    parsed=urlsplit(url)
    # Only supplier originals; never fetch a caller-supplied URL or redirect.
    host=parsed.hostname or ''
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443) or not (
        host.endswith('.blob.core.windows.net') or host=='live-services.pwinty.com'):
        raise ValueError('Supplier original-file location is not approved for verification.')
    response=requests.get(url,stream=True,timeout=(5,90),allow_redirects=False)
    if response.status_code==302 and host=='live-services.pwinty.com':
        target=response.headers.get('Location',''); response.close()
        parsed=urlsplit(target)
        if (parsed.scheme!='https' or not (parsed.hostname or '').endswith('.blob.core.windows.net')
            or parsed.username or parsed.password or parsed.port not in (None,443)):
            raise ValueError('Supplier original-file redirect is not approved.')
        response=requests.get(target,stream=True,timeout=(5,90),allow_redirects=False)
    with response:
        if response.status_code==404:
            return False  # The asset API sometimes reports an unavailable raw-original URL.
        if response.status_code!=200:
            raise ValueError('The supplier original artwork is not available for verification.')
        total=0; digest=hashlib.sha256()
        for block in response.iter_content(1024*1024):
            total+=len(block)
            if total>output['bytes']:
                raise ValueError('Supplier artwork bytes differ from this numbered JPG.')
            digest.update(block)
    if total!=output['bytes'] or digest.hexdigest()!=output['sha256']:
        raise ValueError('Supplier artwork does not match the exact archived numbered JPG.')
    return True


def verify_original(provider,source,filename,output,dimensions):
    # The list returns original bytes; GET asset returns its print transform.
    # Bind both through the immutable asset ID, never through a filename alone.
    wanted=urlsplit(source)
    candidates=[]
    for asset in provider.assets():
        if asset.get('name') not in (filename,filename.removesuffix('.jpg')):
            continue
        detail=provider.asset(asset['id']);actual=urlsplit(detail.get('url',''))
        if (actual.scheme,actual.hostname,actual.path)==(wanted.scheme,wanted.hostname,wanted.path):
            candidates.append(asset)
    if len(candidates)!=1:
        raise ValueError('The print image could not be bound to one original uploaded asset.')
    asset=candidates[0]
    if asset.get('sizeBytes')!=output['bytes'] or asset.get('mimeType')!='image/jpeg':
        raise ValueError('Supplier original-file metadata differs from the archived JPG.')
    dims=asset.get('dimensions') or {}
    if [dims.get('widthPx'),dims.get('heightPx')]!=dimensions:
        raise ValueError('Supplier uploaded-image dimensions differ from the archived JPG.')
    return str(asset['id']),bool(verify_file(asset['url'],output))


def finish(key,token,stage='readback',error=''):
    return _finish(key,lambda cur:authorised(cur,key,token),stage,error)


def recheck(user,key):
    """Staff can re-read an uncertain Save; this never issues another permit."""
    prep.require_user(user)
    def saved(cur):
        value=read(cur,key)
        if not (value.get('browser') or {}).get('started'):
            raise ValueError('No permitted Save exists to recheck.')
        return value
    return _finish(key,saved,'readback')


def resume_unstarted(user,key):
    """Retry only a proved untouched item; never repeat an uncertain Save."""
    prep.require_user(user)
    provider,resolver,_,sandbox=context(key)
    with stages.edit(LOCK) as cur:
        value=read(cur,key);receipt=value.get('browser') or {}
        if receipt.get('started') is not False or value.get('submission'):
            raise ValueError('Only an upload stopped before its Save permit can restart.')
        _,order,item=checked(value,provider,resolver,sandbox)
        if (has_existing_artwork(item) or (item.get('assets') or [])!=receipt.get('empty_slots',[])
                or business(order,item['id'])!=receipt['before']):
            raise ValueError('The supplier item changed. Preserve it and recheck instead of uploading again.')
        value.setdefault('browser_history',[]).append({k:receipt.get(k) for k in
            ('claimed_at','filename','started','last_stage')})
        value.pop('browser',None);value.pop('last_failure',None)
        value.update(status=WAITING,message='Verified no artwork Save occurred. Retrying this same product and numbered JPG.')
        value.setdefault('history',[]).append(dict(at=prep.now(),event='untouched_browser_upload_restarted'))
        save(cur,key,value)
        return value


def recover_selected_empty_editors(user,*,page_supported=False,processing_supported=False):
    """Recover this known pre-permit handoff bug, never uncertain supplier writes.

    Called only by companions advertising the empty-editor transition fix.
    resume_unstarted independently checks fresh source, empty assets and the full
    pinned supplier business state before removing an unused upload intent.
    """
    prep.require_user(user)
    from companion_poll_transaction import connection
    with connection(prep.connect) as conn,conn.cursor() as cur:
        cur.execute("""SELECT key FROM app_settings WHERE key LIKE 'prodigi_prepare:%%'
            AND (value->>'status'='Needs review' OR (%s AND value->>'status'='Browser uploading'
                 AND (value->'browser'->>'claimed_at')::timestamptz<now()-interval '5 minutes'))
            AND value->'browser'->>'started'='false'
            AND ((value->'browser'->>'last_stage'='page'
                  AND value->'browser'->>'client_error'='An existing editor requires manual review.'
                  AND value->'product_browser'->>'verified'='true')
              OR (value->'browser'->>'last_stage' IN ('signin','readiness')
                  AND value->'browser'->>'client_error' IN ('Sign into Prodigi in Edge, then review the same draft.',
                    'The exact Prodigi order page did not become ready; check its loading or sign-in state.')
                  AND (COALESCE((value->>'readiness_recoveries')::int,0)<1
                    OR (%s AND COALESCE(value->>'readiness_recovery_policy','')<>'fresh-owned-context-v1'))
                  AND (value->'product_browser'->>'verified'='true' OR value ? 'reset_authorisation'))
              OR (%s AND value->>'status'='Browser uploading'
                  AND (value->'product_browser'->>'verified'='true' OR value ? 'reset_authorisation')
                  AND COALESCE(value->>'readiness_recovery_policy','')<>'fresh-owned-context-v1')
              OR (%s AND value->'browser'->>'last_stage'='permit'
                  AND value->>'message' LIKE 'Prodigi returned HTTP 429;%%'
                  AND COALESCE((value->>'api_rate_recoveries')::int,0)<1
                  AND COALESCE((value->>'api_rate_retry_at')::timestamptz,'epoch')<now()
                  AND (value->'product_browser'->>'verified'='true' OR value ? 'reset_authorisation'))
              OR (%s AND value->'browser'->>'last_stage'='uploaded'
                  AND value->'browser'->>'client_error'='The expected Prodigi control did not finish loading.'
                  AND COALESCE((value->>'processing_recoveries')::int,0)<1
                  AND (value->'product_browser'->>'verified'='true' OR value ? 'reset_authorisation')))
            AND NOT value ? 'submission'
            AND NOT COALESCE((value->>'hidden')::boolean,false)
            ORDER BY updated_at LIMIT 2""",(page_supported,page_supported,page_supported,page_supported,processing_supported))
        keys=[row['key'] for row in cur.fetchall()]
    recovered=recover_saved_uploads(user)
    for key in keys:
        try:
            recovered+=bool(_recover_ready_editor(user,key,page_supported=page_supported,processing_supported=processing_supported))
        except (ValueError,PermissionError):
            pass  # Changed artwork/address/source stays stopped for review.
    if recovered:
        import logging
        logging.getLogger(__name__).info('ORDERS_EMPTY_EDITOR_RECOVERY resumed=%d',recovered)
    return recovered


def saved_readback_candidate(value):
    """One read-only retry for a saved upload, never a new supplier permit."""
    receipt=value.get('browser') or {}
    if (value.get('status')!='Needs review' or receipt.get('started') is not True
            or receipt.get('last_stage')!='save' or value.get('saved_readback_recoveries',0)>=1
            or value.get('submission') or value.get('hidden')):return False
    if receipt.get('client_error')=='The expected Prodigi control did not finish loading.':return True
    import re
    paths=receipt.get('readback_changed_fields')
    return bool(isinstance(paths,list) and paths and all(isinstance(path,str) and
        re.fullmatch(r'items\[\d+\]\.(?:unitPrice|lineTotal|assets|sizing)(?:[.\[].*)?',path) for path in paths))


def recover_saved_uploads(user):
    """Reconcile a timed-out Save once using persisted proof; never issue a write."""
    prep.require_user(user)
    from companion_poll_transaction import connection
    with connection(prep.connect) as conn,conn.cursor() as cur:
        cur.execute("""SELECT key,value FROM app_settings WHERE key LIKE 'prodigi_prepare:%%'
          AND value->>'status'='Needs review' AND value->'browser'->>'started'='true'
          AND value->'browser'->>'last_stage'='save'
          AND COALESCE((value->>'saved_readback_recoveries')::int,0)<1
          AND NOT value ? 'submission' AND NOT COALESCE((value->>'hidden')::boolean,false)
          ORDER BY updated_at LIMIT 20""")
        keys=[row['key'] for row in cur.fetchall() if saved_readback_candidate(row['value'])][:2]
    recovered=0
    for key in keys:
        def receipt(q):
            value=read(q,key);b=value.get('browser') or {}
            if not saved_readback_candidate(value):
                raise PermissionError('Saved artwork recovery is unavailable.')
            value['saved_readback_recoveries']=1
            return value
        result=_finish(key,receipt,'readback')
        recovered+=result.get('status') not in ('Needs review','Handoff unavailable')
    return recovered


@stages.stale_result(False)
def _recover_ready_editor(user,key,*,page_supported=False,processing_supported=False):
    provider,resolver,_,sandbox=context(key)
    with stages.edit(LOCK) as q:
        value=read(q,key);receipt=value.get('browser') or {}
        stalled=False
        if page_supported and value.get('status')=='Browser uploading' and value.get('readiness_recovery_policy')!=READINESS_POLICY:
            try:
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(receipt['claimed_at'])).total_seconds()
                q.execute('SELECT key,value FROM app_settings WHERE key=%s',('orders_runtime:'+str(value['allocation_id']),))
                seen=q.fetchone();seen=seen['value'] if seen else {}
                stale=(datetime.now(timezone.utc)-datetime.fromisoformat(seen['seen_at'])).total_seconds()>90
                stalled=age>300 and stale and seen.get('claim')==receipt.get('token_hash')
            except (KeyError,TypeError,ValueError):pass
        if (value.get('status')!='Needs review' and not stalled) or receipt.get('started') is not False or value.get('submission'):return False
        rate_wait=(page_supported and receipt.get('last_stage')=='permit'
                   and value.get('message','').startswith('Prodigi returned HTTP 429;')
                   and value.get('api_rate_recoveries',0)<1)
        processing_wait=(processing_supported and receipt.get('last_stage')=='uploaded'
                         and receipt.get('client_error')=='The expected Prodigi control did not finish loading.'
                         and value.get('processing_recoveries',0)<1)
        readiness=stalled or receipt.get('last_stage') in ('signin','readiness') and receipt.get('client_error') in (
            'Sign into Prodigi in Edge, then review the same draft.',
            'The exact Prodigi order page did not become ready; check its loading or sign-in state.')
        if readiness:
            attempts=value.get('readiness_recoveries',0)
            if page_supported and value.get('readiness_recovery_policy')!=READINESS_POLICY:attempts=0
            if attempts>=1:return False
            _,order,item=checked(value,provider,resolver,sandbox)
            from prodigi_reset import replacement_allowed
            if not ((value.get('product_browser') or {}).get('verified') is True or replacement_allowed(value,order,item)):return False
        elif rate_wait or processing_wait:
            if value.get('api_rate_retry_at') and datetime.fromisoformat(value['api_rate_retry_at'])>datetime.now(timezone.utc):return False
            _,order,item=checked(value,provider,resolver,sandbox)
            from prodigi_reset import replacement_allowed
            if not ((value.get('product_browser') or {}).get('verified') is True or replacement_allowed(value,order,item)):return False
        elif not (receipt.get('last_stage')=='page' and receipt.get('client_error')=='An existing editor requires manual review.'
                  and (value.get('product_browser') or {}).get('verified') is True):return False
        # Nested stage would lose the outer observation. Perform its exact checks here.
        _,order,item=checked(value,provider,resolver,sandbox)
        if (has_existing_artwork(item) or (item.get('assets') or [])!=receipt.get('empty_slots',[])
            or business(order,item['id'])!=receipt.get('before')):return False
        value.setdefault('browser_history',[]).append({k:receipt.get(k) for k in ('claimed_at','filename','started','last_stage')})
        if rate_wait:value['api_rate_recoveries']=value.get('api_rate_recoveries',0)+1
        if processing_wait:value['processing_recoveries']=value.get('processing_recoveries',0)+1
        if readiness:
            value['readiness_recoveries']=attempts+1
            if page_supported:value['readiness_recovery_policy']=READINESS_POLICY
        value.pop('browser',None);value.pop('last_failure',None)
        value.update(status=WAITING,message='Retrying the unchanged empty item in a fresh companion page; no Save was repeated.')
        save(q,key,value)
        return True


@stages.stale_result({'status':'Handoff unavailable'})
def _finish(key,read_receipt,stage,client_error=''):
    provider,resolver,_,sandbox=context(key)
    with stages.edit(LOCK) as cur:
        try:
            value=read_receipt(cur)
        except (ValueError,PermissionError):
            # A removed/superseded receipt must not wedge the desktop queue.
            # This performs no supplier read/write and never grants Save.
            return {'status':'Handoff unavailable'}
        value['browser']['last_stage']=stage
        if client_error:value['browser']['client_error']=str(client_error)[:240]
        if value['browser'].get('verified'):
            return {'status':value['status']}
        try:
            snap,order,item=checked(value,provider,resolver,sandbox)
            # Saving the first artwork makes Prodigi calculate target-item prices.
            # Pre-Save checks stay strict; charges and every other item stay pinned.
            before=value['browser']['before']
            if not sandbox:
                before,verified=verified_sibling_baseline(cur,value,order,item['id'],provider,resolver)
                if verified:value['browser']['verified_sibling_items']=verified
            current_business=business(order,item['id'],after_save=True,before=before)
            expected_business=business(before,item['id'],after_save=True)
            if not value['browser']['started'] or current_business!=expected_business:
                from prodigi_product_browser import changed_fields
                value['browser']['readback_changed_fields']=changed_fields(expected_business,current_business)
                raise ValueError('Supplier order changed or Save was not permitted. Review this exact draft.')
            if value['browser'].get('companion_sha256')!=snap['output']['sha256']:
                raise ValueError('The paired companion source checksum was not confirmed.')
            assets=item.get('assets') or []
            if len(assets)!=1 or assets[0].get('printArea')!='default':
                raise ValueError('Browser upload is not confirmed. No automatic retry will occur.')
            asset_id,raw_verified=verify_original(provider,original_file(assets[0]['url'],snap['dimensions']),
                value['browser']['filename'],snap['output'],snap['dimensions'])
            # A second read catches concurrent edits during the byte download.
            _,latest,current=checked(value,provider,resolver,sandbox)
            if latest!=order:
                # Download status may progress independently; artwork and business must not change.
                if (business(latest,item['id'],after_save=True)!=business(order,item['id'],after_save=True) or
                    [a.get('url') for a in current.get('assets',[])]!=[assets[0]['url']]):
                    raise ValueError('Supplier artwork/order changed during verification.')
            from prodigi_qa import evaluate
            url_hash=prep.digest(assets[0]['url']); qa=evaluate(snap,latest,current,url_hash)
            qa.update(companion_source_sha256_verified=True,supplier_original_bytes_verified=raw_verified,
                supplier_asset_identity_verified=True,supplier_full_image_fit_verified=True)
            value.update(write_intent=True,url_hash=url_hash,checks=qa['checks'],qa=qa,
                status='Ready for manual payment' if all(qa['checks'].values()) else 'Needs QA',
                message='Companion verified the numbered JPG checksum; supplier product, uploaded asset and full-image fit verified. '+
                    ('Payment and production remain manual.' if not qa['blockers'] else ' '.join(qa['blockers'])))
            value['browser'].update(verified=True,verified_at=prep.now(),
                original_sha256=snap['output']['sha256'],original_asset_id=asset_id,
                supplier_original_bytes_verified=raw_verified,full_image_fit_verified=True)
            value.pop('last_failure',None)
            from prodigi_full_qa import enabled,live_enabled
            if enabled() and (sandbox or live_enabled()):
                if sandbox:
                    value.update(status='Checking QA',message='Artwork saved. Checking production evidence, certificate and packing slip.')
                else:
                    from prodigi_dashboard_qa import enqueue
                    enqueue(value,provider,resolver,lambda _:None,verified_order=latest)
            if sandbox:
                value.update(sandbox_unpaid_verified=True,artwork_readback_verified=True)
        except Exception as error:
            value.update(status='Needs review',message=str(error) if isinstance(error,ValueError)
                else 'Supplier artwork could not be verified. Review the exact draft; no automatic retry.')
            retry_after=getattr(error,'retry_after',None)
            if isinstance(retry_after,(int,float)) and 0<=retry_after<86400:
                value['api_rate_retry_at']=(datetime.now(timezone.utc)+timedelta(seconds=max(5,retry_after))).isoformat()
            value['message']+=' Browser stage: '+stage+'.'
            if client_error:value['message']+=' '+str(client_error)[:240]
            prep.record_failure(value,'artwork.'+stage,value['message'],type(error).__name__)
        save(cur,key,value)
    return {'status':value['status']}
