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



def composer_styles():
    # Campaign-only overrides: the shell, Inbox and Flow canvas keep their styles.
    st.html("""<style>
    [data-testid="stMainBlockContainer"]:has(.st-key-crm-composer-layout){max-width:none;padding:calc(var(--sc-topbar-height, 64px) + 8px) 18px 10px !important}
    [data-testid="stMainBlockContainer"]:has(.st-key-crm-composer-layout)>[data-testid="stVerticalBlock"]{gap:0 !important}
    .st-key-crm-workspace:has(.st-key-crm-composer-layout){gap:8px}
    .st-key-crm-workspace:has(.st-key-crm-composer-layout) h3{padding:0;margin:0;font-size:20px}
    .st-key-crm-composer-layout{--crm-panel-height:calc(100dvh - var(--sc-topbar-height, 64px) - 120px);align-items:stretch}
    .st-key-crm-composer-layout > div:has(>.st-key-crm-composer-controls){width:360px !important;flex:0 0 360px !important;height:var(--crm-panel-height) !important}
    .st-key-crm-composer-controls{width:100% !important;flex:1 1 auto !important;height:var(--crm-panel-height) !important;min-height:440px;background:#faf9f6;border:1px solid #e5e2da;border-radius:8px;padding:10px;overflow-y:auto}
    .st-key-crm-composer-controls [data-testid="stVerticalBlock"]{gap:8px}
    .st-key-crm-composer-controls label p{font-size:12px}
    .st-key-crm-composer-controls [role="tablist"]{gap:18px}
    .st-key-crm-composer-controls [role="tab"]{font-size:13px;padding:4px 0;height:34px;background:transparent !important;color:#242424 !important}
    .st-key-crm-composer-controls [role="tab"][aria-selected="true"]{border-bottom:2px solid #b49450 !important}
    .st-key-crm-composer-controls [data-baseweb="tab-highlight"]{background:#b49450}
    .st-key-crm-composer-controls textarea{font:12px/1.5 Consolas,monospace;background:#fff}
    .st-key-campaign-body-source textarea{height:max(320px,calc(var(--crm-panel-height) - 250px)) !important}
    .st-key-crm-composer-preview{flex:0 0 auto;height:var(--crm-panel-height);min-height:440px;background:white;border:1px solid #e5e2da;border-radius:8px;padding:10px;min-width:0;overflow:hidden}
    .st-key-crm-composer-preview iframe{max-width:100%;height:max(370px,calc(var(--crm-panel-height) - 65px)) !important}
    .st-key-crm-composer-preview [data-testid="stElementContainer"]:has(>iframe){height:max(370px,calc(var(--crm-panel-height) - 65px)) !important}
    .st-key-crm-preview-devices button{padding:3px 8px;min-height:30px}
    .st-key-crm-workspace:has(.st-key-crm-composer-layout) button[kind="secondary"],
    .st-key-crm-workspace:has(.st-key-crm-composer-layout) button[kind="tertiary"]{background:#fff !important;color:#242424 !important;border:1px solid #ddd8ce !important;box-shadow:none !important;min-height:32px;padding:5px 10px;font-size:13px}
    .st-key-crm-workspace:has(.st-key-crm-composer-layout) button[kind="primary"]{background:#c9a33f !important;border-color:#b99436 !important;min-height:32px;padding:5px 10px;font-size:13px}
    .st-key-crm-workspace:has(.st-key-crm-composer-layout) .st-key-crm-composer-preview button[kind="primary"]{background:#ece7dc !important;color:#242424 !important;border-color:#b49450 !important}
    @media(max-width:1450px){.st-key-crm-composer-layout > div:has(>.st-key-crm-composer-controls){width:330px !important;flex-basis:330px !important}}
    @media(max-width:1000px){.st-key-crm-composer-layout > div:has(>.st-key-crm-composer-controls){width:300px !important;flex-basis:300px !important}}
    </style>""")


def section_editor(doc,cfg,key,store=None,user=None):
    from crm_campaign_sections import section_defaults
    from crm_brand_template_ui import section_picker,save_section_control
    defaults=section_defaults(cfg)
    sections=doc.get('html_sections',defaults)
    with st.expander('Header',expanded=False):
        if store:section_picker(store,user,'header',key+'header_source',key+'header_',cfg,sections['header'])
        header=st.text_area('Header HTML',sections['header'],height=220,key=key+'header_source')
        if store:save_section_control(store,user,'header',header,key+'header_')
    with st.expander('Body',expanded=True):
        with st.container(key='campaign-body-source'):
            body=st.text_area('Body HTML',doc.get('custom_html',''),height=430,key=key+'body_source',
                placeholder='<!-- Paste your campaign body HTML here -->',label_visibility='collapsed')
    with st.expander('Footer',expanded=False):
        if store:section_picker(store,user,'footer',key+'footer_source',key+'footer_',cfg,sections['footer'])
        footer=st.text_area('Footer HTML',sections['footer'],height=180,key=key+'footer_source')
        st.caption('{{SYSTEM_FOOTER}} adds the protected identity, address, contact and unsubscribe content. It is restored if removed.')
        if store:save_section_control(store,user,'footer',footer,key+'footer_')
    if header!=sections['header'] or footer!=sections['footer']:
        doc['html_sections']={'header':header,'footer':footer}
    doc['custom_html']=body


PREVIEW_WIDTHS=(600,430,390,375,320)


def composer_canvas(doc,cfg,key):
    """Campaign preview only; the shared Flow canvas above is unchanged."""
    with st.container(key='crm-composer-preview'):
        with st.container(horizontal=True,vertical_alignment='center'):
            st.markdown('**Email Preview**')
            with st.container(horizontal=True,horizontal_alignment='right',gap='small',key='crm-preview-devices'):
                mode=st.session_state.get(key+'preview_device','Desktop')
                for label,icon in [('Desktop',':material/desktop_windows:'),('Mobile',':material/smartphone:')]:
                    if st.button('',icon=icon,help=label,key=key+'device_'+label,type='primary' if mode==label else 'secondary'):
                        st.session_state[key+'preview_device']=label;mode=label;st.rerun()
        try:
            rendered=render_campaign(doc,cfg)
            with st.container(horizontal=True,horizontal_alignment='center'):
                components.html(rendered['html'],width=600 if mode=='Desktop' else 390,height=680,scrolling=True)
        except ValueError as exc:st.warning(str(exc))
