"""One Flow page: existing analytics, sequence operations and shared editor."""
from table_design import TABLE_ROW_HEIGHT
from copy import deepcopy
from html import escape,unescape
import re
import streamlit as st
from crm_automation_analytics_ui import read,arm,state,checkout_panel
from crm_checkout_analytics import PERIODS,window,report
from crm_automation_home_data import step_metrics
from crm_automation_definition import email_step,status
from crm_automation_timing import delay_controls
from crm_flow_builder import save,edit_sequence

STYLE='''<style>
.st-key-crm-automation-editor{gap:8px!important;min-width:0}
.st-key-crm-automation-editor [data-testid="stVerticalBlock"]{gap:6px}
.st-key-crm-automation-editor button[kind="primary"]{background:#c8a346!important;border-color:#b99436!important;color:#141414!important}
.st-key-crm-automation-editor h3{font-size:17px;padding:4px 0}
.st-key-flow-workspace button[kind="secondary"],.st-key-flow-workspace [data-testid="stPopoverButton"]{background:#fff!important;color:#30332e!important;border:1px solid #dddcd5!important;border-radius:4px!important;min-height:32px!important;height:32px;padding:3px 9px!important;box-shadow:none!important}
.st-key-flow-workspace button[kind="secondary"]:hover,.st-key-flow-workspace [data-testid="stPopoverButton"]:hover{background:#f2f2ee!important;border-color:#b9bab3!important}
.st-key-flow-workspace button:disabled{opacity:.5}
.st-key-flow-workspace{min-width:0!important;max-width:100%!important}
.st-key-flow-workspace [data-testid="stElementContainer"]:has(iframe){max-width:100%!important;min-width:0!important}
.st-key-flow-workspace iframe{max-width:100%!important}
.st-key-flow-workspace button p{font-size:12px!important}
.st-key-flow-workspace [data-baseweb="input"],.st-key-flow-workspace [data-baseweb="select"]>div{min-height:32px!important;border-radius:4px!important}
.st-key-flow-workspace .st-key-automation-toolbar{gap:6px!important;margin-bottom:2px!important}
.st-key-flow-workspace .st-key-automation-toolbar button{min-height:32px!important;height:32px!important;border-radius:4px!important}
.st-key-flow-workspace .automation-title,.st-key-flow-workspace .automation-current{height:32px}
.st-key-flow-step-metrics-refresh{display:none!important}
.st-key-flow-analytics-refresh{display:none!important}
.st-key-flow-workspace{gap:6px!important}
[data-testid="stMainBlockContainer"]:has(.st-key-flow-workspace){padding-top:calc(var(--sc-topbar-height,64px) + 8px)!important}
.st-key-crm-workspace:has(.st-key-flow-workspace),.st-key-automation-flow-route:has(.st-key-flow-workspace){gap:6px!important}
.st-key-flow-workspace [data-testid="stExpander"] details{border-radius:4px!important}
.st-key-flow-workspace [data-testid="stExpander"] summary{min-height:32px;padding:4px 8px;font-size:13px}
.sc-flow-stats{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:6px;margin:0;padding:0!important}
.sc-flow-stats>div{padding:5px 8px;border:1px solid #e8e6df;border-radius:4px;background:#fffefa;min-width:0}
.sc-flow-stats dt{font-size:11px;color:#73747c}.sc-flow-stats dd{font-size:19px;font-weight:600;margin:3px 0;overflow-wrap:anywhere}
[class*='st-key-flow-row-']{border-bottom:1px solid #e8e6df;padding:8px 0;gap:12px!important;align-items:center!important;flex-wrap:nowrap!important}
[class*='st-key-flow-row-'] button{min-height:32px;padding:3px 8px}
.sc-flow-copy{min-width:0;font-size:13px;line-height:1.5}.sc-flow-copy strong{font-size:13px}
.sc-flow-copy p{margin:0!important;line-height:1.4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.sc-flow-copy small{color:#73747c;font-size:11px}.sc-flow-metrics{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;margin-top:4px}
.st-key-flow-workspace{font-family:Segoe UI,Arial,sans-serif}
.st-key-flow-workspace .automation-title strong{font-weight:600;font-size:16px}
.st-key-flow-workspace .automation-state{background:#f2f1eb;border:1px solid #e5e3db;border-radius:12px;padding:2px 7px}
.st-key-flow-workspace button:focus-visible{outline:2px solid #b99436;outline-offset:2px}
.sc-flow-stats>div{background:#fff;padding:8px 10px;border-color:#e5e5e5;border-radius:6px}
.sc-flow-stats dt{font-size:11px;line-height:1.4}.sc-flow-stats dd{font-variant-numeric:tabular-nums;font-size:21px;color:#242424}
.sc-flow-copy>strong{font-size:12px;color:#505050;font-weight:600}
.sc-flow-copy>p:first-of-type{font-size:15px;font-weight:500;color:#242424}
.sc-flow-copy p.sc-flow-summary{white-space:normal;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;line-height:1.45;overflow:hidden;margin-top:3px!important}
.sc-flow-metrics{color:#626262;font-variant-numeric:tabular-nums;gap:12px}.sc-flow-metrics b{color:#242424;font-weight:600}
[class*='st-key-flow-row-']{padding:12px 0;gap:16px!important}
[class*='st-key-flow-row-']>div{min-width:0}
[class*='st-key-flow-thumb-'][class*='load'],[class*='st-key-flow-preview-']{display:none!important}
.sc-flow-thumbnail{cursor:pointer;border:1px solid #eee;border-radius:4px}.sc-flow-thumbnail:focus-visible{outline:2px solid #b99436}
.sc-flow-trigger{font-size:12px;color:#686b65;padding:4px 0}
@media(max-width:1100px){.sc-flow-stats{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(max-width:1000px){.st-key-flow-workspace .automation-title{height:auto!important;min-height:32px;gap:4px;flex-wrap:nowrap!important}.st-key-flow-workspace .automation-title strong{min-width:0!important}}
@media(max-width:700px){[class*='st-key-flow-row-']{flex-wrap:wrap!important}[class*='st-key-flow-row-']>div:nth-child(2){flex:1 1 calc(100% - 100px)!important;min-width:0!important}[class*='st-key-flow-row-']>div:last-child{margin-left:88px}.sc-flow-metrics{gap:8px}.sc-flow-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>'''

