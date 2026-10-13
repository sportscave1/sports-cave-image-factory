"""Explicit operator confirmation for lifecycle publication, using durable jobs."""
import streamlit as st
from crm_store import StoreUnavailable


def dismiss():
    st.session_state.pop('automation-confirm-publication',None)


@st.dialog('Publish automation?',width='small',on_dismiss=dismiss)
def confirm(store,user,identity,revision):
    from crm_automation_publication import preflight,prepare,approved
    try:
        row=store.flow(identity)
        flow=preflight(row,revision)
        # Full authoring/provider checks before presenting an actionable confirmation.
        prepare(store,identity,approved(flow),row['config']['published_version']+1,row['name'])
        st.write('Publish **'+row['name']+'**?')
        st.write('Future eligible customers can receive these emails after the CRM worker confirms publication. Existing drafts and version history are preserved. Historical customers and orders will not be backfilled.')
        if row['status']=='PAUSED':st.caption('This flow will remain paused until you resume it.')
        if st.button('Confirm publication',type='primary',key='automation-publication-confirm'):
            job=store.request_publish(user,identity,revision)
            if not job.get('unchanged'):
                from crm_automation_home import accepted_publication
                accepted_publication(job)
            st.session_state.pop('automation-confirm-publication',None)
            from crm_automation_ui import changed
            changed();st.rerun(scope='app')
    except (ValueError,PermissionError,StoreUnavailable,RuntimeError) as exc:
        st.error(str(exc))
    if st.button('Cancel',key='automation-publication-cancel'):
        st.session_state.pop('automation-confirm-publication',None)
        st.rerun(scope='app')
