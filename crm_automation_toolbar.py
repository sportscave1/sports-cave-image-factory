"""Compact native controls; publication authority remains in the backend."""
from copy import deepcopy
from html import escape
import inspect
import streamlit as st
from crm_automation_publish_state import has_changes,label


@st.fragment(**({'key':'crm_automation_toolbar'} if 'key' in inspect.signature(st.fragment).parameters else {}))
def toolbar(store,user,identity,*,editor=None,key='',cfg=None):
    from crm_campaign_recovery import flush_current
    from crm_automation_ui import changed
    from crm_automation_definition import status
    from crm_store import StoreUnavailable
    from crm_flow_builder import display_name
    row=store.flow(identity);flow=deepcopy(row['config']['draft'])
    editor=st.session_state.get('automation_editor') if editor else None
    if editor and str(editor['id'])==str(identity):
        for step in flow['emails']:
            if step['step_id']==store.step_id:step['document']=deepcopy(editor['document'])
    dirty=bool(editor and (editor['document']!=st.session_state.get('automation_saved',{}).get('document') or editor['name']!=st.session_state.get('automation_saved',{}).get('name')))
    pending=has_changes(store,row,flow);version=row['config']['published_version']
    publication=row['config'].get('publication',{});busy=publication.get('state')=='PUBLISHING';archived=status(row)=='ARCHIVED'
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
    .st-key-automation-toolbar [data-testid="stPopover"]{width:auto!important}
    .st-key-toolbar-refresh{display:none!important}
    @media(max-width:1000px){.automation-title{flex-wrap:wrap;height:auto;min-height:38px}.automation-state{white-space:normal}}
    </style>''')
    try:
        st.button('Refresh automation toolbar',key='toolbar-refresh')
        with st.container(horizontal=True,vertical_alignment='center',gap='small',key='automation-toolbar'):
            if st.button('← Automations',key='toolbar-back'):
                if flush_current(force=True):
                    st.session_state.pop('automation_selected',None);st.query_params.pop('automation',None);st.rerun(scope='app')
            title=display_name(editor['name'] if editor else row['name'])
            st.html('<div class="automation-title"><strong title="'+escape(title,quote=True)+'">'+escape(title)+'</strong><span class="automation-state">'+escape(label(row,pending))+'</span></div>')
            if editor and st.button('Flow',key='toolbar-sequence',help='Return to this flow’s sequence'):
                if flush_current(force=True):
                    st.session_state['automation_composing']=False;st.session_state.pop('automation_editor',None);st.rerun(scope='app')
            if st.button('Save draft',disabled=not dirty or archived,key='toolbar-save'):
                if flush_current(force=True):changed();st.toast('Draft saved');st.rerun(scope='fragment')
            if editor:
                from crm_campaign_send_ui import test_control
                test_control(store,user,editor,key,cfg=cfg)
            elif st.button('Test Flow',key='toolbar-test'):
                name='flow-top-'+str(identity)+'simulation'
                st.session_state[name]=not st.session_state.get(name,False);st.rerun(scope='app')
            if busy:st.html('<span class="automation-current" role="status">Publishing…</span>')
            elif not pending:st.html('<span class="automation-current" role="status">Up to date</span>')
            elif st.button('Publish changes' if version else 'Publish now',type='primary',disabled=archived,key='toolbar-publish',help='Publish for new enrollments; existing recipients keep their sequence.'):
                if flush_current(force=True):
                    revision=editor['version'] if editor else row['config']['revision']
                    job=store.request_publish(user,identity,revision)
                    if not job.get('unchanged'):
                        from crm_automation_home import accepted_publication
                        accepted_publication(job)
                    changed();st.rerun(scope='fragment')
            if row['status'] in ('ACTIVE','PAUSED') and not archived:
                action='pause' if row['status']=='ACTIVE' else 'resume'
                if st.button(action.title(),key='toolbar-lifecycle'):
                    store.lifecycle(user,identity,action);changed();st.rerun(scope='fragment')
        if publication.get('state')=='FAILED':st.error(publication.get('error') or 'Publication failed. Retry publishing.')
        if busy:
            from crm_automation_analytics_ui import arm
            arm('automation-toolbar-publication',2)
        from pathlib import Path
        script=Path(__file__).with_name('components').joinpath('crm_sections','automation_publish.js').read_text(encoding='utf-8')
        st.html('<script>'+script+'</script>',unsafe_allow_javascript=True)
    except (ValueError,PermissionError,StoreUnavailable) as exc:st.error(str(exc))
