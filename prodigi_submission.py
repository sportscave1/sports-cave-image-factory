"""QA-gated submission of existing orders; durable intent forbids repeat submits.

Disabled until an owner activates it in the OS. Supplier delay settings belong
to Prodigi. No create, resume, payment-setting or artwork-update API is used.
"""
import json
import threading
from datetime import datetime, timezone, timedelta
import prodigi_preparation as prep

SETTING='orders_submit_after_qa'
LOCK=19721129
ACCEPTED={'submitted','paused','on_hold','in_production','partially_shipped','shipped','completed'}
FINALISED={'in_production','partially_shipped','shipped','completed'}
_gate=threading.Lock()

class StaleQA(ValueError):pass


def setting():
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT value FROM app_settings WHERE key=%s',(SETTING,))
        row=q.fetchone()
    return row['value'] if row else {'enabled':False}


def configure(user,enabled):
    prep.require_user(user)
    value=dict(enabled=bool(enabled),actor=str(user['id']),changed_at=prep.now())
    with prep.connect() as c,c.cursor() as q:
        q.execute('INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now()) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()',
                  (SETTING,json.dumps(value)))
    return value


def checked(value,provider,resolver,authorisation,*,whole_order=True):
    from prodigi_dashboard_qa import current,pinned_order,POLICY,CHECKS
    receipt=value.get('dashboard_qa') or {};qa=value.get('qa') or {}
    if (not authorisation.get('enabled') or qa.get('policy')!=POLICY or not receipt.get('verified')
        or set(qa.get('checks') or {})!=set(CHECKS) or not all(v is True for v in qa['checks'].values())):
        raise ValueError('Submission requires activated owner authorisation and every automatic QA check.')
    stamp=datetime.fromisoformat(receipt['checked_at'])
    age=(datetime.now(timezone.utc)-stamp).total_seconds()
    if not -30<=age<=300 or receipt['checked_at']<authorisation['changed_at']:
        raise StaleQA('Refreshing automatic QA before submission.')
    snap,order,_=current(value,provider,resolver)
    if str((snap.get('recipient') or {}).get('address',{}).get('countryCode','')).upper()=='US':
        from prodigi_dashboard_qa import TAX_POLICY
        if receipt.get('tax_policy')!=TAX_POLICY or receipt.get('tax_collected') is not True or order.get('usSalesTaxAlreadyCollected') is False:
            raise StaleQA('Refreshing the saved sales-tax declaration before submission.')
    pinned=pinned_order(order);pinned['shippingMethod']=order.get('shippingMethod')
    if prep.digest(pinned)!=receipt.get('validated_order_hash'):
        raise ValueError('The supplier order changed after QA. Recheck this exact order before submission.')
    if 'submit' not in order.get('allowedActions',[]):
        raise ValueError('Prodigi does not allow this existing order to be submitted through the API. Open it for manual handling.')
    if whole_order and len(order.get('items',[]))>1:
        from prodigi_order_group import members,WaitingForItems
        for unit in members(value,order,resolver):
            if unit['allocation_id']==value['allocation_id']:continue
            if unit['status']!='Ready for manual payment' and not unit.get('submission'):
                raise WaitingForItems('Waiting for every numbered item in this order to pass QA before submission.')
            checked(unit,provider,resolver,authorisation,whole_order=False)
    return order


def complete_certificate(value):
    """Existing Shopify certificate/account flow; never marks Shopify shipped."""
    import os_pages,certificate_job,supabase_backend
    rows,_=os_pages.prodigi_find_order_rows_from_cache(value['snapshot']['order_reference'])
    rows=[r for r in rows if str(r.get('edition_order_id'))==str(value['allocation_id'])]
    if len(rows)!=1:raise ValueError('Submitted order certificate row is missing or ambiguous.')
    row=dict(rows[0])
    result=certificate_job.run_certificate_job_with_timeout(row,source_page='Prodigi',upload=True)
    if not result.get('ok') or result.get('metafields_synced') is False:
        raise ValueError(result.get('error') or 'Certificate/account upload is not confirmed.')
    record=result.get('record') or {}
    url=record.get('certificate_pdf_url') or record.get('pdf_url') or record.get('certificate_url')
    if not url or not url.startswith('https://'):raise ValueError('Uploaded certificate has no confirmed hosted PDF.')
    row.update(certificate_pdf_url=url,shopify_file_url=url)
    answers={k:'Yes' for k in prep.CHECKS}
    _,saved=os_pages.prodigi_upsert_dispatch_row([],row,status='Complete',qa_answers=answers,
        notes='Supplier submission confirmed; automatic dashboard QA passed. Supplier status: '+value['submission']['supplier_status'])
    supabase_backend.upsert_prodigi_dispatch_row(saved,ensure_schema_first=False)
    os_pages.bump_supabase_cache_version('orders','order-summary')
    return url


