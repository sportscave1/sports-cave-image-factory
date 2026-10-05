"""One dialog refresh owner; bounded cached reads never mutate UI state."""
from crm_automation_read_cache import isolated
from html import escape
from time import monotonic
from concurrent.futures import Future
import streamlit as st
from crm_automation_read_cache import job,resolve,dispose,pack
from crm_checkout_analytics import PERIODS,window,checkouts,report,disabled_reason,reconcile
from crm_automation_analytics import activity,add_to_flow
from crm_logic import now

def state():return st.session_state.setdefault('automation_analytics_reads',{})

def read(store,key,fn,ttl=180):
    def verified():
        value=fn()
        if key[0]=='analytics-report':
            required=('sent','delivered','opened','clicked','conversions','history','revenue')
            if not isinstance(value,list) or len(value)!=1 or not isinstance(value[0],dict) or any(value[0].get(k) is None for k in required):raise ValueError('Incomplete analytics report')
        return value
    future=job(state(),store,key,verified,ttl=ttl)
    if key[0] in ('analytics-definition','checkout-list') and future is not None and not future.done():
        try:future.result(timeout=.05)
        except Exception:pass
    data,phase=resolve(state(),store,key,future)
    if phase in ('LOADING','REFRESHING'):st.session_state['automation-analytics-pending']=True
    return data,phase

def arm(key,seconds):
    """One shot, fragment-only refresh. No server timer per checkout."""
    from crm_automation_home import arm_section
    arm_section(key,max(1,seconds),dialog=True)

def patch_checkout(store,identity,checkout):
    """Replace only the mutated row in resolved date-range tables; fence old reads."""
    cache=state().setdefault('campaign_home_cache',{});resolved=state().setdefault('campaign_home_resolved',{})
    for token,records in list(resolved.items()):
        if token[0]!=store.connect or token[1][:2]!=('checkout-list',str(identity)):continue
        updated=[checkout if c['checkout_key']==checkout['checkout_key'] else c for c in records]
        future=Future();future.set_result(pack(updated));cache[token]=(monotonic(),future);resolved[token]=pack(updated)

def invalidate_activity(store,identity):
    cache=state().get('campaign_home_cache',{})
    for token in list(cache):
        if token[0]==store.connect and token[1][:2]==('analytics-activity',str(identity)):cache.pop(token)

def safe_add_error(exc):
    text=str(exc).lower()
    if any(k in text for k in ('recovered','completed')):return 'Checkout is recovered or unavailable.'
    if 'already' in text or 'ineligible' in text:return 'Already in flow or customer not eligible. No new journey was created.'
    if 'identity' in text or 'signed' in text:return 'Verified checkout identity is missing or changed. Refresh checkout details.'
    if 'abandon' in text and 'wait' in text or 'not yet abandoned' in text:return 'Checkout still inside abandonment wait period.'
    if 'active' in text or 'published' in text:return 'Flow is not live.'
    if 'shopify' in text or 'capability' in text:return 'Latest Shopify verification temporarily unavailable.'
    return 'Unable to verify this checkout safely. Refresh details and retry.'

def stats(value):
    cards=''.join('<div><dt>'+key.title()+'</dt><dd>'+escape(format(value[key],',') if value else '—')+'</dd></div>' for key in ('sent','delivered','opened','clicked','conversions'))
    st.html('''<style>.sc-analytics-stats{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:8px 0}
    .sc-analytics-stats>div{padding:10px;border:1px solid #e8e6df;border-radius:9px;background:#fffefa;min-width:0}
    .sc-analytics-stats dt{font-size:12px;color:#73747c}.sc-analytics-stats dd{font-size:22px;font-weight:600;margin:4px 0 0;font-variant-numeric:tabular-nums}
    @media(max-width:750px){.sc-analytics-stats{grid-template-columns:repeat(3,minmax(0,1fr))}}
    @media(max-width:390px){.sc-analytics-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}</style><dl class="sc-analytics-stats">'''+cards+'</dl>')

