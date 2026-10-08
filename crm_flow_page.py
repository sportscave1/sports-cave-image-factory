"""One Flow page: existing analytics, sequence operations and shared editor."""
from copy import deepcopy
from html import escape,unescape
import re
import streamlit as st
from crm_automation_analytics_ui import read,arm,state,checkout_panel
from crm_checkout_analytics import PERIODS,window,report
from crm_automation_home_data import step_metrics
from crm_automation_definition import TRIGGERS,email_step,status
from crm_automation_timing import delay_controls
from crm_flow_builder import save,edit_sequence,timing,test_flow

STYLE='''<style>
.st-key-crm-automation-editor{gap:8px!important;min-width:0}
.st-key-crm-automation-editor [data-testid="stVerticalBlock"]{gap:6px}
.st-key-crm-automation-editor button[kind="primary"]{background:#c8a346!important;border-color:#b99436!important;color:#141414!important}
.st-key-crm-automation-editor h3{font-size:17px;padding:4px 0}
.sc-flow-stats{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:6px;margin:0}
.sc-flow-stats>div{padding:8px 10px;border:1px solid #e8e6df;border-radius:7px;background:#fffefa;min-width:0}
.sc-flow-stats dt{font-size:11px;color:#73747c}.sc-flow-stats dd{font-size:19px;font-weight:600;margin:3px 0;overflow-wrap:anywhere}
[class*='st-key-flow-row-']{border-bottom:1px solid #e8e6df;padding:8px 0;gap:12px!important;align-items:center!important;flex-wrap:nowrap!important}
[class*='st-key-flow-row-'] button{min-height:32px;padding:3px 8px}
.sc-flow-copy{min-width:0;font-size:13px;line-height:1.5}.sc-flow-copy strong{font-size:13px}
.sc-flow-copy p{margin:0!important;line-height:1.4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.sc-flow-copy small{color:#73747c;font-size:11px}.sc-flow-metrics{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;margin-top:4px}
[class*='st-key-flow-thumb-'] [data-testid='stButton'],[class*='st-key-flow-preview-']{display:none!important}
.sc-flow-thumbnail{cursor:pointer;border:1px solid #eee;border-radius:4px}.sc-flow-thumbnail:focus-visible{outline:2px solid #b99436}
.sc-flow-trigger{font-size:12px;color:#686b65;padding:4px 0}
@media(max-width:1100px){.sc-flow-stats{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(max-width:700px){[class*='st-key-flow-row-']{flex-wrap:wrap!important}[class*='st-key-flow-row-']>div:nth-child(2){flex:1 1 calc(100% - 100px)!important;min-width:0!important}[class*='st-key-flow-row-']>div:last-child{margin-left:88px}.sc-flow-metrics{gap:8px}.sc-flow-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>'''

def rate(n,total):return f'{100*n/total:.1f}%' if total else '—'

def summary_cards(value):
    from crm_automation_home import money
    fields=[('Entered',value['entered']),('Sent',value['sent']),('Delivery',rate(value['delivered'],value['sent'])),('Opens',rate(value['opened'],value['sent'])),('Clicks',rate(value['clicked'],value['sent'])),('Conversions',value['conversions']),('Revenue',money(value['revenue'])),('Bounce',rate(value['bounced'],value['sent']))] if value else [(k,'—') for k in ('Entered','Sent','Delivery','Opens','Clicks','Conversions','Revenue','Bounce')]
    st.html('<dl class="sc-flow-stats">'+''.join('<div><dt>'+k+'</dt><dd>'+escape(str(v))+'</dd></div>' for k,v in fields)+'</dl>')

def refresh_reads(store,identity):
    cache=state()
    for token in list(cache.get('campaign_home_cache',{})):
        if token[0]==store.connect and str(identity) in token[1]:
            _,future=cache['campaign_home_cache'].pop(token)
            future.cancel()
            for name in ('automation_read_terminal','automation_read_started','campaign_home_reported_errors'):cache.get(name,{}).pop(token,None)

