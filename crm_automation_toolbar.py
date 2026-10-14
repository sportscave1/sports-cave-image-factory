"""Compact native controls; publication authority remains in the backend."""
from html import escape
import inspect
import streamlit as st
from crm_automation_publish_state import has_changes,label

def period_changed():
    st.session_state['flow-period-dirty']=True


def request_confirmation(identity,revision,selected,flow_status):
    from crm_campaign_recovery import flush_current
    if not flush_current(force=True):return
    editor=st.session_state.get('automation_editor')
    if editor and str(editor['id'])==str(identity):revision=editor['version']
    cached=st.session_state.get('_automation_toolbar_definition')
    row=cached[1] if cached and str(cached[1]['id'])==str(identity) else None
    st.session_state['automation-confirm-publication']=(str(identity),revision,None,flow_status,row)


def definition(store,state,identity):
    """Only the current flow is cached, scoped to this authenticated session.

    Every rerun checks database updated_at. Mutations still lock and validate a
    fresh row; cached documents are solely for display and dirty comparison.
    """
    from crm_automation_store import AutomationStore
    snapshot=store.display_snapshot(identity) if isinstance(store,AutomationStore) else None
    if snapshot is not None:return snapshot
    marker=store.q('SELECT updated_at FROM crm_automations WHERE id=%s',(identity,),True)
    token=(str(identity),marker and marker['updated_at'])
    cached=state.get('_automation_toolbar_definition')
    if not cached or cached[0]!=token:
        cached=(token,store.flow(identity));state['_automation_toolbar_definition']=cached
    return cached[1]


