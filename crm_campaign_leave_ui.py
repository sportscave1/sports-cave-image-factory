"""Native, page-local confirmation; persistence/navigation remain with the composer."""
from copy import deepcopy
import json
import streamlit as st
from crm_campaign_recovery import flush_current, preference_key


def cancel_leave():
    st.session_state.pop('crm_requested_route',None)
    st.session_state.pop('campaign_pending_open',None)


@st.dialog('Save changes?',width='small',on_dismiss=cancel_leave)
def leave_dialog(user,continue_leave):
    scope=json.dumps('sc-campaign-recovery:'+preference_key(user))
    st.html('''<span class="sc-campaign-leave"></span><style>
    [role="dialog"]:has(.sc-campaign-leave) {
      position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);
      width:min(480px,calc(100vw - 32px));max-height:calc(100vh - 32px);
      background:#faf9f6;border-radius:10px;
    }
    [data-testid="stDialog"]:has(.sc-campaign-leave) {background:rgba(17,17,17,.12)!important;}
    [role="dialog"] .stElementContainer:has(> [data-testid="stHtml"] > .sc-campaign-leave) {display:none;}
    [role="dialog"]:has(.sc-campaign-leave) button[kind="secondary"] {
      background:#fff!important;color:#222!important;border:1px solid #dedbd4!important;
    }
    [role="dialog"]:has(.sc-campaign-leave) button[kind="tertiary"] {
      background:transparent!important;color:#666!important;border:0!important;
    }
    [role="dialog"]:has(.sc-campaign-leave) [data-testid="stButton"]:has(button[kind="tertiary"]) {text-align:center;}
    </style><script>(()=>{
      window.scCampaignLeaveCleanup?.();
      const abort=new AbortController();
      const observer=new MutationObserver(()=>{
        if(!document.querySelector('.sc-campaign-leave'))cleanup();
      });
      const cleanup=()=>{abort.abort();observer.disconnect();};
      window.scCampaignLeaveCleanup=cleanup;
      document.addEventListener('click',e=>{
        const button=e.target.closest('button');
        if(button?.closest('[role="dialog"]')?.querySelector('.sc-campaign-leave') &&
           button.textContent.trim()==='Discard and leave'){
          window.dispatchEvent(new Event('sc-campaign-discard'));
          try{sessionStorage.removeItem(SCOPE);}catch{}
        }
      },{capture:true,signal:abort.signal});
      observer.observe(document.documentElement,{childList:true,subtree:true});
    })();</script>'''.replace('SCOPE',scope),unsafe_allow_javascript=True)
    st.write('You have unsaved campaign changes.')
    discard,save=st.columns(2,gap='small')
    if discard.button('Discard and leave',use_container_width=True):
        st.session_state['campaign_editor']=deepcopy(st.session_state['campaign_saved'])
        st.session_state.pop('campaign_browser_recovery',None)
        st.session_state.pop('campaign_save_error',None)
        st.session_state.pop('campaign_edit_key',None)
        continue_leave()
    if save.button('Save draft and leave',type='primary',use_container_width=True):
        if flush_current(force=True):continue_leave()
        else:st.error(st.session_state.get('campaign_save_error','Save failed. Your changes are retained.'))
    if st.button('Cancel',type='tertiary'):
        cancel_leave()
        st.rerun()