def rate(n,total):return f'{100*n/total:.1f}%' if total else '—'

def summary_cards(value):
    fields=[('Entered',value['entered']),('Sent',value['sent']),('Delivery',rate(value['delivered'],value['sent'])),('Opens',rate(value['opened'],value['sent'])),('Clicks',rate(value['clicked'],value['sent'])),('Conversions',value['conversions']),('Orders',value.get('orders','—')),('Bounce',rate(value['bounced'],value['sent']))] if value else [(k,'—') for k in ('Entered','Sent','Delivery','Opens','Clicks','Conversions','Orders','Bounce')]
    st.html('<dl class="sc-flow-stats">'+''.join('<div><dt>'+k+'</dt><dd>'+escape(str(v))+'</dd></div>' for k,v in fields)+'</dl>')

def refresh_reads(store,identity,groups=None):
    cache=state()
    for token in list(cache.get('campaign_home_cache',{})):
        if token[0]==store.connect and str(identity) in token[1] and (groups is None or token[1][0] in groups):
            _,future=cache['campaign_home_cache'].pop(token)
            future.cancel()
            for name in ('automation_read_terminal','automation_read_started','campaign_home_reported_errors'):cache.get(name,{}).pop(token,None)

@st.fragment
def summary(store,identity,period):
    data,phase=read(store,('flow-summary',str(identity),period),lambda:[report(store,identity,window(period),include_history=False)])
    value=data[0] if data else None
    summary_cards(value)
    if phase in ('LOADING','REFRESHING'):arm('flow-summary',1)
    elif phase in ('ERROR','TIMED_OUT'):
        st.caption('Summary unavailable. Previously loaded metrics are retained.')
        if st.button('Retry summary'):refresh_reads(store,identity);st.rerun(scope='fragment')


def refresh_control(key):
    """Wake an existing sibling fragment once, using its native button.

    Same scoped-control mechanism as thumbnails and the editor toolbar. Only
    fixed application-owned keys are used; no timers, polling or user HTML.
    """
    import json,uuid
    st.html('<script>/* '+uuid.uuid4().hex+' */document.querySelector('+json.dumps('.st-key-'+key+' button')+')?.click();</script>',unsafe_allow_javascript=True)


def refresh_toolbar():
    if st.session_state.pop('flow-toolbar-dirty',False):refresh_control('toolbar-refresh')


