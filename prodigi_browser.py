"""Guarded browser upload handoff. Supplier API access here is read-only.

An authenticated desktop receives one pinned JPG and one exact draft. A durable
permit precedes Save, carrying the pinned SHA256 verified in both extension
contexts. Completion binds the supplier render to its uploaded asset metadata,
verifies placement and compares original bytes when the supplier exposes them.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import hmac
import json
import secrets
from urllib.parse import urlsplit,parse_qs

import prodigi_preparation as prep
from prodigi_client import Client

LOCK = 19721124
WAITING = 'Awaiting browser upload'


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
    cur.execute('SELECT value FROM app_settings WHERE key=%s', (key,))
    row = cur.fetchone()
    if not row or row['value'].get('hidden'):
        raise ValueError('This Orders handoff is unavailable.')
    return row['value']


def save(cur, key, value):
    value['updated_at'] = prep.now()
    cur.execute('''UPDATE app_settings SET value=%s::jsonb,updated_at=now()
        WHERE key=%s AND NOT COALESCE((value->>'hidden')::boolean,false) RETURNING key''',
        (json.dumps(value), key))
    if not cur.fetchone():
        raise ValueError('This handoff was removed.')


def snapshot(value, resolver, sandbox):
    source = resolver(value['allocation_id'])
    expected = value['source_snapshot'] if sandbox else value['snapshot']
    if prep.digest(source) != prep.digest(expected):
        raise ValueError('The allocated artwork or Fulfilment mapping changed.')
    return value['snapshot']


def business(order, target, *, after_save=False):
    """Pin everything except this item's artwork and its editor sizing."""
    result = {k:deepcopy(order.get(k)) for k in
        ('id','merchantReference','recipient','shippingMethod','branding','packingSlip','charges')}
    result['items'] = []
    for item in order.get('items', []):
        result['items'].append({k:deepcopy(v) for k,v in item.items()
            if k not in ('status','productionTime') and
            (str(item['id']) != str(target) or k not in
             (('assets','sizing','unitPrice','lineTotal') if after_save else ('assets','sizing')))})
    return result


def checked(value, provider, resolver, sandbox):
    snap = snapshot(value, resolver, sandbox)
    order = provider.order(value['order_id'])
    item = prep.validate_order(order, snap, value['order_id'], value['item_id'])
    if order.get('charges'):
        raise ValueError('This order has charges; browser preparation stopped.')
    return snap, order, item


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


