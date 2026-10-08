"""Shared analytics reads and checkout controls used by the unified Flow page."""
from crm_automation_read_cache import isolated
from html import escape
from time import monotonic
from concurrent.futures import Future
import streamlit as st
from crm_automation_read_cache import job,resolve,dispose,pack
from crm_checkout_analytics import PERIODS,window,checkouts,report,reconcile
from crm_automation_analytics import activity
from crm_logic import now

def state():return st.session_state.setdefault('automation_analytics_reads',{})

def read(store,key,fn,ttl=180):
    def verified():
        value=fn()
        if key[0] in ('analytics-report','flow-summary'):
            required=('sent','delivered','opened','clicked','conversions','history','revenue')+ (('orders',) if key[0]=='flow-summary' else ())
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
    patch_checkouts(store,identity,[checkout])


def patch_checkouts(store,identity,checkouts):
    """Patch a batch in one pass through each cache, without reloading the list."""
    replacements={c['checkout_key']:c for c in checkouts}
    cache=state().setdefault('campaign_home_cache',{});resolved=state().setdefault('campaign_home_resolved',{})
    for token,records in list(resolved.items()):
        if token[0]!=store.connect or token[1][:2]!=('checkout-list',str(identity)):continue
        updated=[replacements.get(c['checkout_key'],c) for c in records]
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
def checkout_panel(shop,store,user,row,bounds,period,*,paginated=False):
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
    .st-key-checkout-compact [data-testid="stCustomComponentV1"]{min-width:0;max-width:100%}
    .st-key-checkout-compact iframe{width:100%!important;max-width:100%;min-width:0}
    </style>''')
    with st.container(key='checkout-compact'):
        _checkout_panel(shop,store,user,row,bounds,period,paginated=paginated)


def _checkout_panel(shop,store,user,row,bounds,period,*,paginated=False):
    from pathlib import Path
    import streamlit.components.v1 as components
    from crm_component_json import render_component
    from crm_checkout_identity import display_name,reference
    from crm_checkout_progress import columns,listing
    from os_accounts import timezone_for_user
    slot='auto-checkouts-'+str(row['id']);key=('checkout-list',str(row['id']),period)
    heading,status=st.columns([4,1]);heading.subheader('Abandoned checkouts')
    status.selectbox('Checkout status',['Incomplete'],label_visibility='collapsed',key=slot+'-status')
    search_column,actions=st.columns([1.2,1.5],vertical_alignment='center')
    search=search_column.text_input('Search and filter',placeholder='Checkout, customer name or email',label_visibility='collapsed',key=slot+'-search')
    if paginated:
        criteria=(period,search.strip())
        if st.session_state.get(slot+'-criteria')!=criteria:
            st.session_state[slot+'-criteria']=criteria;st.session_state[slot+'-cursors']=[None]
        cursors=st.session_state.setdefault(slot+'-cursors',[None]);cursor=cursors[-1]
        key+=('page',search.strip(),cursor)
        records,phase=read(store,key,lambda:checkouts(store,row['id'],window(period),page_size=51,after=cursor,search=search),12)
    else:
        records,phase=read(store,key,lambda:checkouts(store,row['id'],window(period)),12)
    if records is None:
        st.caption('Loading abandoned checkouts…' if phase!='ERROR' else 'Checkout records temporarily unavailable.');return
    more=bool(paginated and len(records)>50)
    if paginated:records=records[:50]
    from crm_checkout_enrollment_ui import progress,begin
    enrollment_results,busy=progress(store,row,records,slot)
    needle=search.strip().casefold()
    visible=records if paginated else [c for c in records if not needle or needle in ' '.join((reference(c),display_name(c),str((c.get('analytics') or {}).get('email') or ''),str(c.get('admin_checkout_id') or ''))).casefold()]
    keys={c['checkout_key'] for c in visible}
    selected=[k for k in st.session_state.get(slot+'-selected',[]) if k in keys]
    available=[k for k in selected if k not in busy]
    if paginated and any(k not in keys for k in st.session_state.get(slot+'-selected',[])):
        st.caption('Selections on other pages are retained. Add to flow applies to this page’s selected checkouts.')
    with actions.container(horizontal=True):
        refresh=st.button('Refresh checkout details',key=slot+'-reconcile',help='Repair Shopify details only; never enrol or send')
        add=st.button('Add to flow',disabled=not available,key=slot+'-add',type='secondary')
    if refresh:
        st.session_state.pop(slot+'-timing',None)
        try:
            counts,more=reconcile(shop,store,period)
            from crm_checkout_enrollment_requests import reconcile_requests
            reconcile_requests(store)
            st.session_state[slot+'-results']=[{'Result':k,'Rows':v} for k,v in counts.items()]
            if more:st.session_state[slot+'-results'].append({'Result':'More rows remain; refresh resumes from the saved cursor','Rows':0})
            for token in list(state().get('campaign_home_cache',{})):
                if token[0]==store.connect and token[1][:2]==('checkout-list',str(row['id'])):
                    state()['campaign_home_cache'].pop(token,None)
                    for group in ('automation_read_terminal','automation_read_started'):state().get(group,{}).pop(token,None)
            st.rerun(scope='fragment')
        except Exception:st.warning('Shopify refresh unavailable. Saved records retained.')
    if add:
        begin(store,user,str(row['id']),available,slot)
        st.rerun(scope='fragment')
    if st.session_state.get(slot+'-results'):st.dataframe(st.session_state[slot+'-results'],hide_index=True)
    if phase=='ERROR':st.caption('Refresh unavailable. Last verified records retained.')
    for checkout in visible:
        if checkout['checkout_key'] in enrollment_results:
            checkout['enrollment_request']=enrollment_results[checkout['checkout_key']]
    timing_now=now()
    # Published metadata arrives in the same bounded read as the journeys.
    # Never derive columns from the editable draft or match across versions by index.
    published=records[0].get('published_steps') if records else None
    if published is None:published=(row.get('config',{}).get('published_flow') or {}).get('emails',row.get('steps',[]))
    schema=columns(published)
    rows=listing(visible,schema,timezone_for_user(user),timing_now)
    component=components.declare_component('crm_checkout_table',path=str(Path(__file__).parent/'components/crm_checkout_table'))
    event=render_component(component,rows=rows,columns=schema,selected=selected,
      server_now=timing_now,read_at=records[0].get('read_at') if records else timing_now,
      refresh_seconds=15,phase=phase,key=slot+'-table',default=None)
    if event and event.get('sequence')!=st.session_state.get(slot+'-event'):
        st.session_state[slot+'-event']=event['sequence']
        elsewhere=[k for k in st.session_state.get(slot+'-selected',[]) if k not in keys] if paginated else []
        st.session_state[slot+'-selected']=elsewhere+[k for k in event.get('selected',[]) if k in keys]
        if event.get('detail') in keys:st.session_state[slot+'-detail']=event['detail']
        retry=event.get('retry')
        if retry in keys and retry not in busy and enrollment_results.get(retry,{}).get('state')=='FAILED':
            begin(store,user,str(row['id']),[retry],slot)
        if not event.get('refresh'):st.rerun(scope='fragment')
    chosen=next((c for c in visible if c['checkout_key']==st.session_state.get(slot+'-detail')),None)
    if chosen:checkout_details(store,user,row,chosen)
    if paginated:
        with st.container(horizontal=True):
            if st.button('Previous checkouts',disabled=len(cursors)==1,key=slot+'-previous'):
                cursors.pop();st.rerun(scope='fragment')
            st.caption('Page '+str(len(cursors))+' · '+str(len(visible))+' checkouts')
            if st.button('Next checkouts',disabled=not more,key=slot+'-next'):
                last=records[-1];cursors.append((str(last['created_at']),last['checkout_key']));st.rerun(scope='fragment')

def render(shop,store,user,identity,name=None):
    """Compatibility navigation for callers of the old analytics destination."""
    from crm_automation_ui import open_flow
    open_flow(identity)
