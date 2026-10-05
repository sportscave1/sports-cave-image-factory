"""Independent, cached analytics panels. Read futures never mutate UI state."""
from html import escape
from time import monotonic
from concurrent.futures import Future
from uuid import uuid4
import streamlit as st
from crm_campaign_home_cache import job,resolve
from crm_checkout_analytics import PERIODS,window,checkouts,report,disabled_reason,reconcile
from crm_automation_analytics import flow_state,activity,add_to_flow
from crm_logic import now,date

def state():return st.session_state.setdefault('automation_analytics_reads',{})

def read(store,key,fn,ttl=30):
    def verified():
        value=fn()
        if key[0]=='analytics-report':
            required=('sent','delivered','opened','clicked','conversions','history','revenue')
            if not isinstance(value,list) or len(value)!=1 or not isinstance(value[0],dict) or any(value[0].get(k) is None for k in required):raise ValueError('Incomplete analytics report')
        return value
    data,phase=resolve(state(),store,key,job(state(),store,key,verified,ttl=ttl))
    if phase in ('LOADING','REFRESHING'):st.session_state['automation-analytics-pending']=True
    return data,phase

def arm(key,seconds):
    """One shot, fragment-only refresh. No server timer per checkout."""
    st.button('Refresh analytics status',key=key)
    st.html('<style>.st-key-'+key+'{display:none}</style><script>/* '+uuid4().hex+' */'+
      '(()=>{window.scAnalyticsTimers??={};const key='+repr(key)+';clearTimeout(window.scAnalyticsTimers[key]);'+
      'const tick=()=>{const b=document.querySelector(".st-key-"+key+" button");'+
      'if(!b?.closest("[role=dialog]"))return;if(document.hidden||document.querySelector("[role=listbox]")){window.scAnalyticsTimers[key]=setTimeout(tick,2000);return;}'+
      'if(b.disabled){window.scAnalyticsTimers[key]=setTimeout(tick,250);return;}b.click();window.scAnalyticsTimers[key]=setTimeout(tick,500);};window.scAnalyticsTimers[key]=setTimeout(tick,'+str(int(seconds*1000))+');})();</script>',unsafe_allow_javascript=True)

def patch_checkout(store,identity,checkout):
    """Replace only the mutated row in resolved date-range tables; fence old reads."""
    cache=state().setdefault('campaign_home_cache',{});resolved=state().setdefault('campaign_home_resolved',{})
    for token,records in list(resolved.items()):
        if token[0]!=store.connect or token[1][:2]!=('checkout-list',str(identity)):continue
        updated=[checkout if c['checkout_key']==checkout['checkout_key'] else c for c in records]
        future=Future();future.set_result(updated);cache[token]=(monotonic(),future);resolved[token]=updated

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

def checkout_view(c):
    return {'ledger':c,'completedAt':str(c['activity_at']) if c['status']=='RECOVERED' else None}

def countdown_html(c):
    from datetime import timedelta
    label,next_action=flow_state(checkout_view(c));due=date(c.get('next_due_at'))
    index=int(c.get('current_step') or 0);receipt=next((s for s in c.get('sends',[]) if s['step']==index),None)
    if receipt and receipt['status']=='ACCEPTED' and index+1<len(c.get('steps') or []):
        submitted=date(receipt.get('updated_at'));due=submitted+timedelta(seconds=c['steps'][index+1]['delay_seconds']) if submitted else None
    if 'pending' not in label:due=None
    ident='sc-checkout-countdown'
    stamp=int(due.timestamp()*1000) if due else None
    st.html('<small id="'+ident+'">'+escape(label+' · '+next_action)+'</small><script>/* '+uuid4().hex+' */'+
      '(()=>{clearInterval(window.scCheckoutCountdown);const due='+str(stamp if stamp is not None else 'null')+';'+
      'const label='+__import__('json').dumps(label)+';if(due===null)return;const tick=()=>{const node=document.getElementById("'+ident+'");'+
      'if(!node?.closest("[role=dialog]")){clearInterval(window.scCheckoutCountdown);return;}'+
      'const s=Math.max(0,Math.floor((due-Date.now())/1000));const pad=n=>String(n).padStart(2,"0");'+
      'node.textContent=label+" · "+(s?"Sends in "+pad(Math.floor(s/3600))+":"+pad(Math.floor(s%3600/60))+":"+pad(s%60):"Due · awaiting worker");};'+
      'tick();window.scCheckoutCountdown=setInterval(tick,1000);})();</script>',unsafe_allow_javascript=True)