@st.fragment(run_every=180)
def analytics_controls(store,identity):
    from time import monotonic
    key='auto-analytics-period-'+str(identity)
    previous=st.session_state.get(key+'-applied','All time')
    period=st.session_state.get(key,'All time')
    refresh=st.button('Revalidate metrics',key='flow-analytics-refresh')
    if refresh:refresh_reads(store,identity,{'flow-summary','analytics-steps'})
    summary(store,identity,period)
    st.session_state[key+'-applied']=period
    elapsed=monotonic()-st.session_state.get(key+'-fresh-at',monotonic())
    st.session_state[key+'-fresh-at']=monotonic()
    if refresh or previous!=period or elapsed>=175:refresh_control('flow-step-metrics-refresh')

def open_email(sid):
    from crm_campaign_recovery import flush_current
    if flush_current(force=True):
        from crm_automation_ui import request_email
        request_email(sid);st.rerun(scope='app')

def commit(store,user,row,draft):
    from crm_store import StoreUnavailable
    try:
        if save(store,user,row,draft,rerun=False) is False:return
    except (ValueError,PermissionError,StoreUnavailable) as exc:st.error(str(exc));return
    st.session_state['flow-toolbar-dirty']=True
    st.toast('Draft saved');st.rerun(scope='fragment')

def step_settings(store,user,row,s,index,prefix):
    flow=row['config']['draft'];amount,unit=delay_controls(s['delay_seconds'])
    with st.form(prefix+'settings'):
        name=st.text_input('Email name',s.get('name') or 'Email '+str(index+1),max_chars=150)
        delay=st.number_input('Delay',0,525600,amount)
        units=st.selectbox('Unit',['Minutes','Hours','Days'],index=['Minutes','Hours','Days'].index(unit))
        enabled=st.checkbox('Enable this email',s.get('enabled',True))
        if st.form_submit_button('Save step'):
            draft=deepcopy(flow);step=draft['emails'][index]
            step.update(name=name,enabled=enabled,delay_seconds=s['delay_seconds'] if (delay,units)==(amount,unit) else int(delay)*{'Minutes':60,'Hours':3600,'Days':86400}[units])
            commit(store,user,row,draft)
    for label,action,disabled in [('Duplicate','duplicate',False),('Move up','up',index==0),('Move down','down',index==len(flow['emails'])-1)]:
        if st.button(label,key=prefix+action,disabled=disabled):commit(store,user,row,edit_sequence(flow,s['step_id'],action))
    confirm=st.checkbox('Confirm delete email from this draft',key=prefix+'confirm')
    if st.button('Delete email',key=prefix+'delete',disabled=not confirm or len(flow['emails'])==1):commit(store,user,row,edit_sequence(flow,s['step_id'],'delete'))

def snippet(doc):
    source=doc.get('custom_html','') or doc.get('content',{}).get('body','')
    source=re.sub(r'<(style|script)\b[^>]*>.*?</\1>','',source,flags=re.S|re.I)
    return re.sub(r'\s+',' ',unescape(re.sub('<[^>]+>',' ',source))).strip()[:240]

def delay_origin(emails,index):
    """Disabled rows do not advance the scheduler's timing anchor."""
    return ' after the previous enabled email' if any(s.get('enabled',True) for s in emails[:index]) else ' after trigger'


def step_performance(store,identity,slots,detail_slots):
    """Render in the sequence fragment that owns the row placeholders.

    Do not make this a nested fragment: reorder/add recreates targets during a
    partial rerun, when external layout positions cannot be reserved. Keeping
    slot creation, writes and retry UI in one fragment also avoids Streamlit's
    cascading FragmentHandledException. Reads and thumbnails remain cached.
    """
    st.button('Refresh sequence metrics',key='flow-step-metrics-refresh')
    period=st.session_state.get('auto-analytics-period-'+str(identity),'All time')
    values,phase=read(store,('analytics-steps',str(identity),period),lambda:step_metrics(store,identity,window(period)))
    metrics={r['step_id']:r for r in values or []}
    for sid,slot in slots.items():
        m=metrics.get(sid,{k:0 for k in ('sent','opened','clicked','orders','delivered','queued','bounced','failed','skipped')})
        fields=[('Sent',m['sent']),('Opens',rate(m['opened'],m['sent'])),('Clicks',rate(m['clicked'],m['sent'])),('Sales',m['orders']),('Orders',m['orders'])]
        slot.html('<div class="sc-flow-metrics" data-period="'+escape(period,quote=True)+'" data-phase="'+escape(phase,quote=True)+'">'+''.join('<span>'+label+' <b>'+escape(str(value) if values is not None else '—')+'</b></span>' for label,value in fields)+'</div>')
        if sid in detail_slots:
            detail_slots[sid].html('<small>'+escape(' · '.join(label+' '+(str(m[key]) if values is not None else '—') for label,key in [('Delivered','delivered'),('Queued','queued'),('Failed','failed'),('Skipped','skipped'),('Bounced','bounced')]))+'</small>')
    if phase in ('LOADING','REFRESHING'):arm('flow-steps',1)
    elif phase in ('ERROR','TIMED_OUT'):
        st.caption('Step analytics unavailable.')
        if st.button('Retry step analytics'):
            refresh_reads(store,identity,{'analytics-steps'});st.rerun(scope='fragment')
    historical=[m for m in values or [] if m['step_id'] not in slots]
    if historical:
        with st.expander('Previous / removed email history'):st.dataframe([{k:v for k,v in m.items() if k!='revenue'} for m in historical],hide_index=True, row_height=TABLE_ROW_HEIGHT)


