"""Compact Orders table. One batched local status read; no supplier I/O here."""
from pathlib import Path
import re,hashlib,json
from urllib.parse import urljoin

ORIGIN='https://sports-cave-image-factory.onrender.com'
ACTIVE={'Queued','Uploading','Creating sandbox draft','Awaiting browser upload','Browser uploading','Checking QA','Preparing JPG','Preparing certificate','Awaiting certificate browser','Certificate browser uploading','Awaiting dashboard QA','Checking dashboard QA','Submitting','Certificate pending','Submitted'}


def supplier_link(order_id):
    value=str(order_id or '')
    return 'https://dashboard.prodigi.com/orders/'+value+'/detail' if re.fullmatch(r'[A-Za-z0-9-]{1,100}',value) else ''


def action_state(saved, fulfilment=""):
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
    if state in ('Awaiting dashboard QA','Checking dashboard QA'):return dict(label='Checking QA…',tone='pending',action='',url='',detail=saved.get('message',''))
    if state in ACTIVE:return dict(label='Preparing…',tone='pending',action='',url='',detail=saved.get('message',''))
    return dict(label='⚠ Review',tone='warning',action='review',url='',detail=saved.get('message','Review the saved QA checks.'))


def batch_status(ids):
    import prodigi_preparation as queue
    keys=[queue.PREFIX+str(int(i)) for i in ids if str(i).isdigit()]
    if not keys:return {}
    keys += [queue.FAILURE_PREFIX+str(int(i)) for i in ids if str(i).isdigit()]
    keys.append('orders_submit_after_qa')
    with queue.connect() as c,c.cursor() as q:
        q.execute('SELECT key,value FROM app_settings WHERE key=ANY(%s)',(keys,))
        rows=q.fetchall()
    states={r['key'].split(':')[1]:r['value'] for r in rows if r['key'].startswith(queue.PREFIX)}
    states.update({r['key'].split(':')[1]:r['value'] for r in rows if r['key'].startswith(queue.FAILURE_PREFIX) and r['value'].get('active')})
    automatic=next((r['value'].get('enabled') is True for r in rows if r['key']=='orders_submit_after_qa'),False)
    for value in states.values():value['_submit_enabled']=automatic
    return states


def safe_link(value):
    value=str(value or '')
    if value.startswith('/') and not value.startswith('//'):return urljoin(ORIGIN,value)
    if value.startswith('https://'):return value
    return ''


def row_identity(row):
    aid=str(row.get('edition_order_id') or '')
    if aid:return 'allocation:'+aid
    return 'unit:'+hashlib.sha256(json.dumps([str(row.get(k) or '') for k in
        ('shopify_order_id','shopify_line_item_id','allocation_index','unit_ordinal','shopify_product_id')]).encode()).hexdigest()[:24]


def read_statuses(rows,actor):
    import prodigi_preparation as queue
    import os_accounts
    if not (queue.enabled() and os_accounts.is_admin(actor) and os_accounts.can_access_page(actor,'Prodigi')):return {}
    try:return batch_status([r.get('edition_order_id') for r in rows])
    except Exception:
        return {str(r.get('edition_order_id')):{'status':'Status unavailable','message':'Status could not be read. Review this unit before sending.'} for r in rows}



def review(saved,row,jpg):
    from prodigi_dashboard_qa import CHECKS
    state=(saved or {}).get('status','Waiting')
    checks=(saved or {}).get('checks') or {}
    stopped=state in ('Needs QA','Needs review','Submission uncertain','Status unavailable')
    snap=(saved or {}).get('snapshot') or {}
    if re.fullmatch('[a-f0-9]{64}',str(snap.get('job_id') or '')) and snap.get('output',{}).get('sha256'):
        jpg=ORIGIN+'/api/auto-editions/file?allocation_id='+str(row['edition_order_id'])+'&job_id='+snap['job_id']+'&inline=1'
    items=[dict(label=label,state='pass' if checks.get(key) is True else 'fail' if stopped and (checks.get(key) is False or key=='final_check') else 'pending') for key,label in CHECKS.items()]
    return dict(status=state,message=(saved or {}).get('message','Waiting for automatic artwork preparation.'),
        updated_at=(saved or {}).get('updated_at') or ((saved or {}).get('last_failure') or {}).get('at'),proof_url=jpg if '/api/auto-editions/file?' in jpg else '',
        submission_enabled=(saved or {}).get('_submit_enabled'),
        items=items,can_restart=stopped,allocation_id=str(row.get('edition_order_id') or ''),
        order_url=supplier_link((saved or {}).get('order_id')),
        preview=jpg.split('#')[0]+'&preview=1' if '/api/auto-editions/file?' in jpg else '')


