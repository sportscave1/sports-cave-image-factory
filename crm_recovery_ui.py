"""Small same-origin browser checkpoint bridge; never carries credentials."""
from pathlib import Path
from copy import deepcopy
import streamlit as st
import streamlit.components.v1 as components
from crm_campaign_recovery import browser_checkpoint, preference_key, checkpoint
from crm_store import StoreUnavailable
from crm_component_json import render_component


def retry_browser(store,user,editor,key):
    record=st.session_state.get('campaign_browser_recovery')
    if not record:return False
    try:
        updated=browser_checkpoint(store,user,editor,record)
        editor.update(updated);st.session_state['campaign_saved']=deepcopy(editor)
        st.session_state.pop('campaign_browser_recovery',None);st.session_state.pop('campaign_save_error',None)
        from crm_campaign_page import open_editor
        open_editor(editor)
        st.rerun()
    except (ValueError,StoreUnavailable) as exc:st.session_state['campaign_save_error']=str(exc)
    return True


def recovery_bridge(store,user,editor,key):
    component=components.declare_component('campaign_recovery',path=str(Path(__file__).parent/'components'/'campaign_recovery'))
    event=render_component(component,scope=preference_key(user),editor={k:editor.get(k) for k in ('id','version','name','document','recovery_seed')},
        ack=st.session_state.get('campaign_recovery_ack'),failed=bool(st.session_state.get('campaign_save_error')),
        confirmed=bool(editor.get('id')) and checkpoint(editor)==checkpoint(st.session_state.get('campaign_saved',editor)),key=key+'recovery',default=None)
    if not event or event.get('event')==st.session_state.get('campaign_recovery_ack'):return
    st.session_state['campaign_recovery_ack']=event.get('event')
    try:
        record=event['record']
        if record['editor'].get('id') and str(record['editor']['id'])!=str(editor.get('id')):
            raise ValueError('Another draft has pending browser edits. Recovery copy retained; it was not merged into this campaign.')
        updated=browser_checkpoint(store,user,editor,record)
        editor.update(updated)
        st.session_state['campaign_saved']=deepcopy(editor)
        # This runs before these widgets are instantiated in the composer fragment.
        for suffix,value in (('name',editor['name']),('subject',editor['document']['content']['subject']),('preheader',editor['document']['content']['preheader'])):
            st.session_state[key+suffix]=value
        st.session_state['campaign_save_status']='Saved'
        st.session_state.pop('campaign_save_error',None)
        st.session_state.pop('campaign_browser_recovery',None)
    except (ValueError,KeyError,TypeError,StoreUnavailable,PermissionError) as exc:
        st.session_state['campaign_browser_recovery']=event.get('record')
        st.session_state['campaign_save_error']=str(exc) if isinstance(exc,(ValueError,StoreUnavailable)) else 'Browser recovery could not be verified. Your recovery copy is retained.'
        st.session_state['campaign_save_status']='Save failed'
    from crm_section_ui import rerun_editor
    rerun_editor()