def checkout_details(store,user,row,c):
    from crm_checkout_identity import display_name,reference,recovery_status
    with st.expander('Checkout details · '+reference(c),expanded=True):
        data=c.get('analytics') or {};sends=c.get('sends') or []
        facts={'Customer':display_name(c),'Email':data.get('email') or 'Missing email',
          'Region':data.get('region') or data.get('country') or '—','Created':str(c['created_at']),
          'Checkout ID':c.get('admin_checkout_id'),'Recovery status':recovery_status(c),
          'Checkout detected':True,'Identity resolved':display_name(c)!='Guest',
          'Email present':bool(data.get('email')),'Flow enrolled':bool(c.get('enrollment_id')),
          'Suppressed':store.suppressed(c.get('customer_id'),__import__('crm_logic').recipient_hash(data.get('email'))),
          'Next email due':str(c.get('next_due_at') or 'None'),
          'Email queued':any(s['status'] in ('PENDING','CLAIMED','SUBMITTING') for s in sends),
          'Last automation error':next((s['error'] for s in reversed(sends) if s.get('error')),c.get('stop_reason') or 'None'),
          'Last eligibility result':(c.get('evaluation') or {}).get('result') or 'Not evaluated',
          'Recovered order':c.get('order_id'),'Recovered timestamp':data.get('completed_at'),
          'Opened':c.get('opened',0),'Clicked':c.get('clicked',0)}
        st.table([{'Detail':k,'Value':str(v) if v is not None else 'None'} for k,v in facts.items()])
        if sends:st.dataframe(sends,hide_index=True)
        for send in sends:
            if send['status']=='FAILED' and send.get('error')=='provider_rejected':
                if st.button('Retry rejected email',key='checkout-retry-'+str(send['id'])):
                    from crm_checkout_identity import retry_send
                    if retry_send(store,user,send['id']):st.success('Retry scheduled; the worker will recheck consent and recovery.')
                    else:st.warning('Not eligible for retry.')
        st.button('Close details',key='checkout-close-'+str(row['id']),on_click=lambda:st.session_state.pop('auto-checkouts-'+str(row['id'])+'-detail',None))


@isolated
def checkout_panel(shop,store,user,row,bounds,period):
    # Scope every override to this panel or the dialog containing it.
    st.html('''<style>
    div[role="dialog"]:has(.st-key-checkout-compact)>div:first-child{padding:12px 24px 4px!important}
    div[role="dialog"]:has(.st-key-checkout-compact)>div:nth-child(2){padding:4px 24px 16px!important}
    div[role="dialog"]:has(.st-key-checkout-compact) [data-testid="stVerticalBlock"]{gap:.5rem}
    .st-key-checkout-compact [data-testid="stVerticalBlock"]{gap:.5rem}
    .st-key-checkout-compact h3{padding:0;font-size:1.2rem;line-height:2rem}
    .st-key-checkout-compact [data-testid="stHorizontalBlock"]{gap:.5rem;align-items:center}
    .st-key-checkout-compact [data-baseweb="select"]>div{min-height:32px;height:32px}
    .st-key-checkout-compact [data-baseweb="input"]{height:32px;min-height:32px}
    .st-key-checkout-compact [data-testid="stButton"] button{min-height:32px;padding:.2rem .65rem}
    .st-key-checkout-compact [data-testid="stButton"] button p{font-size:13px}
    </style>''')
    with st.container(key='checkout-compact'):
        _checkout_panel(shop,store,user,row,bounds,period)


