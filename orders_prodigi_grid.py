"""Compact Orders table. One batched local status read; no supplier I/O here."""
from pathlib import Path
from datetime import datetime
import re,hashlib,json
from urllib.parse import urljoin

ORIGIN='https://sports-cave-image-factory.onrender.com'
ACTIVE={'Waiting for order','Queued','Uploading','Creating sandbox draft','Awaiting product selection','Awaiting browser upload','Selecting product','Browser uploading','Checking QA','Preparing JPG','Preparing certificate','Awaiting certificate browser','Certificate browser uploading','Awaiting dashboard QA','Checking dashboard QA','Submitting','Certificate pending','Submitted'}


def latest_update(values):
    def stamp(value):
        try:return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
        except (ValueError,TypeError):return 0
    return max(values,key=stamp,default=None)


def supplier_link(order_id):
    value=str(order_id or '')
    return 'https://dashboard.prodigi.com/orders/'+value+'/detail' if re.fullmatch(r'[A-Za-z0-9-]{1,100}',value) else ''


def action_state(saved, fulfilment=""):
    inbox=(saved or {}).get('_inbox') or {}
    if inbox.get('blocking'):
        return dict(label='Paused customer request' if inbox.get('paused') else 'Customer request · review',tone='warning',action='',url=supplier_link((saved or {}).get('order_id')),detail=inbox.get('label','Review customer request in Inbox Companion.'))
    if ((saved or {}).get('signin_wait') or {}).get('state')=='waiting':
        from prodigi_signin import DETAIL
        return dict(label='Sign in to Prodigi',tone='warning',action='',url=supplier_link(saved.get('order_id')),detail=DETAIL)
    if str(fulfilment).strip().lower()=="complete":
        if saved and saved.get('status')=='Complete':
            return dict(label='Complete',tone='success',action='',url=supplier_link(saved.get('order_id')),detail=saved.get('message','Supplier submission confirmed.'))
        return dict(label="✓ Complete",tone="complete",action="",url="",detail="This order is already complete.")
    if not saved:return dict(label='Send',tone='plain',action='send',url='',detail='Prepare and check this existing order. Submission follows the Orders companion setting.')
    state=saved.get('status','Needs review')
    failure=saved.get('last_failure') or {}
    if (state in ('Needs QA','Needs review') and failure.get('stage')=='preflight'
            and failure.get('error_type')=='ArtworkQuality'
            and not any(saved.get(k) for k in ('browser','write_intent','document_write_intent'))):
        return dict(label='Send',tone='plain',action='send',url='',detail='Attach artwork now. Print quality is checked in the later QA stage; payment stays manual.')
    if state in ('Submitted','Complete','Certificate pending'):
        return dict(label='Complete' if state=='Complete' else ('Certificate pending' if state=='Certificate pending' else 'Submitted'),tone='success',action='',url=supplier_link(saved.get('order_id')),detail=saved.get('message','Supplier submission confirmed.'))
    if state in ('Submitting','Submission uncertain'):
        return dict(label=state,tone='pending',action='',url='',detail=saved.get('message',''))
    if state=='Ready for manual payment':
        return dict(label='Ready in Prodigi',tone='success',action='',url=supplier_link(saved.get('order_id')),detail='All QA passed. Submission follows the Orders companion setting; open this exact order.')
    if state=='Waiting for order':return dict(label='Item QA passed',tone='pending',action='',url='',detail=saved.get('message',''))
    if state in ('Awaiting dashboard QA','Checking dashboard QA'):return dict(label='Checking QA…',tone='pending',action='',url='',detail=saved.get('message',''))
    if state in ACTIVE:return dict(label='Preparing…',tone='pending',action='',url='',detail=saved.get('message',''))
    return dict(label='⚠ Review',tone='warning',action='review',url='',detail=saved.get('message','Review the saved QA checks.'))


