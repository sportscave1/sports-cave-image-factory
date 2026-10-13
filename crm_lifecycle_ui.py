"""Lifecycle audiences on the existing Flow page and checkout table component."""
from pathlib import Path
from datetime import datetime, time, timedelta, timezone
import streamlit as st
from contextlib import nullcontext
from crm_automation_analytics_ui import read,arm
from crm_lifecycle_audience import listing,customer_preview,stage,SORTS,FILTERS
from crm_logic import now,date


def dismiss_enrollment():st.session_state.pop('lifecycle-enroll-confirm',None)


@st.dialog('Add selected orders to Post Purchase?',width='small',on_dismiss=dismiss_enrollment)
def confirm_enrollment(store,user,identity,orders):
    st.write('Add '+str(len(orders))+' selected orders? The worker will freshly verify marketing consent, order eligibility and suppression. Historical selected orders are included only by this explicit confirmation.')
    st.caption('The original verified payment time and configured delays are preserved. Already-due eligible stages may be scheduled by the worker. Existing journeys and accepted emails will not be replayed.')
    if st.button('Confirm Add to Flow',type='primary',key='lifecycle-confirm-enroll'):
        try:
            from crm_lifecycle_enrollment_requests import request
            request(store,user,identity,orders,confirmed=True)
            st.session_state.pop('lifecycle-enroll-confirm',None)
            st.session_state['lifecycle-'+str(identity)+'-selected']=[]
            st.rerun(scope='app')
        except (ValueError,PermissionError,RuntimeError) as exc:st.error(str(exc))
    if st.button('Cancel',key='lifecycle-cancel-enroll'):
        st.session_state.pop('lifecycle-enroll-confirm',None);st.rerun(scope='app')

def audience(store,user,row):
    # The disclosure belongs to the page, not the refreshing table fragment.
    # Only an explicit user toggle reruns this shell; table updates cannot
    # replace its DOM or restore an older open/closed value.
    if row['trigger_type']=='post_purchase':
        with st.expander('Orders',key='lifecycle-'+str(row['id'])+'-panel',on_change='rerun') as panel:
            if panel.open:
                with st.container(key='post-purchase-orders'):_audience(store,user,row,orders_open=True)
    else:_audience(store,user,row)


def order_event(slot):
    from crm_post_purchase_audience import selection
    event=st.session_state.get(slot+'-table')
    if event and event.get('context')==st.session_state.get(slot+'-table-context'):
        selection(st.session_state,slot,set(st.session_state.get(slot+'-visible',[])),event)


