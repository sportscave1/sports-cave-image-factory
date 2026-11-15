"""Compact manual email-prompt dialog; no reads until explicit Build/Copy."""
import logging
import streamlit as st
from crm_email_prompt import handoff, build_email, fingerprint, COMPONENTS
from crm_prompt_ui import reference_control


@st.fragment
def email_prompt_control(shop,editor,key):
    with st.container(key='crm-email-ai-trigger'):
        opened=st.button('Auto fill email',type='tertiary',key=key+'email_ai_open')
    st.html("""<style>
    .st-key-crm-email-ai-trigger{height:0!important;min-height:0!important;position:relative;overflow:visible;z-index:2;margin:0!important}
    div:has(>.st-key-crm-email-ai-trigger){height:0!important;margin-bottom:-16px!important}
    [data-testid="stLayoutWrapper"]:has(>.stVerticalBlock>[data-testid="stLayoutWrapper"]>.st-key-crm-email-ai-trigger){margin-bottom:-16px!important}
    .st-key-crm-email-ai-trigger [data-testid="stElementContainer"]{position:static!important}
    .st-key-crm-email-ai-trigger [data-testid="stButton"]{position:absolute;right:12px;top:9px;width:118px!important}
    .st-key-crm-email-ai-trigger button{width:118px!important;white-space:nowrap;min-height:26px!important;padding:2px 6px!important;font-size:12px!important;background:transparent!important;border:0!important}
    .st-key-crm-email-ai-trigger button p{font-size:12px!important}
    </style>""")
    if opened:email_prompt_dialog(shop,editor,key+'email_ai_')


@st.dialog('Auto fill email',width='small',on_dismiss='ignore')
def email_prompt_dialog(shop,editor,key):
    st.html("""<style>
    [role="dialog"]:has(.st-key-crm-email-ai-body){width:min(520px,calc(100vw - 32px));max-height:calc(100dvh - 64px);overflow:auto;box-sizing:border-box}
    .st-key-crm-email-ai-body,.st-key-crm-email-ai-body [data-testid="stVerticalBlock"]{gap:6px!important}
    .st-key-crm-email-ai-body button{min-height:30px}
    .st-key-crm-email-ai-body button[kind="primary"]{background:#242424;border-color:#242424;color:#fff}
    .st-key-crm-email-ai-body button[kind="segmented_controlActive"]{background:#f2eddf;border-color:#b49450;color:#242424}
    </style>""")
    state=st.session_state.setdefault(key+'state',{})
    value=handoff(st.session_state,editor)
    with st.container(key='crm-email-ai-body'):
        if not value:
            st.caption('Complete and copy Auto fill prompt in Settings first.');return
        reference_control((state.get('ready') or {}).get('context',value['context']))
        mode=st.segmented_control('Build mode',('Let AI decide','Choose components'),default='Let AI decide',key=key+'mode')
        selected=st.multiselect('Components',COMPONENTS,key=key+'components') if mode=='Choose components' else []
        direction=st.text_area('Extra direction (optional)',max_chars=800,height=68,key=key+'direction')
        stamp=fingerprint(editor,value,mode,selected,direction)
        if stamp!=state.get('stamp'):
            state.clear();state['stamp']=stamp
        def generate():
            from crm_prompt_readers import PromptReader
            from crm_catalogue import Catalogue
            return build_email(value,editor,PromptReader(shop),Catalogue(shop),mode=mode,components=selected,direction=direction)
        if st.button('Build email prompt',type='primary',key=key+'build'):
            try:state['ready']=generate();state.pop('error',None)
            except ValueError as exc:state['error']=str(exc);state.pop('ready',None)
            except Exception as exc:
                logging.getLogger(__name__).warning('campaign_email_prompt_unavailable type=%s',type(exc).__name__)
                state['error']='Verified public facts unavailable. Retry Build.';state.pop('ready',None)
        if state.get('error'):st.caption(state['error'])
        def revalidate():
            # Fresh public facts replace stale prompt facts; no send/draft writes.
            state['ready']=generate()
            return state['ready']['prompt']
        from crm_prompt_copy import copy_prompt
        try:copy_prompt((state.get('ready') or {}).get('prompt',''),key+'copy',label='Copy email prompt',revalidate=revalidate)
        except Exception as exc:
            logging.getLogger(__name__).warning('campaign_email_prompt_recheck_failed type=%s',type(exc).__name__)
            state.pop('ready',None);state['error']='Facts could not be rechecked. Build again.';st.rerun(scope='fragment')
        if state.get('ready'):
            with st.expander('View prompt'):st.code(state['ready']['prompt'],language=None)