@st.fragment
def sequence(shop,store,user,identity,period):
    from crm_automation_toolbar import definition
    row=definition(store,st.session_state,identity);flow=row['config']['draft']
    slots={};detail_slots={}
    from crm_flow_thumbnail import thumbnail
    for i,s in enumerate(flow['emails']):
        sid=s['step_id'];prefix='flow-step-'+sid+'-';content=s['document']['content']
        amount,unit=delay_controls(s['delay_seconds']);delay=f'{amount} {unit.lower().rstrip("s") if amount==1 else unit.lower()}'+delay_origin(flow['emails'],i)
        with st.container(horizontal=True,key='flow-row-'+sid):
            with st.container(width=78):
                thumbnail(store,s,row)
                if st.button('Preview email',key='flow-preview-'+sid):st.session_state['flow_preview_step']=sid
            with st.container(width='stretch'):
                name=s.get('name') or 'Email '+str(i+1);subject=content.get('subject') or 'Subject not configured';preheader=content.get('preheader') or ''
                body=snippet(s['document'])
                title='Email '+str(i+1)+((' · '+name) if name!='Email '+str(i+1) else '')
                copy=''.join('<p'+(' class="sc-flow-summary"' if n else '')+' title="'+escape(text,quote=True)+'"><small>'+escape(text)+'</small></p>' for n,text in enumerate((preheader,body)) if text)
                st.html('<div class="sc-flow-copy"><strong>'+escape(title)+'</strong><p title="'+escape(subject,quote=True)+'">'+escape(subject)+'</p>'+copy+'<small>'+escape(delay)+' · '+('Enabled' if s.get('enabled',True) else 'Disabled')+'</small></div>')
                slots[sid]=st.empty()
            with st.container(width=130):
                if st.button('Edit Email',key=prefix+'edit'):open_email(sid)
                with st.popover('⋮',help='Email step settings',key=prefix+'menu',on_change='rerun') as menu:
                    if menu.open:
                        if status(row)!='ARCHIVED':step_settings(store,user,row,s,i,prefix)
                        detail_slots[sid]=st.empty()
                        st.caption('Per-email unsubscribe attribution is unavailable in the current ledger.')
    if status(row)!='ARCHIVED' and st.button('+ Add Email',key='flow-add-'+str(identity)):
        draft=deepcopy(flow);draft['emails'].append(email_step(delay_seconds=86400));commit(store,user,row,draft)
    step_performance(store,identity,slots,detail_slots)
    preview=next((s for s in flow['emails'] if s['step_id']==st.session_state.get('flow_preview_step')),None)
    if preview:
        from crm_thumbnail_cache import selection,source_loader
        _,label,live=selection(row,preview)
        st.caption('Email preview · neutral sample data')
        from crm_html_workspace import flow_preview
        try:
            doc,cfg=source_loader(store,row,preview,live)()
            from crm_thumbnail_render import preview_document
            flow_preview(preview_document(doc),cfg,'flow-readonly-'+preview['step_id'])
        except (ValueError,RuntimeError,KeyError,TypeError,AttributeError):
            st.warning('This stage preview could not render. Check its saved content in Edit Email. Sending and publication are unchanged.')
        if st.button('Close preview'):st.session_state.pop('flow_preview_step',None);st.rerun(scope='fragment')
    refresh_toolbar()


@st.fragment
def recipient_details(store,user,identity):
    with st.expander('Recipient timelines and scheduled deliveries',on_change='rerun',key='flow-recipients-'+str(identity)) as panel:
        if panel.open:
            from crm_flow_builder import activity as recipient_activity
            recipient_activity(store,store.flow(identity),user,rerun_scope='fragment')

