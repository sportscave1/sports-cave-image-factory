"""Fast shared confirmation and authoritative durable-publication handoff."""
import streamlit as st
from crm_store import StoreUnavailable


def dismiss():
    st.session_state.pop('automation-confirm-publication',None)


def completed(store,row,state):
    """Only a committed job and its persisted delivery version permit navigation."""
    waiting=state.get('automation-publication-waiting')
    if not waiting or waiting['identity']!=str(row['id']):return False
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
    state.pop('automation-publication-waiting',None)
    state.pop('_automation_toolbar_definition',None)
    state.pop('_automation_published_comparison',None)
    state['automation-publication-toast']=True
    return True


@st.dialog('Publish Email?',width='small',on_dismiss=dismiss)
def confirm(store,user,identity,revision,step_id=None,flow_status='DRAFT'):
    # No database reads or provider validation on open. Request/worker transactions
    # retain every publication safeguard and revalidate authoritative state.
    st.html("""<style>
    [role="dialog"]:has(.sc-publication-confirm){width:min(400px,calc(100vw - 32px))!important;background:#161616;color:#fff;border:1px solid #75602e;border-radius:10px;padding:20px!important}
    [role="dialog"]:has(.sc-publication-confirm) h2{font-size:19px;color:#fff;padding:0 0 8px}
    [role="dialog"]:has(.sc-publication-confirm) p{font-size:13px;color:#eee}
    [role="dialog"]:has(.sc-publication-confirm) button{min-height:34px;padding:4px 14px}
    [role="dialog"]:has(.sc-publication-confirm) button[kind="primary"]{background:#c8a346;color:#141414;border-color:#c8a346}
    </style><span class="sc-publication-confirm"></span>""")
    st.write('Publish this email for future eligible customers?' if step_id else 'Publish all enabled emails and saved flow settings?')
    if flow_status=='PAUSED':st.caption('This flow will remain paused.')
    cancel,publish=st.columns(2)
    if cancel.button('Cancel',key='automation-publication-cancel',use_container_width=True):
        dismiss();st.rerun(scope='app')
    if publish.button('Publish',type='primary',key='automation-publication-confirm',use_container_width=True):
        try:
            with st.spinner('Publishing…'):
                job=store.request_publish(user,identity,revision,step_id=step_id)
            if job.get('id'):
                st.session_state['automation-publication-waiting']={'identity':str(identity),'job_id':str(job['id'])}
            if not job.get('unchanged'):
                from crm_automation_home import accepted_publication
                accepted_publication(job)
            dismiss()
            from crm_automation_ui import changed
            changed();st.rerun(scope='app')
        except (ValueError,PermissionError,StoreUnavailable,RuntimeError) as exc:
            st.error(str(exc))