@st.fragment(**({'key':'crm_automation_toolbar'} if 'key' in inspect.signature(st.fragment).parameters else {}))
def toolbar(store,user,identity,*,editor=None,key='',cfg=None,flow_view=False):
    from crm_campaign_recovery import flush_current
    from crm_automation_ui import changed
    from crm_automation_definition import status
    from crm_store import StoreUnavailable
    from crm_flow_builder import display_name
    # Present from the saved click context before any freshness/readiness reads.
    # Confirmation still submits through the locked, authoritative backend path.
    requested=st.session_state.get('automation-confirm-publication')
    if requested and requested[0]==str(identity):
        from crm_automation_publish_confirm import confirm
        _,revision,selected,flow_status,*context=requested
        confirm(store,user,identity,revision,selected,flow_status,context[0] if context else None)
    try:
        row=definition(store,st.session_state,identity)
        from crm_automation_publication import overdue,expire
        if overdue(row['config'].get('publication',{})):
            expire(store,identity);row=store.flow(identity)
    except StoreUnavailable:
        st.caption('Publication status unavailable. No successful publication is confirmed.')
        if st.button('Retry status',key='toolbar-status-retry'):st.rerun(scope='fragment')
        return
    editor=st.session_state.get('automation_editor') if editor else None
    selected=getattr(store,'step_id',None) if editor else None
    from crm_automation_publish_confirm import completed
    try:finished=completed(store,row,st.session_state)
    except StoreUnavailable:
        st.caption('Publication status unavailable. Checking again; success is not yet confirmed.')
        from crm_automation_analytics_ui import arm
        st.button('Refresh automation toolbar',key='toolbar-refresh')
        arm('automation-toolbar-publication',2)
        return
    if finished:
        from crm_automation_ui import request_email
        if flush_current(force=True):
            changed();request_email(None);st.rerun(scope='app')
    if flow_view and st.session_state.pop('automation-publication-toast',False):st.toast('Flow published successfully.')
    dirty=bool(editor and (editor['document']!=st.session_state.get('automation_saved',{}).get('document') or editor['name']!=st.session_state.get('automation_saved',{}).get('name')))
    # Saved draft vs live is separate from editor vs saved. One session-local
    # comparison is reused until the authoritative definition changes.
    token=(str(identity),row.get('updated_at'),row['config']['revision'],row['config']['published_version'],selected)
    comparison=st.session_state.get('_automation_published_comparison')
    if not comparison or comparison[0]!=token:
        comparison=(token,has_changes(store,row));st.session_state['_automation_published_comparison']=comparison
    pending=comparison[1];version=row['config']['published_version']
    excluded=[s for s in row['config']['draft']['emails'] if not s.get('enabled',True)]
    st.session_state['_automation_toolbar_definition']=((str(identity),row.get('updated_at')),row)
    badge_label=label(row,pending)
    current_label='Published · Up to date' if version else 'Up to date'
    if selected:
        from crm_flow_inline import step_state
        step=next(s for s in row['config']['draft']['emails'] if s['step_id']==selected)
        email_state=step_state(row,step)
        live_step=next((s for s in row['steps'] if s['step_id']==selected),None)
        badge_label=email_state.title()+(' · v'+str(live_step['template_version']) if live_step else '')
        if live_step and pending:badge_label+=' · Unpublished changes'
        current_label={'LIVE':'Published · Up to date','PAUSED':'Published · Paused','DRAFT':'Draft','DISABLED':'Disabled · Excluded from publication'}[email_state]
    elif row['status']=='PAUSED' and version:current_label='Published · Paused'
    if excluded:current_label='Published · '+str(len(excluded))+' disabled / excluded' if version else 'Draft · Disabled emails excluded'
    publication=row['config'].get('publication',{});busy=publication.get('state')=='PUBLISHING';archived=status(row)=='ARCHIVED'
    blockers=[];resume_blockers=[]
    if row['trigger_type']!='abandoned' and not busy and (pending or row['status']=='PAUSED'):
        from crm_automation_readiness import blockers as readiness_blockers
        from crm_automation_publication import preflight
        from crm_automation_publish_state import publication_flow
        scoped=publication_flow(store,row)
        blockers=readiness_blockers(store,{'trigger_type':scoped['trigger'],'config':{'draft':scoped}})
        resume_blockers=readiness_blockers(store,row,published=True) if row['status']=='PAUSED' else []
        try:preflight(row,row['config']['revision'],scoped)
        except ValueError as exc:
            if str(exc)!='Enable at least one email before publishing.':blockers.append(str(exc))
    st.html('''<style>
    .st-key-automation-toolbar{gap:8px!important;align-items:center!important;flex-wrap:wrap!important;margin:0 0 8px!important}
    .st-key-automation-toolbar>[data-testid="stElementContainer"]{width:auto!important;flex:0 0 auto!important}
    .st-key-automation-toolbar>[data-testid="stLayoutWrapper"]{width:auto!important;flex:0 0 auto!important}
    .st-key-automation-toolbar button{min-height:36px!important;height:36px;padding:4px 10px!important;white-space:nowrap}
    .st-key-automation-toolbar button p{font-size:13px!important}
    .st-key-automation-toolbar [data-testid="stElementContainer"]:has(.automation-title){flex:1 1 180px!important;min-width:0!important}
    .automation-title{display:flex;align-items:center;gap:8px;min-width:0;height:38px}
    .automation-title strong{font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:60px}
    .automation-state{font-size:11px;color:#65716b;white-space:nowrap;flex-shrink:0}
    .automation-current{font-size:12px;color:#6c706b;display:flex;align-items:center;justify-content:center;min-width:108px;height:38px}
    .automation-publishing:before{content:'';width:10px;height:10px;border:1px solid #ddd;border-top-color:#a98735;border-radius:50%;margin-right:6px;animation:automation-publishing-spin 1s linear infinite}
    @keyframes automation-publishing-spin{to{transform:rotate(360deg)}}
    @media(prefers-reduced-motion:reduce){.automation-publishing:before{animation:none}}
    .st-key-automation-toolbar [data-testid="stPopover"]{width:auto!important}
    .st-key-automation-toolbar [data-baseweb="select"]>div{height:32px!important;min-height:32px!important}
    .st-key-toolbar-refresh{display:none!important}
    @media(max-width:1000px){.automation-title{flex-wrap:wrap;height:auto;min-height:38px}.automation-state{white-space:normal}}
    </style>''')
    try:
        st.button('Refresh automation toolbar',key='toolbar-refresh')
        with st.container(horizontal=True,vertical_alignment='center',gap='small',key='automation-toolbar'):
            if st.button('← Automations',key='toolbar-back'):
                if flush_current(force=True):
                    from crm_automation_ui import request_route
                    request_route(None);st.rerun(scope='app')
            title=display_name(editor['name'] if editor else row['name'])
            badge='' if flow_view else '<span class="automation-state">'+escape(badge_label+(' · Unsaved changes' if dirty else ''))+'</span>'
            if flow_view:
                from crm_flow_inline import title_control
                title_control(store,user,row,title)
            else:
                st.html('<div class="automation-title"><strong title="'+escape(title,quote=True)+'">'+escape(title)+'</strong>'+badge+'</div>')
            if flow_view:
                from crm_checkout_analytics import PERIODS
                with st.container(width=145):
                    st.selectbox('Reporting period',list(PERIODS),index=list(PERIODS).index('All time'),key='auto-analytics-period-'+str(identity),label_visibility='collapsed',on_change=period_changed)
            if editor and st.button('Flow',key='toolbar-sequence',help='Return to this flow’s sequence'):
                if flush_current(force=True):
                    from crm_automation_ui import request_email
                    request_email(None);st.rerun(scope='app')
            if st.button('Save draft',disabled=not dirty or archived,key='toolbar-save'):
                if flush_current(force=True):changed();st.toast('Draft saved');st.rerun(scope='fragment')
            if editor:
                from crm_email_size_ui import size_meter
                if cfg is not None:size_meter(editor,key,cfg)
                from crm_campaign_send_ui import test_control
                test_control(store,user,editor,key,cfg=cfg)
            elif flow_view:
                from crm_flow_test_ui import control
                control(store,user,row,dirty=dirty)
            elif st.button('Test Flow',key='toolbar-test'):
                name='flow-top-'+str(identity)+'simulation'
                st.session_state[name]=not st.session_state.get(name,False);st.rerun(scope='app')
            import os_accounts
            if not flow_view and os_accounts.is_admin(user):
                with st.popover('Diagnostics',on_change='rerun',key='flow-diagnostics') as diagnostics:
                    if diagnostics.open:
                        if flow_view and st.button('Open operational diagnostics',key='flow-operations-open'):
                            st.session_state['flow-operational-diagnostics']=str(identity)
                            st.rerun(scope='app')
                        from crm_automation_diagnostic_ui import control
                        from crm_shopify import Shopify
                        control(Shopify(),store,user,row['trigger_type'],key+'flow_',automation=row)
            if busy:st.html('<span class="automation-current automation-publishing" role="status">Publishing changes…</span>')
            elif not pending and not dirty and not excluded:st.html('<span class="automation-current" role="status">'+current_label+'</span>')
            else:
                if excluded:st.caption(current_label)
                st.button('Retry Publish' if publication.get('state')=='FAILED' else 'Publish changes' if version else 'Publish now',type='primary',disabled=archived or bool(blockers),key='toolbar-publish',help='; '.join(blockers) if blockers else 'Publish the complete eligible sequence. Disabled emails require explicit inclusion.',on_click=request_confirmation,args=(identity,editor['version'] if editor else row['config']['revision'],selected,row['status']))
            if row['status'] in ('ACTIVE','PAUSED') and not archived:
                action='pause' if row['status']=='ACTIVE' else 'resume'
                if st.button(action.title(),key='toolbar-lifecycle',disabled=action=='resume' and bool(resume_blockers),help='; '.join(resume_blockers) if action=='resume' and resume_blockers else None):
                    store.lifecycle(user,identity,action);changed();st.rerun(scope='fragment')
        if flow_view:
            signature=(str(identity),row['status'],version,publication.get('state'))
            previous=st.session_state.get('flow-status-observed')
            st.session_state['flow-status-observed']=signature
            if previous and previous[0]==str(identity) and previous!=signature:
                from crm_flow_page import refresh_control
                refresh_control('flow-step-metrics-refresh')
        if flow_view and st.session_state.pop('flow-period-dirty',False):
            from crm_flow_page import refresh_control
            refresh_control('flow-analytics-refresh')
        if publication.get('state')=='FAILED':st.html('<span role="status" style="font-size:12px;color:#9c3c36">Publishing failed · '+escape(publication.get('error') or 'Retry publishing.')+'</span>')
        if blockers:
            with st.popover('Publication requirements',icon=':material/warning:'):
                for reason in blockers:st.caption(reason)
        if busy:
            from crm_automation_publication import progress,progress_text
            try:st.caption(progress_text(progress(store,identity)))
            except StoreUnavailable:st.caption('Publication status temporarily unavailable. Checking again; success is not yet confirmed.')
            from crm_automation_analytics_ui import arm
            arm('automation-toolbar-publication',2)
        from pathlib import Path
        script=Path(__file__).with_name('components').joinpath('crm_sections','automation_publish.js').read_text(encoding='utf-8')
        st.html('<script>'+script+'</script>',unsafe_allow_javascript=True)
        if flow_view:
            from crm_flow_inline import scripts
            scripts()
    except (ValueError,PermissionError,StoreUnavailable) as exc:st.error(str(exc))