def claim():
    import os
    with prep.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_try_advisory_xact_lock(%s) AS acquired', (LOCK,))
        if not cur.fetchone()['acquired']:
            return None
        cur.execute('''SELECT key,value FROM app_settings WHERE
            (key LIKE 'prodigi_prepare:%%' OR key LIKE 'prodigi_sandbox_test:%%')
            AND (key LIKE 'prodigi_prepare:%%' OR %s)
            AND value->>'status'=%s AND NOT COALESCE((value->>'hidden')::boolean,false)
            ORDER BY updated_at LIMIT 20''', (os.getenv('SPORTS_CAVE_PRODIGI_SANDBOX_ENABLED','').lower()=='true',WAITING))
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
            try:
                snap, order, item = checked(value, provider, resolver, sandbox)
                if has_existing_artwork(item):
                    raise ValueError('Existing supplier artwork requires manual preservation.')
                colour = (item.get('attributes') or {}).get('color','')
                matches = [i for i in order['items'] if i.get('sku') == item['sku'] and
                    (i.get('attributes') or {}).get('color','').casefold() == colour.casefold()]
                if len(matches) != 1:
                    raise ValueError('Identical supplier rows cannot be distinguished in the browser; review manually.')
                url, _ = link(snap)
                token = secrets.token_urlsafe(32)
                value.update(status='Browser uploading',message='Companion is uploading artwork. Payment and production remain manual.')
                filename=f'SC-{value["allocation_id"]}-{snap["job_id"][:16]}-{prep.digest(token)[:8]}.jpg'
                value['browser'] = dict(token_hash=prep.digest(token), started=False,filename=filename,
                    before=business(order,item['id']),empty_slots=deepcopy(item.get('assets') or []), claimed_at=prep.now(), environment=provider.mode)
                save(cur,key,value)
                host = 'sandbox-beta-dashboard.pwinty.com' if sandbox else 'dashboard.prodigi.com'
                return dict(key=key,token=token,environment=provider.mode,order_id=value['order_id'],
                    item_id=value['item_id'],reference=order['merchantReference'],sku=item['sku'],colour=colour,
                    order_url=f'https://{host}/orders/{value["order_id"]}/detail',artwork_url=url,
                    sha256=snap['output']['sha256'],bytes=snap['output']['bytes'],dimensions=snap['dimensions'],
                    filename=filename)
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
    with prep.connect() as conn,conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK,))
        value=authorised(cur,key,token)
        browser=value['browser']
        if browser['started'] or value['status']!='Browser uploading':
            raise ValueError('This Save permit has already been used. Recheck manually.')
        age=datetime.now(timezone.utc)-datetime.fromisoformat(browser['claimed_at'])
        if age.total_seconds()>900:
            raise ValueError('The browser handoff expired before Save.')
        snap,order,item=checked(value,provider,resolver,sandbox)
        if sha256!=snap['output']['sha256']:
            raise ValueError('The companion did not verify this exact numbered JPG.')
        if (has_existing_artwork(item) or (item.get('assets') or [])!=browser.get('empty_slots',[])
                or business(order,item['id'])!=browser['before']):
            raise ValueError('The supplier order changed before Save.')
        browser.update(started=True,save_permitted_at=prep.now(),companion_sha256=sha256)
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


def finish(key,token,stage='readback'):
    return _finish(key,lambda cur:authorised(cur,key,token),stage)


def recheck(user,key):
    """Staff can re-read an uncertain Save; this never issues another permit."""
    prep.require_user(user)
    def saved(cur):
        value=read(cur,key)
        if not (value.get('browser') or {}).get('started'):
            raise ValueError('No permitted Save exists to recheck.')
        return value
    return _finish(key,saved,'readback')


def _finish(key,read_receipt,stage):
    provider,resolver,_,sandbox=context(key)
    with prep.connect() as conn,conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(%s)',(LOCK,))
        cur.execute("SET LOCAL idle_in_transaction_session_timeout = '0'")
        try:
            value=read_receipt(cur)
        except (ValueError,PermissionError):
            # A removed/superseded receipt must not wedge the desktop queue.
            # This performs no supplier read/write and never grants Save.
            return {'status':'Handoff unavailable'}
        value['browser']['last_stage']=stage
        if value['browser'].get('verified'):
            return {'status':value['status']}
        try:
            snap,order,item=checked(value,provider,resolver,sandbox)
            # Saving the first artwork makes Prodigi calculate target-item prices.
            # Pre-Save checks stay strict; charges and every other item stay pinned.
            if not value['browser']['started'] or business(order,item['id'],after_save=True)!=business(value['browser']['before'],item['id'],after_save=True):
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
            from prodigi_full_qa import enabled,live_enabled
            if enabled() and (sandbox or live_enabled()):
                value.update(status='Checking QA',message='Artwork saved. Checking production evidence, certificate and packing slip.')
            if sandbox:
                value.update(sandbox_unpaid_verified=True,artwork_readback_verified=True)
        except Exception as error:
            value.update(status='Needs review',message=str(error) if isinstance(error,ValueError)
                else 'Supplier artwork could not be verified. Review the exact draft; no automatic retry.')
            value['message']+=' Browser stage: '+stage+'.'
            prep.record_failure(value,'artwork.'+stage,value['message'],type(error).__name__)
        save(cur,key,value)
    return {'status':value['status']}
