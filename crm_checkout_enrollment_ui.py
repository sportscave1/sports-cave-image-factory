"""Nonblocking UI acknowledgement; only the durable worker enrolls checkouts."""
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from time import monotonic
import streamlit as st
from crm_checkout_enrollment_requests import request, read_requests, ACTIVE
from crm_checkout_enrollment_requests import reconciled_result

POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='checkout-request-save')
CAPACITY=BoundedSemaphore(4)


def submit(store,user,identity,keys):
    # Permission is checked on the UI thread and again at the write boundary.
    from crm_navigation import require
    require(user,'crm_automations_manage')
    if not CAPACITY.acquire(blocking=False):raise RuntimeError('Request capacity reached')
    try:future=POOL.submit(request,store,dict(user),identity,tuple(keys))
    except Exception:
        CAPACITY.release();raise
    future.add_done_callback(lambda _:CAPACITY.release())
    return future


def begin(store,user,identity,keys,slot):
    state=st.session_state.setdefault(slot+'-enrollment',{'writes':[],'results':{}})
    try:
        future=submit(store,user,identity,keys)
        state['writes'].append((tuple(keys),future))
        state['batch']=tuple(keys)
        state.setdefault('started',{})[id(future)]=monotonic()
        for k in keys:state['results'][k]={'state':'SAVING','result':'Queued','manual_dispatch':True,'delivery':'queued'}
    except Exception:
        for k in keys:state['results'][k]={'state':'FAILED','result':'Failed — request unavailable'}


def progress(store,row,records,slot):
    from crm_automation_analytics_ui import read,patch_checkouts
    state=st.session_state.setdefault(slot+'-enrollment',{'writes':[],'results':{}})
    results=state['results']
    # Restores active requests when the dialog/browser is reopened.
    for c in records:
        value=c.get('enrollment_request')
        if value and (value.get('state') in (*ACTIVE,'FAILED') or value.get('manual_dispatch')) and c['checkout_key'] not in results:
            results[c['checkout_key']]=value
        if c['checkout_key'] in results:
            value=results[c['checkout_key']]
            # A prior accepted receipt cannot finish a new request before its
            # durable acknowledgement arrives; keep polling the write future.
            if value.get('state')=='SAVING':continue
            # Let the targeted receipt read finish an active request normally.
            # Only reconcile cached membership here after expiry/failure; doing
            # it early can replace a fresh "Added to flow" receipt with stale UI.
            expired=reconciled_result({},value)
            if value.get('state') not in ACTIVE or expired.get('state')=='FAILED':
                results[c['checkout_key']]=reconciled_result(c,expired)
    for keys,future in list(state['writes']):
        started=state.setdefault('started',{}).setdefault(id(future),monotonic())
        if not future.done():
            if monotonic()-started<30:continue
            # The write may have committed before its response was lost. Read
            # the durable request/membership; never retry the enrollment here.
            for k in keys:
                if results.get(k,{}).get('state')=='SAVING':
                    results[k]={'state':'FAILED','result':'Request confirmation timed out — refresh or retry safely','_refresh':True}
            future.cancel()
            state['writes'].remove((keys,future))
            state['started'].pop(id(future),None)
            continue
        state['writes'].remove((keys,future))
        state['started'].pop(id(future),None)
        try:
            for value in future.result():results[value['checkout_key']]=dict(value,_refresh=True)
        except Exception:
            for k in keys:results[k]={'state':'FAILED','result':'Failed — persistence error'}
    watching=tuple(sorted(k for k,v in results.items() if v.get('state') in ACTIVE or (v.get('delivery')=='queued' and v.get('state')!='SAVING') or v.get('_refresh')))
    if watching:
        data,phase=read(store,('checkout-enrollment-progress',str(row['id']),watching),
                        lambda:read_requests(store,row['id'],watching),2)
        if data is not None:
            by_key={c['checkout_key']:c for c in records}
            changed=[]
            for update in data:
                key=update['checkout_key'];value=reconciled_result(update,update['request'])
                # Cached progress predating an explicit retry cannot overwrite
                # its fresh acknowledgement or prematurely stop polling.
                if results.get(key,{}).get('requested_at','')>value.get('requested_at',''):continue
                results[key]=value
                if key in by_key:
                    c=by_key[key]
                    c.update({k:v for k,v in update.items() if k!='request'})
                    c['enrollment_request']=value
                    changed.append(c)
            if changed:patch_checkouts(store,row['id'],changed)
            if phase=='READY':
                found={u['checkout_key'] for u in data}
                for k in watching:
                    if k not in found and results[k].get('state')=='FAILED':results[k].pop('_refresh',None)
        if phase=='ERROR':
            st.caption('Progress temporarily unavailable; saved requests continue in the worker.')
    busy={k for k,v in results.items() if v.get('state') in (*ACTIVE,'SAVING')}
    if busy or watching:st.session_state['checkout-enrollment-pending']=True
    batch=[results[k] for k in state.get('batch',()) if k in results]
    if batch and not any(v.get('state') in (*ACTIVE,'SAVING') for v in batch):
        counts={name:sum(v.get('delivery')==name for v in batch) for name in ('sent','queued','skipped','failed')}
        message=f"{sum(bool(v.get('enrolled')) for v in batch)} enrolled; {counts['sent']} sent; {counts['queued']} queued; {counts['skipped']} skipped; {counts['failed']} failed."
        (st.warning if counts['failed'] else st.success)(message)
        from collections import Counter
        reasons=Counter(v.get('result') or 'Not eligible' for v in batch if v.get('delivery') in ('failed','skipped'))
        for reason,count in reasons.items():st.caption(f'{count}: {reason}')
    return results,busy