def batch_status(ids):
    import prodigi_preparation as queue
    keys=[queue.PREFIX+str(int(i)) for i in ids if str(i).isdigit()]
    if not keys:return {}
    keys += [queue.FAILURE_PREFIX+str(int(i)) for i in ids if str(i).isdigit()]
    keys.append('orders_submit_after_qa')
    keys.append('orders_companion_runtime')
    keys += ['orders_runtime:'+str(int(i)) for i in ids if str(i).isdigit()]
    with queue.connect() as c,c.cursor() as q:
        q.execute('SELECT key,value FROM app_settings WHERE key=ANY(%s)',(keys,))
        rows=q.fetchall()
    states={r['key'].split(':')[1]:r['value'] for r in rows if r['key'].startswith(queue.PREFIX)}
    states.update({r['key'].split(':')[1]:r['value'] for r in rows if r['key'].startswith(queue.FAILURE_PREFIX) and r['value'].get('active')})
    automatic=next((r['value'].get('enabled') is True for r in rows if r['key']=='orders_submit_after_qa'),False)
    from orders_runtime import public
    runtime={r['key'].split(':')[-1]:r['value'] for r in rows if r['key'].startswith('orders_runtime:')}
    companion=next((r['value'] for r in rows if r['key']=='orders_companion_runtime'),{})
    for aid,value in states.items():
        value['_submit_enabled']=automatic
        value['_runtime']=public(value,runtime.get(aid,{}))
        value['_companion_version']=companion.get('version','')
    from orders_artwork_repair import batch as artwork_status
    for aid,artwork in artwork_status(queue.connect,ids).items():
        states.setdefault(aid,{})['_artwork']=artwork
    return states


def safe_link(value):
    value=str(value or '')
    if value.startswith('/') and not value.startswith('//'):return urljoin(ORIGIN,value)
    if value.startswith('https://'):return value
    return ''


def row_identity(row):
    aid=str(row.get('edition_order_id') or '')
    if aid:return 'allocation:'+aid
    return unit_identity(row)


def unit_identity(row):
    return 'unit:'+hashlib.sha256(json.dumps([str(row.get(k) or '') for k in
        ('shopify_order_id','shopify_line_item_id','allocation_index','unit_ordinal','shopify_product_id')]).encode()).hexdigest()[:24]


def read_statuses(rows,actor):
    import prodigi_preparation as queue
    import os_accounts
    if not (queue.enabled() and os_accounts.is_admin(actor) and os_accounts.can_access_page(actor,'Prodigi')):return {}
    try:return batch_status([r.get('edition_order_id') for r in rows])
    except Exception:
        return {str(r.get('edition_order_id')):{'status':'Status unavailable','message':'Status could not be read. Review this unit before sending.'} for r in rows}



def shipping_summary(saved):
    """Use the verified selected quote already saved by QA; no supplier calls."""
    receipt=(saved or {}).get('dashboard_qa') or {}
    if not receipt.get('verified') or (saved or {}).get('checks',{}).get('shipping') is not True:return ''
    shipping=(receipt.get('evidence') or {}).get('shipping') or {}
    selected=shipping.get('selected') or (receipt.get('shipping') or {}).get('target')
    options=shipping.get('options') or (receipt.get('shipping') or {}).get('options') or []
    matches=[row for row in options if isinstance(row,dict) and row.get('service')==selected]
    labels={'budget':'Budget','standard':'Standard','standardplus':'Standard Plus','express':'Express','overnight':'Overnight'}
    if len(matches)!=1 or selected not in labels:return ''
    quote=matches[0];cents=quote.get('cents');currency=quote.get('currency')
    if type(cents) is not int or not 0<=cents<=10000000 or currency not in ('$','£','€'):return ''
    return f"{labels[selected]} · {currency}{cents//100}.{cents%100:02d}"


