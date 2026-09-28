"""Shared, source-first white canvas for campaign and inactive flow emails."""
from copy import deepcopy
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from crm_campaign_content import render_campaign
from crm_email_blocks import render_blocks,legacy_blocks


def html_document(document):
    """Create an editable HTML snapshot without deleting the original structured data.

    Persistence is explicit; existing draft/template versions retain the prior document.
    Pasted HTML is never converted to blocks or normalized.
    """
    doc=deepcopy(document)
    if doc.get('content_mode')!='HTML':
        doc['custom_html']=render_blocks(doc.get('blocks') or legacy_blocks(doc['content']),market=doc['market'])[0]
        # Blocks render table rows. Keep the same table context in the HTML snapshot.
        if doc['custom_html']:doc['custom_html']='<table role="presentation" width="100%">'+doc['custom_html']+'</table>'
        doc['content_mode']='HTML'
    doc.setdefault('custom_html','')
    return doc


def workspace_styles():
    st.html('''<style>
    [data-testid="stMainBlockContainer"]:has(.st-key-crm-email-layout){padding-top:max(64px, calc(var(--sc-topbar-height, 0px) + 12px));padding-bottom:10px}
    .st-key-crm-workspace{gap:.5rem}
    .st-key-crm-email-canvas{background:#fff;border:1px solid #e6e2da;border-radius:8px;padding:10px;min-width:320px}
    .st-key-crm-email-controls{background:#faf9f6;padding:8px;border-radius:8px}
    .st-key-crm-workspace button[kind="primary"]{background:#d6a548;border-color:#d6a548;color:#171717}
    </style>''')


def canvas(doc,cfg,key):
    """One surface; no side-by-side preview and no block controls."""
    with st.container(key='crm-email-canvas'):
        _,toggle=st.columns([3,2])
        view=toggle.radio('Email workspace',('HTML','Preview'),horizontal=True,
                          key=key+'view',label_visibility='collapsed')
        if view=='HTML':
            editor=components.declare_component('crm_html_canvas',path=str(Path(__file__).parent/'components'/'crm_html_editor'))
            original=doc.get('custom_html','')
            value=editor(source=original,height=440,key=key+'html_source',default=original)
            if value!=original:doc['copy_reviewed']=False
            doc['custom_html']=value
        else:
            controls=st.columns([2,2,4])
            width=controls[0].selectbox('Width',(600,430,390,375,320),format_func=lambda w:'Desktop' if w==600 else str(w),key=key+'width',label_visibility='collapsed')
            mode=controls[1].selectbox('Preview display',('Email','Images off','Plain text'),key=key+'display',label_visibility='collapsed')
            try:
                rendered=render_campaign(doc,cfg,images_off=mode=='Images off')
                if mode=='Plain text':st.text_area('Plain text',rendered['text'],height=410,disabled=True,key=key+'plain')
                else:
                    with st.container(horizontal=True,horizontal_alignment='center'):
                        components.html(rendered['html'],width=width,height=410,scrolling=True)
            except ValueError as exc:st.warning(str(exc))
        return view