def _checkout_panel(shop,store,user,row,bounds,period):
    from pathlib import Path
    import streamlit.components.v1 as components
    from crm_component_json import render_component
    from crm_checkout_identity import display_name,reference,recovery_status
    from crm_checkout_timing_ui import time_to_send
    slot='auto-checkouts-'+str(row['id']);key=('checkout-list',str(row['id']),period)
    heading,status=st.columns([4,1]);heading.subheader('Abandoned checkouts')
    status.selectbox('Checkout status',['Incomplete'],label_visibility='collapsed',key=slot+'-status')
    search_column,actions=st.columns([1.2,1.5],vertical_alignment='center')
    search=search_column.text_input('Search and filter',placeholder='Checkout, customer name or email',label_visibility='collapsed',key=slot+'-search')
    records,phase=read(store,key,lambda:checkouts(store,row['id'],window(period)),60)
    if records is None:
        st.caption('Loading abandoned checkouts…' if phase!='ERROR' else 'Checkout records temporarily unavailable.');return
    needle=search.strip().casefold()
    visible=[c for c in records if not needle or needle in ' '.join((reference(c),display_name(c),str((c.get('analytics') or {}).get('email') or ''),str(c.get('admin_checkout_id') or ''))).casefold()]
    keys={c['checkout_key'] for c in visible}
    selected=[k for k in st.session_state.get(slot+'-selected',[]) if k in keys]
    with actions.container(horizontal=True):
        refresh=st.button('Refresh checkout details',key=slot+'-reconcile',help='Repair Shopify details only; never enrol or send')
        add=st.button('Add to flow',disabled=not selected,key=slot+'-add',type='primary')
    if refresh:
        try:
            counts,more=reconcile(shop,store,period)
            st.session_state[slot+'-results']=[{'Result':k,'Rows':v} for k,v in counts.items()]
            if more:st.session_state[slot+'-results'].append({'Result':'More rows remain; refresh resumes from the saved cursor','Rows':0})
            state().get('campaign_home_cache',{}).pop((store.connect,key),None)
            st.rerun(scope='fragment')
        except Exception:st.warning('Shopify refresh unavailable. Saved records retained.')
    if add:
        results=[]
        for c in visible:
            if c['checkout_key'] not in selected:continue
            reason=disabled_reason(c,row)
            if not reason:
                try:
                    add_to_flow(shop,store,user,str(row['id']),c['admin_checkout_id']);reason='Added to flow'
                except ValueError as exc:
                    message=str(exc);allowed=('Already in flow','Recovered','Missing email','Invalid email','Suppressed','Unsubscribed','Not eligible')
                    reason=next((x for x in allowed if message.startswith(x)),safe_add_error(exc))
                except Exception:reason='Error: verification unavailable; retry'
            results.append({'Checkout':reference(c),'Result':reason})
        st.session_state[slot+'-results']=results
        state().get('campaign_home_cache',{}).pop((store.connect,key),None)
        st.rerun(scope='fragment')
    if st.session_state.get(slot+'-results'):st.dataframe(st.session_state[slot+'-results'],hide_index=True)
    if phase=='ERROR':st.caption('Refresh unavailable. Last verified records retained.')
    listing=[{'key':c['checkout_key'],'reference':reference(c),'created':str(c['created_at'])[:16]+' UTC',
      'customer':display_name(c),'region':(c.get('analytics') or {}).get('region') or (c.get('analytics') or {}).get('country') or '—',
      'status':recovery_status(c),'time_to_send':time_to_send(c)} for c in visible]
    component=components.declare_component('crm_checkout_table',path=str(Path(__file__).parent/'components/crm_checkout_table'))
    event=render_component(component,rows=listing,selected=selected,key=slot+'-table',default=None)
    if event and event.get('sequence')!=st.session_state.get(slot+'-event'):
        st.session_state[slot+'-event']=event['sequence']
        st.session_state[slot+'-selected']=[k for k in event.get('selected',[]) if k in keys]
        if event.get('detail') in keys:st.session_state[slot+'-detail']=event['detail']
        st.rerun(scope='fragment')
    chosen=next((c for c in visible if c['checkout_key']==st.session_state.get(slot+'-detail')),None)
    if chosen:checkout_details(store,user,row,chosen)