def review(saved,row,jpg):
    from prodigi_dashboard_qa import CHECKS
    state=(saved or {}).get('status','Waiting')
    checks=(saved or {}).get('checks') or {}
    runtime=(saved or {}).get('_runtime') or {}
    stopped=state in ('Needs QA','Needs review','Submission uncertain','Status unavailable')
    snap=(saved or {}).get('snapshot') or {}
    if re.fullmatch('[a-f0-9]{64}',str(snap.get('job_id') or '')) and snap.get('output',{}).get('sha256'):
        jpg=ORIGIN+'/api/auto-editions/file?allocation_id='+str(row['edition_order_id'])+'&job_id='+snap['job_id']+'&inline=1'
    items=[dict(label=label,state='pass' if checks.get(key) is True else 'fail' if stopped and (checks.get(key) is False or key=='final_check') else 'pending') for key,label in CHECKS.items()]
    artwork=(saved or {}).get('_artwork') or {}
    if state in ('Submitted','Complete','Certificate pending','Submission uncertain') or str(row.get('prodigi','')).lower()=='complete':
        artwork={**artwork,'active':False,'repairable':False} if artwork else {}
    repairing=bool(artwork.get('active') or artwork.get('repairable')) and state not in ('Submitted','Complete','Certificate pending','Submission uncertain')
    if repairing:
        state='PSD repairing' if artwork.get('active') else 'PSD repair'
        stopped=False
        items=[dict(label=label,state='pending') for label in CHECKS.values()]
    timestamps=[str(v) for v in (runtime.get('seen_at'),(saved or {}).get('updated_at'),
        ((saved or {}).get('last_failure') or {}).get('at'),artwork.get('updated_at')) if v]
    message=(artwork.get('message') if repairing else None) or runtime.get('label') or (saved or {}).get('message','Waiting for automatic artwork preparation.')
    inbox=((saved or {}).get('_inbox') or {}).get('label')
    if inbox:message=inbox+' · '+message
    return dict(status=state,message=message,
        artwork=artwork,
        progress=runtime,companion_version=(saved or {}).get('_companion_version',''),
        updated_at=latest_update(timestamps),proof_url=jpg if '/api/auto-editions/file?' in jpg else '',
        submission_enabled=(saved or {}).get('_submit_enabled'),
        insert_names=((saved or {}).get('qa') or {}).get('inserts',{}).get('names',[]),
        shipping_quote=shipping_summary(saved),
        supplier_status=((saved or {}).get('submission') or {}).get('supplier_status',''),
        supplier_checked_at=((saved or {}).get('submission') or {}).get('checked_at'),
        supplier_delayed=((saved or {}).get('supplier_sync') or {}).get('delayed',False),
        can_merge_restart=stopped and bool((saved or {}).get('merge_pending')),
        items=items,can_restart=stopped,can_reset=stopped and not bool((saved or {}).get('submission')) and not bool((saved or {}).get('merge_pending')),allocation_id=str(row.get('edition_order_id') or ''),
        order_url=supplier_link((saved or {}).get('order_id')),
        preview=jpg.split('#')[0]+'&preview=1' if '/api/auto-editions/file?' in jpg else '')


def payload_rows(rows,display_rows,statuses,*,allowed):
    from inbox_companion import available,FLAG,prep,order_identity
    flags={}
    if allowed and available():
        # Include requests received before an allocation/preparation exists, in one read.
        keys=list({FLAG+order_identity(r.get('shopify_order_id')) for r in rows if order_identity(r.get('shopify_order_id'))})
        with prep.connect() as c,c.cursor() as q:
            q.execute('SELECT key,value FROM app_settings WHERE key=ANY(%s)',(keys,))
            flags={r['key']:r['value'] for r in q.fetchall()}
    payload=[]
    for r,d in zip(rows,display_rows):
        aid=str(r.get('edition_order_id') or '')
        saved=dict(statuses.get(aid) or {})
        inbox=flags.get(FLAG+order_identity(r.get('shopify_order_id')))
        if inbox:saved['_inbox']=inbox
        state=action_state(saved or None,r.get("prodigi")) if allowed and (aid.isdigit() or inbox) else dict(label='—',action='',tone='muted',url='',detail='')
        if str(r.get('prodigi','')) in ('Refunded','Refund Pending'):state=dict(label='Blocked',action='',tone='warning',url='',detail='Refunded order')
        payload.append(dict(id=row_identity(r),cells={k:str(d.get(k) or '') for k in ('order','edition','customer','product','variant','shipping','date','prodigi')},
            psd=safe_link(d.get('file')),jpg=safe_link(d.get('print_jpg')),
            jpg_label=str(d.get('print_jpg') or '').rsplit('#',1)[-1] if '#' in str(d.get('print_jpg') or '') else ('Open JPG' if safe_link(d.get('print_jpg')) else str(d.get('print_jpg') or '')),
            state=state,certificate=(ORIGIN+'/api/orders/certificate?allocation_id='+aid if aid.isdigit() and str(r.get('prodigi','')).lower()=='complete' else safe_link(r.get('certificate_pdf_url') or r.get('shopify_file_url'))),
            jpg_download=(safe_link(d.get('print_jpg')).replace('&inline=1','').split('#')[0] if '/api/auto-editions/file?' in str(d.get('print_jpg')) else '')))
        payload[-1]['review']=review(saved,r,payload[-1]['jpg'])
        if statuses.get(aid,{}).get('status')=='Complete' and statuses[aid].get('certificate_url'):
            payload[-1]['cells']['prodigi']='Complete'
            payload[-1]['certificate']=ORIGIN+'/api/orders/certificate?allocation_id='+aid
        if payload[-1]['jpg_label']=='Open':payload[-1]['jpg_label']='Open JPG'
        shipping=payload[-1]['cells']['shipping']
        if shipping.strip().lower() in ('standard','express'):payload[-1]['cells']['shipping']=shipping.strip()+' shipping'
    for raw,item in zip(rows,payload):
        item['unit_key']=unit_identity(raw) if raw.get('shopify_order_id') and raw.get('shopify_line_item_id') else ''
        item['revision']=hashlib.sha256(json.dumps(item,sort_keys=True,default=str).encode()).hexdigest()
    return payload


