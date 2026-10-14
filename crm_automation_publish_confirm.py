"""Fast shared confirmation and authoritative durable-publication handoff."""
import streamlit as st
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
    title='Publish Email?' if step_id is not None else 'Publish All?'
    dialog=st.dialog(title,width='small',on_dismiss=dismiss)
    return dialog(confirmation_body)(store,user,identity,revision,step_id,flow_status,row)


def confirmation_body(store,user,identity,revision,step_id=None,flow_status='DRAFT',row=None):
    # No store reads on open. Locked request/worker validation remains authoritative.
    st.html("""<style>
    [data-testid="stDialog"]:has(.sc-publication-confirm){align-items:center!important;padding:16px!important}
    [role="dialog"]:has(.sc-publication-confirm) [data-testid="stDialogContent"]{background:#f9f9f9!important;padding:0!important}
    [role="dialog"]:has(.sc-publication-confirm){width:min(360px,calc(100vw - 32px))!important;background:#f9f9f9!important;color:#1b1b1b!important;border:1px solid #d6d6d6!important;border-radius:8px!important;padding:16px!important;box-shadow:0 8px 28px #0003}
    [role="dialog"]:has(.sc-publication-confirm) :is(h2,h3){font:600 18px 'Segoe UI',sans-serif!important;color:#1b1b1b!important;padding:0!important;margin:0!important}
    [role="dialog"]:has(.sc-publication-confirm) [data-testid="stVerticalBlock"]{gap:10px!important}
    [role="dialog"]:has(.sc-publication-confirm) p{font:14px 'Segoe UI',sans-serif!important;color:#1b1b1b!important;margin:0!important}
    [role="dialog"]:has(.sc-publication-confirm) button{min-height:32px!important;padding:4px 14px!important;border-radius:4px!important}
    [role="dialog"]:has(.sc-publication-confirm) button p{color:inherit!important}
    [role="dialog"]:has(.sc-publication-confirm) button[kind="secondary"]{background:#fff!important;color:#1b1b1b!important;border:1px solid #ccc!important}
    [role="dialog"]:has(.sc-publication-confirm) button[kind="primary"]{background:#0067c0!important;color:#fff!important;border:1px solid #0067c0!important}
    </style><span class="sc-publication-confirm"></span>""")
    st.write('Publish this email now?' if step_id is not None else 'Publish all enabled emails in this flow now?')
    submitting=st.session_state.get('automation-publication-submitting',False)
    error=st.session_state.pop('automation-publication-submit-error',None)
    if error:st.error(error)
    cancel,publish=st.columns(2)
    if cancel.button('Cancel',key='automation-publication-cancel',disabled=submitting,use_container_width=True):
        dismiss();st.rerun(scope='app')
    publish.button('Publish' if step_id is not None else 'Publish All',type='primary',key='automation-publication-confirm',disabled=submitting,on_click=submit,use_container_width=True)
    if submitting:
        try:
            with st.spinner('Publishing…'):
                job=store.request_publish(user,identity,revision,step_id=step_id)
            if job.get('unchanged'):
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
