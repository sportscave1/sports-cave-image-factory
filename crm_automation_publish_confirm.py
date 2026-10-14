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


@st.dialog('Publish Flow?',width='small',on_dismiss=dismiss)
def confirm(store,user,identity,revision,step_id=None,flow_status='DRAFT',row=None):
    # No database reads or provider validation on open. Request/worker transactions
    # retain every publication safeguard and revalidate authoritative state.
    st.html("""<style>
    [role="dialog"]:has(.sc-publication-confirm){width:min(400px,calc(100vw - 32px))!important;background:#161616;color:#fff;border:1px solid #75602e;border-radius:10px;padding:20px!important}
    [role="dialog"]:has(.sc-publication-confirm) :is(h2,h3){font-size:19px;color:#fff;padding:0 0 8px}
    [role="dialog"]:has(.sc-publication-confirm) p{font-size:13px;color:#eee}
    [role="dialog"]:has(.sc-publication-confirm) button{min-height:34px;padding:4px 14px}
    [role="dialog"]:has(.sc-publication-confirm) button p{color:inherit!important}
    [role="dialog"]:has(.sc-publication-confirm) button[kind="secondary"]{background:#272727;color:#fff;border-color:#626262}
    [role="dialog"]:has(.sc-publication-confirm) button[kind="primary"]{background:#c8a346;color:#141414;border-color:#c8a346}
    </style><span class="sc-publication-confirm"></span>""")
    enable_ids=[]
    emails=(row or {}).get('config',{}).get('draft',{}).get('emails',[])
    from html import escape
    if row:st.write('Publish '+row['name'])
    active=[s for s in emails if s.get('enabled',True)]
    excluded=[s for s in emails if not s.get('enabled',True)]
    if excluded:
        st.caption('Disabled emails stay excluded unless you explicitly include and enable them.')
        for step in excluded:
            title='Email '+str(emails.index(step)+1)+' — '+(step.get('name') or step['document']['content']['subject'] or 'Untitled email')
            if st.checkbox('Include and enable: '+title,key='publication-include-'+step['step_id']):
                enable_ids.append(step['step_id']);active.append(step)
    if emails:
        st.write(str(len(active))+(' emails will be published; the flow stays paused:' if flow_status=='PAUSED' else ' emails will be live for future eligible customers:'))
        names=['Email '+str(i+1)+' — '+(s.get('name') or s['document']['content']['subject'] or 'Untitled') for i,s in enumerate(emails) if s in active]
        st.html('<div style="max-height:160px;overflow:auto;font-size:13px;color:#eee">'+'<br>'.join(escape(n) for n in names)+'</div>')
        omitted=len(excluded)-len(enable_ids)
        if omitted:st.caption(str(omitted)+' disabled email(s) will remain excluded.')
    else:st.write('Publish this email?' if step_id else 'Publish the complete enabled sequence for future eligible customers?')
    if flow_status=='PAUSED':st.caption('This flow will remain paused.')
    submitting=st.session_state.get('automation-publication-submitting',False)
    error=st.session_state.pop('automation-publication-submit-error',None)
    if error:st.error(error)
    cancel,publish=st.columns(2)
    if cancel.button('Cancel',key='automation-publication-cancel',disabled=submitting,use_container_width=True):
        dismiss();st.rerun(scope='app')
    publish.button('Publishing…' if submitting else 'Publish All',type='primary',key='automation-publication-confirm',disabled=submitting or bool(emails and not active),on_click=submit,use_container_width=True)
    if submitting:
        try:
            with st.spinner('Publishing…'):
                job=store.request_publish(user,identity,revision,step_id=step_id,enable_ids=enable_ids)
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