def _rerun_active_fragment(st):
    """A fragment called in a full app render may consume a pending grid event.

    Its browser already applied the delta/selection. Persist that event, but do
    not request an illegal fragment rerun (or force a full-page reload). During
    an actual fragment rerun, acknowledge the adopted state immediately.
    """
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    context=get_script_run_ctx(suppress_warning=True)
    if context and context.fragment_ids_this_run:
        st.rerun(scope='fragment')


def render(rows,display_rows,*,grid_key,selected,actor,statuses=None):
    import streamlit as st
    import streamlit.components.v1 as components
    import prodigi_preparation as queue
    import os_accounts
    component=components.declare_component('orders_prodigi_grid',path=str(Path(__file__).parent/'components/orders_prodigi_grid'))
    allowed=queue.enabled() and os_accounts.is_admin(actor) and os_accounts.can_access_page(actor,'Prodigi')
    import orders_feed
    query=str(st.session_state.get('orders_loaded_query') or '')
    scope=orders_feed.signature([str(actor.get('id') or ''),bool(allowed),query,st.session_state.get('orders_load_generation')])
    live=st.session_state.get('orders-grid-feed') or {}
    if live.get('scope')==scope:
        rows=live['snapshot']['raw']
    by_id={row_identity(r):r for r in rows}
    if statuses is None:statuses=read_statuses(rows,actor)
    payload=live['snapshot']['rows'] if live.get('scope')==scope else payload_rows(rows,display_rows,statuses,allowed=allowed)
    st.session_state['orders-grid-feed-active']=True
    active=allowed and (bool(statuses) or any(str(r.get('prodigi','')).lower()!='complete' for r in rows))
    chosen=st.session_state.get('orders-grid-selected-ids',[row_identity(r) for r in selected])
    event=component(rows=payload,selected=chosen,active=active,feed=dict(scope=scope,query=query,version=live.get('snapshot',{}).get('version','') if live.get('scope')==scope else ''),
                    key='orders-prodigi-grid',default=None)
    if not isinstance(event,dict) or not event.get('event') or event['event']==st.session_state.get('orders-grid-last-event'):return
    st.session_state['orders-grid-last-event']=event['event']
    if event.get('type') in ('feed','select') and event.get('scope') and event['scope']!=scope:return
    if event.get('type') in ('feed','select') and event.get('scope')==scope:
        saved=orders_feed.recalled(actor,query,event.get('version'))
        if saved is not None:
            st.session_state['orders-grid-feed']=dict(scope=scope,snapshot=saved)
            st.session_state['orders_allocation_rows']=saved['raw']
            rows=saved['raw'];by_id={row_identity(r):r for r in rows}
    if event.get('type')=='feed':
        if event.get('scope')!=scope or saved is None:return
        _rerun_active_fragment(st)
        return
    if event.get('type')=='select':
        st.session_state.pop('orders-prodigi-review',None)
        previous=set(st.session_state.get('orders-grid-selected-ids') or [])
        chosen=set(str(i) for i in event.get('ids',[]) if str(i) in by_id or str(i) in previous)
        st.session_state['orders-grid-selected-ids']=list(chosen)
        st.session_state[grid_key]={'selection':{'rows':[i for i,r in enumerate(rows) if row_identity(r) in chosen]}}
        _rerun_active_fragment(st)
        return
    if event.get('type')=='refresh':
        st.rerun()
        return
    rid=str(event.get('id',''))
    if rid not in by_id or not allowed:return
    aid=str(by_id[rid].get('edition_order_id') or '')
    if not aid.isdigit():return
    if event.get('type')=='send':
        if str(by_id[rid].get('prodigi','')).strip().lower()=='complete':return
        try:
            queued=queue.request(actor,int(aid))
        except Exception as error:
            st.session_state['orders-prodigi-feedback']=str(error) if isinstance(error,ValueError) else 'Could not queue preparation. Open Fulfilment for review.'
        else:st.toast((queued or {}).get('message') or 'Preparing the existing Prodigi draft. Payment and Submit stay manual.')
        st.rerun()
    if event.get('type')=='review':
        st.session_state['orders-grid-selected-ids']=[rid]
        st.session_state[grid_key]={'selection':{'rows':[i for i,r in enumerate(rows) if row_identity(r)==rid]}}
        st.session_state['orders-prodigi-review']=aid
        st.rerun()
