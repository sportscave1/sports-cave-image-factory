"""Owner-requested full reset of an existing unpaid draft, without deleting it.

Old receipts are archived, tokens retired, and one exact artwork replacement is
authorised. The supplier keeps its existing image until the browser saves the
replacement. A committed/uncertain Save must be reconciled before reset.
"""
from copy import deepcopy
import json
import uuid
import prodigi_preparation as prep
import prodigi_browser as browser


def reset_order(user,allocation_id):
    prep.require_user(user)
    if not prep.enabled():raise ValueError('Orders preparation is paused.')
    aid=int(allocation_id)
    old=prep.read(aid)
    if old and old.get('merge_pending'):
        raise ValueError('This order is being consolidated. Review its merge receipt before any Reset; the original supplier order has been preserved.')
    if not old:return prep.request(user,aid)
    if old.get('submission') or old.get('status') in ('Complete','Certificate pending','Submitted','Submitting','Submission uncertain'):
        raise ValueError('This order already has a submission intent. Reset cannot change submitted or production orders.')
    receipt=old.get('browser') or {}
    if receipt.get('started') and not receipt.get('verified'):
        # Readback only. Do not revoke a Save that might still be in flight.
        if old.get('status')=='Browser uploading':raise ValueError('An artwork Save is in progress. Wait for its result before Reset.')
        browser.recheck(user,prep.PREFIX+str(aid))
        old=prep.read(aid)
        if not (old.get('browser') or {}).get('verified'):
            raise ValueError('The previous Save is uncertain. Its exact artwork must be verified before a full Reset.')
    product=old.get('product_browser') or {}
    if product.get('started') and not product.get('verified'):
        if old.get('status')=='Selecting product':raise ValueError('Product selection is in progress. Wait for its result before Reset.')
        from prodigi_product_browser import recheck
        recheck(user,prep.PREFIX+str(aid),allow_expired_blank=True);old=prep.read(aid)
        if old.get('product_browser') and not old['product_browser'].get('verified'):
            raise ValueError('The previous product selection is uncertain; it must be verified before Reset.')
    fresh,preparing=prep.preparation_snapshot(user,aid)
    from prodigi_submission import LOCK as submission_lock
    with prep.connect() as c,c.cursor() as q:
        # Submission cannot reserve a new intent while reset is being committed.
        q.execute('SELECT pg_advisory_xact_lock(%s)',(submission_lock,))
        q.execute('SELECT pg_advisory_xact_lock(%s)',(prep.LOCK,))
        q.execute('SELECT pg_advisory_xact_lock(%s)',(browser.LOCK,))
        current=browser.read(q,prep.PREFIX+str(aid))
        if current.get('submission') or current.get('certificate_url'):
            raise ValueError('Submission or certificate completion started. Reset is blocked.')
        # A repeated click/HTTP retry returns the same newly queued generation.
        if current.get('reset_generation') and current['status'] in ('Queued','Preparing JPG','Awaiting browser upload','Awaiting product selection') and not current.get('browser'):
            return current
        if current.get('updated_at')!=old.get('updated_at'):
            raise ValueError('The worker advanced this order. Refresh its status before Reset.')
        oid,iid=current.get('order_id'),current.get('item_id')
        authorisation=None
        if oid or iid:
            if not oid or not iid:raise ValueError('The supplier item identity is incomplete; review it before Reset.')
            q.execute('SELECT 1 FROM app_settings WHERE key=%s',('prodigi_submit_order:'+oid,))
            if q.fetchone():raise ValueError('This supplier order already has a submission intent; Reset is blocked.')
            provider=prep.Client();order=provider.order(oid)
            # A pending JPG has no full mapping yet; the last verified source
            # still pins the existing item. Fresh mapping is rechecked on upload.
            snap=fresh if not preparing else current['snapshot']
            item=prep.validate_order(order,snap,oid,iid,allow_unselected=True)
            if order.get('charges') or order.get('shipments') or any(h.get('status') in ('in_production','partially_shipped','shipped','completed') for h in order.get('statusHistory') or []):
                raise ValueError('A charged or production order cannot be reset.')
            authorisation=dict(order_id=oid,item_id=iid,before=browser.business(order,iid),assets=deepcopy(item.get('assets') or []))
        generation=str(uuid.uuid4())
        q.execute('INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now())',
            ('prodigi_reset_history:'+str(aid)+':'+generation,json.dumps(current)))
        value=dict(allocation_id=aid,order_id=oid or '',item_id=iid or '',snapshot=fresh,fingerprint=prep.digest(fresh),
            requester=str(user['id']),browser_requested=True,checks={},status='Preparing JPG' if preparing else 'Queued',
            message='Reset queued. Starting product verification, artwork upload and all QA again.',
            reset_generation=generation,history=current.get('history',[])[-20:]+[dict(at=prep.now(),event='full_reset',actor=str(user['id']),generation=generation)])
        if authorisation:value['reset_authorisation']=dict(**authorisation,generation=generation)
        # Retire a grouped QA token on siblings too. A late finish cannot restore
        # an old result over this reset, and all items must pass the next batch.
        if oid:
            q.execute("SELECT value FROM app_settings WHERE key LIKE 'prodigi_prepare:%%' AND value->>'order_id'=%s",(oid,))
            for row in q.fetchall():
                sibling=row['value']
                if sibling['allocation_id']==aid or sibling.get('submission'):continue
                previous=sibling.pop('dashboard_qa',None)
                if previous:
                    sibling.setdefault('dashboard_qa_history',[]).append({k:previous.get(k) for k in ('policy','checked_at','claimed_at','verified')})
                    sibling['checks']={}
                    if (sibling.get('browser') or {}).get('verified'):
                        sibling.update(status='Checking QA',message='Waiting for the reset sibling before fresh whole-order QA.')
                    prep.save(q,sibling)
        prep.save(q,value)
        q.execute("UPDATE app_settings SET value=value || %s::jsonb,updated_at=now() WHERE key=%s",
            (json.dumps(dict(active=False,resolved_at=prep.now())),prep.FAILURE_PREFIX+str(aid)))
        return value


def replacement_allowed(value,order,item):
    proof=value.get('reset_authorisation') or {}
    return bool(proof and proof.get('generation')==value.get('reset_generation') and not proof.get('used_at')
        and proof.get('order_id')==str(order.get('id')) and proof.get('item_id')==str(item.get('id'))
        and proof.get('assets')==(item.get('assets') or []) and proof.get('before')==browser.business(order,item['id']))