@st.fragment
def summary(store,identity,period):
    data,phase=read(store,('analytics-report',str(identity),period),lambda:[report(store,identity,window(period))])
    value=data[0] if data else None
    summary_cards(value)
    if phase in ('LOADING','REFRESHING'):arm('flow-summary',1)
    elif phase in ('ERROR','TIMED_OUT'):
        st.caption('Summary unavailable. Previously loaded metrics are retained.')
        if st.button('Retry summary'):refresh_reads(store,identity);st.rerun(scope='fragment')
    with st.expander('Performance history',on_change='rerun',key='flow-history-'+str(identity)) as panel:
        if panel.open and value:
            if value['history']:st.line_chart(value['history'],x='day',y=['sent','delivered','opened','clicked'],height=160)
            st.caption('Sent means provider acceptance. Rates use accepted emails; delivery, opens and clicks require recorded events. Enrolments are counted once, independently of the number of emails.')

def open_email(sid):
    from crm_campaign_recovery import flush_current
    if flush_current(force=True):
        st.session_state.update(automation_step=sid,automation_composing=True,flow_return_step=sid)
        st.session_state.pop('automation_editor',None);st.rerun(scope='app')

def commit(store,user,row,draft):
    from crm_store import StoreUnavailable
    try:
        if save(store,user,row,draft,rerun=False) is False:return
    except (ValueError,PermissionError,StoreUnavailable) as exc:st.error(str(exc));return
    st.toast('Draft saved');st.rerun(scope='app')

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

@st.fragment
def sequence(shop,store,user,identity,period):
    row=store.flow(identity);flow=row['config']['draft']
    values,phase=read(store,('analytics-steps',str(identity),period),lambda:step_metrics(store,identity,window(period)))
    metrics={r['step_id']:r for r in values or []}
    from crm_automation_home import money
    from crm_flow_thumbnail import thumbnail
    st.html('<div class="sc-flow-trigger">Trigger: '+escape(TRIGGERS[flow['trigger']][1])+' · Exit: '+('Customer purchases · ' if flow.get('exit_on_purchase',flow['trigger'] in ('abandoned','win_back')) else '')+'Unsubscribe / suppression</div>')
    for i,s in enumerate(flow['emails']):
        sid=s['step_id'];prefix='flow-step-'+sid+'-'+str(row['config']['revision']);content=s['document']['content']
        amount,unit=delay_controls(s['delay_seconds']);delay=f'{amount} {unit.lower().rstrip("s") if amount==1 else unit.lower()}'+(' after the previous enabled email' if i else ' after trigger')
        m=metrics.get(sid,{k:0 for k in ('sent','opened','clicked','orders','delivered','queued','bounced','failed','skipped')})
        metric=[('Sent',m['sent']),('Opens',rate(m['opened'],m['sent'])),('Clicks',rate(m['clicked'],m['sent'])),('Sales',m['orders']),('Revenue',money(m.get('revenue',{})))]
        with st.container(horizontal=True,key='flow-row-'+sid):
            with st.container(width=78):
                thumbnail(store,s)
                if st.button('Preview email',key='flow-preview-'+sid):st.session_state['flow_preview_step']=sid
            with st.container(width='stretch'):
                name=s.get('name') or 'Email '+str(i+1);subject=content.get('subject') or 'Subject not configured';preheader=content.get('preheader') or ''
                body=snippet(s['document'])
                title='Email '+str(i+1)+((' · '+name) if name!='Email '+str(i+1) else '')
                copy=''.join('<p title="'+escape(text,quote=True)+'"><small>'+escape(text)+'</small></p>' for text in (preheader,body) if text)
                st.html('<div class="sc-flow-copy"><strong>'+escape(title)+'</strong><p title="'+escape(subject,quote=True)+'">'+escape(subject)+'</p>'+copy+'<small>'+escape(delay)+' · '+('Enabled' if s.get('enabled',True) else 'Disabled')+'</small><div class="sc-flow-metrics">'+''.join('<span>'+label+' <b>'+escape(str(value) if values is not None else '—')+'</b></span>' for label,value in metric)+'</div></div>')
            with st.container(width=130):
                if st.button('Edit Email',key=prefix+'edit'):open_email(sid)
                with st.popover('⋮',help='Email step settings',key=prefix+'menu'):
                    if status(row)!='ARCHIVED':step_settings(store,user,row,s,i,prefix)
                    st.caption(' · '.join(label+' '+(str(m[key]) if values is not None else '—') for label,key in [('Delivered','delivered'),('Queued','queued'),('Failed','failed'),('Skipped','skipped'),('Bounced','bounced')]))
                    st.caption('Per-email unsubscribe attribution is unavailable in the current ledger.')
    if phase in ('LOADING','REFRESHING'):arm('flow-steps',1)
    elif phase in ('ERROR','TIMED_OUT'):
        st.caption('Step analytics unavailable.')
        if st.button('Retry step analytics'):refresh_reads(store,identity);st.rerun(scope='fragment')
    if status(row)!='ARCHIVED' and st.button('+ Add Email',key='flow-add-'+str(identity)):
        draft=deepcopy(flow);draft['emails'].append(email_step(delay_seconds=86400));commit(store,user,row,draft)
    historical=[m for m in values or [] if m['step_id'] not in {s['step_id'] for s in flow['emails']}]
    if historical:
        with st.expander('Previous / removed email history'):st.dataframe(historical,hide_index=True)
    preview=next((s for s in flow['emails'] if s['step_id']==st.session_state.get('flow_preview_step')),None)
    if preview:
        st.caption('Saved email preview · neutral sample data')
        from crm_html_workspace import flow_preview
        from crm_checkout_preview import needs_checkout,document,sample
        doc=deepcopy(preview['document'])
        if needs_checkout(doc):doc,_=document(doc,sample(doc))
        flow_preview(doc,store.render_settings(),'flow-readonly-'+preview['step_id'])
        if st.button('Close preview'):st.session_state.pop('flow_preview_step',None);st.rerun(scope='fragment')

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
    st.session_state['automation-analytics-pending']=False
    st.session_state['checkout-enrollment-pending']=False
    checkout_panel(shop,store,user,row,window('All time'),'All time')
    if st.session_state.get('automation-analytics-pending') or st.session_state.get('checkout-enrollment-pending'):arm('flow-checkouts',1)

