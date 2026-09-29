"""Two compact singleton editors; campaign body templates stay separate."""
import streamlit as st
import os_accounts
from crm_store import StoreUnavailable


@st.dialog('Email default',width='small')
def edit_default(store,user,kind,row,target=None):
    from crm_campaign_library import finish_action,action_error,template_dialog
    dialog=template_dialog()
    st.markdown('**Default '+kind.title()+'**')
    source_key='email_default_html_'+kind+'_'+str(row['version'])
    def save():
        store.save_email_default(user,kind,st.session_state[source_key],row['version'])
        st.session_state['email_default_notice']='Default '+kind+' saved'
    with st.form('email_default_edit_'+kind):
        st.text_area(kind.title()+' HTML',row['value']['html'],height=260,key=source_key)
        a,b=st.columns(2)
        a.form_submit_button('Cancel',on_click=finish_action,args=(target,None,dialog,(source_key,)))
        b.form_submit_button('Save default',type='primary',on_click=finish_action,args=(target,save,dialog,(source_key,)))
    action_error()


def brand_templates_settings(store,user,cfg=None,target=None):
    st.markdown('**Email defaults**')
    if st.session_state.get('email_default_notice'):st.success(st.session_state.pop('email_default_notice'))
    for kind in ('header','footer'):
        label,action=st.columns([3,1],vertical_alignment='center')
        label.write('Default '+kind.title())
        if action.button('Edit',key='edit_email_default_'+kind,disabled=not os_accounts.is_admin(user)):
            try:
                with st.spinner('Loading template…'):
                    row=store.email_default(kind,store.render_settings() if cfg is None else cfg)
                edit_default(store,user,kind,row,target)
            except (ValueError,StoreUnavailable):st.error('Template could not be loaded.')