def run(value,provider,resolver,persist,certificate=complete_certificate,*,may_post=False,authorisation=None):
    """Only a caller holding the freshly committed intent may POST once."""
    receipt=value.get('submission') or {}
    if may_post:
        try:
            checked(value,provider,resolver,authorisation or {})
            provider.submit(value['order_id'])
        except Exception as error:
            receipt['request_issue']=str(error) if isinstance(error,ValueError) else 'Supplier acknowledgement uncertain.'
    try:
        order=provider.order(value['order_id'])
        if str(order.get('id'))!=str(value['order_id']):raise ValueError('Supplier returned a different order.')
        state=order.get('status')
        receipt.update(supplier_status=state,checked_at=prep.now())
        # Match identity even after the provider has moved beyond editable draft.
        before=value['dashboard_qa'].get('before') or {}
        if str(order.get('merchantReference'))!=str(before.get('merchantReference')):
            raise ValueError('Supplier order reference changed; review this exact order.')
        if state not in ACCEPTED:
            receipt['lease_until']=prep.now()
            value.update(status='Submission uncertain',message='Submission not confirmed ('+str(state)+'). Open the same order for review; it will not be submitted again automatically.')
            persist(value);return value
        receipt.update(confirmed=True,confirmed_at=receipt.get('confirmed_at') or prep.now())
        if state not in FINALISED:
            receipt['lease_until']=prep.now()
            value.update(status='Submitted',message=(
                'Submitted to Prodigi · supplier reports on hold. Open Prodigi to review its current hold/countdown; payment and production are not confirmed.'
                if state=='on_hold' else 'Submitted to Prodigi · awaiting payment/production under your supplier countdown.'))
            persist(value);return value
        items=order.get('items') or []
        mapping=value['snapshot']['mapping']
        target=[i for i in items if str(i.get('id'))==str(value['item_id'])]
        if (len(target)!=1 or target[0].get('quantity')!=1
            or target[0].get('sku')!=mapping['prodigi_code'] or len(target[0].get('assets') or [])!=1
            or prep.digest(target[0]['assets'][0].get('url'))!=value.get('url_hash')):
            raise ValueError('The finalised order artwork or product differs from its verified unit; review before certificate upload.')
        if len(items)>1:
            from prodigi_order_group import manifest
            if manifest(order)!=receipt.get('items'):raise ValueError('The finalised order items differ from their QA submission manifest.')
        receipt.update(finalised=True,finalised_at=receipt.get('finalised_at') or prep.now())
        value.update(status='Certificate pending',message='Prodigi accepted this order. Uploading the customer certificate; no repeat submission.')
        persist(value)
    except Exception as error:
        receipt['lease_until']=prep.now()
        value.update(status='Submission uncertain',message=str(error) if isinstance(error,ValueError) else 'Supplier readback unavailable. The same order will be checked without resubmitting.')
        persist(value);return value
    # Passive status reconciliation validates production without waiting for a
    # PDF upload. The existing leased certificate worker finishes that job.
    if certificate is None:
        receipt['lease_until']=prep.now()
        persist(value)
        return value
    try:
        value['certificate_url']=value.get('certificate_url') or certificate(value)
        value.pop('last_failure',None)
        value.update(status='Complete',message='Supplier submission and customer certificate upload confirmed.')
    except Exception as error:
        value.update(status='Certificate pending',message='Order already submitted. Certificate upload needs retry; submission will not repeat.')
        prep.record_failure(value,'certificate_after_submission',str(error) if isinstance(error,ValueError) else 'Certificate upload failed.')
    receipt['lease_until']=prep.now()
    persist(value)
    return value


