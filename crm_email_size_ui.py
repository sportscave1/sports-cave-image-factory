"""A compact live fragment mounted in the existing campaign action row."""
import hashlib
import json
import streamlit as st
from html import escape
from crm_email_size import campaign_size,analyze_rendered_email,meter_html,render_production


def automation_size_meter(cache):
    """Native display of the exact preview message's server-side byte analysis."""
    st.html(meter_html(cache['size']))


def measured(doc,cfg,identity):
    from crm_preview_cache import presentation_document
    token=hashlib.sha256(json.dumps([identity,presentation_document(doc),cfg],sort_keys=True,default=str).encode()).hexdigest()
    entries=st.session_state.setdefault('_crm_size_renders',{})
    if token not in entries:
        message=render_production(doc,cfg,identity)
        entries[token]={'token':token,'message':message,'local':analyze_rendered_email(message['html'],message['text'])}
        while len(entries)>8:entries.pop(next(iter(entries)))
    return entries[token]


def publish_size(report,identity):
    """Existing preview rerun updates the action row; no polling or extra iframe."""
    markup=json.dumps(meter_html(report) if report else '<span class="sc-email-size" style="font-size:11px">Email size · Unknown</span>').replace('<','\\u003c')
    identity=json.dumps(str(identity)).replace('<','\\u003c')
    st.html('<script>document.querySelectorAll("[data-email-size-editor]").forEach(n=>{if(n.dataset.emailSizeEditor==='+identity+')n.innerHTML='+markup+'});</script>',unsafe_allow_javascript=True)


def mount(markup,identity):
    st.html('<div data-email-size-editor="'+escape(str(identity),quote=True)+'">'+markup+'</div>')


@st.fragment
def size_meter(editor,key,cfg):
    from crm_email_editor_context import current as current_editor
    current=current_editor(st.session_state,editor)
    if str(current.get('id'))!=str(editor.get('id')):return
    cfg=st.session_state.get(key+'review_preview_settings',cfg)
    try:
        doc=current['document']
        if st.session_state.get('email_editor_mode')=='automation':
            store,_=st.session_state['automation_editor_context']
            from crm_automation_preview_cache import output
            cache,_,_=output(st.session_state,store,doc,cfg,current.get('id'))
            mount(meter_html(cache['size']),current.get('id'))
            return
        from crm_smart_catalogue import enabled as smart_enabled,preview as smart_preview
        if smart_enabled(doc):
            from crm_shopify import Shopify
            from crm_campaign_store import CampaignStore
            adapter=st.session_state.get('_smart_preview_adapter')
            store,shop=adapter if adapter is not None else (CampaignStore(),Shopify())
            doc=smart_preview(st.session_state,store,shop,doc)
        cache=measured(doc,cfg,current.get('id'));st.session_state[key+'size_cache']=cache
        message=cache['message']
        local=cache['local']
        from crm_email_asset_size import metadata
        assets=metadata(local['asset_urls'],start=bool(st.session_state.get(key+'editor_emitted')))
        if cache.get('assets')!=assets or 'report' not in cache:
            from crm_email_size import with_asset_metadata
            cache['report']=with_asset_metadata(local,assets);cache['assets']=assets.copy()
        report=cache['report']
        mount(meter_html(report),current.get('id'))
    except Exception as exc:
        # Invalid/incomplete compose state must not interrupt the editor or leak
        # content in diagnostics. Review/send independently validate it.
        from crm_flow_preview import NoPreviewCustomer
        label='Calculating…' if isinstance(exc,NoPreviewCustomer) else 'Unknown'
        mount('<span class="sc-email-size" style="font-size:11px">Email size · '+label+'</span>',current.get('id'))
    # Authoring reruns already update this fragment. No periodic asset/Shopify poll.
