"""Nonblocking UI acknowledgement; only the durable worker enrolls checkouts."""
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
import streamlit as st
from crm_checkout_enrollment_requests import request, read_requests, ACTIVE

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
        for k in keys:state['results'][k]={'state':'SAVING','result':'Adding…'}
    except Exception:
        for k in keys:state['results'][k]={'state':'FAILED','result':'Failed — request unavailable'}


def progress(store,row,records,slot):
    from crm_automation_analytics_ui import read,patch_checkouts
    state=st.session_state.setdefault(slot+'-enrollment',{'writes':[],'results':{}})
    results=state['results']
    # Restores active requests when the dialog/browser is reopened.
    for c in records:
        value=c.get('enrollment_request')
        if value and value.get('state') in (*ACTIVE,'FAILED') and c['checkout_key'] not in results:
            results[c['checkout_key']]=value
    for keys,future in list(state['writes']):
        if not future.done():continue
        state['writes'].remove((keys,future))
        try:
            for value in future.result():results[value['checkout_key']]=dict(value,_refresh=True)
        except Exception:
            for k in keys:results[k]={'state':'FAILED','result':'Failed — persistence error'}
    watching=tuple(sorted(k for k,v in results.items() if v.get('state') in ACTIVE or v.get('_refresh')))
    if watching:
        data,phase=read(store,('checkout-enrollment-progress',str(row['id']),watching),
                        lambda:read_requests(store,row['id'],watching),2)
        if data is not None:
            by_key={c['checkout_key']:c for c in records}
            changed=[]
            for update in data:
                key=update['checkout_key'];value=update['request']
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
        if phase=='ERROR':
            st.caption('Progress temporarily unavailable; saved requests continue in the worker.')
    busy={k for k,v in results.items() if v.get('state') in (*ACTIVE,'SAVING')}
    if busy or watching:st.session_state['checkout-enrollment-pending']=True
    return results,busy