def flow_page(shop,store,user,row):
    st.html(STYLE)
    from crm_automation_toolbar import toolbar
    toolbar(store,user,row['id'])
    if st.session_state.get('flow-top-'+str(row['id'])+'simulation'):test_flow(row)
    error=st.session_state.pop('flow_builder_error',None)
    if error:st.warning(error)
    with st.container(horizontal=True,vertical_alignment='center'):
        with st.container(width=240):period=st.selectbox('Date range',list(PERIODS),index=4,key='auto-analytics-period-'+str(row['id']),label_visibility='collapsed')
        if st.button('Refresh analytics'):refresh_reads(store,row['id']);st.rerun(scope='app')
    summary(store,row['id'],period)
    with st.expander('Trigger and flow settings',on_change='rerun',key='flow-rules-'+str(row['id'])) as rules:
        if rules.open and status(row)!='ARCHIVED':timing(store,user,row)
    sequence(shop,store,user,row['id'],period)
    if row['trigger_type']=='abandoned':
        with st.expander('Abandoned checkouts',on_change='rerun',key='flow-checkout-panel-'+str(row['id'])) as panel:
            if panel.open:checkouts(shop,store,user,row)
    recent(store,row,user,period)
    from crm_flow_thumbnail import SCRIPT
    st.html('<span hidden data-flow-script="true"></span>'+SCRIPT,unsafe_allow_javascript=True)
    anchor=st.session_state.pop('flow_return_step',None)
    if anchor:
        import json
        st.html('<script>(()=>{const e=document.querySelector('+json.dumps('.st-key-flow-row-'+anchor)+');e?.scrollIntoView({block:"nearest"});})()</script>',unsafe_allow_javascript=True)
