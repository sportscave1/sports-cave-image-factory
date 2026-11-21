"""Single-use companion upload for certificate packing slips; never Submit."""
from datetime import datetime,timezone
import hmac,secrets,os
from urllib.parse import urlsplit
import prodigi_browser as browser
import prodigi_preparation as prep

WAITING='Awaiting certificate browser'
ACTIVE='Certificate browser uploading'


def unpack(key):
    if not key.startswith('document:'):raise ValueError('Unknown certificate handoff.')
    raw=key.removeprefix('document:')
    return raw,browser.context(raw)


def current(value,provider,resolver,sandbox):
    from prodigi_full_qa import same_order,enabled,live_enabled
    if not enabled() or (not sandbox and not live_enabled()):raise ValueError('Automatic certificate upload is paused.')
    snap,order,item=browser.checked(value,provider,resolver,sandbox)
    if not (value.get('browser') or {}).get('verified'):raise ValueError('Verify saved artwork first.')
    if len(order.get('items',[]))!=1 or item.get('quantity')!=1:raise ValueError('One numbered item is required.')
    if prep.digest((item.get('assets') or [{}])[0].get('url'))!=value.get('url_hash'):
        raise ValueError('Saved artwork changed.')
    if value.get('document_before') and not same_order(value['document_before'],order):
        raise ValueError('Supplier order changed during certificate preparation.')
    return snap,order,item


def claim():
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT pg_try_advisory_xact_lock(%s) AS acquired',(browser.LOCK,))
        if not q.fetchone()['acquired']:return None
        q.execute("""SELECT key,value FROM app_settings WHERE
            (key LIKE 'prodigi_prepare:%%' OR key LIKE 'prodigi_sandbox_test:%%')
            AND (key LIKE 'prodigi_prepare:%%' OR %s)
            AND value->>'status'=%s AND NOT COALESCE((value->>'hidden')::boolean,false)
            ORDER BY updated_at LIMIT 1""",(os.getenv('SPORTS_CAVE_PRODIGI_SANDBOX_ENABLED','').lower()=='true',WAITING));row=q.fetchone()
        if not row:return None
        key,value=row['key'],row['value']
        if key.startswith('prodigi_sandbox_test:'):
            if os.getenv('SPORTS_CAVE_PRODIGI_SANDBOX_ENABLED','').lower()!='true':return None
        if value.get('document_browser'):return None
        try:
            provider,resolver,_,sandbox=browser.context(key)
            snap,order,item=current(value,provider,resolver,sandbox)
            if (order.get('packingSlip') or {}).get('url'):
                raise ValueError('An existing packing slip requires preservation and review.')
            document=value['document'];token=secrets.token_urlsafe(32)
            filename=f'SC-{value["allocation_id"]}-certificate-{document["output"]["sha256"][:16]}.pdf'
            value['document_browser']=dict(token_hash=prep.digest(token),started=False,filename=filename,
                claimed_at=prep.now(),before=order)
            value.update(status=ACTIVE,message='Companion is attaching the exact certificate. Payment and Submit remain manual.')
            browser.save(q,key,value)
            host='sandbox-beta-dashboard.pwinty.com' if sandbox else 'dashboard.prodigi.com'
            return dict(kind='certificate',key='document:'+key,token=token,environment=provider.mode,
                order_id=value['order_id'],reference=order['merchantReference'],sku=item['sku'],
                colour=(item.get('attributes') or {}).get('color',''),
                order_url=f'https://{host}/orders/{value["order_id"]}/detail',artwork_url=document['url'],
                sha256=document['output']['sha256'],bytes=document['output']['bytes'],filename=filename)
        except ValueError as error:
            value.update(status='Needs review',message=str(error));browser.save(q,key,value)


def authorised(q,key,token):
    value=browser.read(q,key);receipt=value.get('document_browser') or {}
    if not hmac.compare_digest(receipt.get('token_hash',''),prep.digest(token)):
        raise PermissionError('Certificate handoff token rejected.')
    return value


def permit(key,token,sha256):
    raw,(provider,resolver,_,sandbox)=unpack(key)
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT pg_advisory_xact_lock(%s)',(browser.LOCK,))
        value=authorised(q,raw,token);receipt=value['document_browser']
        if receipt.get('started') or value['status']!=ACTIVE:raise ValueError('Certificate upload permit already used.')
        if (datetime.now(timezone.utc)-datetime.fromisoformat(receipt['claimed_at'])).total_seconds()>900:
            raise ValueError('Certificate handoff expired.')
        _,order,_=current(value,provider,resolver,sandbox)
        if order.get('packingSlip') or not __import__('prodigi_full_qa').same_order(receipt['before'],order):
            raise ValueError('Supplier order changed before certificate upload.')
        if sha256!=value['document']['output']['sha256']:raise ValueError('Certificate checksum differs.')
        receipt.update(started=True,companion_sha256=sha256,permitted_at=prep.now())
        browser.save(q,raw,value)
    return {'permitted':True}