def stats(value):
    cards=''.join('<div><dt>'+key.title()+'</dt><dd>'+escape(format(value[key],',') if value else '—')+'</dd></div>' for key in ('sent','delivered','opened','clicked','conversions'))
    st.html('''<style>.sc-analytics-stats{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:8px 0}
    .sc-analytics-stats>div{padding:10px;border:1px solid #e8e6df;border-radius:9px;background:#fffefa;min-width:0}
    .sc-analytics-stats dt{font-size:12px;color:#73747c}.sc-analytics-stats dd{font-size:22px;font-weight:600;margin:4px 0 0;font-variant-numeric:tabular-nums}
    @media(max-width:750px){.sc-analytics-stats{grid-template-columns:repeat(3,minmax(0,1fr))}}
    @media(max-width:390px){.sc-analytics-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}</style><dl class="sc-analytics-stats">'''+cards+'</dl>')

@st.fragment(run_every='20s')
def checkout_panel(shop,store,user,row,bounds,period):
    slot='auto-checkouts-'+str(row['id']);key=('checkout-list',str(row['id']),period)
    st.subheader('Abandoned checkouts')
    st.caption('Signed checkout ledger · filtered by checkout creation time, rolling UTC. Missing details stay unavailable until verified.')
    search=st.text_input('Search checkouts',placeholder='Customer, email or checkout ID',key=slot+'-search')
    if st.button('Refresh checkout details',key=slot+'-reconcile',help='Bounded Shopify reconciliation; never enrolls customers'):
        try:
            count,more=reconcile(shop,store,period)
            state().get('campaign_home_cache',{}).pop((store.connect,key),None)
            st.caption('Verified '+str(count)+' Shopify checkout details'+(' · more records remain for reconciliation' if more else '')+'.')
        except Exception:st.caption('Latest Shopify verification temporarily unavailable. Local records remain visible.')
    records,phase=read(store,key,lambda:checkouts(store,row['id'],window(period)),20)
    if records is None:
        st.dataframe({'Checkout':[],'Customer':[],'Flow status':[],'Next action':[]},height=360,hide_index=True)
        st.caption('Loading signed checkout records…' if phase!='ERROR' else 'Checkout records temporarily unavailable. Retry shortly.')
        return
    st.session_state['analytics-primary-ready-'+str(row['id'])]=True
    if phase=='ERROR':st.caption('Checkout refresh unavailable. Last verified records are retained.')
    needle=search.strip().casefold()
    visible=[c for c in records if not needle or needle in ' '.join(str(v or '') for v in (c.get('admin_checkout_id'),c['checkout_key'],c['customer_id'],c['analytics'].get('name'),c['analytics'].get('email'))).casefold()]
    listing=[]
    for c in visible:
        display=c['analytics'];label,next_action=flow_state(checkout_view(c));sent={s['step']:s['status'] for s in c['sends']}
        listing.append({'Checkout':(c.get('admin_checkout_id') or c['checkout_key']).rsplit('/',1)[-1],
          'Customer':display.get('name') or 'Customer '+c['customer_id'].rsplit('/',1)[-1] if c['customer_id'] else 'Guest',
          'Email':display.get('email') or '—','Region':display.get('country') or '—',
          'Total':(display.get('currency','')+' '+display.get('amount','')).strip() or '—',
          'Recovery':'Recovered' if label=='Recovered' else 'Not recovered','Flow status':label,
          'Email 1':'Sent' if sent.get(0)=='ACCEPTED' else sent.get(0,'Not sent'),
          'Email 2':'Sent' if sent.get(1)=='ACCEPTED' else sent.get(1,'Not sent'),
          'Opened':c['opened'],'Clicked':c['clicked'],'Last activity':str(c.get('last_activity_at') or ''),'Next action':next_action})
    keys=[c['checkout_key'] for c in visible];table_key=slot+'-table'
    def selected():
        indices=st.session_state[table_key]['selection']['rows']
        st.session_state[slot+'-selected']=keys[indices[0]] if indices and indices[0]<len(keys) else None
    st.dataframe(listing or {'Checkout':[],'Customer':[],'Flow status':[],'Next action':[]},height=400,hide_index=True,
      use_container_width=True,on_select=selected,selection_mode='single-row',key=table_key)
    st.caption(str(len(visible))+' matching checkouts · '+str(sum(c['status']=='RECOVERED' for c in visible))+' recovered')
    chosen=next((c for c in visible if c['checkout_key']==st.session_state.get(slot+'-selected')),None)
    if chosen:
        countdown_html(chosen);reason=disabled_reason(chosen,row)
        if reason:st.caption(reason)
        if st.button('Add to flow',disabled=bool(reason),type='primary',key=slot+'-add-'+chosen['checkout_key']):
            try:
                add_to_flow(shop,store,user,str(row['id']),chosen['admin_checkout_id'])
                updated=checkouts(store,row['id'],window(period),chosen['checkout_key'])
                if updated:patch_checkout(store,row['id'],updated[0])
                invalidate_activity(store,row['id'])
                from crm_automation_ui import changed
                changed();st.toast('Added to flow · awaiting the background worker.');st.rerun(scope='fragment')
            except Exception as exc:st.warning(safe_add_error(exc))