@isolated
def secondary(store,row,bounds,period,charts=False):
    slot='auto-analytics-'+str(row['id'])
    if row['trigger_type']=='abandoned' and not st.session_state.get('analytics-primary-ready-'+str(row['id'])):
        if not charts:stats(None)
        st.session_state['automation-analytics-pending']=True;return
    data,phase=read(store,('analytics-report',str(row['id']),period),lambda:[report(store,row['id'],window(period))])
    value=data[0] if data else None
    if not charts:
        stats(value)
        if phase=='ERROR':st.caption('Performance refresh unavailable. Last verified values are retained.')
        return
    if value:
        st.caption('Send/order metrics use event occurrence within the selected UTC period. Checkout rows use creation date.')
        if value['history']:st.line_chart(value['history'],x='day',y=['sent','delivered','opened','clicked'],height=180)
        else:st.caption('No accepted sends in this reporting period.')
        from crm_automation_home import money
        st.caption('Revenue · '+money(value['revenue']))
    if phase=='ERROR':st.caption('Performance refresh unavailable. Last verified values are retained.')
    events,event_phase=read(store,('analytics-activity',str(row['id']),period),lambda:activity(store,row['id'],12,bounds=window(period)))
    st.subheader('Recent activity')
    if events:
        from crm_automation_home import activity_html
        st.html(activity_html(events))
    elif events is not None:st.caption('No recorded activity in this reporting period.')

@isolated
def content(shop,store,user,identity,period,bounds):
    # Keep initial-load scheduling above the fold even on narrow dialogs. The
    # dialog owns all controls; nested fragments caused duplicate widget IDs.
    poll=st.container();st.session_state['automation-analytics-pending']=False
    rows,phase=read(store,('analytics-definition',str(identity)),lambda:[store.get('automations',identity)],60)
    if not rows:
        with poll:arm('auto-analytics-definition-poll',1 if phase!='ERROR' else 30)
        st.dataframe({'Checkout':[],'Created':[],'Customer name':[],'Region':[],'Recovery status':[]},height=360,hide_index=True)
        st.caption('Loading automation…' if phase!='ERROR' else 'Automation details temporarily unavailable.')
        return
    row=rows[0]
    if not row or row['config'].get('deleted_at'):st.warning('Automation unavailable.');return
    if row['trigger_type']=='abandoned':
        checkout_panel(shop,store,user,row,window('All time'),'All time')
        with poll:arm('auto-analytics-definition-poll',1 if st.session_state.get('automation-analytics-pending') else 30)
        return
    st.subheader('Automation analytics')
    st.caption(row['name'])
    period=st.selectbox('Date range',list(PERIODS),index=1,key='auto-analytics-period-'+str(identity))
    bounds=window(period)
    # Containers reserve KPI position while primary work is submitted first.
    metrics=st.container();primary=st.container();chart=st.container()
    with primary:
        if row['trigger_type']=='abandoned':checkout_panel(shop,store,user,row,bounds,period)
        else:
            from crm_automation_home_data import step_metrics
            steps,_=read(store,('analytics-steps',str(identity)),lambda:step_metrics(store,identity))
            if steps is not None:st.dataframe(steps,hide_index=True,width='stretch')
    with metrics:secondary(store,row,bounds,period)
    with chart:secondary(store,row,bounds,period,charts=True)
    with poll:arm('auto-analytics-definition-poll',1 if st.session_state.get('automation-analytics-pending') else 30)

def render(shop,store,user,identity,name=None):
    previous=state().get('owner')
    if previous!=str(identity):
        dispose(state());state()['owner']=str(identity)
    # The operational checkout panel owns its title; other flow headings render below.
    period=st.session_state.get('auto-analytics-period-'+str(identity),'Last 30 days')
    slot='auto-analytics-window-'+str(identity)
    current=st.session_state.get(slot)
    if not current or current[0]!=period:current=(period,window(period));st.session_state[slot]=current
    content(shop,store,user,identity,period,current[1])
