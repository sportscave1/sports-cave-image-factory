"""Fast shared confirmation and authoritative durable-publication handoff."""
import streamlit as st
from html import escape
from pathlib import Path
from crm_store import StoreUnavailable


def dismiss():
    for key in list(st.session_state):
        if key.startswith('publication-include-'):st.session_state.pop(key,None)
    st.session_state.pop('automation-confirm-publication',None)
    st.session_state.pop('automation-publication-submitting',None)
    st.session_state.pop('automation-publication-submit-error',None)


def submit():
    st.session_state['automation-publication-submitting']=True


def completed(store,row,state):
    """Only a committed job and its persisted delivery version permit navigation."""
    waiting=state.get('automation-publication-waiting')
    if not waiting or waiting['identity']!=str(row['id']):return False
    if waiting.get('unchanged'):
        from crm_automation_publish_state import email_has_changes,has_changes
        selected=waiting.get('step_id')
        if row['config']['published_version']<waiting['version']:return False
        changed=email_has_changes(store,row,selected) if selected else has_changes(store,row)
        if changed:return False
        state.pop('automation-publication-waiting',None)
        state['automation-publication-toast']=True
        return True
    publication=row['config'].get('publication',{})
    if publication.get('state')=='PUBLISHING':return False
    job=store.q('SELECT state,error,publication_version,snapshot FROM crm_automation_publish_jobs WHERE id=%s AND automation_id=%s',
                (waiting['job_id'],row['id']),True)
    if not job:return False
    if job['state']=='FAILED':
        state.pop('automation-publication-waiting',None)
        return False
    if job['state']!='SUCCEEDED' or row['config']['published_version']<job['publication_version']:return False
    selected=job['snapshot'].get('step_id')
    if selected:
        email=next(s for s in job['snapshot']['flow']['emails'] if s['step_id']==selected)
        if email.get('enabled',True) and not any(s['step_id']==selected and s['template_version']>=job['publication_version'] for s in row['steps']):return False
    if not selected:
        expected={s['step_id'] for s in job['snapshot']['flow']['emails'] if s.get('enabled',True)}
        actual={s['step_id'] for s in row['steps'] if s.get('template_version',0)>=job['publication_version']}
        if not expected<=actual:return False
    state.pop('automation-publication-waiting',None)
    state.pop('_automation_toolbar_definition',None)
    state.pop('_automation_published_comparison',None)
    state['automation-publication-toast']=True
    return True


def confirm(store,user,identity,revision,step_id=None,flow_status='DRAFT',row=None):
    """One dialog body and submission path; scope is explicit at every entry point."""
    title='Publish email?' if step_id is not None else 'Publish All?'
    dialog=st.dialog(title,width='small',on_dismiss=dismiss)
    return dialog(confirmation_body)(store,user,identity,revision,step_id,flow_status,row)


def confirmation_body(store,user,identity,revision,step_id=None,flow_status='DRAFT',row=None):
    # No store reads on open. Locked request/worker validation remains authoritative.
    submitting=st.session_state.get('automation-publication-submitting',False)
    error=st.session_state.pop('automation-publication-submit-error',None)
    assets=Path(__file__).with_name('components')/'crm_sections'
    with st.container(key='sc-publication-body'):
        st.html('<span class="sc-publication-confirm" hidden></span><style>'+assets.joinpath('publication_confirm.css').read_text(encoding='utf8')+'</style>')
        if row:
            step=next((s for s in row['config']['draft']['emails'] if s['step_id']==step_id),None)
            name=(step.get('name') or step['document']['content'].get('subject') or 'Untitled email') if step else 'All enabled emails'
            st.html('<div class="sc-publication-summary"><strong>'+escape(name)+'</strong><span>'+escape(row['name'])+'</span></div>')
        st.caption('Publish this email’s saved content. '+('The flow stays active.' if flow_status=='ACTIVE' else 'The flow stays disabled.' ) if step_id else 'Publish all enabled emails in this flow now?')
        if error:st.error(error)
        cancel,publish=st.columns(2,gap='small')
        if cancel.button('Cancel',key='automation-publication-cancel',disabled=submitting,use_container_width=True):
            dismiss();st.rerun(scope='app')
        publish.button('Publish email' if step_id is not None else 'Publish All',type='primary',key='automation-publication-confirm',disabled=submitting,on_click=submit,use_container_width=True)
        st.html('<script>'+assets.joinpath('publication_confirm.js').read_text(encoding='utf8')+'</script>',unsafe_allow_javascript=True)
    if submitting:
        try:
            with st.spinner('Publishing…'):
                # Recheck the save barrier at final confirmation as well as open.
                from crm_campaign_recovery import flush_current
                if not flush_current(force=True):raise ValueError('Save failed. Your draft is retained. Retry saving before publishing.')
                editor=st.session_state.get('automation_editor')
                if editor and str(editor['id'])==str(identity):revision=editor['version']
                job=store.request_publish(user,identity,revision,step_id=step_id)
            if step_id is not None:
                # Acceptance is durable. The destination owns completion status.
                from crm_automation_ui import request_route
                request_route(identity)
                st.session_state.pop('automation-publication-waiting',None)
            elif job.get('unchanged'):
                st.session_state['automation-publication-waiting']={'identity':str(identity),'unchanged':True,'version':job['publication_version'],'step_id':step_id}
            elif job.get('id'):
                st.session_state['automation-publication-waiting']={'identity':str(identity),'job_id':str(job['id'])}
            if not job.get('unchanged'):
                from crm_automation_home import accepted_publication
                accepted_publication(job)
            dismiss()
            from crm_automation_ui import changed
            changed();st.rerun(scope='app')
        except (ValueError,PermissionError,StoreUnavailable,RuntimeError) as exc:
            st.session_state.pop('automation-publication-submitting',None)
            st.session_state['automation-publication-submit-error']=str(exc)
            st.rerun(scope='fragment')
