"""Lifecycle audiences on the existing Flow page and checkout table component."""
from datetime import datetime, time, timedelta
import streamlit as st
from crm_lifecycle_audience import listing,customer_preview,stage
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
    from crm_flow_recipients import panel
    from crm_flow_recipient_adapters import adapter_for
    panel(adapter_for(row).title,'lifecycle-'+str(row['id']),_audience,store,user,row)


# Compatibility for callers of the former order-only callback.
from crm_flow_recipients import table_event as order_event


@st.fragment
def _audience(store,user,row):
    from os_accounts import timezone_for_user
    from zoneinfo import ZoneInfo
    from crm_store import StoreUnavailable
    from crm_flow_recipients import current_definition
    row=current_definition(row)
    slot='lifecycle-'+str(row['id']);kind=row['trigger_type']
    zone=ZoneInfo(timezone_for_user(user))
    def display(value):
        value=date(value)
        return value.astimezone(zone).strftime('%d %b %Y %H:%M %Z') if value else '—'
    from crm_flow_recipient_adapters import adapter_for,project,LIFECYCLE
    from crm_flow_recipients import table,retry_read,read_page,STYLE
    st.html(STYLE)
    adapter=adapter_for(row)
    native=not row['config']['draft'].get('lifecycle_version')
    loader=listing
    if native:
        from crm_native_audience import listing as loader
    # All lifecycle sources use the same compact checkout-master surface.
    with st.container(key='checkout-compact'):
        with st.container(key='flow-recipient-toolbar'):
            controls=st.columns([3,1.15,1.15,.5,1] if adapter.enrollment else [3,1.15,1.15,.5])
            search_col,filter_col,sort_col=controls[:3]
            search=search_col.text_input('Search and filter',key=slot+'-search',placeholder=adapter.search,label_visibility='collapsed')
        filter_by=filter_col.selectbox('Status',adapter.filters,key=slot+'-filter',label_visibility='collapsed')
        sorts=adapter.sorts
        sort=sort_col.selectbox('Sort',sorts,index=sorts.index(adapter.default_sort),key=slot+'-sort',label_visibility='collapsed')
        with controls[3]:
            with st.container(key='flow-recipient-dates'):
                dates=st.popover('Date filters',icon=':material/calendar_month:',help='Filter '+adapter.date_label.lower())
        with dates:
            start=st.date_input('From',value=None,key=slot+'-from')
            end=st.date_input('Through',value=None,key=slot+'-through')
        st.html('<style>.st-key-flow-recipient-dates button{box-shadow:'+('inset 0 0 0 2px #9a7937' if start or end else 'none')+'!important}</style>')
        from crm_flow_recipients import retain
        retain(slot)  # Preserve user input even while its new page is still loading.
        criteria=(search,filter_by,sort,start,end)
        if st.session_state.get(slot+'-criteria')!=criteria:
            st.session_state[slot+'-criteria']=criteria;st.session_state[slot+'-page']=0
        page=st.session_state.get(slot+'-page',0)
        if start and end and start>end:st.warning('Choose an end date after the start date.');return
        begin=datetime.combine(start,time.min,zone) if start else None
        until=datetime.combine(end+timedelta(days=1),time.min,zone) if end else None
        generation=st.session_state.get(slot+'-refresh',0)
        key=('lifecycle-audience',str(row['id']),row.get('updated_at'),criteria,page,generation)
        records,phase,read_at=read_page(store,slot,key,
            lambda:loader(store,row,search=search,filter_by=filter_by,sort=sort,start=begin,end=until,page=page),30)
        with st.container(key=slot+'-read-notice'):
            if records is None:
                st.caption('Loading audience…' if phase not in ('ERROR','TIMED_OUT') else 'Audience unavailable. Check database access and the audience migration.')
            elif phase in ('ERROR','TIMED_OUT'):
                st.caption('Refresh failed; last verified records shown.')
            retry_read(slot,phase)
        if records is None:
            if adapter.enrollment:controls[4].button('Add to Flow',key=slot+'-add',disabled=True)
            return
        visible=records[:50];at=now()
        st.session_state[slot+'-customers']=list({r['customer_id'] for r in visible if r['customer_id']})
        keys={r['key'] for r in visible}
        selected=st.session_state.get(slot+'-selected',[])
        if adapter.enrollment:
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
        columns,rows=project(adapter,row,visible,display,at)
        table(slot,(criteria,page),rows=rows,columns=columns,server_now=at,
            read_at=read_at,refresh_seconds=15,
            table_label=adapter.title,date_label=adapter.date_label,
            empty_label='No matching '+adapter.title.lower(),phase=phase)
        from crm_flow_recipients import pagination,close_details
        pagination(slot,page,len(visible),len(records)>50,
            lambda:st.session_state.update({slot+'-page':page-1}),
            lambda:st.session_state.update({slot+'-page':page+1}),noun=adapter.title.lower())
        chosen=next((r for r in visible if r['key']==st.session_state.get(slot+'-detail')),None)
        if chosen:close_details(slot)
        if chosen and native:
            st.subheader(chosen['name'] or chosen['customer_id'])
            st.dataframe(chosen.get('sends') or [],hide_index=True,width='stretch')
        if chosen and not native:
            st.subheader(chosen['name'] or chosen['email'])
            st.caption(str(chosen['customer_id'] or 'Customer unverified')+' · consent verified '+display(chosen['verified_at']))
            if adapter.enrollment:
                st.caption('Email: '+chosen['email']+' · Payment: '+chosen['financial_status']+' · Marketing consent: '+chosen['consent'])
            customer_number=str(chosen['customer_id'] or '').rsplit('/',1)[-1]
            domain=__import__('os').getenv('SHOPIFY_STORE_DOMAIN','').removeprefix('https://').split('.')[0]
            if domain and customer_number.isdigit():st.link_button('Shopify customer','https://admin.shopify.com/store/'+domain+'/customers/'+customer_number)
            try:
                def details():
                    data=customer_preview(store,row,chosen['customer_id'],chosen['key'] if kind=='post_purchase' else None)
                    history=store.q('''SELECT s.step_index+1 AS email,s.status,s.first_submitted_at,s.error_code,e.event_type,e.occurred_at
                      FROM crm_marketing_sends s LEFT JOIN crm_delivery_events e ON e.send_id=s.id
                      WHERE s.shopify_customer_id=%s AND NOT s.test_send ORDER BY s.created_at DESC,e.occurred_at DESC LIMIT 100''',(chosen['customer_id'],))
                    return [dict(data=data,history=history)]
                detail_key=('recipient-detail',str(row['id']),row.get('updated_at'),chosen['key'],generation,st.session_state.get(slot+'-detail-refresh',0))
                detail,detail_phase,_=read_page(store,slot+'-detail',detail_key,details,30)
                if detail is None:
                    st.caption('Loading recipient details…' if detail_phase not in ('ERROR','TIMED_OUT') else 'Recipient details unavailable.')
                    retry_read(slot+'-detail',detail_phase);return
                data=detail[0]['data']
                st.caption('Eligibility: '+(data['reason'] or 'Eligible; delivery requires an active published sequence'))
                st.dataframe([{'Email':s['name'],'Status':s['state'],'Scheduled preview':display(s['due_at']),'Timing source':s['anchor'],'Hold':s['reason']} for s in data['stages']],hide_index=True,width='stretch')
                if st.button('Stage eligibility preview',key=slot+'-stage',disabled=not data['eligible'] or row['status']!='DRAFT'):
                    stage(store,user,row,chosen['customer_id'],chosen['key'] if kind=='post_purchase' else None)
                    st.success('Preview staged for review. No customer enrolled and no email queued.')
                history=detail[0]['history']
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
        if adapter.enrollment:
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