def render(rows,display_rows,*,grid_key,selected,actor,statuses=None):
    import streamlit as st
    import streamlit.components.v1 as components
    import prodigi_preparation as queue
    import os_accounts
    component=components.declare_component('orders_prodigi_grid',path=str(Path(__file__).parent/'components/orders_prodigi_grid'))
    allowed=queue.enabled() and os_accounts.is_admin(actor) and os_accounts.can_access_page(actor,'Prodigi')
    by_id={row_identity(r):r for r in rows}
    if statuses is None:statuses=read_statuses(rows,actor)
    payload=[]
    for r,d in zip(rows,display_rows):
        aid=str(r.get('edition_order_id') or '')
        state=action_state(statuses.get(aid),r.get("prodigi")) if allowed and aid.isdigit() else dict(label='—',action='',tone='muted',url='',detail='')
        if str(r.get('prodigi','')) in ('Refunded','Refund Pending'):state=dict(label='Blocked',action='',tone='warning',url='',detail='Refunded order')
        payload.append(dict(id=row_identity(r),cells={k:str(d.get(k) or '') for k in ('order','edition','customer','product','variant','shipping','date','prodigi')},
            psd=safe_link(d.get('file')),jpg=safe_link(d.get('print_jpg')),
            jpg_label=str(d.get('print_jpg') or '').rsplit('#',1)[-1] if '#' in str(d.get('print_jpg') or '') else ('Open JPG' if safe_link(d.get('print_jpg')) else str(d.get('print_jpg') or '')),
            state=state,certificate=(ORIGIN+'/api/orders/certificate?allocation_id='+aid if aid.isdigit() and str(r.get('prodigi','')).lower()=='complete' else safe_link(r.get('certificate_pdf_url') or r.get('shopify_file_url'))),
            jpg_download=(safe_link(d.get('print_jpg')).replace('&inline=1','').split('#')[0] if '/api/auto-editions/file?' in str(d.get('print_jpg')) else '')))
        payload[-1]['review']=review(statuses.get(aid),r,payload[-1]['jpg'])
        if statuses.get(aid,{}).get('status')=='Complete' and statuses[aid].get('certificate_url'):
            payload[-1]['cells']['prodigi']='Complete'
            payload[-1]['certificate']=ORIGIN+'/api/orders/certificate?allocation_id='+aid
        if payload[-1]['jpg_label']=='Open':payload[-1]['jpg_label']='Open JPG'
        shipping=payload[-1]['cells']['shipping']
        if shipping.strip().lower() in ('standard','express'):payload[-1]['cells']['shipping']=shipping.strip()+' shipping'
    active=allowed and any(str(r.get('prodigi','')).lower()!='complete' for r in rows)
    event=component(rows=payload,selected=[row_identity(r) for r in selected],active=active,
                    key='orders-prodigi-grid',default=None)
    if not isinstance(event,dict) or not event.get('event') or event['event']==st.session_state.get('orders-grid-last-event'):return
    st.session_state['orders-grid-last-event']=event['event']
    if event.get('type')=='select':
        st.session_state.pop('orders-prodigi-review',None)
        chosen=set(str(i) for i in event.get('ids',[]) if str(i) in by_id)
        st.session_state['orders-grid-selected-ids']=list(chosen)
        st.session_state[grid_key]={'selection':{'rows':[i for i,r in enumerate(rows) if row_identity(r) in chosen]}}
        st.rerun(scope='fragment')
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
