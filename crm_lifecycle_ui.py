"""Lifecycle audiences on the existing Flow page and checkout table component."""
from pathlib import Path
from datetime import datetime, time, timedelta, timezone
import streamlit as st
from crm_automation_analytics_ui import read,arm
from crm_lifecycle_audience import listing,customer_preview,stage,SORTS,FILTERS
from crm_logic import now,date

@st.fragment
def audience(store,user,row):
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
    titles={'welcome':'Marketing subscribers','post_purchase':'Paid orders','win_back':'Inactive purchasers'}
    with st.expander(titles[kind],key=slot+'-panel',on_change='rerun') as panel:
        if not panel.open:return
        search_col,filter_col,sort_col=st.columns([2,1,1])
        search=search_col.text_input('Search and filter',key=slot+'-search',placeholder='Customer, email or Shopify ID')
        filter_by=filter_col.selectbox('Status',FILTERS,key=slot+'-filter')
        sort=sort_col.selectbox('Sort',list(SORTS),index=2 if kind=='win_back' else 0,key=slot+'-sort')
        with st.popover('Date filters'):
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
        if st.button('Refresh audience',key=slot+'-refresh-button'):
            st.session_state[slot+'-refresh']=generation+1;st.rerun(scope='fragment')
        key=('lifecycle-audience',str(row['id']),criteria,page,generation)
        records,phase=read(store,key,lambda:listing(store,row,search=search,filter_by=filter_by,sort=sort,start=begin,end=until,page=page),30)
        if records is None:
            st.caption('Loading audience…' if phase not in ('ERROR','TIMED_OUT') else 'Audience unavailable. Apply the audience migration and check background sync, then refresh.')
            if phase in ('LOADING','REFRESHING'):arm('lifecycle-audience',1)
            return
        if phase in ('ERROR','TIMED_OUT'):st.caption('Refresh failed; last verified records shown.')
        visible=records[:50];at=now()
        labels=['Email','Consent','Flow','Stage','Last email','Next email']
        if kind=='post_purchase':labels+=['Order','Payment','Fulfilment']
        elif kind=='win_back':labels+=['Inactive days','Paid orders','Customer value']
        else:labels+=['Purchased','Source']
        columns=[dict(label=v,name=v,enabled=True) for v in labels]
        rows=[]
        for r in visible:
            values=[r['email'],r['consent'],'Suppressed' if r['suppressed'] else r['flow_state'] or 'Draft preview',r['stage'] or '—',r['last_email'] or 'No emails',display(r['next_due_at'])]
            if kind=='post_purchase':values += [r['order_name'] or r['key'],r['financial_status'],r['fulfillment_status'] or 'Unknown']
            elif kind=='win_back':values += [(at-date(r['last_paid_at'])).days if r['last_paid_at'] else '—',r['order_count'],str(r['lifetime_value'])+' '+str(r['currency'] or '') if r['lifetime_value'] is not None else 'Not verified']
            else:values += ['Yes' if r['order_count'] else 'No',r['source'] or 'Not provided']
            rows.append(dict(key=r['key'],customer=r['name'] or r['email'] or r['customer_id'],created=display(r['audience_at']),created_full=display(r['audience_at']),
                cells=[dict(label=str(v or '—'),tone='muted') for v in values]))
        component=components.declare_component('crm_checkout_table',path=str(Path(__file__).parent/'components/crm_checkout_table'))
        event=render_component(component,rows=rows,columns=columns,selected=[],server_now=at,read_at=at,refresh_seconds=0,
            table_label=titles[kind],date_label={'welcome':'Subscribed','post_purchase':'Order date','win_back':'Last purchase'}[kind],
            empty_label='No matching '+titles[kind].lower(),phase=phase,key=slot+'-table',default=None)
        if event and event.get('detail') in {r['key'] for r in visible}:st.session_state[slot+'-detail']=event['detail']
        previous,next_col=st.columns(2)
        if previous.button('Previous',disabled=page==0,key=slot+'-previous'):
            st.session_state[slot+'-page']=page-1;st.rerun(scope='fragment')
        if next_col.button('Next',disabled=len(records)<=50,key=slot+'-next'):
            st.session_state[slot+'-page']=page+1;st.rerun(scope='fragment')
        st.caption('Draft / preview only · background Shopify reconciliation · no historical email replay. Page '+str(page+1))
        chosen=next((r for r in visible if r['key']==st.session_state.get(slot+'-detail')),None)
        if chosen:
            st.subheader(chosen['name'] or chosen['email'])
            st.caption(chosen['customer_id']+' · consent verified '+display(chosen['verified_at']))
            customer_number=chosen['customer_id'].rsplit('/',1)[-1]
            domain=__import__('os').getenv('SHOPIFY_STORE_DOMAIN','').removeprefix('https://').split('.')[0]
            if domain and customer_number.isdigit():st.link_button('Shopify customer','https://admin.shopify.com/store/'+domain+'/customers/'+customer_number)
            try:
                data=customer_preview(store,row,chosen['customer_id'],chosen['key'] if kind=='post_purchase' else None)
                st.caption('Eligibility: '+(data['reason'] or 'Eligible for future review; sending remains locked'))
                st.dataframe([{'Email':s['name'],'Status':s['state'],'Scheduled preview':display(s['due_at']),'Timing source':s['anchor'],'Hold':s['reason']} for s in data['stages']],hide_index=True,width='stretch')
                if st.button('Stage eligibility preview',key=slot+'-stage',disabled=not data['eligible']):
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