@st.fragment
def recent(store,row,user,period):
    from crm_automation_analytics import activity
    from crm_automation_home import activity_html
    st.subheader('Recent activity')
    more=st.toggle('Show more activity',key='flow-more-'+str(row['id']))
    limit=48 if more else 8
    events,phase=read(store,('analytics-activity',str(row['id']),period,limit),lambda:activity(store,row['id'],limit,bounds=window(period)))
    if events:st.html(activity_html(events))
    elif events is not None:st.caption('No recorded activity in this period.')
    else:st.caption('Loading activity…' if phase!='ERROR' else 'Activity unavailable.')
    if phase in ('LOADING','REFRESHING'):arm('flow-activity',1)
    elif phase in ('ERROR','TIMED_OUT') and st.button('Retry activity'):
        refresh_reads(store,row['id']);st.rerun(scope='fragment')
    with st.expander('Recipient timelines and scheduled deliveries',on_change='rerun',key='flow-recipients-'+str(row['id'])) as details:
        if details.open:
            from crm_flow_builder import activity as recipient_activity
            recipient_activity(store,row,user)

@st.fragment
def checkouts(shop,store,user,row):
    slot='auto-checkouts-'+str(row['id'])
    for suffix in ('-search','-status'):
        key=slot+suffix
        if key not in st.session_state and key+'-retained' in st.session_state:
            st.session_state[key]=st.session_state[key+'-retained']
    st.session_state['automation-analytics-pending']=False
    st.session_state['checkout-enrollment-pending']=False
    with st.expander('Abandoned checkouts',on_change='rerun',key='flow-checkout-panel-'+str(row['id'])) as panel:
        if panel.open:checkout_panel(shop,store,user,row,window('All time'),'All time',paginated=True)
        for suffix in ('-search','-status'):
            key=slot+suffix
            if key in st.session_state:st.session_state[key+'-retained']=st.session_state[key]
    enrollment=st.session_state.get(slot+'-enrollment',{})
    batch=[(k,enrollment.get('results',{}).get(k,{})) for k in enrollment.get('batch',())]
    signature=tuple((k,v.get('state'),v.get('delivery'),v.get('enrolled')) for k,v in batch)
    if (batch and all(v.get('state') in ('DONE','FAILED') for _,v in batch)
            and any(v.get('enrolled') or v.get('delivery')=='sent' for _,v in batch)
            and st.session_state.get(slot+'-metrics-receipt')!=signature):
        st.session_state[slot+'-metrics-receipt']=signature
        refresh_control('flow-analytics-refresh')
    if panel.open and (st.session_state.get('automation-analytics-pending') or st.session_state.get('checkout-enrollment-pending')):arm('flow-checkouts',1)

def flow_page(shop,store,user,row):
    st.html(STYLE)
    # The parent route already loaded this authenticated, current definition.
    # Sibling fragments still check updated_at before reusing the document.
    st.session_state['_automation_toolbar_definition']=((str(row['id']),row.get('updated_at')),row)
    import os_accounts
    if st.session_state.get('flow-operational-diagnostics')==str(row['id']) and os_accounts.is_admin(user):
        if st.button('← Back to Flow',key='flow-operations-back'):
            st.session_state.pop('flow-operational-diagnostics',None);st.rerun(scope='app')
        st.subheader('Operational diagnostics')
        recipient_details(store,user,row['id'])
        if row['trigger_type']=='abandoned':checkouts(shop,store,user,row)
        return
    from crm_automation_toolbar import toolbar
    with st.container(key='flow-workspace'):
        toolbar(store,user,row['id'],flow_view=True)
        error=st.session_state.pop('flow_builder_error',None)
        if error:st.warning(error)
        analytics_controls(store,row['id'])
        sequence(shop,store,user,row['id'],'All time')
        recipient_details(store,user,row['id'])
        if row['trigger_type']=='abandoned':checkouts(shop,store,user,row)
    from crm_flow_thumbnail import SCRIPT
    st.html('<span hidden data-flow-script="true"></span>'+SCRIPT,unsafe_allow_javascript=True)
    anchor=st.session_state.pop('flow_return_step',None)
    if anchor:
        import json
        st.html('<script>(()=>{const e=document.querySelector('+json.dumps('.st-key-flow-row-'+anchor)+');e?.scrollIntoView({block:"nearest"});})()</script>',unsafe_allow_javascript=True)
