"""Compact Orders table. One batched local status read; no supplier I/O here."""
from pathlib import Path
import re,hashlib,json
from urllib.parse import urljoin

ORIGIN='https://sports-cave-image-factory.onrender.com'
ACTIVE={'Queued','Uploading','Creating sandbox draft','Awaiting browser upload','Browser uploading','Checking QA','Preparing JPG','Preparing certificate'}


def supplier_link(order_id):
    value=str(order_id or '')
    return 'https://dashboard.prodigi.com/orders/'+value+'/detail' if re.fullmatch(r'[A-Za-z0-9-]{1,100}',value) else ''


def action_state(saved):
    if not saved:return dict(label='Send',tone='plain',action='send',url='',detail='Prepare this existing draft. Payment and Submit stay manual.')
    state=saved.get('status','Needs review')
    if state=='Ready for manual payment':
        return dict(label='✓ Ready',tone='success',action='',url=supplier_link(saved.get('order_id')),detail='All QA passed. Open this exact order to review and submit manually.')
    if state in ACTIVE:return dict(label='Preparing…',tone='pending',action='',url='',detail=saved.get('message',''))
    return dict(label='⚠ Review',tone='warning',action='review',url='',detail=saved.get('message','Review the saved QA checks.'))


def batch_status(ids):
    import prodigi_preparation as queue
    keys=[queue.PREFIX+str(int(i)) for i in ids if str(i).isdigit()]
    if not keys:return {}
    with queue.connect() as c,c.cursor() as q:
        q.execute('SELECT key,value FROM app_settings WHERE key=ANY(%s)',(keys,))
        return {r['key'].split(':')[1]:r['value'] for r in q.fetchall()}


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


def render(rows,display_rows,*,grid_key,selected,actor):
    import streamlit as st
    import streamlit.components.v1 as components
    import prodigi_preparation as queue
    import os_accounts
    component=components.declare_component('orders_prodigi_grid',path=str(Path(__file__).parent/'components/orders_prodigi_grid'))
    allowed=queue.enabled() and os_accounts.is_admin(actor) and os_accounts.can_access_page(actor,'Prodigi')
    by_id={row_identity(r):r for r in rows}
    try:statuses=batch_status([r.get('edition_order_id') for r in rows]) if allowed else {}
    except Exception:
        statuses={str(r.get('edition_order_id')):{'status':'Status unavailable','message':'Status could not be read. Review this unit before sending.'} for r in rows}
    payload=[]
    for r,d in zip(rows,display_rows):
        aid=str(r.get('edition_order_id') or '')
        state=action_state(statuses.get(aid)) if allowed and aid.isdigit() else dict(label='—',action='',tone='muted',url='',detail='')
        if str(r.get('prodigi','')) in ('Refunded','Refund Pending'):state=dict(label='Blocked',action='',tone='warning',url='',detail='Refunded order')
        payload.append(dict(id=row_identity(r),cells={k:str(d.get(k) or '') for k in ('order','edition','customer','product','variant','shipping','date','prodigi')},
            psd=safe_link(d.get('file')),jpg=safe_link(d.get('print_jpg')),
            jpg_label=str(d.get('print_jpg') or '').rsplit('#',1)[-1] if '#' in str(d.get('print_jpg') or '') else ('Open' if safe_link(d.get('print_jpg')) else str(d.get('print_jpg') or '')),
            state=state))
        if statuses.get(aid,{}).get('status')=='Ready for manual payment':payload[-1]['cells']['prodigi']='QA ready'
    active=any(v.get('status') in ACTIVE for v in statuses.values())
    event=component(rows=payload,selected=[row_identity(r) for r in selected],active=active,
                    key='orders-prodigi-grid',default=None)
    if not isinstance(event,dict) or not event.get('event') or event['event']==st.session_state.get('orders-grid-last-event'):return
    st.session_state['orders-grid-last-event']=event['event']
    if event.get('type')=='select':
        chosen=set(str(i) for i in event.get('ids',[]) if str(i) in by_id)
        st.session_state['orders-grid-selected-ids']=list(chosen)
        st.session_state[grid_key]={'selection':{'rows':[i for i,r in enumerate(rows) if row_identity(r) in chosen]}}
        st.rerun()
    rid=str(event.get('id',''))
    if rid not in by_id or not allowed:return
    aid=str(by_id[rid].get('edition_order_id') or '')
    if not aid.isdigit():return
    if event.get('type')=='send':
        try:queue.request(actor,int(aid))
        except Exception as error:st.error(str(error) if isinstance(error,ValueError) else 'Could not queue preparation. Open Fulfilment for review.')
        else:st.toast('Preparing the existing Prodigi draft. Payment and Submit stay manual.')
        st.rerun()
    if event.get('type')=='review':
        st.session_state['orders-grid-selected-ids']=[rid]
        st.session_state[grid_key]={'selection':{'rows':[i for i,r in enumerate(rows) if row_identity(r)==rid]}}
        st.session_state['orders-prodigi-review']=aid
        st.rerun()
