"""A compact live fragment mounted in the existing campaign action row."""
import hashlib
import json
import streamlit as st
from crm_email_size import campaign_size,analyze_rendered_email,meter_html,render_production


def automation_size_meter(editor,key,cfg):
    """No timer or second render: analyze the embedded preview's exact HTML."""
    from crm_automation_preview_cache import output
    store,_=st.session_state['automation_editor_context']
    try:
        cache,_,_=output(st.session_state,store,editor['document'],cfg,editor.get('id'))
        from pathlib import Path
        import streamlit.components.v1 as components
        component=components.declare_component('crm_automation_stable_size',path=str(Path(__file__).parent/'components'/'crm_automation_preview'))
        component(kind='size',scope=key,meter=meter_html(cache['size']),key=key+'stable_size',default=None)
    except (ValueError,RuntimeError):
        st.caption('Email size · Calculating…')


@st.fragment(run_every='2s')
def size_meter(editor,key,cfg):
    from crm_email_editor_context import current as current_editor
    current=current_editor(st.session_state,editor)
    if str(current.get('id'))!=str(editor.get('id')):return
    cfg=st.session_state.get(key+'review_preview_settings',cfg)
    try:
        doc=current['document']
        if st.session_state.get('email_editor_mode')=='automation':
            store,_=st.session_state['automation_editor_context'];doc,_=store.preview_document(doc)
        token=hashlib.sha256(json.dumps([current['id'],doc,cfg],sort_keys=True,default=str).encode()).hexdigest()
        cache=st.session_state.get(key+'size_cache')
        if not cache or cache['token']!=token:
            message=render_production(doc,cfg,current.get('id'))
            cache={'token':token,'message':message};st.session_state[key+'size_cache']=cache
        message=cache['message']
        local=analyze_rendered_email(message['html'],message['text'])
        from crm_email_asset_size import metadata
        assets=metadata(local['asset_urls'],start=bool(st.session_state.get(key+'editor_emitted')))
        report=analyze_rendered_email(message['html'],message['text'],assets)
        st.html(meter_html(report))
    except Exception:
        # Invalid/incomplete compose state must not interrupt the editor or leak
        # content in diagnostics. Review/send independently validate it.
        label='Calculating…' if st.session_state.get('email_editor_mode')=='automation' else 'Unknown'
        st.html('<span class="sc-email-size" style="font-size:11px">Email size · '+label+'</span>')
