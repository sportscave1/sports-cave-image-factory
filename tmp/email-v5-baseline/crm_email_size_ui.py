"""A compact live fragment mounted in the existing campaign action row."""
import hashlib
import json
import streamlit as st
from crm_email_size import campaign_size,analyze_rendered_email,meter_html,render_production


def automation_size_meter(cache):
    """Native display of the exact preview message's server-side byte analysis."""
    st.html(meter_html(cache['size']))


@st.fragment
def size_meter(editor,key,cfg):
    from crm_email_editor_context import current as current_editor
    current=current_editor(st.session_state,editor)
    if str(current.get('id'))!=str(editor.get('id')):return
    cfg=st.session_state.get(key+'review_preview_settings',cfg)
    try:
        doc=current['document']
        if st.session_state.get('email_editor_mode')=='automation':
            store,_=st.session_state['automation_editor_context'];doc,_=store.preview_document(doc)
        from crm_preview_cache import presentation_document
        token=hashlib.sha256(json.dumps([current['id'],presentation_document(doc),cfg],sort_keys=True,default=str).encode()).hexdigest()
        cache=st.session_state.get(key+'size_cache')
        if not cache or cache['token']!=token:
            message=render_production(doc,cfg,current.get('id'))
            cache={'token':token,'message':message,'local':analyze_rendered_email(message['html'],message['text'])};st.session_state[key+'size_cache']=cache
        message=cache['message']
        local=cache['local']
        from crm_email_asset_size import metadata
        assets=metadata(local['asset_urls'],start=bool(st.session_state.get(key+'editor_emitted')))
        if cache.get('assets')!=assets or 'report' not in cache:
            cache['report']=analyze_rendered_email(message['html'],message['text'],assets);cache['assets']=assets.copy()
        report=cache['report']
        st.html(meter_html(report))
    except Exception:
        # Invalid/incomplete compose state must not interrupt the editor or leak
        # content in diagnostics. Review/send independently validate it.
        label='Calculating…' if st.session_state.get('email_editor_mode')=='automation' else 'Unknown'
        st.html('<span class="sc-email-size" style="font-size:11px">Email size · '+label+'</span>')
    poll=key+'size-poll'
    st.html('<style>.st-key-'+poll+'{display:none}</style>')
    with st.container(key=poll):st.button('Refresh email size',key=poll+'-tick')
    from crm_campaign_home import arm_home_poll
    arm_home_poll(key=poll,seconds=2)