def tick():
    from prodigi_consolidation import admit_pending
    if admit_pending() is False:return # another admission/readback owns this decision
    authorisation=setting()
    # Reconciliation and certificate retries continue if new submissions pause.
    with prep.connect() as c,c.cursor() as q:
        q.execute('SELECT pg_try_advisory_xact_lock(%s) AS acquired',(LOCK,))
        if not q.fetchone()['acquired']:return
        q.execute("""SELECT key,value FROM app_settings WHERE key LIKE 'prodigi_prepare:%%'
          AND NOT COALESCE((value->>'hidden')::boolean,false) AND NOT value ? 'merge_pending' AND (
           (value->>'status'='Ready for manual payment' AND %s AND NOT value ? 'submission'
            AND COALESCE((value->>'submit_check_after')::timestamptz,'epoch')<now()) OR
           (value->>'status' IN ('Submitting','Submission uncertain','Certificate pending') AND
            (value->>'status'='Certificate pending' OR updated_at<now()-interval '30 seconds')
            AND COALESCE((value->'submission'->>'lease_until')::timestamptz,'epoch')<now()))
          ORDER BY CASE value->>'status' WHEN 'Ready for manual payment' THEN 0
            WHEN 'Submitting' THEN 1 WHEN 'Submission uncertain' THEN 1
            WHEN 'Certificate pending' THEN 2 ELSE 3 END,updated_at
          LIMIT 1 FOR UPDATE SKIP LOCKED""",(bool(authorisation.get('enabled')),))
        row=q.fetchone()
        if not row:return
        value=row['value'];may_post=not bool(value.get('submission'))
        if may_post:
            from prodigi_order_group import WaitingForItems,refresh_qa
            try:order=checked(value,prep.Client(),prep.resolve,authorisation)
            except WaitingForItems as error:
                value.update(message=str(error),submit_check_after=(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat())
                prep.save(q,value);return
            except StaleQA:
                refresh_qa(q,value);return
            except ValueError as error:
                value.update(status='Needs QA',message=str(error));prep.save(q,value);return
            # A supplier-wide unique fence also covers an accidental second OS
            # allocation pointing at this same existing provider order.
            q.execute('INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now()) ON CONFLICT(key) DO NOTHING RETURNING key',
                ('prodigi_submit_order:'+value['order_id'],json.dumps({'allocation_id':value['allocation_id'],'at':prep.now()})))
            if not q.fetchone():
                value.update(status='Needs review',message='This supplier order already has a submission intent. Review the original handoff.');prep.save(q,value);return
            value['submission']=dict(intent_at=prep.now(),actor=authorisation['actor'])
            from prodigi_order_group import reserve
            reserve(q,value,order,authorisation)
        value.update(status='Submitting' if may_post else value['status'],message='Confirming this exact supplier order. Submission is never blindly retried.')
        value['submission']['lease_until']=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()
        prep.save(q,value)
    run(value,prep.Client(),prep.resolve,lambda v:_save(v),may_post=may_post,authorisation=authorisation)
    from prodigi_order_group import publish
    publish(value)


def _save(value):
    with prep.connect() as c,c.cursor() as q:prep.save(q,value)


def kick():
    if not prep.enabled() or not _gate.acquire(blocking=False):return
    def work():
        try:tick()
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Orders submission worker stopped safely')
        finally:_gate.release()
    threading.Thread(target=work,daemon=True,name='orders-submit').start()


def controls(user):
    import streamlit as st
    prep.require_user(user)
    with st.expander('Orders companion · submission settings'):
        current=setting()
        st.caption('After all QA passes, submit the existing Prodigi order and upload the customer certificate. Submit commits supplier charges and production under your Prodigi settings.')
        if current.get('enabled'):
            st.success('Submit after QA is enabled.')
            if st.button('Pause automatic submission',key='orders-submit-pause'):
                configure(user,False);st.rerun()
        else:
            agreed=st.checkbox('I authorise supplier charges and production when every QA check passes.',key='orders-submit-authorise')
            if st.button('Enable submit after QA',disabled=not agreed,key='orders-submit-enable'):
                configure(user,True);st.rerun()
            st.caption('Currently paused. Existing ready orders need a fresh QA pass after activation.')
