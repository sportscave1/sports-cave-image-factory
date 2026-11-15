"""Email-only Flow test popover. Reads happen only while open."""
import uuid
import streamlit as st


@st.fragment
def control(store,user,row,*,dirty=False):
    # Keep popover callbacks isolated from sequence navigation and publication.
    import os_accounts
    from crm_store import StoreUnavailable
    with st.popover('Test',help='Test the saved sequence using its configured delays',on_change='rerun',key='flow-test-popover',disabled=not os_accounts.is_admin(user)) as panel:
        if not panel.open:return
        st.write('**Test entire email flow**')
        prefix='flow-test-'+str(row['id'])
        with st.form(prefix+'-start',border=False):
            recipient=st.text_input('Email address',placeholder='Enter your test email address',key=prefix+'-recipient')
            submit=st.form_submit_button('Start Test')
        try:
            from crm_flow_tests import start,latest,cancel
            if submit:
                editor=st.session_state.get('automation_editor')
                saved=st.session_state.get('automation_saved',{})
                unsaved=editor and (editor.get('document')!=saved.get('document') or editor.get('name')!=saved.get('name'))
                if dirty or unsaved:raise ValueError('Save unsaved changes before starting a test.')
                from crm_automation_toolbar import definition
                current=definition(store,st.session_state,row['id'])
                operations=st.session_state.setdefault(prefix+'-operations',{})
                token=(recipient.strip().casefold(),current['config']['revision'])
                operation=operations.setdefault(token,str(uuid.uuid4()))
                result=start(store,user,row['id'],recipient,operation,current['config']['revision'])
                st.success(result['source']+' · scheduled')
            test=latest(store,user,row['id'])
            if test:
                st.caption(test['source']+' · '+test['recipient'])
                from os_accounts import timezone_for_user
                from crm_logic import date
                from zoneinfo import ZoneInfo
                for stage in test['stages']:
                    text='Email '+str(stage['position']+1)+' — '+stage['status'].title()
                    if stage['due_at'] and stage['status']=='SCHEDULED':
                        text+=' · '+date(stage['due_at']).astimezone(ZoneInfo(timezone_for_user(user))).strftime('%d %b %H:%M %Z')
                    st.caption(text)
                if any(s['status']=='SUBMITTED' for s in test['stages']):st.caption('Submission awaiting confirmation. Acceptance and inbox delivery are unverified.')
                if any(s['status'] in ('WAITING','SCHEDULED') for s in test['stages']) and st.button('Cancel pending test',key=prefix+'-cancel'):
                    cancel(store,user,test['id']);st.rerun(scope='fragment')
                if st.button('Check test status',key=prefix+'-status'):st.rerun(scope='fragment')
        except (ValueError,PermissionError,StoreUnavailable,RuntimeError) as exc:st.error(str(exc))