@st.fragment
def _audience(store,user,row,*,orders_open=False):
    from crm_component_json import render_component
    from os_accounts import timezone_for_user
    from zoneinfo import ZoneInfo
    from crm_store import StoreUnavailable
    import streamlit.components.v1 as components
    slot='lifecycle-'+str(row['id']);kind=row['trigger_type']
    zone=ZoneInfo(timezone_for_user(user))
    def display(value):
        value=date(value)
        return value.astimezone(zone).strftime('%d %b %Y %H:%M') if value else '—'
    titles={'welcome':'Marketing subscribers','post_purchase':'Orders','win_back':'Inactive purchasers'}
    with nullcontext() if orders_open else st.expander(titles[kind],key=slot+'-panel',on_change='rerun') as panel:
        if not orders_open and not panel.open:return
        if orders_open:
            st.html('''<style>
            .st-key-post-purchase-orders [data-testid="stVerticalBlock"]{gap:.35rem}
            .st-key-post-purchase-toolbar [data-testid="stHorizontalBlock"]{gap:.4rem;align-items:center}
            .st-key-post-purchase-toolbar [data-baseweb="input"],.st-key-post-purchase-toolbar [data-baseweb="select"]>div{height:32px;min-height:32px;font-size:13px}
            .st-key-post-purchase-toolbar :is([data-testid="stTextInputRootElement"],.react-aria-ComboBox>[role="group"]){height:32px;min-height:32px;background:#fffefa;border:1px solid #e4e2da;border-radius:4px}
            .st-key-post-purchase-toolbar :is([data-testid="stTextInputField"],[role="combobox"]){height:30px;min-height:0;padding:.2rem .55rem;font-size:13px}
            .st-key-post-purchase-toolbar button{min-height:32px;height:32px;padding:.2rem .55rem;white-space:nowrap}
            .st-key-post-purchase-toolbar button p{font-size:13px}
            .st-key-post-purchase-toolbar :is(input,button,[role="combobox"]){font-family:'Segoe UI',system-ui,sans-serif}
            .st-key-post-purchase-toolbar [data-testid="stPopover"] button [data-testid="stMarkdownContainer"]{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
            .st-key-post-purchase-orders [data-testid="stCustomComponentV1"]{min-width:0;max-width:100%}
            .st-key-post-purchase-orders iframe{max-width:100%;width:100%}
            @media(min-width:900px){.st-key-post-purchase-toolbar [data-testid="stHorizontalBlock"]{flex-wrap:nowrap}}
            @media(max-width:899px){.st-key-post-purchase-toolbar [data-testid="stHorizontalBlock"]{flex-wrap:wrap}.st-key-post-purchase-toolbar [data-testid="stColumn"]{min-width:110px;flex:1 1 110px}}
            </style>''')
        with st.container(key='post-purchase-toolbar' if orders_open else slot+'-toolbar'):
            controls=st.columns([3,1.15,1.15,.5,1] if orders_open else [2,1,1])
            search_col,filter_col,sort_col=controls[:3]
            search=search_col.text_input('Search and filter',key=slot+'-search',placeholder='Search orders' if orders_open else 'Customer, email or Shopify ID',label_visibility='collapsed' if orders_open else 'visible')
        from crm_post_purchase_audience import FILTERS as ORDER_FILTERS,selection,email_cells
        filter_by=filter_col.selectbox('Status',ORDER_FILTERS if kind=='post_purchase' else FILTERS,key=slot+'-filter',label_visibility='collapsed' if orders_open else 'visible')
        sorts=[s for s in SORTS if kind!='post_purchase' or s in ('Newest','Oldest','Customer value','Sequence stage')]
        sort=sort_col.selectbox('Sort',sorts,index=2 if kind=='win_back' else 0,key=slot+'-sort',label_visibility='collapsed' if orders_open else 'visible')
        with controls[3] if orders_open else nullcontext():
            dates=st.popover('Date filters',icon=':material/calendar_month:',help='Filter order dates') if orders_open else st.popover('Date filters')
        with dates:
            start=st.date_input('From',value=None,key=slot+'-from')
            end=st.date_input('Through',value=None,key=slot+'-through')
        criteria=(search,filter_by,sort,start,end)
        if st.session_state.get(slot+'-criteria')!=criteria:
            st.session_state[slot+'-criteria']=criteria;st.session_state[slot+'-page']=0
        page=st.session_state.get(slot+'-page',0)
        if start and end and start>end:st.warning('Choose an end date after the start date.');return
        begin=datetime.combine(start,time.min,zone) if start else None
        until=datetime.combine(end+timedelta(days=1),time.min,zone) if end else None
        generation=st.session_state.get(slot+'-refresh',0)
        if not orders_open and st.button('Refresh audience',key=slot+'-refresh-button'):
            if kind=='post_purchase':
                from crm_lifecycle_audience import refresh_customers
                refresh_customers(store,user,st.session_state.get(slot+'-customers',[]))
            st.session_state[slot+'-refresh']=generation+1;st.rerun(scope='fragment')
        key=('lifecycle-audience',str(row['id']),criteria,page,generation)
        records,phase=read(store,key,lambda:listing(store,row,search=search,filter_by=filter_by,sort=sort,start=begin,end=until,page=page),30,
            wait_budget=.15 if kind=='post_purchase' else 0)
        last=st.session_state.setdefault(slot+'-rows',{})
        page_key=(criteria,page)
        if records is not None:
            last[page_key]=(now(),records)
            while len(last)>8:last.pop(next(iter(last)))
        elif page_key in last:
            records=last[page_key][1]
            if phase in ('LOADING','REFRESHING'):phase='REFRESHING'
        if phase in ('LOADING','REFRESHING'):arm(slot+'-settle',1)
        if records is None:
            st.caption('Loading audience…' if phase not in ('ERROR','TIMED_OUT') else 'Audience unavailable. Check database access and the audience migration.')
            if orders_open and phase in ('ERROR','TIMED_OUT') and st.button('Retry orders',key=slot+'-retry-read'):
                st.session_state[slot+'-refresh']=generation+1;st.rerun(scope='fragment')
            return
        if phase in ('ERROR','TIMED_OUT'):st.caption('Refresh failed; last verified records shown.')
        visible=records[:50];at=now()
        st.session_state[slot+'-customers']=list({r['customer_id'] for r in visible if r['customer_id']})
        keys={r['key'] for r in visible}
        selected=st.session_state.get(slot+'-selected',[])
        if kind=='post_purchase':
            import os_accounts
            from crm_post_purchase_audience import add_candidate
            candidates=st.session_state.setdefault(slot+'-candidates',{})
            candidates.update({r['key']:add_candidate(r) for r in visible})
            # Keep only selected or current rows; no unbounded customer cache.
            for identity in list(candidates):
                if identity not in keys and identity not in selected:candidates.pop(identity)
            eligible=[k for k in selected if candidates.get(k)]
            can_add=row['status']=='ACTIVE' and bool(row['config'].get('published_version')) and os_accounts.is_admin(user)
            if controls[4].button('Add to Flow',key=slot+'-add',disabled=not eligible or not can_add or len(eligible)>100,
                    help='Select eligible orders (maximum 100). Publish/resume and administrator confirmation are required; the worker freshly verifies consent, suppression and payment.'):
                st.session_state['lifecycle-enroll-confirm']=(str(row['id']),eligible)
            pending=st.session_state.get('lifecycle-enroll-confirm')
            if pending and pending[0]==str(row['id']):confirm_enrollment(store,user,*pending)
        labels=['Email','Consent','Flow','Stage','Last email','Next email']
        if kind=='post_purchase':labels+=['Order','Payment','Fulfilment']
        elif kind=='win_back':labels+=['Inactive days','Paid orders','Customer value']
        else:labels+=['Purchased','Source']
        columns=[dict(label=v,name=v,enabled=True) for v in labels]
        if kind=='post_purchase':
            labels=['Order','Fulfilment','Flow']
            columns=[dict(label=v,name=v,enabled=True) for v in labels]
            active_flow=row['config'].get('published_flow') or row['config']['draft']
            columns += [dict(id=s['step_id'],label='Email '+str(i+1),name=s.get('name') or 'Email '+str(i+1),enabled=s.get('enabled',True)) for i,s in enumerate(active_flow['emails'])]
        rows=[]
        for r in visible:
            values=[r['email'],r['consent'],'Suppressed' if r['suppressed'] else r['flow_state'] or 'Not enrolled',r['stage'] or '—',r.get('last_email') or 'No emails',display(r['next_due_at'])]
            if kind=='post_purchase':values += [r['order_name'] or r['key'],r['financial_status'],r['fulfillment_status'] or 'Unknown']
            elif kind=='win_back':values += [(at-date(r['last_paid_at'])).days if r['last_paid_at'] else '—',r['order_count'],str(r['lifetime_value'])+' '+str(r['currency'] or '') if r['lifetime_value'] is not None else 'Not verified']
            else:values += ['Yes' if r['order_count'] else 'No',r['source'] or 'Not provided']
            cells=[dict(label=str(v or '—'),tone='muted') for v in values]
            if kind=='post_purchase':
                values=[r['order_name'] or r['key'],str(r['fulfillment_status'] or 'Unfulfilled').replace('_',' ').capitalize(),
                    'Suppressed' if r['suppressed'] else r['flow_state'] or {'QUEUED':'Awaiting verification','CHECKING':'Verifying eligibility','FAILED':'Not eligible'}.get(r.get('enrollment_request_state'),'Not enrolled')]
                cells=[dict(label=str(v or '—'),tone='muted',reason=r.get('enrollment_request_result') or '') for v in values]+email_cells({**r,'automation_status':row['status']},active_flow,at)
            rows.append(dict(key=r['key'],customer=r['name'] or r['email'] or r['customer_id'] or 'Guest',created=display(r['audience_at']),created_full=display(r['audience_at']),cells=cells))
        component=components.declare_component('crm_checkout_table',path=str(Path(__file__).parent/'components/crm_checkout_table'))
        import json
        context=json.dumps((criteria,page),default=str)
        st.session_state[slot+'-table-context']=context
        st.session_state[slot+'-visible']=sorted(keys)
        event=render_component(component,rows=rows,columns=columns,selected=selected,server_now=at,read_at=last.get(page_key,(at,))[0],refresh_seconds=15,
            table_label=titles[kind],date_label={'welcome':'Subscribed','post_purchase':'Order date','win_back':'Last purchase'}[kind],
            empty_label='No matching '+titles[kind].lower(),phase=phase,key=slot+'-table',default=None,
            **(dict(presentation='orders',selection_context=context,on_change=lambda:order_event(slot)) if orders_open else {}))
        new_event=bool(event and event.get('sequence')!=st.session_state.get(slot+'-event'))
        if not orders_open:selection(st.session_state,slot,keys,event)
        if new_event and not orders_open:
            if event.get('refresh'):st.session_state[slot+'-refresh']=generation+1
            st.rerun(scope='fragment')
        previous,next_col=st.columns(2)
        if previous.button('Previous',disabled=page==0,key=slot+'-previous'):
            st.session_state[slot+'-page']=page-1;st.rerun(scope='fragment')
        if next_col.button('Next',disabled=len(records)<=50,key=slot+'-next'):
            st.session_state[slot+'-page']=page+1;st.rerun(scope='fragment')
        if not orders_open:st.caption(('Draft selection / preview only' if row['status']=='DRAFT' else 'Published sequence · fresh eligibility before delivery')+' · no automatic historical replay. Page '+str(page+1))
        chosen=next((r for r in visible if r['key']==st.session_state.get(slot+'-detail')),None)
        if chosen:
            st.subheader(chosen['name'] or chosen['email'])
            st.caption(chosen['customer_id']+' · consent verified '+display(chosen['verified_at']))
            if kind=='post_purchase':
                st.caption('Email: '+chosen['email']+' · Payment: '+chosen['financial_status']+' · Marketing consent: '+chosen['consent'])
            customer_number=chosen['customer_id'].rsplit('/',1)[-1]
            domain=__import__('os').getenv('SHOPIFY_STORE_DOMAIN','').removeprefix('https://').split('.')[0]
            if domain and customer_number.isdigit():st.link_button('Shopify customer','https://admin.shopify.com/store/'+domain+'/customers/'+customer_number)
            try:
                data=customer_preview(store,row,chosen['customer_id'],chosen['key'] if kind=='post_purchase' else None)
                st.caption('Eligibility: '+(data['reason'] or 'Eligible; delivery requires an active published sequence'))
                st.dataframe([{'Email':s['name'],'Status':s['state'],'Scheduled preview':display(s['due_at']),'Timing source':s['anchor'],'Hold':s['reason']} for s in data['stages']],hide_index=True,width='stretch')
                if st.button('Stage eligibility preview',key=slot+'-stage',disabled=not data['eligible'] or row['status']!='DRAFT'):
                    stage(store,user,row,chosen['customer_id'],chosen['key'] if kind=='post_purchase' else None)
                    st.success('Preview staged for review. No customer enrolled and no email queued.')
                history=store.q('''SELECT s.step_index+1 AS email,s.status,s.first_submitted_at,s.error_code,e.event_type,e.occurred_at
                  FROM crm_marketing_sends s LEFT JOIN crm_delivery_events e ON e.send_id=s.id
                  WHERE s.shopify_customer_id=%s AND NOT s.test_send ORDER BY s.created_at DESC,e.occurred_at DESC LIMIT 100''',(chosen['customer_id'],))
                st.dataframe(history,hide_index=True,width='stretch') if history else st.caption('No recorded customer email activity.')
                with st.expander('Order and product history'):
                    for order in data['orders']:
                        number=order['id'].rsplit('/',1)[-1]
                        if domain and number.isdigit():st.link_button(str(order['name'] or order['id']),'https://admin.shopify.com/store/'+domain+'/orders/'+number)
                        else:st.write(str(order['name'] or order['id']))
                        st.caption(str(order['displayFinancialStatus'])+' · '+str(order['displayFulfillmentStatus']))
                        issues=[key for key in ('cancelledAt','fraudulent','disputed','unresolved_return') if order.get(key)]
                        if issues:st.caption('Follow-ups held: '+', '.join(issues))
                        for product in order['products']:
                            st.write(product.get('title') or product.get('name') or product.get('id'))
                            image=product.get('image') or (product.get('product') or {}).get('featuredImage') or {}
                            url=image.get('url') or image.get('src') if isinstance(image,dict) else None
                            if url and url.startswith('https://cdn.shopify.com/'):st.image(url,width=100)
            except (ValueError,StoreUnavailable) as exc:st.warning(str(exc))
        if kind=='post_purchase':
            with st.popover('Delivery timing fallback'):
                flow=row['config']['draft'];enabled=st.checkbox('Allow verified fulfilment fallback',value=flow.get('fulfilment_fallback_days') is not None)
                days=st.number_input('Days after verified fulfilment',min_value=14,max_value=90,value=flow.get('fulfilment_fallback_days') or 14)
                if st.button('Save fallback'):
                    from copy import deepcopy
                    from crm_flow_page import commit
                    draft=deepcopy(flow);draft['fulfilment_fallback_days']=days if enabled else None
                    commit(store,user,row,draft)
        if row['config'].get('lifecycle_previous'):
            with st.expander('Preserved legacy draft and audit snapshot'):
                st.json(row['config']['lifecycle_previous'])
                saved=row['config']['lifecycle_previous'].get('emails',[])
                if saved:
                    source=st.selectbox('Preserved email',range(len(saved)),format_func=lambda i:saved[i].get('name') or 'Email '+str(i+1),key=slot+'-preserved-source')
                    target=st.selectbox('Draft email to replace',range(len(row['config']['draft']['emails'])),format_func=lambda i:row['config']['draft']['emails'][i]['name'],key=slot+'-preserved-target')
                    st.caption('Copies the preserved content into the selected shared-editor draft. Both prior versions remain in audit history.')
                    if st.button('Restore preserved content to selected draft',key=slot+'-restore'):
                        from copy import deepcopy
                        from crm_flow_page import commit
                        draft=deepcopy(row['config']['draft']);draft['emails'][target]['document']=deepcopy(saved[source]['document'])
                        commit(store,user,row,draft)