@st.fragment(run_every='30s')
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

@st.fragment
def content(shop,store,user,identity,period,bounds):
    # Keep initial-load scheduling above the fold even on narrow dialogs. The
    # table/summary subsequently refresh in their own bounded server fragments.
    poll=st.container();st.session_state['automation-analytics-pending']=False
    rows,phase=read(store,('analytics-definition',str(identity)),lambda:[store.get('automations',identity)],20)
    if not rows:
        with poll:arm('auto-analytics-definition-poll',.1 if phase!='ERROR' else 20)
        stats(None)
        st.dataframe({'Checkout':[],'Customer':[],'Flow status':[],'Next action':[]},height=360,hide_index=True)
        st.caption('Loading automation…' if phase!='ERROR' else 'Automation details temporarily unavailable.')
        return
    row=rows[0]
    if not row or row['config'].get('deleted_at'):st.warning('Automation unavailable.');return
    st.caption(row['name'])
    # Containers reserve KPI position while primary work is submitted first.
    metrics=st.container();primary=st.container();chart=st.container()
    with primary:
        if row['trigger_type']=='abandoned':checkout_panel(shop,store,user,row,bounds,period)
        else:
            from crm_automation_home_data import step_metrics
            steps,_=read(store,('analytics-steps',str(identity)),lambda:step_metrics(store,identity))
            if steps is not None:st.dataframe(steps,hide_index=True,use_container_width=True)
    with metrics:secondary(store,row,bounds,period)
    with chart:secondary(store,row,bounds,period,charts=True)
    if st.session_state.get('automation-analytics-pending'):
        with poll:arm('auto-analytics-definition-poll',.1)

def render(shop,store,user,identity,name=None):
    st.subheader('Automation analytics')
    if name:st.caption(name)
    period=st.selectbox('Date range',list(PERIODS),index=1,key='auto-analytics-period-'+str(identity))
    slot='auto-analytics-window-'+str(identity)
    current=st.session_state.get(slot)
    if not current or current[0]!=period:current=(period,window(period));st.session_state[slot]=current
    content(shop,store,user,identity,period,current[1])