def verify(provider,value,order):
    receipt=value['document_browser'];output=value['document']['output']
    if not receipt.get('started') or receipt.get('companion_sha256')!=output['sha256']:
        raise ValueError('Exact certificate upload permit/checksum is missing.')
    slip=order.get('packingSlip') or {};wanted=urlsplit(slip.get('url',''))
    if wanted.scheme!='https' or wanted.hostname!='live-services.pwinty.com':
        raise ValueError('Supplier certificate attachment is not confirmed. No automatic retry.')
    candidates=[]
    for asset in provider.assets():
        if asset.get('name') not in (receipt['filename'],receipt['filename'].removesuffix('.pdf')):continue
        detail=provider.asset(asset['id']);actual=urlsplit(detail.get('url',''))
        if (actual.scheme,actual.hostname,actual.path)==(wanted.scheme,wanted.hostname,wanted.path):candidates.append(asset)
    if len(candidates)!=1:raise ValueError('Certificate is not bound to one exact supplier asset.')
    asset=candidates[0]
    if asset.get('sizeBytes')!=output['bytes'] or asset.get('mimeType')!='application/pdf':
        raise ValueError('Supplier certificate metadata differs from the archived PDF.')
    raw=browser.verify_file(asset['url'],output)
    return dict(verified=True,verified_at=prep.now(),supplier_url=slip['url'],asset_id=str(asset['id']),
        sha256=output['sha256'],supplier_original_bytes_verified=bool(raw))


def finish(key,token,stage='readback'):
    raw,(provider,resolver,_,sandbox)=unpack(key)
    return _finish(raw,provider,resolver,sandbox,lambda q:authorised(q,raw,token),stage)


def recheck(user,key):
    prep.require_user(user)
    provider,resolver,_,sandbox=browser.context(key)
    def read(q):
        value=browser.read(q,key)
        if not (value.get('document_browser') or {}).get('started'):
            raise ValueError('No permitted certificate upload exists to recheck.')
        return value
    return _finish(key,provider,resolver,sandbox,read,'readback')


def resume_unstarted(user,key):
    """Explicit staff retry before any upload permit; never resets a used permit."""
    prep.require_user(user)
    provider,resolver,_,sandbox=browser.context(key)
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT pg_advisory_xact_lock(%s)',(browser.LOCK,))
        q.execute('SELECT value FROM app_settings WHERE key=%s',(key,));row=q.fetchone()
        if not row:raise ValueError('Certificate handoff not found.')
        value=row['value'];receipt=value.get('document_browser') or {}
        if value.get('hidden'):raise ValueError('This preparation was removed.')
        if value.get('status')!='Needs review' or receipt.get('started') is not False or receipt.get('verified'):
            raise ValueError('Only a stopped, unused certificate permit can receive a new handoff.')
        _,order,_=current(value,provider,resolver,sandbox)
        if (order.get('packingSlip') or {}).get('url'):raise ValueError('An existing packing slip requires preservation and review.')
        value.setdefault('certificate_attempts',[]).append(dict(claimed_at=receipt.get('claimed_at'),
            stopped_before_permit=True,rechecked_at=prep.now(),actor=str(user['id'])))
        value.pop('document_browser')
        value.update(hidden=False,status=WAITING,message='Staff rechecked this unchanged draft. Waiting for a fresh certificate handoff; no upload permit was previously issued.')
        browser.save(q,key,value)
    return {'status':WAITING}


def _finish(raw,provider,resolver,sandbox,read,stage):
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT pg_advisory_xact_lock(%s)',(browser.LOCK,))
        q.execute("SET LOCAL idle_in_transaction_session_timeout = '0'")
        try:value=read(q)
        except (ValueError,PermissionError):return {'status':'Handoff unavailable'}
        if value['document_browser'].get('verified'):return {'status':value['status']}
        try:
            _,order,_=current(value,provider,resolver,sandbox)
            proof=verify(provider,value,order)
            _,latest,_=current(value,provider,resolver,sandbox)
            if (latest.get('packingSlip') or {}).get('url')!=proof['supplier_url']:
                raise ValueError('Certificate changed during verification.')
            value['document_browser'].update(proof)
            value.update(status='Checking QA',message='Certificate attached. Checking every QA answer together.')
        except Exception as error:
            value.update(status='Needs review',message=(str(error) if isinstance(error,ValueError)
                else 'Certificate verification is unavailable. Recheck this exact draft; no automatic retry.')+' Certificate stage: '+stage+'.')
            prep.record_failure(value,'certificate.'+stage,value['message'],type(error).__name__)
        browser.save(q,raw,value)
    return {'status':value['status']}
